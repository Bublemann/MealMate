"""Images made in memory, so the suite needs no binary fixture files."""

import struct
import zlib

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(kind: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(kind + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", crc)


def png(width: int = 64, height: int = 48) -> bytes:
    """An 8-bit RGB PNG of `width` by `height` pixels with a colour gradient."""
    rows = b"".join(
        b"\x00"  # filter type "none" for each scanline
        + bytes(
            channel
            for x in range(width)
            for channel in (x * 255 // max(width - 1, 1), y * 255 // max(height - 1, 1), 96)
        )
        for y in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        PNG_SIGNATURE
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(rows))
        + _chunk(b"IEND", b"")
    )
