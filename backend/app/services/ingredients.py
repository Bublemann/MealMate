"""Ingredients: the shared wiki (ING-01..06) with their own nutrition (NUT-02), barcode and Open
Food Facts data (BAR-03..06), and the admin actions merge and delete (ING-05).

There is one kind of ingredient: typed by hand, with a brand, or created from an Open Food Facts
proposal (a scan or the name search) in one request. Names need not be unique (two brands of
"Milch" are two ingredients); the "similar ingredient exists" hint is only a hint. A barcode
belongs to at most one ingredient.

Everyone views and edits ingredients (plan § 5.5, `services.access`); merging and deleting need
an admin, which the API checks. Barcode uniqueness is checked inside the write transaction,
which holds the write lock (`BEGIN IMMEDIATE`).

On an ingredient from Open Food Facts (`source` off), every Open Food Facts field a user sets
(`OFF_FIELDS`: name, brand, pack, nutrients) is marked user-edited, so that a refresh
(`services.off_refresh`) never overwrites it; see `services.off_fields` for the pending update.

References from meals and lists go through `services.hooks`: `ingredient_references` blocks
deletion (and is shown as the usage), and `on_ingredients_merged` repoints them when merging.
"""

from collections.abc import Sequence
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
from app.domain.catalog import OFF_FIELDS, nutrient_field
from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.reference import OTHER_CATEGORY
from app.domain.similarity import SIMILAR_LIMIT, similar_names
from app.domain.text import normalize
from app.domain.units import NUTRITION_BASIS, BaseUnit, Unit
from app.models import Ingredient as IngredientRow
from app.repositories import ingredients as ingredients_repo
from app.repositories import reference as reference_repo
from app.schemas.admin import AdminAction
from app.schemas.ingredients import (
    BaseUnitName,
    Ingredient,
    IngredientBarcodeLink,
    IngredientCreate,
    IngredientSource,
    IngredientSummary,
    IngredientUpdate,
    IngredientUsage,
)
from app.schemas.nutrition import NutrientValues
from app.services import events, hooks, reference
from app.services.off_fields import (
    IGNORED,
    drop_pending,
    ignored_entries,
    pending_fields,
    pending_update,
    set_brand,
    set_field_value,
    set_name,
)
from app.services.principal import Principal
from app.services.users import user_refs

SEARCH_LIMIT = 1000
# Name-similar candidates looked at before those with the same name and brand are put first.
_SIMILAR_CANDIDATES = 50
# The plain fields of an update that are Open Food Facts fields (the others need more care).
_PLAIN_OFF_FIELDS = ("quantity_text", "pack_quantity")


def base_unit_name(value: str) -> BaseUnitName:
    match value:
        case "ml":
            return "ml"
        case "piece":
            return "piece"
        case _:
            return "g"


def source_name(value: str) -> IngredientSource:
    return "off" if value == "off" else "manual"


def summary(row: IngredientRow) -> IngredientSummary:
    return IngredientSummary(
        id=row.id,
        name=row.name,
        brand=row.brand,
        barcode=row.barcode,
        source=source_name(row.source),
        category_id=row.category_id,
        base_unit=base_unit_name(row.base_unit),
    )


async def detail(session: AsyncSession, row: IngredientRow) -> Ingredient:
    """The API view of an ingredient, with its usage and who created and changed it."""
    refs = await user_refs(session, [row.created_by, row.updated_by])
    usage = await hooks.ingredient_references(session, row.id)
    return Ingredient(
        id=row.id,
        name=row.name,
        brand=row.brand,
        barcode=row.barcode,
        category_id=row.category_id,
        base_unit=base_unit_name(row.base_unit),
        piece_weight_g=row.piece_weight_g,
        density_g_per_ml=row.density_g_per_ml,
        nutrients=NutrientValues.model_validate(row.nutrients()),
        quantity_text=row.quantity_text,
        pack_quantity=row.pack_quantity,
        pack_unit=None if row.pack_unit is None else Unit(row.pack_unit),
        source=source_name(row.source),
        user_edited_fields=[field for field in OFF_FIELDS if field in row.user_edited_fields],
        off_last_modified_at=row.off_last_modified_at,
        fetched_at=row.fetched_at,
        pending_update=pending_update(row),
        usage=IngredientUsage(meals=usage["meals"], lists=usage["lists"]),
        created_by=refs.get(row.created_by) if row.created_by else None,
        updated_by=refs.get(row.updated_by) if row.updated_by else None,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def canonical_barcode(text: str, loc: tuple[str, ...] = ("body", "barcode")) -> str:
    """The canonical barcode (`app.domain.barcodes`); 422 `invalid_format` if it is none."""
    barcode = normalize_barcode(text)
    if barcode is None:
        raise validation_error([FieldProblem(loc, FieldErrorCode.INVALID_FORMAT)])
    return barcode


async def _check_barcode_free(
    session: AsyncSession, barcode: str, *, except_id: str | None = None
) -> None:
    """409 `ingredient.barcode_taken` (with the other ingredient's id) if another ingredient
    has this barcode."""
    owner = await ingredients_repo.barcode_owner(session, barcode, except_id=except_id)
    if owner is not None:
        raise ApiError(
            ErrorCode.INGREDIENT_BARCODE_TAKEN, status_code=409, params={"ingredient_id": owner}
        )


async def _category_problem(
    session: AsyncSession, category_id: str, *, current: str | None = None
) -> FieldProblem | None:
    """A deleted category and *Uncategorized* can't be picked (ING-02); keeping the category an
    ingredient has is always fine, so an uncategorized one can be saved as it is."""
    if not await reference.can_pick(session, category_id, keeping=current):
        return FieldProblem(("body", "category_id"), FieldErrorCode.INVALID)
    return None


async def _other_category_id(session: AsyncSession) -> str:
    other = await reference_repo.category_by_key(session, OTHER_CATEGORY)
    if other is None:  # pragma: no cover -- seeded by migration 0003, never deleted (REF-01)
        raise RuntimeError("the 'other' category is missing")
    return other.id


async def search(
    session: AsyncSession, *, query: str | None, category_ids: Sequence[str]
) -> list[IngredientSummary]:
    """Search name and brand ignoring case, umlaut spelling and accents (ING-03): an exact
    name first, then names starting with the query, then the rest, each in dictionary order by
    name and brand. Without a query: every ingredient (at most 1000) in that order. With
    `category_ids`, only ingredients in any of those categories (UI-01, D-23)."""
    async with session.begin():
        rows = await ingredients_repo.search(
            session, query=normalize(query or ""), category_ids=category_ids, limit=SEARCH_LIMIT
        )
    return [summary(row) for row in rows]


async def similar(
    session: AsyncSession, name: str, brand: str | None = None
) -> list[IngredientSummary]:
    """Up to five ingredients with a name similar to `name` (the hint of ING-03); those with
    the same name and brand come first, as they are most likely the very same thing."""
    name_norm, brand_norm = normalize(name), normalize(brand or "") or None
    async with session.begin():
        ids = similar_names(
            name_norm, await ingredients_repo.names(session), limit=_SIMILAR_CANDIDATES
        )
        rows = await ingredients_repo.by_ids(session, ids)
    ranked = sorted(
        (rows[ingredient_id] for ingredient_id in ids),
        key=lambda row: not (row.name_norm == name_norm and row.brand_norm == brand_norm),
    )
    return [summary(row) for row in ranked[:SIMILAR_LIMIT]]


async def get_ingredient(session: AsyncSession, ingredient_id: str) -> Ingredient:
    async with session.begin():
        row = await ingredients_repo.get(session, ingredient_id)
        if row is None:
            raise not_found()
        return await detail(session, row)


async def create_ingredient(
    session: AsyncSession, principal: Principal, body: IngredientCreate, *, now: datetime
) -> Ingredient:
    """Add an ingredient (ING-02), by hand or from an Open Food Facts proposal (`off`, BAR-03):
    then `source` is off, it counts as fetched now, and only the fields the user changed
    compared with the proposal (`off.edited_fields`) are user-edited (BAR-04)."""
    barcode = None if body.barcode is None else canonical_barcode(body.barcode)
    from_off = body.off is not None
    async with session.begin():
        problems: list[FieldProblem] = []
        if from_off and barcode is None:
            problems.append(FieldProblem(("body", "barcode"), FieldErrorCode.REQUIRED))
        if body.category_id is not None and (
            problem := await _category_problem(session, body.category_id)
        ):
            problems.append(problem)
        if problems:
            raise validation_error(problems)
        if barcode is not None:
            await _check_barcode_free(session, barcode)
        edited = set(body.off.edited_fields) if body.off is not None else set()
        row = IngredientRow(
            barcode=barcode,
            category_id=body.category_id or await _other_category_id(session),
            base_unit=body.base_unit,
            piece_weight_g=body.piece_weight_g,
            density_g_per_ml=body.density_g_per_ml,
            quantity_text=body.quantity_text,
            pack_quantity=body.pack_quantity,
            pack_unit=None if body.pack_unit is None else body.pack_unit.value,
            source="off" if from_off else "manual",
            off_last_modified_at=body.off.off_last_modified_at if body.off is not None else None,
            fetched_at=now if from_off else None,
            user_edited_fields=[field for field in OFF_FIELDS if field in edited],
            created_by=principal.user_id,
            updated_by=principal.user_id,
            created_at=now,
            updated_at=now,
        )
        set_name(row, body.name)
        set_brand(row, body.brand)
        row.set_nutrients((body.nutrients or NutrientValues()).model_dump())
        session.add(row)
        await session.flush()
        return await detail(session, row)


def _nutrient_keys(values: NutrientValues | None) -> list[str]:
    """The nutrients an update sent, in registry order."""
    return (
        [] if values is None else [key for key in NUTRIENT_KEYS if key in values.model_fields_set]
    )


def _make_manual(row: IngredientRow) -> None:
    """Turn an ingredient from Open Food Facts whose barcode was cleared or changed into a
    manual one, with its values as they are. Without a barcode there is nothing to refresh it
    by; with another one, a refresh would fetch another product and overwrite the name, brand,
    pack and nutrients with its data. So its Open Food Facts data goes as well."""
    row.source = "manual"
    row.user_edited_fields = []
    row.pending_update = None
    row.ignored_off_modified_at = None
    row.off_last_modified_at = None
    row.fetched_at = None


async def update_ingredient(
    session: AsyncSession,
    principal: Principal,
    ingredient_id: str,
    body: IngredientUpdate,
    *,
    now: datetime,
) -> Ingredient:
    """Change the fields that were sent and record who changed it last (ING-01). On an
    ingredient from Open Food Facts, the Open Food Facts fields sent become user-edited and
    their pending values go (BAR-04, BAR-06); a base unit whose values are per 100 of something
    else (g or ml) drops the pending nutrients, and leaving `piece` clears the piece weight
    unless one is sent along (ING-02). Clearing or changing the barcode makes it a manual ingredient
    (`_make_manual`)."""
    sent = body.model_fields_set
    barcode = None if body.barcode is None else canonical_barcode(body.barcode)
    async with session.begin():
        row = await ingredients_repo.get(session, ingredient_id)
        if row is None:
            raise not_found()
        if body.category_id is not None and (
            problem := await _category_problem(session, body.category_id, current=row.category_id)
        ):
            raise validation_error([problem])
        if barcode is not None:
            await _check_barcode_free(session, barcode, except_id=row.id)

        edited: list[str] = []
        if body.name is not None:
            set_name(row, body.name)
            edited.append("name")
        if "brand" in sent:
            set_brand(row, body.brand)
            edited.append("brand")
        for field in _PLAIN_OFF_FIELDS:
            if field in sent:
                setattr(row, field, getattr(body, field))
                edited.append(field)
        if "pack_unit" in sent:
            row.pack_unit = None if body.pack_unit is None else body.pack_unit.value
            edited.append("pack_unit")
        for key in _nutrient_keys(body.nutrients):
            row.set_nutrient(key, getattr(body.nutrients, key))
            edited.append(nutrient_field(key))
        if body.category_id is not None:
            row.category_id = body.category_id
        decided = list(edited)
        if body.base_unit is not None and body.base_unit != row.base_unit:
            old, new = BaseUnit(row.base_unit), BaseUnit(body.base_unit)
            if old == BaseUnit.PIECE:
                row.piece_weight_g = None
            if NUTRITION_BASIS[old] != NUTRITION_BASIS[new]:
                decided += [nutrient_field(key) for key in NUTRIENT_KEYS]
            row.base_unit = body.base_unit
        if "piece_weight_g" in sent:
            row.piece_weight_g = body.piece_weight_g
        if "density_g_per_ml" in sent:
            row.density_g_per_ml = body.density_g_per_ml
        if "barcode" in sent and barcode != row.barcode:
            row.barcode = barcode
            if row.source == "off":
                _make_manual(row)
        if row.source == "off":
            row.user_edited_fields = [
                field for field in OFF_FIELDS if field in {*row.user_edited_fields, *edited}
            ]
            drop_pending(row, decided)
        row.updated_by = principal.user_id
        row.updated_at = now
        await session.flush()
        return await detail(session, row)


async def link_barcode(
    session: AsyncSession,
    principal: Principal,
    ingredient_id: str,
    body: IngredientBarcodeLink,
    *,
    now: datetime,
) -> Ingredient:
    """Give an ingredient without a barcode the scanned one (the scanner's "already in
    MealMate", BAR-03). The server refuses to replace a barcode (409 `ingredient.has_barcode`):
    the picker offers only ingredients without one, but the list may be stale, and replacing
    it here would silently take the barcode from what the user scanned before. The ingredient
    stays manual; it has no Open Food Facts data to refresh."""
    barcode = canonical_barcode(body.barcode)
    async with session.begin():
        row = await ingredients_repo.get(session, ingredient_id)
        if row is None:
            raise not_found()
        if row.barcode is not None:
            raise ApiError(ErrorCode.INGREDIENT_HAS_BARCODE, status_code=409)
        await _check_barcode_free(session, barcode)
        row.barcode = barcode
        row.updated_by = principal.user_id
        row.updated_at = now
        await session.flush()
        return await detail(session, row)


async def _with_pending_update(session: AsyncSession, ingredient_id: str) -> IngredientRow:
    row = await ingredients_repo.get(session, ingredient_id)
    if row is None:
        raise not_found()
    if not pending_fields(row):
        raise ApiError(ErrorCode.INGREDIENT_NO_PENDING_UPDATE, status_code=409)
    return row


async def apply_pending_update(
    session: AsyncSession, principal: Principal, ingredient_id: str, *, now: datetime
) -> Ingredient:
    """Take Open Food Facts' newer values for user-edited fields (BAR-06). They are Open Food
    Facts values again, so they are no longer user-edited and later refreshes update them."""
    async with session.begin():
        row = await _with_pending_update(session, ingredient_id)
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
        return await detail(session, row)


async def ignore_pending_update(
    session: AsyncSession, principal: Principal, ingredient_id: str, *, now: datetime
) -> Ingredient:
    """Keep the user's values (BAR-06). The Open Food Facts version they came with is
    remembered, so a refresh proposes them again only after the product changes there; without
    a version, the ignored values are remembered instead (marked `IGNORED`), so a refresh
    proposes only other values."""
    async with session.begin():
        row = await _with_pending_update(session, ingredient_id)
        row.ignored_off_modified_at = row.off_last_modified_at
        ignored = ignored_entries(row)
        if row.off_last_modified_at is None:
            stored: dict[str, Any] = row.pending_update or {}
            ignored |= {field: stored[field] | {IGNORED: True} for field in pending_fields(row)}
        row.pending_update = ignored or None
        row.updated_by = principal.user_id
        row.updated_at = now
        await session.flush()
        return await detail(session, row)


async def merge(
    session: AsyncSession, actor: Principal, ingredient_id: str, into_id: str, *, now: datetime
) -> Ingredient:
    """Merge a duplicate into another ingredient (ING-05, admins): every meal and list reference
    moves to `into_id`, then the duplicate is deleted. The target keeps its own attributes and
    values and records the admin as the one who changed it last.

    The duplicate's barcode moves to the target if the target has none (only the barcode: the
    target's values, source and Open Food Facts data stay); otherwise it is dropped with the
    duplicate, as one ingredient has one barcode.
    """
    if into_id == ingredient_id:
        raise validation_error([FieldProblem(("body", "into_id"), FieldErrorCode.INVALID)])
    async with session.begin():
        source = await ingredients_repo.get(session, ingredient_id)
        if source is None:
            raise not_found()
        target = await ingredients_repo.get(session, into_id)
        if target is None:
            raise validation_error([FieldProblem(("body", "into_id"), FieldErrorCode.INVALID)])
        if source.barcode is not None and target.barcode is None:
            barcode, source.barcode = source.barcode, None
            await session.flush()  # the barcode is unique: free it before the target takes it
            target.barcode = barcode
        await hooks.on_ingredients_merged(session, source.id, target.id, now=now)
        target.updated_by = actor.user_id
        target.updated_at = now
        events.record(
            session,
            actor_id=actor.user_id,
            action=AdminAction.INGREDIENT_MERGE,
            target_user_id=None,
            now=now,
            details={"from_name": source.name, "into_name": target.name},
        )
        await session.delete(source)
        await session.flush()
        return await detail(session, target)


async def delete(
    session: AsyncSession, actor: Principal, ingredient_id: str, *, now: datetime
) -> None:
    """Delete an ingredient nothing refers to (ING-05, admins); otherwise 409
    `ingredient.in_use` with the number of references per kind."""
    async with session.begin():
        row = await ingredients_repo.get(session, ingredient_id)
        if row is None:
            raise not_found()
        references = await hooks.ingredient_references(session, row.id)
        if any(references.values()):
            raise ApiError(ErrorCode.INGREDIENT_IN_USE, status_code=409, params=references)
        events.record(
            session,
            actor_id=actor.user_id,
            action=AdminAction.INGREDIENT_DELETE,
            target_user_id=None,
            now=now,
            details={"name": row.name},
        )
        await hooks.before_ingredient_deleted(session, row.id)
        await session.delete(row)
