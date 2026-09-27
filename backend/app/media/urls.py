"""Signed media URLs (VIS-05, plan § 5.10).

`/api/media/<name>?exp=<unix>&sig=<b64url>`: `sig` is HMAC-SHA256 under the HKDF `media` key
over `"<name>:<exp>"`, base64url without padding. `exp` is now + 1 hour rounded up to the next
full hour (UTC), so a URL lives 1 to 2 hours and stays the same within an hour, which lets browsers
cache the image. URLs are only issued in meal responses, after the view check; rotating the
secret key invalidates all of them.
"""

import base64
import hashlib
import hmac
import math
import re
from datetime import datetime

MEDIA_PATH = "/api/media"
URL_LIFETIME_SECONDS = 3600
_HOUR_SECONDS = 3600
# `<key>.webp` or `<key>-thumb.webp`, the key being a uuid4 in hex.
MEDIA_NAME = re.compile(r"[0-9a-f]{32}(?:-thumb)?\.webp")
_SIGNATURE = re.compile(r"[A-Za-z0-9_-]{43}")
_EXPIRY = re.compile(r"[0-9]{1,12}")


def expiry(now: datetime) -> int:
    """Unix time of now + 1 hour, rounded up to the next full hour."""
    return math.ceil((now.timestamp() + URL_LIFETIME_SECONDS) / _HOUR_SECONDS) * _HOUR_SECONDS


def signature(key: bytes, name: str, exp: int) -> str:
    digest = hmac.digest(key, f"{name}:{exp}".encode(), hashlib.sha256)
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def signed_url(key: bytes, name: str, *, now: datetime) -> str:
    exp = expiry(now)
    return f"{MEDIA_PATH}/{name}?exp={exp}&sig={signature(key, name, exp)}"


def is_valid(key: bytes, name: str, exp: str, sig: str, *, now: datetime) -> bool:
    """Whether `name` is a media file name and `exp`/`sig` a signature for it that has not
    expired. Malformed values are simply invalid; signatures are compared in constant time."""
    if not (MEDIA_NAME.fullmatch(name) and _EXPIRY.fullmatch(exp) and _SIGNATURE.fullmatch(sig)):
        return False
    if int(exp) <= now.timestamp():
        return False
    return hmac.compare_digest(signature(key, name, int(exp)), sig)
