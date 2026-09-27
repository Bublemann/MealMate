"""Random tokens, their keyed hashes, and access tokens (plan § 5.4, SEC-03, SEC-10).

Refresh tokens and invite/reset codes are 32 random bytes (base64url). The database stores only
their HMAC-SHA256 under the HKDF `token` key, so a copy of the database or a backup cannot be
used to log in or register. Access tokens are JWTs (HS256, HKDF `jwt` key) valid for 15 minutes.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import jwt

TOKEN_BYTES = 32
ACCESS_TOKEN_TTL = timedelta(minutes=15)
_JWT_ALGORITHM = "HS256"
_REQUIRED_CLAIMS = ("sub", "sid", "iat", "exp")


def random_token() -> str:
    """256 random bits, base64url without padding (43 characters)."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def keyed_hash(key: bytes, token: str) -> str:
    """HMAC-SHA256 of `token` as hex: what the database stores instead of the token."""
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


class InvalidAccessTokenError(Exception):
    """Not a well-formed access token signed with our key."""


class AccessTokenExpiredError(InvalidAccessTokenError):
    """Signed by us, but past its expiry; the client should refresh it."""


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: str
    session_id: str


def create_access_token(key: bytes, *, user_id: str, session_id: str, now: datetime) -> str:
    payload = {
        "sub": user_id,
        "sid": session_id,
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TOKEN_TTL).timestamp()),
    }
    return jwt.encode(payload, key, algorithm=_JWT_ALGORITHM)


def decode_access_token(key: bytes, token: str, *, now: datetime) -> AccessTokenClaims:
    """Check the signature and claims. Expiry is checked against `now` (the app's clock), not
    PyJWT's own, so tests can move time."""
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=[_JWT_ALGORITHM],
            options={"require": list(_REQUIRED_CLAIMS), "verify_exp": False, "verify_iat": False},
        )
    except jwt.PyJWTError as exc:
        raise InvalidAccessTokenError from exc
    user_id, session_id, expires = payload["sub"], payload["sid"], payload["exp"]
    if not (isinstance(user_id, str) and isinstance(session_id, str)):
        raise InvalidAccessTokenError
    if not isinstance(expires, int) or isinstance(expires, bool):
        raise InvalidAccessTokenError
    if expires <= now.timestamp():
        raise AccessTokenExpiredError
    return AccessTokenClaims(user_id=user_id, session_id=session_id)
