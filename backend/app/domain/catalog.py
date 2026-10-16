"""Input rules for ingredients, categories, cuisines and tags (ING-02, REF-01, REF-03, REF-04,
BAR-10).

Names are stored as typed (trimmed) and compared through `normalize()` (`*_norm` columns).
Typed text with control, format, surrogate, private-use or unassigned characters is refused
(`check_text`); text from Open Food Facts is cleaned of them instead (`clean_text`).
"""

import re
import unicodedata
from decimal import Decimal

from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.text import normalize
from app.domain.units import UNIT_FACTOR, UNIT_KIND, BaseUnit, Unit, UnitKind

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
# than the nutrients: the name, the brand and the pack size's text (`quantity_text`, D-47). Each
# one a user changes on an ingredient from Open Food Facts is recorded as user-edited, nutrients
# as `nutrients.<key>`. The barcode, category, base unit and piece weight are the user's alone: a
# refresh never touches them.
OFF_DATA_FIELDS: tuple[str, ...] = ("name", "brand", "quantity_text")

# The pack size's amount, always taken from its text (`pack_amount`, D-47). Before D-38 these
# were marked user-edited on their own; such a mark counts as one on the pack size.
PACK_AMOUNT_FIELDS: tuple[str, ...] = ("pack_quantity", "pack_unit")

# A plain amount and unit, such as "500 g" or "1,5 l"; ASCII digits only. Anchored at both
# ends, so that a long run of digits is tried from one start only (no polynomial backtracking).
_PACK_AMOUNT = re.compile(r"^([0-9]+)(?:[.,]([0-9]+))?\s*(kg|g|ml|l)\Z", re.IGNORECASE)


def nutrient_field(key: str) -> str:
    """The field name of a nutrient in `user_edited_fields` and pending updates."""
    return f"nutrients.{key}"


OFF_FIELDS: tuple[str, ...] = (
    *OFF_DATA_FIELDS,
    *(nutrient_field(key) for key in NUTRIENT_KEYS),
)


def pack_amount(text: str | None) -> tuple[float, BaseUnit] | None:
    """The amount of a pack size that is a plain amount and unit ("500 g", "1,5 l"), in the base
    unit of its kind: g for g and kg, ml for ml and l (D-47). None for any other text ("6 x 1,5
    l", "4 Stück"), for an amount that is 0 or over `PACK_QUANTITY_MAX`, and where the separator
    may be a thousands one ("1.000 g", "1,250 kg"): such an amount is not guessed."""
    match = None if text is None else _PACK_AMOUNT.match(text)
    if match is None:
        return None
    whole, fraction, unit_text = match.groups()
    if fraction is not None and len(fraction) == 3 and int(whole) != 0:
        return None
    unit = Unit(unit_text.lower())
    # Decimal, so that "0,07 kg" is 70 g and not 70.00000000000001.
    number = Decimal(whole if fraction is None else f"{whole}.{fraction}")
    amount = float(number * Decimal(UNIT_FACTOR[unit]))
    if not 0 < amount <= PACK_QUANTITY_MAX:
        return None
    return amount, BaseUnit.G if UNIT_KIND[unit] is UnitKind.MASS else BaseUnit.ML


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
