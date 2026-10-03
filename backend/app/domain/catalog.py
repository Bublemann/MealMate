"""Input rules for ingredients, categories, cuisines and tags (ING-02, REF-01, REF-03, REF-04,
BAR-10).

Names are stored as typed (trimmed) and compared through `normalize()` (`*_norm` columns).
Typed text with control, format, surrogate, private-use or unassigned characters is refused
(`check_text`); text from Open Food Facts is cleaned of them instead (`clean_text`).
"""

import unicodedata

from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.text import normalize

INGREDIENT_NAME_MAX_LENGTH = 60
CATEGORY_NAME_MAX_LENGTH = 40
CUISINE_NAME_MAX_LENGTH = 40
TAG_NAME_MAX_LENGTH = 30
BRAND_MAX_LENGTH = 80
QUANTITY_TEXT_MAX_LENGTH = 40
BARCODE_INPUT_MAX_LENGTH = 32

# Exclusive lower bound 0, inclusive upper bound.
PIECE_WEIGHT_MAX_G = 10_000.0
PACK_QUANTITY_MAX = 100_000.0

# Normalised names can be longer than typed ones ("ß" → "ss", compatibility forms).
NAME_NORM_FACTOR = 4

# The fields of an ingredient that Open Food Facts provides and refreshes (BAR-04..06), other
# than the nutrients and the pack size. Each one a user changes on an ingredient from Open Food
# Facts is recorded as user-edited, nutrients as `nutrients.<key>`. The barcode, category, base
# unit and piece weight are the user's alone: a refresh never touches them.
OFF_DATA_FIELDS: tuple[str, ...] = ("name", "brand")

# The pack size (ING-02, D-38): Open Food Facts' alone. It is never typed in or edited, so it is
# never user-edited and a refresh always updates it; "user-edited" marks on it from before D-38
# are ignored, not rewritten.
PACK_FIELDS: tuple[str, ...] = ("quantity_text", "pack_quantity", "pack_unit")


def nutrient_field(key: str) -> str:
    """The field name of a nutrient in `user_edited_fields` and pending updates."""
    return f"nutrients.{key}"


OFF_FIELDS: tuple[str, ...] = (
    *OFF_DATA_FIELDS,
    *(nutrient_field(key) for key in NUTRIENT_KEYS),
)


# Control, format (including bidi overrides), surrogate, private-use and unassigned characters.
# A lone surrogate (e.g. from a JSON `\ud800` escape) cannot even be encoded as UTF-8.
_UNSAFE_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn"})


def has_control_characters(text: str) -> bool:
    """Control, format (including bidi overrides), surrogate, private-use or unassigned
    characters, which text must not carry."""
    return any(unicodedata.category(char) in _UNSAFE_CATEGORIES for char in text)


def clean_text(text: str, max_length: int) -> str | None:
    """Untrusted text made safe to store (BAR-10): control, format (including bidi overrides),
    surrogate, private-use and unassigned characters removed, whitespace collapsed, cut to
    `max_length` characters; None if nothing is left."""
    kept = "".join(
        " " if char.isspace() else char
        for char in text
        if char.isspace() or unicodedata.category(char) not in _UNSAFE_CATEGORIES
    )
    return " ".join(kept.split())[:max_length].rstrip() or None


def cut_at_word(text: str, max_length: int) -> str:
    """`text` shortened to at most `max_length` characters at the last word boundary, so that a
    long Open Food Facts name becomes a readable ingredient name ("Bio Vollmilch 3,8 % Fett
    frisch" rather than "Bio Vollmilch 3,8 % Fe"). Where that would lose more than half, such as
    before one overlong word, it is cut hard instead."""
    if len(text) <= max_length:
        return text
    hard = text[:max_length].rstrip()
    head = text[: max_length + 1]
    cut = head.rsplit(" ", 1)[0].rstrip(" ,;:-/(") if " " in head else ""
    return cut if len(cut) >= max_length // 2 else hard


def check_text(text: str) -> str:
    """A validator for free text: rejects the characters `has_control_characters` finds."""
    if has_control_characters(text):
        raise ValueError("control, format or unassigned characters")
    return text


def check_name(text: str) -> str:
    """A validator for names: like `check_text`, and something must be left after
    normalisation, which uniqueness and search go by."""
    check_text(text)
    if not normalize(text):
        raise ValueError("nothing left after normalisation")
    return text
