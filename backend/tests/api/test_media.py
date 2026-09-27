"""Meal photos: the upload pipeline, signed URLs, copies, deletion and cleanup (MEAL-04,
MEAL-08, SEC-07, VIS-05, PERF-05)."""

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from PIL import ExifTags, Image

from app.db.session import Database
from app.media import images, urls
from app.media.store import MediaStore
from app.services import jobs
from tests.accounts import Account, FakeClock, error, fields, login, make_user, set_privacy
from tests.meals import (
    create_meal,
    decoded,
    encode,
    get_meal,
    jpeg,
    picture,
    png_header,
    upload,
)


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def carl(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "carl")


@pytest.fixture
async def meal(api: AsyncClient, anna: Account) -> Any:
    return await create_meal(api, anna, "Curry")


def store(app: FastAPI) -> MediaStore:
    media: MediaStore = app.state.media
    return media


def media_files(app: FastAPI) -> set[str]:
    return {path.name for path in store(app).directory.iterdir()}


def photo_key(meal: Any) -> str:
    """The key in the meal's photo URL."""
    return str(urlsplit(meal["photo"]["url"]).path.rsplit("/", 1)[1]).removesuffix(".webp")


def files_of(key: str) -> set[str]:
    return {f"{key}.webp", f"{key}-thumb.webp"}


async def uploaded(api: AsyncClient, user: Account, meal_id: str, content: bytes) -> Any:
    response = await upload(api, user, meal_id, content)
    assert response.status_code == 200, response.text
    return response.json()


async def fetch(api: AsyncClient, url: str) -> Response:
    """GET a media URL without any credentials, as an `<img>` does."""
    return await api.get(url)


# --- upload (MEAL-04, SEC-07) ----------------------------------------------------------------


async def test_upload_a_jpeg(
    app: FastAPI, api: AsyncClient, anna: Account, meal: Any, clock: FakeClock
) -> None:
    clock.advance(minutes=3)

    response = await upload(api, anna, meal["id"], jpeg((64, 48)))

    assert response.status_code == 200
    body = response.json()
    key = photo_key(body)
    assert len(key) == 32
    assert body["photo"] == {
        "url": f"/api/media/{key}.webp?exp={body['photo']['url'].split('exp=')[1]}",
        "thumb_url": body["photo"]["thumb_url"],
    }
    assert body["photo"]["thumb_url"].startswith(f"/api/media/{key}-thumb.webp?exp=")
    assert body["updated_at"] == "2026-09-27T12:03:00Z"
    assert media_files(app) == files_of(key)
    assert (store(app).directory.stat().st_mode & 0o777) == 0o700

    served = await fetch(api, body["photo"]["url"])
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/webp"
    assert served.headers["cache-control"] == "private, max-age=3600"
    assert served.headers["x-content-type-options"] == "nosniff"
    image = decoded(served.content)
    assert (image.format, image.size, image.mode) == ("WEBP", (64, 48), "RGB")
    thumb = decoded((await fetch(api, body["photo"]["thumb_url"])).content)
    assert thumb.size == (64, 48)

    # Detail and list carry the same (cacheable) URLs within the hour.
    assert (await get_meal(api, anna, meal["id"])).json()["photo"] == body["photo"]
    listed = await api.get("/api/meals", headers=anna.headers)
    assert listed.json()[0]["thumb_url"] == body["photo"]["thumb_url"]


async def test_large_photos_are_scaled_down(
    app: FastAPI, api: AsyncClient, anna: Account, meal: Any
) -> None:
    body = await uploaded(api, anna, meal["id"], jpeg((3200, 1800)))

    main = decoded((await fetch(api, body["photo"]["url"])).content)
    thumb = decoded((await fetch(api, body["photo"]["thumb_url"])).content)
    assert main.size == (1600, 900)
    assert thumb.size == (400, 225)


async def test_photos_are_rotated_upright_and_lose_their_metadata(
    api: AsyncClient, anna: Account, meal: Any
) -> None:
    original = jpeg((64, 48), orientation=6)
    exif = decoded(original).getexif()
    assert exif[ExifTags.Base.Make] == "TestCam"
    assert exif.get_ifd(ExifTags.IFD.GPSInfo)

    body = await uploaded(api, anna, meal["id"], original)

    for url in (body["photo"]["url"], body["photo"]["thumb_url"]):
        image = decoded((await fetch(api, url)).content)
        # Orientation 6 means "rotate 90° clockwise": the red left half is now on top.
        assert image.size == (48, 64)
        red = image.getpixel((24, 8))
        blue = image.getpixel((24, 56))
        assert isinstance(red, tuple)
        assert isinstance(blue, tuple)
        assert red[0] > 200
        assert red[2] < 60
        assert blue[2] > 200
        assert blue[0] < 60
        assert not image.getexif()
        assert not {"exif", "xmp", "icc_profile"} & set(image.info)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(encode(picture(mode="RGBA"), "PNG"), id="png"),
        pytest.param(encode(picture(), "WEBP", quality=90), id="webp"),
        pytest.param(encode(picture().convert("P"), "PNG"), id="png-palette"),
        pytest.param(encode(picture().convert("L"), "JPEG"), id="jpeg-grey"),
        pytest.param(encode(picture().convert("CMYK"), "JPEG"), id="jpeg-cmyk"),
    ],
)
async def test_png_and_webp_are_accepted(
    api: AsyncClient, anna: Account, meal: Any, content: bytes
) -> None:
    body = await uploaded(api, anna, meal["id"], content)
    image = decoded((await fetch(api, body["photo"]["url"])).content)
    assert (image.format, image.mode, image.size) == ("WEBP", "RGB", (64, 48))


async def test_transparency_becomes_white(api: AsyncClient, anna: Account, meal: Any) -> None:
    transparent = Image.new("RGBA", (20, 20), (255, 0, 0, 0))
    palette = Image.new("P", (20, 20), 0)
    palette.info["transparency"] = 0
    for content in (encode(transparent, "PNG"), encode(palette, "PNG", transparency=0)):
        body = await uploaded(api, anna, meal["id"], content)
        image = decoded((await fetch(api, body["photo"]["url"])).content)
        pixel = image.getpixel((10, 10))
        assert isinstance(pixel, tuple)
        assert min(pixel) > 245


async def test_too_large_uploads(app: FastAPI, api: AsyncClient, anna: Account, meal: Any) -> None:
    content = jpeg((64, 48))
    content += b"\0" * (images.MAX_UPLOAD_BYTES + 1 - len(content))

    response = await upload(api, anna, meal["id"], content)

    assert response.status_code == 413
    assert error(response) == "media.too_large"
    assert media_files(app) == set()
    assert (await get_meal(api, anna, meal["id"])).json()["photo"] is None
    # Exactly the limit is fine (trailing bytes after the JPEG are ignored).
    assert (await upload(api, anna, meal["id"], content[:-1])).status_code == 200


@pytest.mark.parametrize(
    ("content", "filename", "content_type"),
    [
        pytest.param(encode(picture(), "GIF"), "photo.jpg", "image/jpeg", id="gif-as-jpeg"),
        pytest.param(encode(picture(), "BMP"), "photo.png", "image/png", id="bmp-as-png"),
        pytest.param(encode(picture(), "TIFF"), "photo.webp", "image/webp", id="tiff"),
        pytest.param(b"<svg xmlns='http://www.w3.org/2000/svg'/>", "a.png", "image/png", id="svg"),
        pytest.param(b"hello", "photo.jpg", "image/jpeg", id="text"),
        pytest.param(b"", "photo.jpg", "image/jpeg", id="empty"),
        pytest.param(jpeg((640, 480))[:600], "photo.jpg", "image/jpeg", id="truncated-jpeg"),
        pytest.param(png_header(6000, 4000), "photo.png", "image/png", id="no-pixel-data"),
    ],
)
async def test_unsupported_uploads(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    meal: Any,
    content: bytes,
    filename: str,
    content_type: str,
) -> None:
    response = await upload(
        api, anna, meal["id"], content, filename=filename, content_type=content_type
    )
    assert response.status_code == 415
    assert error(response) == "media.unsupported_type"
    assert media_files(app) == set()


@pytest.mark.parametrize(
    ("width", "height"),
    [
        pytest.param(6000, 4001, id="above-the-limit"),  # Pillow's warning, as an error
        pytest.param(10_000, 10_000, id="decompression-bomb"),  # Pillow's own error
        pytest.param(1, 24_000_001, id="thin"),
    ],
)
async def test_too_many_pixels(
    app: FastAPI, api: AsyncClient, anna: Account, meal: Any, width: int, height: int
) -> None:
    response = await upload(api, anna, meal["id"], png_header(width, height), filename="a.png")
    assert response.status_code == 422
    assert error(response) == "media.too_many_pixels"
    assert media_files(app) == set()


async def test_the_pixel_limit_holds_without_pillows_check(
    api: AsyncClient, anna: Account, meal: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", None)
    response = await upload(api, anna, meal["id"], png_header(6000, 4001), filename="a.png")
    assert error(response) == "media.too_many_pixels"


async def test_upload_needs_a_file(api: AsyncClient, anna: Account, meal: Any) -> None:
    response = await api.put(f"/api/meals/{meal['id']}/photo", headers=anna.headers)
    assert response.status_code == 422
    assert fields(response) == {("body", "file"): "required"}


async def test_uploads_are_rate_limited_per_user(
    api: AsyncClient, anna: Account, carl: Account, meal: Any, clock: FakeClock
) -> None:
    for _ in range(20):
        assert (await upload(api, anna, meal["id"], b"x")).status_code == 415

    limited = await upload(api, anna, meal["id"], b"x")

    assert limited.status_code == 429
    assert error(limited) == "common.rate_limited"
    assert limited.headers["retry-after"] == "600"
    other = await create_meal(api, carl, "Chili")
    assert (await upload(api, carl, other["id"], b"x")).status_code == 415
    clock.advance(minutes=10)
    assert (await upload(api, anna, meal["id"], b"x")).status_code == 415


# --- replace and delete ------------------------------------------------------------------------


async def test_replacing_the_photo_removes_the_old_files(
    app: FastAPI, api: AsyncClient, anna: Account, meal: Any
) -> None:
    first = await uploaded(api, anna, meal["id"], jpeg())
    second = await uploaded(api, anna, meal["id"], jpeg())

    assert photo_key(first) != photo_key(second)
    assert media_files(app) == files_of(photo_key(second))
    assert (await fetch(api, first["photo"]["url"])).status_code == 404
    assert (await fetch(api, second["photo"]["url"])).status_code == 200


async def test_delete_the_photo(
    app: FastAPI, api: AsyncClient, anna: Account, meal: Any, clock: FakeClock
) -> None:
    body = await uploaded(api, anna, meal["id"], jpeg())
    clock.advance(minutes=1)

    response = await api.delete(f"/api/meals/{meal['id']}/photo", headers=anna.headers)

    assert response.status_code == 204
    after = (await get_meal(api, anna, meal["id"])).json()
    assert (after["photo"], after["updated_at"]) == (None, "2026-09-27T12:01:00Z")
    assert media_files(app) == set()
    assert (await fetch(api, body["photo"]["url"])).status_code == 404
    clock.advance(minutes=1)
    again = await api.delete(f"/api/meals/{meal['id']}/photo", headers=anna.headers)
    assert again.status_code == 204
    assert (await get_meal(api, anna, meal["id"])).json()["updated_at"] == after["updated_at"]


async def test_deleting_the_meal_removes_its_files(
    app: FastAPI, api: AsyncClient, anna: Account, meal: Any
) -> None:
    await uploaded(api, anna, meal["id"], jpeg())
    assert (await api.delete(f"/api/meals/{meal['id']}", headers=anna.headers)).status_code == 204
    assert media_files(app) == set()


async def test_failed_file_deletion_is_only_logged(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    meal: Any,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    body = await uploaded(api, anna, meal["id"], jpeg())

    def refuse(self: Path, *, missing_ok: bool = False) -> None:
        raise PermissionError(self)

    monkeypatch.setattr(Path, "unlink", refuse)
    response = await api.delete(f"/api/meals/{meal['id']}/photo", headers=anna.headers)

    assert response.status_code == 204
    assert media_files(app) == files_of(photo_key(body))  # left for the cleanup job
    assert [record.message for record in caplog.records if record.levelname == "WARNING"] == [
        "could not delete a media file"
    ] * 2


# --- copies (MEAL-08) -------------------------------------------------------------------------


async def test_a_copy_has_its_own_photo_files(
    app: FastAPI, api: AsyncClient, anna: Account, carl: Account, meal: Any
) -> None:
    original = await uploaded(api, anna, meal["id"], jpeg())

    copy = (await api.post(f"/api/meals/{meal['id']}/copy", headers=carl.headers)).json()

    assert photo_key(copy) != photo_key(original)
    assert media_files(app) == files_of(photo_key(original)) | files_of(photo_key(copy))
    same = await fetch(api, copy["photo"]["url"])
    assert same.content == (await fetch(api, original["photo"]["url"])).content
    await api.delete(f"/api/meals/{meal['id']}", headers=anna.headers)
    assert (await fetch(api, copy["photo"]["url"])).status_code == 200


async def test_a_copy_of_a_meal_whose_files_are_gone(
    app: FastAPI, api: AsyncClient, anna: Account, carl: Account, meal: Any
) -> None:
    original = await uploaded(api, anna, meal["id"], jpeg())
    (store(app).directory / f"{photo_key(original)}-thumb.webp").unlink()

    copy = (await api.post(f"/api/meals/{meal['id']}/copy", headers=carl.headers)).json()

    assert copy["photo"] is None
    assert media_files(app) == {f"{photo_key(original)}.webp"}


# --- signed URLs (VIS-05) ---------------------------------------------------------------------


def with_params(url: str, **changes: str | None) -> str:
    parts = urlsplit(url)
    params = {key: values[0] for key, values in parse_qs(parts.query).items()}
    for key, value in changes.items():
        if value is None:
            params.pop(key)
        else:
            params[key] = value
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"{parts.path}?{query}" if query else parts.path


async def test_signed_urls_expire(
    api: AsyncClient, anna: Account, meal: Any, clock: FakeClock
) -> None:
    body = await uploaded(api, anna, meal["id"], jpeg())
    url = body["photo"]["url"]
    # Issued at 12:00:00: valid until 13:00, then no longer (1 to 2 hours in general).
    assert "exp=" + str(int(clock.now.timestamp()) + 3600) in url

    clock.advance(minutes=59, seconds=59)
    assert (await fetch(api, url)).status_code == 200
    clock.advance(seconds=1)
    expired = await fetch(api, url)
    assert expired.status_code == 404
    assert error(expired) == "common.not_found"

    # URLs issued within the same hour are identical, so browsers can cache the image.
    clock.advance(seconds=1)
    await login(api, anna)
    first = (await get_meal(api, anna, meal["id"])).json()["photo"]
    clock.advance(minutes=59)
    await login(api, anna)
    assert (await get_meal(api, anna, meal["id"])).json()["photo"] == first
    clock.advance(minutes=1)
    assert (await get_meal(api, anna, meal["id"])).json()["photo"] != first


async def test_tampered_urls_are_refused(api: AsyncClient, anna: Account, meal: Any) -> None:
    body = await uploaded(api, anna, meal["id"], jpeg())
    url, thumb_url = body["photo"]["url"], body["photo"]["thumb_url"]
    signature = parse_qs(urlsplit(url).query)["sig"][0]
    exp = parse_qs(urlsplit(url).query)["exp"][0]
    key = photo_key(body)
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]

    for tampered in (
        with_params(url, sig=flipped),
        with_params(url, sig=signature[:-1]),
        with_params(url, sig=signature + "A"),
        with_params(url, sig=None),
        with_params(url, exp=str(int(exp) + 3600)),
        with_params(url, exp="later"),
        with_params(url, exp=None),
        with_params(url, exp=None, sig=None),
        with_params(thumb_url, sig=signature),  # the main image's signature
        with_params(url.replace(".webp", ".png"), sig=signature),
        f"/api/media/{key.upper()}.webp?exp={exp}&sig={signature}",
        f"/api/media/mealmate.db?exp={exp}&sig={signature}",
    ):
        response = await fetch(api, tampered)
        assert response.status_code == 404, tampered
        assert error(response) == "common.not_found"
        assert response.headers["content-type"] == "application/json"
    assert (await fetch(api, url)).status_code == 200


async def test_a_valid_signature_for_a_missing_file(app: FastAPI, api: AsyncClient) -> None:
    name = "0" * 32 + ".webp"
    url = urls.signed_url(store(app).key, name, now=app.state.clock())
    response = await fetch(api, url)
    assert response.status_code == 404
    assert error(response) == "common.not_found"


async def test_urls_are_only_issued_to_viewers(
    api: AsyncClient, anna: Account, carl: Account, meal: Any
) -> None:
    await uploaded(api, anna, meal["id"], jpeg())
    assert (await get_meal(api, carl, meal["id"])).json()["photo"] is not None
    await set_privacy(api, anna, meals_public=False)
    assert (await get_meal(api, carl, meal["id"])).status_code == 404
    listed = await api.get("/api/meals", headers=carl.headers)
    assert listed.json() == []


async def test_rotating_the_secret_key_invalidates_urls(
    app: FastAPI, api: AsyncClient, anna: Account, meal: Any
) -> None:
    body = await uploaded(api, anna, meal["id"], jpeg())
    app.state.media.key = b"\x01" * 32
    assert (await fetch(api, body["photo"]["url"])).status_code == 404


# --- cleanup (plan § 5.11) ----------------------------------------------------------------------


async def test_cleanup_removes_old_orphans_only(
    app: FastAPI, api: AsyncClient, anna: Account, meal: Any
) -> None:
    kept = photo_key(await uploaded(api, anna, meal["id"], jpeg()))
    media = store(app)
    processed = images.process(jpeg())
    old_orphan = media.write(processed)
    new_orphan = media.write(processed)
    leftover = media.directory / "abc.webp.0123.tmp"
    leftover.write_bytes(b"partial")
    unrelated = media.directory / "notes.txt"
    unrelated.write_text("mine")
    now = time.time()
    two_hours_ago = now - 7200
    for name in (*files_of(kept), *files_of(old_orphan), leftover.name, unrelated.name):
        os.utime(media.path(name), (two_hours_ago, two_hours_ago))

    database: Database = app.state.database
    async with database.write_sessions() as session:
        removed = await jobs.cleanup(session, media, now=datetime.fromtimestamp(now, UTC))

    assert removed.media_files == 3
    assert media_files(app) == files_of(kept) | files_of(new_orphan) | {"notes.txt"}
    # A missing directory is simply empty.
    assert MediaStore(media.directory / "missing", key=b"").remove_orphans(set(), now=now) == 0
