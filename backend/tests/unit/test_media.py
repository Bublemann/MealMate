"""Signed media URLs and the image processor (VIS-05, PERF-05)."""

import threading
import time
from datetime import UTC, datetime

import anyio
import pytest
from PIL import ExifTags, Image, ImageOps

from app.media import images, urls
from app.media.images import ImageProcessor, ProcessedImage
from app.media.store import key_of
from tests.meals import decoded, encode, jpeg, picture

KEY = b"k" * 32
NAME = "0123456789abcdef0123456789abcdef.webp"


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC), datetime(2026, 9, 27, 13, 0, tzinfo=UTC)),
        (datetime(2026, 9, 27, 12, 0, 1, tzinfo=UTC), datetime(2026, 9, 27, 14, 0, tzinfo=UTC)),
        (datetime(2026, 9, 27, 12, 59, 59, tzinfo=UTC), datetime(2026, 9, 27, 14, 0, tzinfo=UTC)),
        (datetime(2026, 12, 31, 23, 30, tzinfo=UTC), datetime(2027, 1, 1, 1, 0, tzinfo=UTC)),
    ],
)
def test_expiry_is_an_hour_rounded_up_to_the_next_full_hour(
    now: datetime, expected: datetime
) -> None:
    exp = urls.expiry(now)
    assert exp == int(expected.timestamp())
    assert 3600 <= exp - now.timestamp() < 7200


def test_signature_is_hmac_sha256_base64url_without_padding() -> None:
    signature = urls.signature(KEY, NAME, 1_790_000_000)
    assert len(signature) == 43
    assert "=" not in signature
    assert urls.signature(KEY, NAME, 1_790_000_000) == signature
    assert urls.signature(KEY, NAME, 1_790_003_600) != signature
    assert urls.signature(b"x" * 32, NAME, 1_790_000_000) != signature


def test_signed_url_round_trip() -> None:
    now = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
    url = urls.signed_url(KEY, NAME, now=now)
    path, _, query = url.partition("?")
    assert path == f"/api/media/{NAME}"
    params = dict(part.split("=", 1) for part in query.split("&"))
    assert urls.is_valid(KEY, NAME, params["exp"], params["sig"], now=now)
    assert not urls.is_valid(b"x" * 32, NAME, params["exp"], params["sig"], now=now)
    assert not urls.is_valid(KEY, NAME, "9" * 13, params["sig"], now=now)


@pytest.mark.parametrize(
    ("name", "key"),
    [
        (NAME, NAME.removesuffix(".webp")),
        (NAME.replace(".webp", "-thumb.webp"), NAME.removesuffix(".webp")),
        ("notes.txt", None),
        (NAME + ".1234.tmp", None),
        (NAME.upper(), None),
    ],
)
def test_key_of(name: str, key: str | None) -> None:
    assert key_of(name) == key


async def test_images_are_processed_one_at_a_time_off_the_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    running = 0
    most = 0
    lock = threading.Lock()
    threads: set[int] = set()

    def slow_process(data: bytes) -> ProcessedImage:
        nonlocal running, most
        with lock:
            running += 1
            most = max(most, running)
        threads.add(threading.get_ident())
        time.sleep(0.02)
        with lock:
            running -= 1
        return ProcessedImage(main=data, thumb=data)

    monkeypatch.setattr(images, "process", slow_process)
    processor = ImageProcessor()
    ticks = 0

    async def tick() -> None:
        nonlocal ticks
        for _ in range(5):
            await anyio.sleep(0.005)
            ticks += 1

    async with anyio.create_task_group() as group:
        group.start_soon(tick)
        for index in range(3):
            group.start_soon(processor.process, bytes([index]))

    assert most == 1
    assert threading.get_ident() not in threads
    assert ticks == 5


def png_with_orientation(size: tuple[int, int], orientation: int) -> bytes:
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientation
    return encode(picture(size), "PNG", exif=exif)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(jpeg((4000, 3000), orientation=6), id="jpeg"),
        pytest.param(png_with_orientation((4000, 3000), 6), id="png"),
    ],
)
def test_images_are_scaled_down_before_rotating_and_flattening(
    monkeypatch: pytest.MonkeyPatch, content: bytes
) -> None:
    """A 12-megapixel photo is never copied at full size (PERF-05), and still ends up upright."""
    transpose = ImageOps.exif_transpose
    sizes: list[tuple[int, int]] = []

    def recording_transpose(image: Image.Image) -> Image.Image:
        sizes.append(image.size)
        return transpose(image)

    monkeypatch.setattr(ImageOps, "exif_transpose", recording_transpose)

    processed = images.process(content)

    assert sizes == [(1600, 1200)]
    main = decoded(processed.main)
    thumb = decoded(processed.thumb)
    assert (main.size, thumb.size) == ((1200, 1600), (300, 400))
    for image in (main, thumb):
        # Orientation 6 means "rotate 90° clockwise": the red left half is now on top.
        width, height = image.size
        top = image.getpixel((width // 2, height // 8))
        bottom = image.getpixel((width // 2, height * 7 // 8))
        assert isinstance(top, tuple)
        assert isinstance(bottom, tuple)
        assert top[0] > 200
        assert top[2] < 60
        assert bottom[2] > 200
        assert bottom[0] < 60


@pytest.mark.parametrize("mode", ["P", "1", "L", "LA", "RGBA", "I;16"])
def test_every_mode_is_scaled_down(mode: str) -> None:
    image = picture((3200, 2400)).convert("RGBA" if mode == "LA" else "RGB").convert(mode)

    processed = images.process(encode(image, "PNG"))

    main = decoded(processed.main)
    assert (main.mode, main.size) == ("RGB", (1600, 1200))
