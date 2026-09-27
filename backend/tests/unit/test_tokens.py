from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.tokens import (
    ACCESS_TOKEN_TTL,
    AccessTokenExpiredError,
    InvalidAccessTokenError,
    create_access_token,
    decode_access_token,
    keyed_hash,
    random_token,
)

KEY = b"k" * 32
NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def test_random_tokens_are_long_and_url_safe() -> None:
    tokens = {random_token() for _ in range(100)}
    assert len(tokens) == 100
    for token in tokens:
        assert len(token) == 43  # 32 bytes, base64url without padding
        assert set(token) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_keyed_hash() -> None:
    assert keyed_hash(KEY, "abc") == keyed_hash(KEY, "abc")
    assert keyed_hash(KEY, "abc") != keyed_hash(b"x" * 32, "abc")
    assert len(keyed_hash(KEY, "abc")) == 64
    assert "abc" not in keyed_hash(KEY, "abc")


def test_access_token_round_trip() -> None:
    token = create_access_token(KEY, user_id="u1", session_id="s1", now=NOW)
    claims = decode_access_token(KEY, token, now=NOW + ACCESS_TOKEN_TTL - timedelta(seconds=1))
    assert (claims.user_id, claims.session_id) == ("u1", "s1")
    options = {"verify_exp": False, "verify_iat": False}
    payload = jwt.decode(token, KEY, algorithms=["HS256"], options=options)
    assert payload == {
        "sub": "u1",
        "sid": "s1",
        "iat": int(NOW.timestamp()),
        "exp": int((NOW + timedelta(minutes=15)).timestamp()),
    }


def test_expired_access_token() -> None:
    token = create_access_token(KEY, user_id="u1", session_id="s1", now=NOW)
    with pytest.raises(AccessTokenExpiredError):
        decode_access_token(KEY, token, now=NOW + ACCESS_TOKEN_TTL)


def forge(payload: dict[str, object], key: bytes = KEY, algorithm: str = "HS256") -> str:
    return jwt.encode(payload, key, algorithm=algorithm)


VALID = {"sub": "u1", "sid": "s1", "iat": int(NOW.timestamp()), "exp": int(NOW.timestamp()) + 60}


@pytest.mark.parametrize(
    "token",
    [
        "not-a-jwt",
        "",
        forge(VALID, key=b"other" * 8),
        forge({k: v for k, v in VALID.items() if k != "sid"}),
        forge({k: v for k, v in VALID.items() if k != "exp"}),
        forge(VALID | {"sid": 5}),
        forge(VALID | {"exp": "tomorrow"}),
        forge(VALID | {"exp": True}),
        forge(VALID, key=KEY * 2, algorithm="HS512"),
        jwt.encode(VALID, None, algorithm="none"),
    ],
)
def test_invalid_access_tokens(token: str) -> None:
    with pytest.raises(InvalidAccessTokenError) as excinfo:
        decode_access_token(KEY, token, now=NOW)
    assert not isinstance(excinfo.value, AccessTokenExpiredError)
