"""Helpers for tests of meals and their photos."""

import io
import struct
import zlib
from typing import Any

from httpx import AsyncClient, Response
from PIL import ExifTags, Image

from tests.accounts import Account


async def create_meal(api: AsyncClient, user: Account, name: str, **body: Any) -> Any:
    response = await api.post("/api/meals", json={"name": name, **body}, headers=user.headers)
    assert response.status_code == 201, response.text
    return response.json()


async def get_meal(api: AsyncClient, user: Account, meal_id: str) -> Response:
    return await api.get(f"/api/meals/{meal_id}", headers=user.headers)


async def list_meals(api: AsyncClient, user: Account, **params: Any) -> list[str]:
    """The names of the meals listed for `user`."""
    response = await api.get("/api/meals", params=params, headers=user.headers)
    assert response.status_code == 200, response.text
    return [item["name"] for item in response.json()]


async def upload(
    api: AsyncClient,
    user: Account,
    meal_id: str,
    content: bytes,
    *,
    filename: str = "photo.jpg",
    content_type: str = "image/jpeg",
) -> Response:
    return await api.put(
        f"/api/meals/{meal_id}/photo",
        files={"file": (filename, content, content_type)},
        headers=user.headers,
    )


def encode(image: Image.Image, image_format: str, **options: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, image_format, **options)
    return buffer.getvalue()


def picture(size: tuple[int, int] = (64, 48), mode: str = "RGB") -> Image.Image:
    """Left half red, right half blue: the orientation can be told after rotating."""
    width, height = size
    image = Image.new(mode, size, (0, 0, 255) if mode == "RGB" else (0, 0, 255, 255))
    image.paste((255, 0, 0) if mode == "RGB" else (255, 0, 0, 255), (0, 0, width // 2, height))
    return image


def jpeg(size: tuple[int, int] = (64, 48), *, orientation: int | None = None) -> bytes:
    """A JPEG with EXIF (camera make and GPS position; optionally an orientation)."""
    exif = Image.Exif()
    exif[ExifTags.Base.Make] = "TestCam"
    if orientation is not None:
        exif[ExifTags.Base.Orientation] = orientation
    gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps[ExifTags.GPS.GPSLatitudeRef] = "N"
    gps[ExifTags.GPS.GPSLatitude] = (52.0, 31.0, 12.0)
    return encode(picture(size), "JPEG", exif=exif, quality=95)


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png_header(width: int, height: int) -> bytes:
    """A PNG that claims a size but carries almost no pixel data (a decompression bomb only
    needs the header to be refused)."""
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(b"\x00"))
        + png_chunk(b"IEND", b"")
    )


def decoded(content: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(content))
    image.load()
    return image
