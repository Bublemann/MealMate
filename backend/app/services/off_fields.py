"""The Open Food Facts fields of an ingredient and its pending update (BAR-04, BAR-06).

An ingredient from Open Food Facts (`source` off) has the fields of `OFF_FIELDS`: `name`,
`brand`, `quantity_text` (the pack size) and `nutrients.<key>`. Those a user changed are listed in
`user_edited_fields` (`edited_fields`); a refresh (`services.off_refresh`) updates the others
silently and collects newer values for the user-edited ones into `pending_update`. The pack size's
amount (`pack_quantity`, `pack_unit`) always follows its text (`set_pack_size`, D-47); a mark on
it from before D-38 counts as one on the pack size.

`pending_update` is stored as `{field: {"current": ..., "proposed": ...}}`; the API shows the
entries whose proposed value still differs from the ingredient's value, as of its
`off_last_modified_at`. Ignoring an update remembers that Open Food Facts version
(`ignored_off_modified_at`); when Open Food Facts gave none, the entries stay instead, marked
`"ignored": true`, so that a refresh does not propose these very values again. The API never
shows ignored entries.
"""

from collections.abc import Iterable
from typing import Any

from app.domain.catalog import OFF_FIELDS, PACK_AMOUNT_FIELDS, nutrient_field, pack_amount
from app.domain.text import normalize, sort_key
from app.models import Ingredient as IngredientRow
from app.schemas.ingredients import PendingUpdate, PendingUpdateField

_NUTRIENT_PREFIX = nutrient_field("")
# Marks a `pending_update` entry the user ignored while its Open Food Facts version was unknown.
IGNORED = "ignored"

type FieldValue = str | float | None


def field_value(row: IngredientRow, field: str) -> FieldValue:
    """The value of an Open Food Facts field (`name`, ..., `nutrients.kcal`)."""
    if field.startswith(_NUTRIENT_PREFIX):
        return row.nutrients()[field.removeprefix(_NUTRIENT_PREFIX)]
    value: FieldValue = getattr(row, field)
    return value


def edited_fields(row: IngredientRow) -> list[str]:
    """The Open Food Facts fields a user changed (BAR-04), in field order. A mark on the pack
    size's amount from before D-38 counts as one on the pack size: a user did change it (D-47)."""
    marks = set(row.user_edited_fields)
    if marks.intersection(PACK_AMOUNT_FIELDS):
        marks.add("quantity_text")
    return [field for field in OFF_FIELDS if field in marks]


def unmark(row: IngredientRow, fields: Iterable[str]) -> None:
    """These fields are Open Food Facts' again (an applied update): no longer user-edited, the
    pack size along with any mark on its amount from before D-38."""
    unmarked = set(fields)
    if "quantity_text" in unmarked:
        unmarked.update(PACK_AMOUNT_FIELDS)
    row.user_edited_fields = [field for field in row.user_edited_fields if field not in unmarked]


def set_field_value(row: IngredientRow, field: str, value: Any) -> None:
    """Set an Open Food Facts field; a new name or brand also updates its normalised form, a new
    pack size its amount."""
    if field.startswith(_NUTRIENT_PREFIX):
        row.set_nutrient(field.removeprefix(_NUTRIENT_PREFIX), value)
    elif field == "name":
        set_name(row, value)
    elif field == "brand":
        set_brand(row, value)
    else:  # `quantity_text`, the last of `OFF_DATA_FIELDS`
        set_pack_size(row, value)


def set_name(row: IngredientRow, name: str) -> None:
    """Set the name together with its normalised form (search, similarity hints) and its sort
    key (dictionary order)."""
    row.name, row.name_norm, row.name_sort = name, normalize(name), sort_key(name)


def set_brand(row: IngredientRow, brand: str | None) -> None:
    """Set the brand together with its normalised form (search) and its sort key."""
    row.brand = brand
    row.brand_norm = None if brand is None else normalize(brand) or None
    row.brand_sort = None if brand is None else sort_key(brand) or None


def set_pack_size(row: IngredientRow, text: str | None) -> None:
    """Set the pack size's text together with its amount, taken from the text (D-47)."""
    amount = pack_amount(text)
    row.quantity_text = text
    row.pack_quantity = None if amount is None else amount[0]
    row.pack_unit = None if amount is None else amount[1].value


def ignored_entries(row: IngredientRow) -> dict[str, Any]:
    """The `pending_update` entries the user ignored (marked `IGNORED`)."""
    stored: dict[str, Any] = row.pending_update or {}
    return {field: entry for field, entry in stored.items() if entry.get(IGNORED)}


def pending_fields(row: IngredientRow) -> dict[str, FieldValue]:
    """The proposed values of the pending update that are not ignored and still differ from
    the ingredient's, in field order."""
    stored: dict[str, Any] = row.pending_update or {}
    return {
        field: stored[field]["proposed"]
        for field in OFF_FIELDS
        if field in stored
        and not stored[field].get(IGNORED)
        and stored[field]["proposed"] != field_value(row, field)
    }


def pending_update(row: IngredientRow) -> PendingUpdate | None:
    """The API view of the pending update, if anything is pending."""
    proposed = pending_fields(row)
    if not proposed:
        return None
    return PendingUpdate(
        fields=[
            PendingUpdateField(field=field, current=field_value(row, field), proposed=value)
            for field, value in proposed.items()
        ],
        off_last_modified_at=row.off_last_modified_at,
    )


def drop_pending(row: IngredientRow, fields: Iterable[str]) -> None:
    """The user just decided these fields, so Open Food Facts' pending values for them go (the
    ignored ones stay remembered)."""
    if row.pending_update:
        decided = set(fields)
        remaining = {
            field: entry
            for field, entry in row.pending_update.items()
            if field not in decided or entry.get(IGNORED)
        }
        row.pending_update = remaining or None
