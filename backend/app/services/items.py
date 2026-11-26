"""Items: the shared wiki (ING-01..06) with their own nutrition (NUT-02), barcode and Open
Food Facts data (BAR-03..06), and the admin actions merge and delete (ING-05).

An item is typed by hand, with a brand, or created from an Open Food Facts proposal (a scan or
the name search) in one request. It is food or a supply (D-55): a supply holds no nutrients and
no piece weight (`_nutrient_problems`, `_piece_weight_problem`, `_make_supply`), and no meal
uses it as an ingredient (`_check_not_in_meals`, `services.meals`); Open Food Facts never sets
the kind, and a refresh leaves a supply's nutrients alone (`services.off_refresh`). Names need
not be unique (two brands of "Milch" are two items); the "similar item exists" hint is only a
hint. A barcode belongs to at most one item.

Everyone views and edits items (plan § 5.5, `services.access`); merging and deleting need
an admin, which the API checks. Barcode uniqueness is checked inside the write transaction,
which holds the write lock (`BEGIN IMMEDIATE`).

On an item from Open Food Facts (`source` off), every Open Food Facts field a user sets
(`OFF_FIELDS`: name, brand, nutrients) is marked user-edited, so that a refresh
(`services.off_refresh`) never overwrites it; see `services.off_fields` for the pending update.

References from meals and lists go through `services.hooks`: `item_references` blocks
deletion (and is shown as the usage), and `on_items_merged` repoints them when merging.
Recurring items (LIST-16) are no references: a merge moves them, and a deletion removes them
after `before_item_deleted` has left their users a notice (D-51).
A base-unit change or a merge that would leave amounts not fitting (`amounts_that_would_not_fit`)
asks first (`_check_amounts_fit`, D-33).

Since D-32 an item has no density, and a piece weight only when it is counted in pieces:
migration 0014 dropped the density and cleared the piece weight of g and ml items (D-34).
A piece weight on a g or ml item would still never be shown, taken or used to calculate
(`attrs()`).
"""

from collections.abc import Callable, Sequence
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
from app.domain.catalog import FOOD, OFF_FIELDS, SUPPLY, nutrient_field
from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.reference import OTHER_CATEGORY
from app.domain.similarity import SIMILAR_LIMIT, similar_names
from app.domain.text import normalize, same_name
from app.domain.units import NUTRITION_BASIS, BaseUnit, fits, stops_fitting
from app.models import Item as ItemRow
from app.repositories import items as items_repo
from app.repositories import meals as meals_repo
from app.repositories import reference as reference_repo
from app.schemas.admin import AdminAction
from app.schemas.items import (
    Item,
    ItemBarcodeLink,
    ItemCreate,
    ItemKind,
    ItemMerge,
    ItemSearchResult,
    ItemSource,
    ItemSummary,
    ItemUpdate,
    ItemUsage,
    base_unit_name,
    kind_name,
)
from app.schemas.nutrition import NutrientValues
from app.services import access, events, hooks, reference
from app.services.off_fields import (
    IGNORED,
    drop_pending,
    edited_fields,
    ignored_entries,
    pending_fields,
    pending_update,
    set_brand,
    set_field_value,
    set_name,
    unmark_edited,
)
from app.services.principal import Principal
from app.services.users import user_refs

SEARCH_LIMIT = 1000
# Name-similar candidates looked at before those with the same name and brand are put first.
_SIMILAR_CANDIDATES = 50


def source_name(value: str) -> ItemSource:
    return "off" if value == "off" else "manual"


def summary(row: ItemRow) -> ItemSummary:
    return ItemSummary(
        id=row.id,
        name=row.name,
        brand=row.brand,
        barcode=row.barcode,
        source=source_name(row.source),
        kind=kind_name(row.kind),
        category_id=row.category_id,
        base_unit=base_unit_name(row.base_unit),
    )


async def detail(session: AsyncSession, row: ItemRow) -> Item:
    """The API view of an item, with its usage and who created and changed it."""
    refs = await user_refs(session, [row.created_by, row.updated_by])
    usage = await hooks.item_references(session, row.id)
    return Item(
        id=row.id,
        name=row.name,
        brand=row.brand,
        barcode=row.barcode,
        kind=kind_name(row.kind),
        category_id=row.category_id,
        base_unit=base_unit_name(row.base_unit),
        piece_weight_g=row.attrs().piece_weight_g,
        nutrients=NutrientValues.model_validate(row.nutrients()),
        source=source_name(row.source),
        user_edited_fields=edited_fields(row),
        off_last_modified_at=row.off_last_modified_at,
        fetched_at=row.fetched_at,
        pending_update=pending_update(row),
        usage=ItemUsage(meals=usage["meals"], lists=usage["lists"]),
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
    """409 `item.barcode_taken` (with the other item's id) if another item
    has this barcode."""
    owner = await items_repo.barcode_owner(session, barcode, except_id=except_id)
    if owner is not None:
        raise ApiError(ErrorCode.ITEM_BARCODE_TAKEN, status_code=409, params={"item_id": owner})


async def _check_amounts_fit(
    session: AsyncSession,
    item_id: str,
    would_not_fit: Callable[[float | None, str | None], bool],
    *,
    accepted: bool | None,
) -> None:
    """409 `item.unit_mismatch`, with the counts of `hooks.amounts_that_would_not_fit`,
    while amounts of the item `would_not_fit` after the change and the request hasn't
    `accepted` that (D-33). Nothing is ever converted."""
    if accepted:
        return
    counts = await hooks.amounts_that_would_not_fit(session, item_id, would_not_fit)
    if counts["amounts"]:
        raise ApiError(ErrorCode.ITEM_UNIT_MISMATCH, status_code=409, params=counts)


def _piece_weight_problem(
    piece_weight_g: float | None, base_unit: str, kind: str
) -> FieldProblem | None:
    """Only food counted in pieces takes a piece weight (ING-02, D-32, D-55)."""
    if piece_weight_g is not None and (base_unit != BaseUnit.PIECE or kind == SUPPLY):
        return FieldProblem(("body", "piece_weight_g"), FieldErrorCode.INVALID)
    return None


def _nutrient_problems(kind: str, nutrients: NutrientValues | None) -> list[FieldProblem]:
    """A supply takes no nutrient value; a null one is fine (D-55)."""
    if kind != SUPPLY:
        return []
    return [
        FieldProblem(("body", "nutrients", key), FieldErrorCode.INVALID)
        for key in _nutrient_keys(nutrients)
        if getattr(nutrients, key) is not None
    ]


async def _check_not_in_meals(session: AsyncSession, principal: Principal, item_id: str) -> None:
    """409 `item.used_in_meals` while any meal uses the item, which a supply can't be in
    (D-55): it counts them and names those the user may see, so that someone else's private
    meal is only counted (VIS-02)."""
    meals = await meals_repo.with_item(session, item_id)
    if not meals:
        return
    visible = await access.visible_owner_ids(session, principal.user_id, "meals")
    names = [name for owner_id, name in meals if owner_id in visible]
    raise ApiError(
        ErrorCode.ITEM_USED_IN_MEALS, status_code=409, params={"meals": len(meals), "names": names}
    )


def _make_supply(row: ItemRow) -> None:
    """A supply has no nutrients and no piece weight (D-55): they go, and with them their
    marks and pending Open Food Facts values, which no longer apply."""
    row.kind = SUPPLY
    row.piece_weight_g = None
    row.set_nutrients(dict.fromkeys(NUTRIENT_KEYS))
    nutrient_fields = [nutrient_field(key) for key in NUTRIENT_KEYS]
    row.user_edited_fields = [
        field for field in row.user_edited_fields if field not in nutrient_fields
    ]
    drop_pending(row, nutrient_fields)


async def _category_problem(
    session: AsyncSession, category_id: str, *, current: str | None = None
) -> FieldProblem | None:
    """A deleted category and *Uncategorized* can't be picked (ING-02); keeping the category an
    item has is always fine, so an uncategorized one can be saved as it is."""
    if not await reference.can_pick(session, category_id, keeping=current):
        return FieldProblem(("body", "category_id"), FieldErrorCode.INVALID)
    return None


async def _other_category_id(session: AsyncSession) -> str:
    other = await reference_repo.category_by_key(session, OTHER_CATEGORY)
    if other is None:  # pragma: no cover -- seeded by migration 0003, never deleted (REF-01)
        raise RuntimeError("the 'other' category is missing")
    return other.id


async def search(
    session: AsyncSession,
    *,
    query: str | None,
    category_ids: Sequence[str],
    kind: ItemKind | None = None,
) -> list[ItemSearchResult]:
    """Search name and brand ignoring case, umlaut spelling and accents (ING-03): an exact
    name first, then names starting with the query, then the rest, each in dictionary order by
    name and brand. The exact names are marked (D-41). Without a query: every item (at
    most 1000) in that order. With `category_ids`, only items in any of those categories
    (UI-01, D-23). With `kind`, only items of that kind (D-55)."""
    query_norm = normalize(query or "")
    async with session.begin():
        rows = await items_repo.search(
            session, query=query_norm, category_ids=category_ids, kind=kind, limit=SEARCH_LIMIT
        )
    return [
        ItemSearchResult(**summary(row).model_dump(), exact=same_name(row.name_norm, query_norm))
        for row in rows
    ]


async def similar(session: AsyncSession, name: str, brand: str | None = None) -> list[ItemSummary]:
    """Up to five items with a name similar to `name` (the hint of ING-03); those with
    the same name and brand come first, as they are most likely the very same thing."""
    name_norm, brand_norm = normalize(name), normalize(brand or "") or None
    async with session.begin():
        ids = similar_names(name_norm, await items_repo.names(session), limit=_SIMILAR_CANDIDATES)
        rows = await items_repo.by_ids(session, ids)
    ranked = sorted(
        (rows[item_id] for item_id in ids),
        key=lambda row: not (row.name_norm == name_norm and row.brand_norm == brand_norm),
    )
    return [summary(row) for row in ranked[:SIMILAR_LIMIT]]


async def get_item(session: AsyncSession, item_id: str) -> Item:
    async with session.begin():
        row = await items_repo.get(session, item_id)
        if row is None:
            raise not_found()
        return await detail(session, row)


async def create_item(
    session: AsyncSession, principal: Principal, body: ItemCreate, *, now: datetime
) -> Item:
    """Add an item (ING-02), by hand or from an Open Food Facts proposal (`off`, BAR-03):
    then `source` is off, it counts as fetched now, and only the fields the user changed compared
    with the proposal (`off.edited_fields`) are user-edited (BAR-04). It is food unless the request
    makes it a supply, which takes no nutrient value and no piece weight (D-55)."""
    barcode = None if body.barcode is None else canonical_barcode(body.barcode)
    from_off = body.off is not None
    kind = body.kind or FOOD
    async with session.begin():
        problems: list[FieldProblem] = []
        if from_off and barcode is None:
            problems.append(FieldProblem(("body", "barcode"), FieldErrorCode.REQUIRED))
        if problem := _piece_weight_problem(body.piece_weight_g, body.base_unit, kind):
            problems.append(problem)
        problems.extend(_nutrient_problems(kind, body.nutrients))
        if body.category_id is not None and (
            problem := await _category_problem(session, body.category_id)
        ):
            problems.append(problem)
        if problems:
            raise validation_error(problems)
        if barcode is not None:
            await _check_barcode_free(session, barcode)
        edited = set(body.off.edited_fields) if body.off is not None else set()
        if kind == SUPPLY:  # it has no nutrients to keep from a refresh (D-55)
            edited -= {nutrient_field(key) for key in NUTRIENT_KEYS}
        row = ItemRow(
            barcode=barcode,
            category_id=body.category_id or await _other_category_id(session),
            kind=kind,
            base_unit=body.base_unit,
            piece_weight_g=body.piece_weight_g,
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


def _make_manual(row: ItemRow) -> None:
    """Turn an item from Open Food Facts whose barcode was cleared or changed into a
    manual one, with its values as they are. Without a barcode there is nothing to refresh it
    by; with another one, a refresh would fetch another product and overwrite the name, brand,
    and nutrients with its data. So its Open Food Facts data goes as well."""
    row.source = "manual"
    row.user_edited_fields = []
    row.pending_update = None
    row.ignored_off_modified_at = None
    row.off_last_modified_at = None
    row.fetched_at = None


async def update_item(
    session: AsyncSession,
    principal: Principal,
    item_id: str,
    body: ItemUpdate,
    *,
    now: datetime,
) -> Item:
    """Change the fields that were sent and record who changed it last (ING-01). On an
    item from Open Food Facts, the Open Food Facts fields sent become user-edited and
    their pending values go (BAR-04, BAR-06); a base unit whose values are per 100 of something
    else (g or ml) drops the pending nutrients, and a change to or from `piece` clears the piece
    weight unless one is sent along to `piece` (ING-02). A piece weight is refused unless the
    item is, or becomes, counted in pieces; a null one is ignored then. A base-unit change
    that would leave amounts that fit now not fitting (`stops_fitting`) changes nothing unless
    the request accepts that (D-33). Clearing or changing the barcode makes it a manual
    item (`_make_manual`). A supply takes no nutrient value and no piece weight; switching to
    supply is refused while meals use the item and clears both (`_make_supply`, D-55)."""
    sent = body.model_fields_set
    barcode = None if body.barcode is None else canonical_barcode(body.barcode)
    async with session.begin():
        row = await items_repo.get(session, item_id)
        if row is None:
            raise not_found()
        base_unit = body.base_unit or row.base_unit
        kind = body.kind or row.kind
        problems: list[FieldProblem] = []
        if body.category_id is not None and (
            problem := await _category_problem(session, body.category_id, current=row.category_id)
        ):
            problems.append(problem)
        if problem := _piece_weight_problem(body.piece_weight_g, base_unit, kind):
            problems.append(problem)
        problems.extend(_nutrient_problems(kind, body.nutrients))
        if problems:
            raise validation_error(problems)
        if barcode is not None:
            await _check_barcode_free(session, barcode, except_id=row.id)
        to_supply = kind == SUPPLY and row.kind != SUPPLY
        if to_supply:
            await _check_not_in_meals(session, principal, row.id)
        if base_unit != row.base_unit:
            before = row.base_unit
            await _check_amounts_fit(
                session,
                row.id,
                lambda amount, unit: stops_fitting(amount, unit, before, base_unit),
                accepted=body.accept_unit_mismatch,
            )

        edited: list[str] = []
        if body.name is not None:
            set_name(row, body.name)
            edited.append("name")
        if "brand" in sent:
            set_brand(row, body.brand)
            edited.append("brand")
        # A supply's nutrients stay unknown, so its null ones are not the user's (D-55).
        sent_nutrients = [] if kind == SUPPLY else _nutrient_keys(body.nutrients)
        for key in sent_nutrients:
            row.set_nutrient(key, getattr(body.nutrients, key))
            edited.append(nutrient_field(key))
        if body.category_id is not None:
            row.category_id = body.category_id
        decided = list(edited)
        if body.base_unit is not None and body.base_unit != row.base_unit:
            old, new = BaseUnit(row.base_unit), BaseUnit(body.base_unit)
            # Leaving pieces drops the piece weight; coming to pieces takes only one sent along,
            # never a hidden one of a g or ml item (none since migration 0014, D-34).
            if BaseUnit.PIECE in (old, new):
                row.piece_weight_g = None
            if NUTRITION_BASIS[old] != NUTRITION_BASIS[new]:
                decided += [nutrient_field(key) for key in NUTRIENT_KEYS]
            row.base_unit = body.base_unit
        if "piece_weight_g" in sent and base_unit == BaseUnit.PIECE:
            row.piece_weight_g = body.piece_weight_g
        if "barcode" in sent and barcode != row.barcode:
            row.barcode = barcode
            if row.source == "off":
                _make_manual(row)
        if row.source == "off":
            row.user_edited_fields = [
                *row.user_edited_fields,
                *(field for field in edited if field not in row.user_edited_fields),
            ]
            drop_pending(row, decided)
        if to_supply:
            _make_supply(row)
        else:
            row.kind = kind
        row.updated_by = principal.user_id
        row.updated_at = now
        await session.flush()
        return await detail(session, row)


async def link_barcode(
    session: AsyncSession,
    principal: Principal,
    item_id: str,
    body: ItemBarcodeLink,
    *,
    now: datetime,
) -> Item:
    """Give an item without a barcode the scanned one (the scanner's "already in
    MealMate", BAR-03). The server refuses to replace a barcode (409 `item.has_barcode`):
    the picker offers only items without one, but the list may be stale, and replacing
    it here would silently take the barcode from what the user scanned before. The item
    stays manual; it has no Open Food Facts data to refresh."""
    barcode = canonical_barcode(body.barcode)
    async with session.begin():
        row = await items_repo.get(session, item_id)
        if row is None:
            raise not_found()
        if row.barcode is not None:
            raise ApiError(ErrorCode.ITEM_HAS_BARCODE, status_code=409)
        await _check_barcode_free(session, barcode)
        row.barcode = barcode
        row.updated_by = principal.user_id
        row.updated_at = now
        await session.flush()
        return await detail(session, row)


async def _with_pending_update(session: AsyncSession, item_id: str) -> ItemRow:
    row = await items_repo.get(session, item_id)
    if row is None:
        raise not_found()
    if not pending_fields(row):
        raise ApiError(ErrorCode.ITEM_NO_PENDING_UPDATE, status_code=409)
    return row


async def apply_pending_update(
    session: AsyncSession, principal: Principal, item_id: str, *, now: datetime
) -> Item:
    """Take Open Food Facts' newer values for user-edited fields (BAR-06). They are Open Food
    Facts values again, so they are no longer user-edited and later refreshes update them."""
    async with session.begin():
        row = await _with_pending_update(session, item_id)
        proposed = pending_fields(row)
        for field, value in proposed.items():
            set_field_value(row, field, value)
        unmark_edited(row, proposed)
        row.pending_update = ignored_entries(row) or None
        row.updated_by = principal.user_id
        row.updated_at = now
        await session.flush()
        return await detail(session, row)


async def ignore_pending_update(
    session: AsyncSession, principal: Principal, item_id: str, *, now: datetime
) -> Item:
    """Keep the user's values (BAR-06). The Open Food Facts version they came with is
    remembered, so a refresh proposes them again only after the product changes there; without
    a version, the ignored values are remembered instead (marked `IGNORED`), so a refresh
    proposes only other values."""
    async with session.begin():
        row = await _with_pending_update(session, item_id)
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
    session: AsyncSession,
    actor: Principal,
    item_id: str,
    body: ItemMerge,
    *,
    now: datetime,
) -> Item:
    """Merge a duplicate into another item (ING-05, admins): every meal and list reference
    moves to `into_id`, then the duplicate is deleted. The target keeps its own attributes and
    values and records the admin as the one who changed it last. When their base units differ,
    amounts of the duplicate that won't fit the target's are kept as they are; while there are
    any, nothing is merged unless the request accepts that (D-33). Nothing is merged into a
    supply while meals use the duplicate (D-55).

    The duplicate's barcode moves to the target if the target has none (only the barcode: the
    target's values, source and Open Food Facts data stay); otherwise it is dropped with the
    duplicate, as one item has one barcode.
    """
    into_id = body.into_id
    if into_id == item_id:
        raise validation_error([FieldProblem(("body", "into_id"), FieldErrorCode.INVALID)])
    async with session.begin():
        source = await items_repo.get(session, item_id)
        if source is None:
            raise not_found()
        target = await items_repo.get(session, into_id)
        if target is None:
            raise validation_error([FieldProblem(("body", "into_id"), FieldErrorCode.INVALID)])
        if target.kind == SUPPLY:
            await _check_not_in_meals(session, actor, source.id)
        if source.base_unit != target.base_unit:
            into_base_unit = target.base_unit
            await _check_amounts_fit(
                session,
                source.id,
                lambda amount, unit: not fits(amount, unit, into_base_unit),
                accepted=body.accept_unit_mismatch,
            )
        if source.barcode is not None and target.barcode is None:
            barcode, source.barcode = source.barcode, None
            await session.flush()  # the barcode is unique: free it before the target takes it
            target.barcode = barcode
        await hooks.on_items_merged(session, source.id, target.id, now=now)
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


async def delete(session: AsyncSession, actor: Principal, item_id: str, *, now: datetime) -> None:
    """Delete an item nothing refers to (ING-05, admins); otherwise 409
    `item.in_use` with the number of references per kind."""
    async with session.begin():
        row = await items_repo.get(session, item_id)
        if row is None:
            raise not_found()
        references = await hooks.item_references(session, row.id)
        if any(references.values()):
            raise ApiError(ErrorCode.ITEM_IN_USE, status_code=409, params=references)
        events.record(
            session,
            actor_id=actor.user_id,
            action=AdminAction.INGREDIENT_DELETE,
            target_user_id=None,
            now=now,
            details={"name": row.name},
        )
        await hooks.before_item_deleted(session, row.id, now=now)
        await session.delete(row)
