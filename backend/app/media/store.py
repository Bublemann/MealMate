"""Photo files in `<data dir>/media` (SEC-07, plan § 5.10).

Each photo is two files, `<key>.webp` and `<key>-thumb.webp`, the key being a random uuid4 in
hex; the directory is outside any web root and only served through signed URLs. Files are
written atomically (a temporary file, then `os.replace`) before the database refers to them, and
deleted best-effort after the reference is gone; whatever is left over (a failed transaction, a
deleted user) is removed by `mealmate jobs cleanup`.
"""

import logging
import os
import uuid
from collections.abc import Collection, Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import anyio

from app.media import urls
from app.media.images import ImageProcessor, ProcessedImage

logger = logging.getLogger(__name__)

# Unreferenced files younger than this are kept: they may belong to an upload or copy whose
# transaction has not committed yet.
ORPHAN_MIN_AGE_SECONDS = 3600
_TEMP_SUFFIX = ".tmp"


def new_key() -> str:
    return uuid.uuid4().hex


def main_name(key: str) -> str:
    return f"{key}.webp"


def thumb_name(key: str) -> str:
    return f"{key}-thumb.webp"


def file_names(key: str) -> tuple[str, str]:
    return main_name(key), thumb_name(key)


def key_of(name: str) -> str | None:
    """The photo key of a media file name, or None for any other file."""
    if not urls.MEDIA_NAME.fullmatch(name):
        return None
    return name.removesuffix(".webp").removesuffix("-thumb")


@dataclass(frozen=True)
class SignedPhoto:
    url: str
    thumb_url: str


@dataclass
class MediaStore:
    """The media directory, the key that signs its URLs, and the image processor."""

    directory: Path
    key: bytes = field(repr=False)
    processor: ImageProcessor = field(default_factory=ImageProcessor, repr=False)

    def ensure_directory(self) -> None:
        """Create the directory (mode 0700) if it is missing."""
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.directory / name

    def signed(self, photo_key: str, *, now: datetime) -> SignedPhoto:
        return SignedPhoto(
            url=urls.signed_url(self.key, main_name(photo_key), now=now),
            thumb_url=urls.signed_url(self.key, thumb_name(photo_key), now=now),
        )

    def thumb_url(self, photo_key: str, *, now: datetime) -> str:
        return urls.signed_url(self.key, thumb_name(photo_key), now=now)

    def _write_file(self, name: str, content: bytes) -> None:
        temporary = self.path(f"{name}.{uuid.uuid4().hex}{_TEMP_SUFFIX}")
        try:
            with temporary.open("xb") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path(name))
        finally:
            temporary.unlink(missing_ok=True)

    def write(self, image: ProcessedImage) -> str:
        """Store a processed photo under a new key, which is returned."""
        key = new_key()
        self._write_file(main_name(key), image.main)
        self._write_file(thumb_name(key), image.thumb)
        return key

    def copy(self, photo_key: str) -> str | None:
        """Copy a photo's files under a new key (a meal copy has its own files, MEAL-08);
        None if the files are gone."""
        key = new_key()
        try:
            for source, target in zip(file_names(photo_key), file_names(key), strict=True):
                self._write_file(target, self.path(source).read_bytes())
        except FileNotFoundError:
            self.delete(key)
            return None
        return key

    def delete(self, photo_key: str) -> None:
        """Remove a photo's files; missing files are fine, other failures are only logged
        (the cleanup job retries)."""
        for name in file_names(photo_key):
            try:
                self.path(name).unlink(missing_ok=True)
            except OSError:
                logger.warning("could not delete a media file", exc_info=True)

    async def process_and_write(self, data: bytes) -> str:
        """Run the pipeline in a worker thread and store the result; returns the new key."""
        image = await self.processor.process(data)
        return await anyio.to_thread.run_sync(self.write, image)

    async def copy_in_thread(self, photo_key: str) -> str | None:
        return await anyio.to_thread.run_sync(self.copy, photo_key)

    async def delete_in_thread(self, photo_key: str) -> None:
        await anyio.to_thread.run_sync(self.delete, photo_key)

    def _entries(self) -> Iterator[os.DirEntry[str]]:
        with suppress(FileNotFoundError), os.scandir(self.directory) as entries:
            yield from (entry for entry in entries if entry.is_file(follow_symlinks=False))

    def remove_orphans(self, referenced: Collection[str], *, now: float) -> int:
        """Delete photo files whose key is not in `referenced`, and leftover temporary files,
        if they are older than an hour. Returns how many files were deleted."""
        removed = 0
        for entry in list(self._entries()):
            key = key_of(entry.name)
            orphan = entry.name.endswith(_TEMP_SUFFIX) or (
                key is not None and key not in referenced
            )
            if not orphan or now - entry.stat().st_mtime < ORPHAN_MIN_AGE_SECONDS:
                continue
            with suppress(FileNotFoundError):
                os.unlink(entry.path)
                removed += 1
        return removed
