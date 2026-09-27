"""Input rules for ingredients, products, cuisines and tags (ING-02, REF-03, REF-04, BAR-10).

Names are stored as typed (trimmed) and compared through `normalize()` (`*_norm` columns).
Typed text with control, format, surrogate, private-use or unassigned characters is refused
(`check_text`); text from Open Food Facts is cleaned of them instead (`clean_text`).
"""

import unicodedata

from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.text import normalize

INGREDIENT_NAME_MAX_LENGTH = 60
CUISINE_NAME_MAX_LENGTH = 40
TAG_NAME_MAX_LENGTH = 30
PRODUCT_NAME_MAX_LENGTH = 120
PRODUCT_BRAND_MAX_LENGTH = 80
PRODUCT_QUANTITY_TEXT_MAX_LENGTH = 40
BARCODE_INPUT_MAX_LENGTH = 32

# Exclusive lower bound 0, inclusive upper bound.
PIECE_WEIGHT_MAX_G = 10_000.0
DENSITY_MIN_G_PER_ML = 0.1
DENSITY_MAX_G_PER_ML = 5.0
PACK_QUANTITY_MAX = 100_000.0

# Normalised names can be longer than typed ones ("ß" → "ss", compatibility forms).
NAME_NORM_FACTOR = 4

# A product's data fields, as opposed to its barcode and ingredient link. Each one a user
# typed or changed is recorded as user-edited (BAR-04), nutrients as `nutrients.<key>`.
PRODUCT_DATA_FIELDS: tuple[str, ...] = (
    "nutrition_basis",
    "name",
    "brand",
    "quantity_text",
    "pack_quantity",
    "pack_unit",
)


def nutrient_field(key: str) -> str:
    """The field name of a nutrient in `user_edited_fields` and pending updates."""
    return f"nutrients.{key}"


PRODUCT_FIELDS: tuple[str, ...] = (
    *PRODUCT_DATA_FIELDS,
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
