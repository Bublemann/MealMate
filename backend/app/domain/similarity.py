"""The "similar ingredient already exists" hint (ING-03).

Works on normalised names with umlaut spellings folded (`fold_umlauts`), so case, umlauts,
their spelling ("ae") and accents never make a difference: "Apfel" is similar to "Äpfel".
"""

from collections.abc import Iterable

from app.domain.text import fold_umlauts

SIMILAR_LIMIT = 5
CONTAINS_MIN_LENGTH = 3
SHORT_NAME_LENGTH = 5


def levenshtein(a: str, b: str) -> int:
    """The edit distance: insertions, deletions and substitutions of single characters."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        for j, char_b in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


def max_distance(name_norm: str) -> int:
    """How many edits still count as similar: 1 for names up to 5 characters, else 2."""
    return 1 if len(name_norm) <= SHORT_NAME_LENGTH else 2


def _contains(a: str, b: str) -> bool:
    return len(a) >= CONTAINS_MIN_LENGTH and len(b) >= CONTAINS_MIN_LENGTH and (a in b or b in a)


def similar_names(
    name_norm: str, candidates: Iterable[tuple[str, str]], limit: int = SIMILAR_LIMIT
) -> list[str]:
    """The ids of at most `limit` candidates `(id, name_norm)` similar to `name_norm`.

    Similar means (after folding umlaut spellings) that one name contains the other, both at
    least 3 characters long, or that they are at most `max_distance()` edits apart. An exact
    match comes first, then the closest, then by name (and id, for equal names).
    """
    if not name_norm:
        return []
    folded = fold_umlauts(name_norm)
    allowed = max_distance(folded)
    matches: list[tuple[bool, int, str, str]] = []
    for candidate_id, candidate in candidates:
        other = fold_umlauts(candidate)
        contained = _contains(folded, other)
        if abs(len(other) - len(folded)) > allowed and not contained:
            continue
        distance = levenshtein(folded, other)
        if distance <= allowed or contained:
            matches.append((candidate != name_norm, distance, candidate, candidate_id))
    matches.sort()
    return [match[-1] for match in matches[:limit]]
