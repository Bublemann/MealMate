import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.text import normalize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Müller", "mueller"),
        ("MUELLER", "mueller"),
        ("  Anna   Maria \t", "anna maria"),
        ("Straße", "strasse"),
        ("STRASSE", "strasse"),
        ("Ärger Öl Übel", "aerger oel uebel"),
        ("Crème brûlée", "creme brulee"),
        ("Zoë", "zoe"),
        ("a\u0308pfel", "aepfel"),  # decomposed ä
        ("ẞ", "ss"),  # capital sharp s
        ("\uff22\uff45\uff4e", "ben"),  # full-width letters
        ("", ""),
        ("\u0301", ""),  # a lone combining accent
    ],
)
def test_normalize(text: str, expected: str) -> None:
    assert normalize(text) == expected


@given(st.text())
def test_normalize_is_idempotent(text: str) -> None:
    once = normalize(text)
    assert normalize(once) == once


@given(st.text())
def test_normalized_text_has_no_outer_or_double_whitespace(text: str) -> None:
    result = normalize(text)
    assert result == result.strip()
    assert "  " not in result
