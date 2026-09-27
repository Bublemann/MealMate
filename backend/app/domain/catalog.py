"""Input rules for ingredients, products, cuisines and tags (ING-02, REF-03, REF-04, BAR-10).

Names are stored as typed (trimmed) and compared through `normalize()` (`*_norm` columns).
"""

import unicodedata

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


def has_control_characters(text: str) -> bool:
    """Control or format characters (including bidi overrides), which text must not carry."""
    return any(unicodedata.category(char) in {"Cc", "Cf"} for char in text)


def check_text(text: str) -> str:
    """A validator for free text: rejects control and format characters."""
    if has_control_characters(text):
        raise ValueError("control or format characters")
    return text


def check_name(text: str) -> str:
    """A validator for names: like `check_text`, and something must be left after
    normalisation, which uniqueness and search go by."""
    check_text(text)
    if not normalize(text):
        raise ValueError("nothing left after normalisation")
    return text
