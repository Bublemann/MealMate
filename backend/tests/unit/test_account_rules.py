import pytest

from app.core.errors import FieldErrorCode
from app.core.passwords import common_passwords
from app.domain.accounts import (
    clean_display_name,
    display_name_problem,
    password_problem,
    username_norm,
    username_problem,
)

COMMON = frozenset({"password", "sommer2024"})


@pytest.mark.parametrize("username", ["abc", "anna", "a.b_c-d", "x" * 30, "0815"])
def test_valid_usernames(username: str) -> None:
    assert username_problem(username) is None


@pytest.mark.parametrize(
    ("username", "problem"),
    [
        ("ab", FieldErrorCode.TOO_SHORT),
        ("", FieldErrorCode.TOO_SHORT),
        ("x" * 31, FieldErrorCode.TOO_LONG),
        ("Anna", FieldErrorCode.INVALID_FORMAT),
        ("an na", FieldErrorCode.INVALID_FORMAT),
        ("anna!", FieldErrorCode.INVALID_FORMAT),
        ("jürgen", FieldErrorCode.INVALID_FORMAT),
        ("anna\n", FieldErrorCode.INVALID_FORMAT),
    ],
)
def test_invalid_usernames(username: str, problem: FieldErrorCode) -> None:
    assert username_problem(username) == problem


def test_username_norm() -> None:
    assert username_norm(" Anna ") == "anna"


@pytest.mark.parametrize("name", ["A", "Anna Müller", "x" * 40, "  padded  ", "Zoë 🍝"])
def test_valid_display_names(name: str) -> None:
    assert display_name_problem(name) is None


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("", FieldErrorCode.TOO_SHORT),
        ("   ", FieldErrorCode.TOO_SHORT),
        ("x" * 41, FieldErrorCode.TOO_LONG),
        ("Anna\u0000", FieldErrorCode.INVALID_FORMAT),
        ("An\u200bna", FieldErrorCode.INVALID_FORMAT),
        ("\u0301", FieldErrorCode.INVALID_FORMAT),
    ],
)
def test_invalid_display_names(name: str, problem: FieldErrorCode) -> None:
    assert display_name_problem(name) == problem


def test_clean_display_name() -> None:
    assert clean_display_name("  Anna  ") == "Anna"


@pytest.mark.parametrize(
    ("password", "problem"),
    [
        ("kurz", FieldErrorCode.TOO_SHORT),
        ("1234567", FieldErrorCode.TOO_SHORT),
        ("ä" * 37, FieldErrorCode.TOO_LONG),  # 37 characters, 74 bytes
        ("x" * 73, FieldErrorCode.TOO_LONG),
        ("annabelle", FieldErrorCode.SAME_AS_USERNAME),
        ("AnnaBelle", FieldErrorCode.SAME_AS_USERNAME),
        ("PASSWORD", FieldErrorCode.TOO_COMMON),
        ("Sommer2024", FieldErrorCode.TOO_COMMON),
        ("correct horse", None),
        ("x" * 72, None),
        ("ä" * 36, None),
        ("12345678", None),  # not in this test's list
    ],
)
def test_password_rules(password: str, problem: FieldErrorCode | None) -> None:
    assert password_problem(password, username="annabelle", common=COMMON) == problem


def test_bundled_common_password_list() -> None:
    common = common_passwords()
    assert len(common) >= 9_900
    assert {"password", "123456", "qwerty", "iloveyou"} <= common
    assert all(entry == entry.lower() and entry.strip() == entry for entry in common)
    assert not any(entry.startswith("#") for entry in common)
    assert password_problem("Password1", username="x", common=common) is FieldErrorCode.TOO_COMMON
    assert password_problem("QWERTY123", username="x", common=common) is FieldErrorCode.TOO_COMMON
