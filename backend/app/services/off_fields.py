"""The Open Food Facts fields of an item and its pending update (BAR-04, BAR-06).

An item from Open Food Facts (`source` off) has the fields of `OFF_FIELDS`: `name`,
`brand` and `nutrients.<key>`. Those a user changed are listed in `user_edited_fields`
(`edited_fields`); a refresh (`services.off_refresh`) updates the others silently and collects
newer values for the user-edited ones into `pending_update`.

`pending_update` is stored as `{field: {"current": ..., "proposed": ...}}`; the API shows the
entries whose proposed value still differs from the item's value, as of its
`off_last_modified_at`. Ignoring an update remembers that Open Food Facts version
(`ignored_off_modified_at`); when Open Food Facts gave none, the entries stay instead, marked
`"ignored": true`, so that a refresh does not propose these very values again. The API never
shows ignored entries.
"""

from collections.abc import Iterable
from typing import Any

from app.domain.catalog import OFF_FIELDS, nutrient_field
from app.domain.text import normalize, sort_key
from app.models import Item as ItemRow
from app.schemas.items import PendingUpdate, PendingUpdateField

_NUTRIENT_PREFIX = nutrient_field("")
# Marks a `pending_update` entry the user ignored while its Open Food Facts version was unknown.
IGNORED = "ignored"

type FieldValue = str | float | None


def field_value(row: ItemRow, field: str) -> FieldValue:
    """The value of an Open Food Facts field (`name`, ..., `nutrients.kcal`)."""
    if field.startswith(_NUTRIENT_PREFIX):
        return row.nutrients()[field.removeprefix(_NUTRIENT_PREFIX)]
    value: FieldValue = getattr(row, field)
    return value


def edited_fields(row: ItemRow) -> list[str]:
    """The Open Food Facts fields a user changed (BAR-04), in field order."""
    marks = set(row.user_edited_fields)
    return [field for field in OFF_FIELDS if field in marks]


def unmark_edited(row: ItemRow, fields: Iterable[str]) -> None:
    """These fields are Open Food Facts' again (an applied update): no longer user-edited."""
    unmarked = set(fields)
    row.user_edited_fields = [field for field in row.user_edited_fields if field not in unmarked]


def set_field_value(row: ItemRow, field: str, value: Any) -> None:
    """Set an Open Food Facts field; a new name or brand also updates its normalised form."""
    if field.startswith(_NUTRIENT_PREFIX):
        row.set_nutrient(field.removeprefix(_NUTRIENT_PREFIX), value)
    elif field == "name":
        set_name(row, value)
    else:  # `brand`, the last of `OFF_DATA_FIELDS`
        set_brand(row, value)


def set_name(row: ItemRow, name: str) -> None:
    """Set the name together with its normalised form (search, similarity hints) and its sort
    key (dictionary order)."""
    row.name, row.name_norm, row.name_sort = name, normalize(name), sort_key(name)


def set_brand(row: ItemRow, brand: str | None) -> None:
    """Set the brand together with its normalised form (search) and its sort key."""
    row.brand = brand
    row.brand_norm = None if brand is None else normalize(brand) or None
    row.brand_sort = None if brand is None else sort_key(brand) or None


def ignored_entries(row: ItemRow) -> dict[str, Any]:
    """The `pending_update` entries the user ignored (marked `IGNORED`)."""
    stored: dict[str, Any] = row.pending_update or {}
    return {field: entry for field, entry in stored.items() if entry.get(IGNORED)}


def pending_fields(row: ItemRow) -> dict[str, FieldValue]:
    """The proposed values of the pending update that are not ignored and still differ from
    the item's, in field order."""
    stored: dict[str, Any] = row.pending_update or {}
    return {
        field: stored[field]["proposed"]
        for field in OFF_FIELDS
        if field in stored
        and not stored[field].get(IGNORED)
        and stored[field]["proposed"] != field_value(row, field)
    }


def pending_update(row: ItemRow) -> PendingUpdate | None:
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


def drop_pending(row: ItemRow, fields: Iterable[str]) -> None:
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
