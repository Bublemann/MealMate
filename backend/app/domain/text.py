"""Text normalisation for `*_norm` columns (plan § 5.2).

`normalize()` is used for uniqueness and search: "Müller", "MUELLER" and " mueller " are the
same name, and so are "Crème" and "creme".
"""

import unicodedata

_GERMAN_FOLDS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def normalize(text: str) -> str:
    """Lowercase, `ä→ae ö→oe ü→ue ß→ss`, accents stripped, whitespace collapsed and trimmed."""
    # NFKC first: a decomposed "a" + combining diaeresis becomes "ä" (and folds to "ae"), and
    # compatibility forms such as full-width letters become plain ones before lowercasing.
    folded = unicodedata.normalize("NFKC", text).lower().translate(_GERMAN_FOLDS)
    decomposed = unicodedata.normalize("NFKD", folded)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.split())


UMLAUT_SPELLINGS = (("ae", "a"), ("oe", "o"), ("ue", "u"))


def fold_umlauts(text_norm: str) -> str:
    """A normalised text with `ae oe ue` reduced to `a o u`, for search only: "apfel" then
    finds "Äpfel" (`aepfel`) as well as "aepfel" does (ING-03)."""
    for spelled, plain in UMLAUT_SPELLINGS:
        text_norm = text_norm.replace(spelled, plain)
    return text_norm
