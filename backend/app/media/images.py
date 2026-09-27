"""The photo pipeline (MEAL-04, SEC-07, PERF-05, plan § 5.10).

Uploads are untrusted (SEC-13): only the JPEG, PNG and WebP decoders are allowed, whatever the
file name or content type claims; the pixel count is checked right after reading the header
(Pillow's own decompression-bomb warning is turned into an error too); the image is rotated
upright by its EXIF orientation and always re-encoded as WebP without any metadata (so GPS
and camera data are gone). It is scaled down right after decoding, so the later steps never
copy it at full size.

`process` is CPU-bound; `process_in_thread` runs it off the event loop, one image at a time.
"""

import io
import warnings
from dataclasses import dataclass

import anyio
from PIL import Image, ImageOps

from app.core.errors import ApiError, ErrorCode

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 24_000_000
MAIN_EDGE = 1600
THUMB_EDGE = 400
WEBP_QUALITY = 80
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")
_WHITE = (255, 255, 255)

# Pillow warns above this many pixels and refuses twice as many; `process` also checks it
# itself and turns the warning into an error.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def too_large() -> ApiError:
    return ApiError(ErrorCode.MEDIA_TOO_LARGE, status_code=413)


def unsupported_type() -> ApiError:
    return ApiError(ErrorCode.MEDIA_UNSUPPORTED_TYPE, status_code=415)


def too_many_pixels() -> ApiError:
    return ApiError(ErrorCode.MEDIA_TOO_MANY_PIXELS, status_code=422)


@dataclass(frozen=True, repr=False)
class ProcessedImage:
    """The re-encoded photo (≤ 1600 px on the long edge) and its thumbnail (≤ 400 px)."""

    main: bytes
    thumb: bytes


def _open(data: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(data), formats=ALLOWED_FORMATS)
    except Image.DecompressionBombError, Image.DecompressionBombWarning:
        raise too_many_pixels() from None
    except Exception:
        # Pillow raises all sorts of exceptions for files it cannot identify.
        raise unsupported_type() from None
    if image.width * image.height > MAX_PIXELS:
        image.close()
        raise too_many_pixels()
    return image


def _shrink(image: Image.Image) -> Image.Image:
    """The decoded image at most 1600 px on the long edge, its EXIF (orientation) kept.

    Shrinking comes first, so rotating and flattening never copy a full-size image of up to
    24 megapixels (PERF-05). Palette and bilevel images are converted before, since Pillow would
    scale them nearest-neighbour.
    """
    if image.mode in {"1", "P", "PA"}:
        image = image.convert("RGBA" if image.has_transparency_data else "RGB")
    image.thumbnail((MAIN_EDGE, MAIN_EDGE), Image.Resampling.LANCZOS)
    return image


def _flatten(image: Image.Image) -> Image.Image:
    """RGB; transparent areas become white."""
    if image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, _WHITE)
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _webp(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "WEBP", quality=WEBP_QUALITY)
    return buffer.getvalue()


def process(data: bytes) -> ProcessedImage:
    """Decode, check, rotate upright and re-encode an uploaded photo.

    Raises `ApiError`: 413 `media.too_large` (more than 10 MB), 415 `media.unsupported_type`
    (not a JPEG, PNG or WebP Pillow can decode) or 422 `media.too_many_pixels` (more than 24
    megapixels).
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise too_large()
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with _open(data) as image:
            if image.format == "JPEG":
                image.draft("RGB", (MAIN_EDGE, MAIN_EDGE))
            try:
                upright = ImageOps.exif_transpose(_shrink(image))
                main = _flatten(upright)
            except Exception:
                # A header that parsed, but pixel data that does not decode (truncated, corrupt).
                raise unsupported_type() from None
    thumb = main.copy()
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE), Image.Resampling.LANCZOS)
    return ProcessedImage(main=_webp(main), thumb=_webp(thumb))


class ImageProcessor:
    """Runs `process` in a worker thread, at most one image at a time (PERF-05), so photo
    uploads never block other requests nor use more than one core of the Pi."""

    def __init__(self) -> None:
        self._limiter: anyio.CapacityLimiter | None = None

    async def process(self, data: bytes) -> ProcessedImage:
        if self._limiter is None:
            # Created on first use, inside the event loop it belongs to.
            self._limiter = anyio.CapacityLimiter(1)
        return await anyio.to_thread.run_sync(process, data, limiter=self._limiter)
