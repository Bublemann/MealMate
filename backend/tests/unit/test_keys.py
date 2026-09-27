import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import SecretStr

from app.core.keys import (
    KEY_LENGTH,
    KeyPurpose,
    derive_key,
    derive_keys,
    hkdf,
    hkdf_expand,
    hkdf_extract,
)

# RFC 5869, appendix A.1 (basic test case with SHA-256).
IKM = bytes.fromhex("0b" * 22)
SALT = bytes.fromhex("000102030405060708090a0b0c")
INFO = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9")
PRK = bytes.fromhex("077709362c2e32df0ddc3f0dc47bba6390b6c73bb50f9c3122ec844ad7c2b3e5")
OKM = bytes.fromhex(
    "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"
)

# RFC 5869, appendix A.3 (zero-length salt and info).
PRK_NO_SALT = bytes.fromhex("19ef24a32c717b167f33a91d6f648bdf96596776afdb6377ac434c1c293ccb04")
OKM_NO_SALT = bytes.fromhex(
    "8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8"
)

SECRET = SecretStr("k" * 40)


def test_rfc5869_test_case_1() -> None:
    assert hkdf_extract(SALT, IKM) == PRK
    assert hkdf_expand(PRK, INFO, 42) == OKM
    assert hkdf(IKM, salt=SALT, info=INFO, length=42) == OKM


def test_rfc5869_test_case_3() -> None:
    assert hkdf_extract(b"", IKM) == PRK_NO_SALT
    assert hkdf(IKM, salt=b"", info=b"", length=42) == OKM_NO_SALT


@pytest.mark.parametrize("length", [0, 255 * 32 + 1])
def test_expand_rejects_impossible_lengths(length: int) -> None:
    with pytest.raises(ValueError, match="length"):
        hkdf_expand(PRK, INFO, length)


@given(st.integers(min_value=1, max_value=255 * 32), st.integers(min_value=1, max_value=255 * 32))
def test_shorter_output_is_a_prefix_of_longer(a: int, b: int) -> None:
    short, long = sorted((a, b))
    assert hkdf_expand(PRK, INFO, long)[:short] == hkdf_expand(PRK, INFO, short)


def test_each_purpose_gets_its_own_key() -> None:
    keys = derive_keys(SECRET)
    values = {keys.jwt, keys.media, keys.token}
    assert len(values) == 3
    assert all(len(key) == KEY_LENGTH for key in values)
    assert keys.jwt == derive_key(SECRET, KeyPurpose.JWT)
    assert keys.media == derive_key(SECRET, KeyPurpose.MEDIA)
    assert keys.token == derive_key(SECRET, KeyPurpose.TOKEN)
    assert SECRET.get_secret_value().encode() not in values


def test_keys_are_deterministic_and_change_with_the_secret() -> None:
    assert derive_keys(SECRET) == derive_keys(SecretStr("k" * 40))
    assert derive_keys(SECRET).jwt != derive_keys(SecretStr("r" * 40)).jwt


def test_keys_are_not_shown_in_repr() -> None:
    keys = derive_keys(SECRET)
    assert keys.jwt.hex() not in repr(keys)
    assert repr(keys.jwt) not in repr(keys)
