"""Rules for usernames, display names and passwords (ACC-05, ACC-06)."""

import re
import unicodedata
from collections.abc import Collection

from app.core.errors import FieldErrorCode
from app.domain.text import normalize

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
USERNAME_PATTERN = r"^[a-z0-9._-]+$"
DISPLAY_NAME_MAX_LENGTH = 40
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72  # bcrypt ignores (bcrypt >= 5: rejects) anything beyond 72 bytes

_USERNAME = re.compile(USERNAME_PATTERN)


def username_norm(username: str) -> str:
    """The uniqueness key of a username; also what a login is looked up by."""
    return username.strip().lower()


def username_problem(username: str) -> FieldErrorCode | None:
    """3–30 characters of `a–z 0–9 . _ -`. Uppercase is rejected; the UI lowercases."""
    if len(username) < USERNAME_MIN_LENGTH:
        return FieldErrorCode.TOO_SHORT
    if len(username) > USERNAME_MAX_LENGTH:
        return FieldErrorCode.TOO_LONG
    if not _USERNAME.fullmatch(username):
        return FieldErrorCode.INVALID_FORMAT
    return None


def clean_display_name(display_name: str) -> str:
    """The display name as stored: surrounding whitespace removed."""
    return display_name.strip()


def display_name_problem(display_name: str) -> FieldErrorCode | None:
    """1–40 characters after trimming, no control or format characters, and something left
    after normalisation (unique ignoring case and umlaut spelling via `display_name_norm`)."""
    cleaned = clean_display_name(display_name)
    if not cleaned:
        return FieldErrorCode.TOO_SHORT
    if len(cleaned) > DISPLAY_NAME_MAX_LENGTH:
        return FieldErrorCode.TOO_LONG
    if any(unicodedata.category(char) in {"Cc", "Cf"} for char in cleaned):
        return FieldErrorCode.INVALID_FORMAT
    if not normalize(cleaned):
        return FieldErrorCode.INVALID_FORMAT
    return None


def password_problem(
    password: str, *, username: str, common: Collection[str]
) -> FieldErrorCode | None:
    """At least 8 characters, at most 72 bytes of UTF-8, not the username, not a common one.

    `common` holds lowercased passwords; the comparison ignores case, as does the username check.
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        return FieldErrorCode.TOO_SHORT
    if len(password.encode()) > PASSWORD_MAX_BYTES:
        return FieldErrorCode.TOO_LONG
    lowered = password.lower()
    if lowered == username.strip().lower():
        return FieldErrorCode.SAME_AS_USERNAME
    if lowered in common:
        return FieldErrorCode.TOO_COMMON
    return None
