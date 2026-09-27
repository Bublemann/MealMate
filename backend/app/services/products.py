"""Products: barcodes linked to an ingredient, entered by hand or saved from an Open Food Facts
proposal (ING-04, BAR-03, BAR-04), and their pending Open Food Facts updates (BAR-06).

Everyone may add and edit products (plan § 5.5). A product's nutrition basis is always its
ingredient's base unit. Every data field a user sets is marked user-edited, so that an Open
Food Facts refresh (`services.off_refresh`) never overwrites it. The barcode and the ingredient
link are not data from Open Food Facts and are never marked.

`pending_update` is stored as `{field: {"current": ..., "proposed": ...}}`; the API shows the
entries whose proposed value still differs from the product's value, as of the product's
`off_last_modified_at`. Ignoring an update remembers that Open Food Facts version
(`ignored_off_modified_at`); when Open Food Facts gave none, the entries stay instead, marked
`"ignored": true`, so that a refresh does not propose these very values again (see
`services.off_refresh`). The API never shows ignored entries.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ApiError,
    ErrorCode,
    FieldErrorCode,
    FieldProblem,
    not_found,
    validation_error,
)
from app.domain.barcodes import normalize_barcode
from app.domain.catalog import PRODUCT_DATA_FIELDS, PRODUCT_FIELDS, nutrient_field
from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.text import normalize
from app.domain.units import Unit
from app.models import Ingredient as IngredientRow
from app.models import Product as ProductRow
from app.repositories import ingredients as ingredients_repo
from app.repositories import products as products_repo
from app.schemas.ingredients import BaseUnitName
from app.schemas.nutrition import NutrientValues
from app.schemas.products import (
    PendingUpdate,
    PendingUpdateField,
    Product,
    ProductCreate,
    ProductSource,
    ProductUpdate,
)
from app.schemas.users import UserRef
from app.services.principal import Principal
from app.services.users import user_refs

_TEXT_AND_NUMBER_FIELDS = ("name", "brand", "quantity_text", "pack_quantity")
_NUTRIENT_PREFIX = nutrient_field("")
# Marks a `pending_update` entry the user ignored while its Open Food Facts version was unknown.
IGNORED = "ignored"

type FieldValue = str | float | None


def base_unit_name(value: str) -> BaseUnitName:
    return "ml" if value == "ml" else "g"


def _source(value: str) -> ProductSource:
    return "off" if value == "off" else "manual"


def field_value(row: ProductRow, field: str) -> FieldValue:
    """The value of a product field (`name`, ..., `nutrients.kcal`)."""
    if field.startswith(_NUTRIENT_PREFIX):
        return row.nutrients()[field.removeprefix(_NUTRIENT_PREFIX)]
    value: FieldValue = getattr(row, field)
    return value


def set_field_value(row: ProductRow, field: str, value: Any) -> None:
    if field.startswith(_NUTRIENT_PREFIX):
        row.set_nutrient(field.removeprefix(_NUTRIENT_PREFIX), value)
    else:
        setattr(row, field, value)


def ignored_entries(row: ProductRow) -> dict[str, Any]:
    """The `pending_update` entries the user ignored (marked `IGNORED`)."""
    stored: dict[str, Any] = row.pending_update or {}
    return {field: entry for field, entry in stored.items() if entry.get(IGNORED)}


def pending_fields(row: ProductRow) -> dict[str, FieldValue]:
    """The proposed values of the pending update that are not ignored and still differ from
    the product's, in field order."""
    stored: dict[str, Any] = row.pending_update or {}
    return {
        field: stored[field]["proposed"]
        for field in PRODUCT_FIELDS
        if field in stored
        and not stored[field].get(IGNORED)
        and stored[field]["proposed"] != field_value(row, field)
    }


def _pending_update(row: ProductRow) -> PendingUpdate | None:
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


def product(row: ProductRow, refs: dict[str, UserRef]) -> Product:
    return Product(
        id=row.id,
        barcode=row.barcode,
        ingredient_id=row.ingredient_id,
        nutrition_basis=base_unit_name(row.nutrition_basis),
        name=row.name,
        brand=row.brand,
        quantity_text=row.quantity_text,
        pack_quantity=row.pack_quantity,
        pack_unit=None if row.pack_unit is None else Unit(row.pack_unit),
        nutrients=NutrientValues.model_validate(row.nutrients()),
        source=_source(row.source),
        user_edited_fields=list(row.user_edited_fields),
        fetched_at=row.fetched_at,
        pending_update=_pending_update(row),
        created_by=refs.get(row.created_by) if row.created_by else None,
        updated_by=refs.get(row.updated_by) if row.updated_by else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _display_order(row: ProductRow) -> tuple[bool, str, str]:
    """By name (products without one last), then barcode."""
    return (row.name is None, normalize(row.name or ""), row.barcode)


async def products(session: AsyncSession, rows: Sequence[ProductRow]) -> list[Product]:
    """The API view of `rows`, by name and barcode."""
    refs = await user_refs(
        session, [user for row in rows for user in (row.created_by, row.updated_by)]
    )
    return [product(row, refs) for row in sorted(rows, key=_display_order)]


def _barcode(text: str) -> str:
    barcode = normalize_barcode(text)
    if barcode is None:
        raise validation_error([FieldProblem(("body", "barcode"), FieldErrorCode.INVALID_FORMAT)])
    return barcode


def _check_basis(basis: str, ingredient: IngredientRow) -> None:
    if basis != ingredient.base_unit:
        raise ApiError(ErrorCode.PRODUCT_BASIS_MISMATCH, status_code=409)


def _nutrient_fields(values: NutrientValues | None, keys: Iterable[str]) -> list[str]:
    return [] if values is None else [f"nutrients.{key}" for key in keys]


def _created_edited_fields(body: ProductCreate) -> list[str]:
    """By hand: every field given (not null). From Open Food Facts: the fields the user
    changed compared with the proposal."""
    if body.source == "off":
        edited = set(body.edited_fields or ())
        return [field for field in PRODUCT_FIELDS if field in edited]
    given = body.model_dump(include=set(PRODUCT_DATA_FIELDS), exclude_none=True)
    nutrients = {} if body.nutrients is None else body.nutrients.model_dump()
    return [
        *(field for field in PRODUCT_DATA_FIELDS if field in given),
        *_nutrient_fields(
            body.nutrients, (key for key, value in nutrients.items() if value is not None)
        ),
    ]


async def create_product(
    session: AsyncSession, principal: Principal, body: ProductCreate, *, now: datetime
) -> Product:
    """Add a product by hand (`source` manual), or from an Open Food Facts proposal (`source`
    off, fetched now). The basis defaults to the ingredient's base unit; see
    `_created_edited_fields` for what is marked user-edited."""
    barcode = _barcode(body.barcode)
    async with session.begin():
        problems: list[FieldProblem] = []
        if await products_repo.barcode_taken(session, barcode):
            problems.append(FieldProblem(("body", "barcode"), FieldErrorCode.TAKEN))
        ingredient = await ingredients_repo.get(session, body.ingredient_id)
        if ingredient is None:
            problems.append(FieldProblem(("body", "ingredient_id"), FieldErrorCode.INVALID))
        if problems or ingredient is None:
            raise validation_error(problems)
        basis = body.nutrition_basis or ingredient.base_unit
        _check_basis(basis, ingredient)
        from_off = body.source == "off"
        nutrients = {} if body.nutrients is None else body.nutrients.model_dump()
        row = ProductRow(
            barcode=barcode,
            ingredient_id=ingredient.id,
            nutrition_basis=basis,
            name=body.name,
            brand=body.brand,
            quantity_text=body.quantity_text,
            pack_quantity=body.pack_quantity,
            pack_unit=None if body.pack_unit is None else body.pack_unit.value,
            source=body.source,
            off_last_modified_at=body.off_last_modified_at if from_off else None,
            fetched_at=now if from_off else None,
            user_edited_fields=_created_edited_fields(body),
            created_by=principal.user_id,
            updated_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        row.set_nutrients(NutrientValues().model_dump() | nutrients)
        session.add(row)
        await session.flush()
        return (await products(session, [row]))[0]


async def get_product(session: AsyncSession, product_id: str) -> Product:
    async with session.begin():
        row = await products_repo.get(session, product_id)
        if row is None:
            raise not_found()
        return (await products(session, [row]))[0]


async def update_product(
    session: AsyncSession,
    principal: Principal,
    product_id: str,
    body: ProductUpdate,
    *,
    now: datetime,
) -> Product:
    """Change the fields that were sent (null clears an optional one) and mark them
    user-edited (BAR-04). A new `ingredient_id` relinks the product; the basis must match the
    (new) ingredient's base unit."""
    sent = body.model_fields_set
    barcode = None if body.barcode is None else _barcode(body.barcode)
    async with session.begin():
        row = await products_repo.get(session, product_id)
        if row is None:
            raise not_found()
        problems: list[FieldProblem] = []
        if barcode is not None and await products_repo.barcode_taken(
            session, barcode, except_id=row.id
        ):
            problems.append(FieldProblem(("body", "barcode"), FieldErrorCode.TAKEN))
        ingredient = await ingredients_repo.get(session, body.ingredient_id or row.ingredient_id)
        if ingredient is None:
            problems.append(FieldProblem(("body", "ingredient_id"), FieldErrorCode.INVALID))
        if problems or ingredient is None:
            raise validation_error(problems)
        basis = body.nutrition_basis or row.nutrition_basis
        _check_basis(basis, ingredient)

        if barcode is not None:
            row.barcode = barcode
        row.ingredient_id = ingredient.id
        basis_changed = basis != row.nutrition_basis
        row.nutrition_basis = basis
        for field in _TEXT_AND_NUMBER_FIELDS:
            if field in sent:
                setattr(row, field, getattr(body, field))
        if "pack_unit" in sent:
            row.pack_unit = None if body.pack_unit is None else body.pack_unit.value
        nutrient_keys = (
            []
            if body.nutrients is None
            else [key for key in NUTRIENT_KEYS if key in body.nutrients.model_fields_set]
        )
        for key in nutrient_keys:
            row.set_nutrient(key, getattr(body.nutrients, key))
        edited = [field for field in PRODUCT_DATA_FIELDS if field in sent]
        edited += _nutrient_fields(body.nutrients, nutrient_keys)
        row.user_edited_fields = list(dict.fromkeys([*row.user_edited_fields, *edited]))
        if basis_changed:  # pending nutrients were per the old basis
            edited += [nutrient_field(key) for key in NUTRIENT_KEYS]
        _drop_pending(row, edited)
        row.updated_by = principal.user_id
        row.updated_at = now
        await session.flush()
        return (await products(session, [row]))[0]


def _drop_pending(row: ProductRow, fields: Iterable[str]) -> None:
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


async def _with_pending_update(session: AsyncSession, product_id: str) -> ProductRow:
    row = await products_repo.get(session, product_id)
    if row is None:
        raise not_found()
    if not pending_fields(row):
        raise ApiError(ErrorCode.PRODUCT_NO_PENDING_UPDATE, status_code=409)
    return row


async def apply_pending_update(
    session: AsyncSession, principal: Principal, product_id: str, *, now: datetime
) -> Product:
    """Take Open Food Facts' newer values for user-edited fields (BAR-06). They are Open Food
    Facts values again, so they are no longer user-edited and later refreshes update them."""
    async with session.begin():
        row = await _with_pending_update(session, product_id)
        proposed = pending_fields(row)
        for field, value in proposed.items():
            set_field_value(row, field, value)
        row.user_edited_fields = [
            field for field in row.user_edited_fields if field not in proposed
        ]
        row.pending_update = ignored_entries(row) or None
        row.updated_by = principal.user_id
        row.updated_at = now
        await session.flush()
        return (await products(session, [row]))[0]


async def ignore_pending_update(
    session: AsyncSession, principal: Principal, product_id: str, *, now: datetime
) -> Product:
    """Keep the user's values (BAR-06). The Open Food Facts version they came with is
    remembered, so a refresh proposes them again only after the product changes there; without
    a version, the ignored values are remembered instead (marked `IGNORED`), so a refresh
    proposes only other values."""
    async with session.begin():
        row = await _with_pending_update(session, product_id)
        row.ignored_off_modified_at = row.off_last_modified_at
        ignored = ignored_entries(row)
        if row.off_last_modified_at is None:
            stored: dict[str, Any] = row.pending_update or {}
            ignored |= {field: stored[field] | {IGNORED: True} for field in pending_fields(row)}
        row.pending_update = ignored or None
        row.updated_by = principal.user_id
        row.updated_at = now
        await session.flush()
        return (await products(session, [row]))[0]
