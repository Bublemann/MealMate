"""Input rules for names and texts (ING-02, BAR-10) and the umlaut folding for search."""

import pytest

from app.domain.catalog import check_name, check_text, has_control_characters
from app.domain.text import fold_umlauts, normalize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Äpfel", False),
        ("Crème fraîche 30 %", False),
        ("tab\there", True),
        ("new\nline", True),
        ("bidi‮override", True),
        ("zero​width", True),
        ("\x00", True),
        ("lone\ud800surrogate", True),
        ("private\ue000use", True),
        ("unassigned\u0378", True),
        ("Käse 🧀 - 45 % Fett", False),
    ],
)
def test_control_characters(text: str, expected: bool) -> None:
    assert has_control_characters(text) is expected


def test_check_text_and_name() -> None:
    assert check_text("Barilla") == "Barilla"
    assert check_name("Äpfel") == "Äpfel"
    with pytest.raises(ValueError, match="control"):
        check_text("Bari‮lla")
    with pytest.raises(ValueError, match="control"):
        check_name("Ä\npfel")
    with pytest.raises(ValueError, match="normalisation"):
        check_name("́́")


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Äpfel", "apfel"), ("aepfel", "apfel"), ("Öl", "ol"), ("Müsli", "musli"), ("Reis", "reis")],
)
def test_fold_umlauts(text: str, expected: str) -> None:
    assert fold_umlauts(normalize(text)) == expected
