"""The "similar ingredient exists" hint (ING-03)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.similarity import levenshtein, max_distance, similar_names
from app.domain.text import normalize


@pytest.mark.parametrize(
    ("a", "b", "distance"),
    [
        ("", "", 0),
        ("", "abc", 3),
        ("apfel", "apfel", 0),
        ("apfel", "aepfel", 1),
        ("kitten", "sitting", 3),
        ("tomate", "tomaten", 1),
        ("reis", "mais", 2),
    ],
)
def test_levenshtein(a: str, b: str, distance: int) -> None:
    assert levenshtein(a, b) == distance
    assert levenshtein(b, a) == distance


@given(st.text(max_size=12), st.text(max_size=12), st.text(max_size=12))
def test_levenshtein_is_a_metric(a: str, b: str, c: str) -> None:
    assert (levenshtein(a, b) == 0) is (a == b)
    assert levenshtein(a, b) == levenshtein(b, a)
    assert levenshtein(a, c) <= levenshtein(a, b) + levenshtein(b, c)
    assert levenshtein(a, b) <= max(len(a), len(b))


def test_max_distance() -> None:
    assert [max_distance("x" * n) for n in (1, 5, 6, 20)] == [1, 1, 2, 2]


NAMES = [
    "Äpfel",
    "Apfelmus",
    "Birnen",
    "Tomaten",
    "Tomate getrocknet",
    "Reis",
    "Mais",
    "Ei",
    "Eis",
    "Olivenöl",
]
CANDIDATES = [(name, normalize(name)) for name in NAMES]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Apfel", ["Äpfel", "Apfelmus"]),
        ("Äpfel", ["Äpfel", "Apfelmus"]),
        ("aepfel", ["Äpfel", "Apfelmus"]),
        ("Tomate", ["Tomaten", "Tomate getrocknet"]),
        ("Birne", ["Birnen"]),
        ("Reis", ["Reis", "Eis"]),
        ("Eis", ["Eis", "Ei", "Reis"]),
        ("Eier", []),
        ("Oel", []),  # too short to be contained in "olivenoel"
        ("Olivenoel extra", ["Olivenöl"]),
        ("Gurke", []),
        ("", []),
    ],
)
def test_similar_names(name: str, expected: list[str]) -> None:
    assert similar_names(normalize(name), CANDIDATES) == expected


def test_exact_matches_first_and_the_limit() -> None:
    candidates = [(f"id{i}", f"tee {i}") for i in range(8)] + [("exact", "tee")]
    assert similar_names("tee", candidates) == ["exact", "id0", "id1", "id2", "id3"]
    assert similar_names("tee", candidates, limit=2) == ["exact", "id0"]


def test_equal_names_are_ordered_by_id() -> None:
    assert similar_names("reis", [("b", "reis"), ("a", "reis")]) == ["a", "b"]
