"""Text normalisation for `*_norm` columns and dictionary order (plan § 5.2).

`normalize()` is used for uniqueness and search: "Müller", "MUELLER" and " mueller " are the
same name, and so are "Crème" and "creme". `sort_key()` is used for dictionary order: "Äpfel"
sorts as "apfel", next to "Apfel".
"""

import unicodedata

_GERMAN_FOLDS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_DICTIONARY_FOLDS = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})


def _fold(text: str, folds: dict[int, str]) -> str:
    """Lowercase, `folds` applied, accents stripped, whitespace collapsed and trimmed."""
    # NFKC first: a decomposed "a" + combining diaeresis becomes "ä" (and is folded), and
    # compatibility forms such as full-width letters become plain ones before lowercasing.
    folded = unicodedata.normalize("NFKC", text).lower().translate(folds)
    decomposed = unicodedata.normalize("NFKD", folded)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.split())


def normalize(text: str) -> str:
    """Lowercase, `ä→ae ö→oe ü→ue ß→ss`, accents stripped, whitespace collapsed and trimmed."""
    return _fold(text, _GERMAN_FOLDS)


def sort_key(text: str) -> str:
    """The key of dictionary order (ING-03, MEAL-09, D-27): lowercase, `ä→a ö→o ü→u ß→ss`,
    accents stripped, whitespace collapsed and trimmed. It is built from the text as typed, not
    from `normalize()`: folding `ae oe ue` back would also move real letter pairs ("Quelle",
    "Feuer", "Aloe")."""
    return _fold(text, _DICTIONARY_FOLDS)


UMLAUT_SPELLINGS = (("ae", "a"), ("oe", "o"), ("ue", "u"))


def fold_umlauts(text_norm: str) -> str:
    """A normalised text with `ae oe ue` reduced to `a o u`, for search only: "apfel" then
    finds "Äpfel" (`aepfel`) as well as "aepfel" does (ING-03)."""
    for spelled, plain in UMLAUT_SPELLINGS:
        text_norm = text_norm.replace(spelled, plain)
    return text_norm
