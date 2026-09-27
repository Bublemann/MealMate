"""Key derivation: one `SECRET_KEY`, a separate subkey per purpose (plan § 5.4).

HKDF-SHA256 as specified in RFC 5869, built on the standard library. Rotating the secret key
changes every subkey, which invalidates all sessions, open codes and media URLs at once.
"""

import hashlib
import hmac
from dataclasses import dataclass
from enum import StrEnum

from pydantic import SecretStr

_DIGEST = "sha256"
_HASH_LENGTH = hashlib.sha256().digest_size
_SALT = b"mealmate/v2"
KEY_LENGTH = 32


class KeyPurpose(StrEnum):
    JWT = "jwt"
    MEDIA = "media"
    TOKEN = "token"  # noqa: S105 -- a purpose label, not a secret


@dataclass(frozen=True, repr=False)
class DerivedKeys:
    """Subkeys for signing access tokens, signing media URLs and hashing tokens and codes."""

    jwt: bytes
    media: bytes
    token: bytes


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    """RFC 5869 § 2.2. An empty salt behaves like HashLen zero bytes, as the RFC requires."""
    return hmac.digest(salt, ikm, _DIGEST)


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """RFC 5869 § 2.3."""
    if not 0 < length <= 255 * _HASH_LENGTH:
        raise ValueError(f"length must be between 1 and {255 * _HASH_LENGTH}")
    output = b""
    block = b""
    counter = 1
    while len(output) < length:
        block = hmac.digest(prk, block + info + bytes([counter]), _DIGEST)
        output += block
        counter += 1
    return output[:length]


def hkdf(ikm: bytes, *, salt: bytes, info: bytes, length: int) -> bytes:
    return hkdf_expand(hkdf_extract(salt, ikm), info, length)


def derive_key(secret_key: SecretStr, purpose: KeyPurpose) -> bytes:
    return hkdf(
        secret_key.get_secret_value().encode(),
        salt=_SALT,
        info=f"mealmate:{purpose}".encode(),
        length=KEY_LENGTH,
    )


def derive_keys(secret_key: SecretStr) -> DerivedKeys:
    return DerivedKeys(
        jwt=derive_key(secret_key, KeyPurpose.JWT),
        media=derive_key(secret_key, KeyPurpose.MEDIA),
        token=derive_key(secret_key, KeyPurpose.TOKEN),
    )
