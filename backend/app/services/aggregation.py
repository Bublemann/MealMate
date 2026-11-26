"""The aggregation service: the lines of a list from its meals and extra items, with their
check state (AGG, LIST-05..08, LIST-11/12, LIST-15, plan §§ 5.6 and 5.7).

It only turns the list's content into `Part`s and lets `domain.aggregation` group, total, round
and sort them and tell whether a checked line needs more; no amounts are calculated here or in
the frontend (AGG-01).

1. A live list meal (`frozen_at` null) contributes the meal's current rows with the live
   item attributes (`Item.attrs()`: no density, a piece weight only for pieces,
   D-32); a frozen or detached one its `list_meal_ingredients` with the attributes captured
   then, which before D-32 included a density and a g or ml item's piece weight (LIST-11).
   Each row is scaled by `servings ÷ meal servings` (LIST-04). A leftover meal (LIST-17) is
   frozen without rows, so it contributes nothing.
2. A linked extra item contributes to its item's line with its `attrs_snapshot` once it
   has one (taken when shopping starts or when it is added while shopping), else with the live
   attributes. A free-text item is a line of its own, `x:<id>`, without amounts: its
   `amount_text` is shown as it is.
3. In a draft, an item line shows the live item's name, brand and category; a line
   that only detached meals make keeps the category they were frozen with, a deleted one
   included (REF-01, LIST-15). Once shopping started, a line shows the name, brand and category
   of the first of its parts with a snapshot (frozen rows in the order of the meals, then extra
   items), so item edits no longer change the list (LIST-11).
   Two brands of the same thing are two items and so two lines. A free-text line shows
   its text and category. Lines are sorted by category order, then normalised name and brand,
   then key (AGG-05), and carry their hidden state (LIST-07). The category order is the
   viewer's walking order (REF-01, D-48): the admins' or their couple's own. A deleted category
   keeps its last position in it (D-30), so a tie goes to the category that isn't deleted, then
   by category id.
4. Outside a draft, lines carry their check state (plan § 5.7): a line without a stored state
   is `new` while shopping; a checked line that needs more since it was checked (or a free-text
   item that was edited) is reported unchecked, with the reason (LIST-12). Nothing is stored
   for that: checking it again replaces its snapshot.

Everything is loaded in batches for any number of lists (`load`), so reading a list or the
summaries of many takes a fixed number of queries.
"""

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregation import (
    CheckSnapshot,
    Line,
    LineTotals,
    Part,
    SourceRef,
    aggregate,
    grown_display,
    needs_more,
    text_changed,
)
from app.domain.lists import ITEM_KEY_PREFIX, TEXT_KEY_PREFIX, item_key, text_key
from app.domain.reference import OTHER_CATEGORY
from app.domain.text import normalize
from app.domain.units import BaseUnit, ItemAttrs, Unit
from app.domain.walking_order import WalkingOrder
from app.models import (
    Category,
    Item,
    ListExtraItem,
    ListLineState,
    ListMeal,
    ListMealIngredient,
    Meal,
    MealIngredient,
    ShoppingList,
)
from app.repositories import items as items_repo
from app.repositories import lists as lists_repo
from app.repositories import meals as meals_repo
from app.repositories import reference as reference_repo
from app.schemas.lists import DisplayAmountOut, LineNeedsMore, LineSource, ListLine
from app.schemas.users import UserRef


@dataclass(frozen=True)
class ListContent:
    """Everything the lines of some lists are computed from.

    `meals`, `extras` (not deleted) and `states` are per list id; `meals` holds only the
    leftovers that are shown (see `shown_meals`), and `sources` their source meals by id;
    `linked_meals` per meal id (the meals list meals still link to, frozen or not); `meal_rows`
    per meal id (live list meals only); `frozen_rows` per list meal id; `items` only those whose
    live data is used (see `load`).
    """

    meals: dict[str, list[ListMeal]]
    sources: dict[str, ListMeal]
    linked_meals: dict[str, Meal]
    meal_rows: dict[str, list[MealIngredient]]
    frozen_rows: dict[str, list[ListMealIngredient]]
    extras: dict[str, list[ListExtraItem]]
    items: dict[str, Item]
    categories: dict[str, Category]
    states: dict[str, dict[str, ListLineState]]

    def live_meal(self, list_meal: ListMeal) -> Meal | None:
        """The meal a live list meal takes its rows from; None once it is frozen."""
        if list_meal.frozen_at is not None:
            return None
        return self.linked_meal(list_meal)

    def linked_meal(self, list_meal: ListMeal) -> Meal | None:
        """The meal a list meal still links to (live or frozen); None once it is detached."""
        return None if list_meal.meal_id is None else self.linked_meals.get(list_meal.meal_id)

    def eaten(self, list_meal: ListMeal) -> bool:
        """Whether the meal is eaten: a leftover is when its source is (LIST-17)."""
        if list_meal.leftover_of_id is None:
            return list_meal.eaten
        return self.sources[list_meal.leftover_of_id].eaten

    def other_category_id(self) -> str:
        return next(row.id for row in self.categories.values() if row.key == OTHER_CATEGORY)


def is_live(list_meal: ListMeal) -> bool:
    return list_meal.frozen_at is None and list_meal.meal_id is not None


async def shown_meals(
    session: AsyncSession, lists: Iterable[ShoppingList]
) -> tuple[dict[str, list[ListMeal]], dict[str, ListMeal]]:
    """The meals of the lists, per list id, and the source meals of their leftovers by id.

    A leftover whose source is eaten is left out of drafts and lists being shopped (it has left
    them, LIST-17); a done list shows it, eaten, as it shows its other eaten meals."""
    status = {row.id: row.status for row in lists}
    meals = await lists_repo.meals_for(session, status)
    sources = await lists_repo.meals_by_ids(
        session,
        (row.leftover_of_id for group in meals.values() for row in group if row.leftover_of_id),
    )
    shown = {
        list_id: [
            row
            for row in group
            if row.leftover_of_id is None
            or status[list_id] == "done"
            or not sources[row.leftover_of_id].eaten
        ]
        for list_id, group in meals.items()
    }
    return shown, sources


async def load(session: AsyncSession, lists: Iterable[ShoppingList]) -> ListContent:
    """The content of the given lists, in nine queries whatever their size.

    Items are loaded only where their live data is shown: for live meals, linked extra
    items without a snapshot, and the frozen rows of drafts (a detached meal's line shows the
    live name there); a list that is shopped or done needs none of them (LIST-11).
    """
    lists = list(lists)
    ids = {row.id for row in lists}
    drafts = {row.id for row in lists if row.status == "draft"}
    meals, sources = await shown_meals(session, lists)
    list_meals = [list_meal for group in meals.values() for list_meal in group]
    linked_meals = await meals_repo.by_ids(session, (row.meal_id for row in list_meals))
    live_ids = {list_meal.meal_id for list_meal in list_meals if is_live(list_meal)}
    meal_rows = await meals_repo.rows_for(
        session, (meal_id for meal_id in linked_meals if meal_id in live_ids)
    )
    frozen_rows = await lists_repo.frozen_rows_for(
        session, (list_meal.id for list_meal in list_meals if not is_live(list_meal))
    )
    extras = await lists_repo.extras_for(session, ids)
    item_ids = {
        *(row.item_id for rows in meal_rows.values() for row in rows),
        *(
            row.item_id
            for list_meal in list_meals
            if list_meal.list_id in drafts
            for row in frozen_rows.get(list_meal.id, [])
        ),
        *(
            extra.item_id
            for group in extras.values()
            for extra in group
            if extra.attrs_snapshot is None
        ),
    }
    items = await items_repo.by_ids(
        session, (item_id for item_id in item_ids if item_id is not None)
    )
    categories = {row.id: row for row in await reference_repo.categories_in_order(session)}
    states = await lists_repo.states_for(session, ids)
    return ListContent(
        meals=meals,
        sources=sources,
        linked_meals=linked_meals,
        meal_rows=meal_rows,
        frozen_rows=frozen_rows,
        extras=extras,
        items=items,
        categories=categories,
        states=states,
    )


def _snapshot_attrs(row: ListMealIngredient) -> ItemAttrs:
    return ItemAttrs(
        base_unit=BaseUnit(row.base_unit_snapshot),
        piece_weight_g=row.piece_weight_g_snapshot,
        density_g_per_ml=row.density_snapshot,
    )


def attrs_snapshot(item: Item) -> dict[str, Any]:
    """What a linked extra item keeps of its item once shopping started (LIST-11):
    `{name, brand, base_unit, piece_weight_g, category_id}`, with the live attributes (D-32).
    Snapshots taken before D-32 also hold a `density_g_per_ml`."""
    attrs = item.attrs()
    return {
        "name": item.name,
        "brand": item.brand,
        "base_unit": attrs.base_unit.value,
        "piece_weight_g": attrs.piece_weight_g,
        "category_id": item.category_id,
    }


def extra_attrs(content: ListContent, extra: ListExtraItem) -> ItemAttrs:
    """A linked extra item's attributes: its snapshot once it has one, else the live ones."""
    if (snapshot := extra.attrs_snapshot) is not None:
        return ItemAttrs(
            base_unit=BaseUnit(snapshot["base_unit"]),
            piece_weight_g=snapshot["piece_weight_g"],
            density_g_per_ml=snapshot.get("density_g_per_ml"),
        )
    return content.items[str(extra.item_id)].attrs()


def _part(
    item_id: str,
    amount: float | None,
    unit: str | None,
    attrs: ItemAttrs,
    source: SourceRef,
    factor: float = 1.0,
) -> Part:
    return Part(
        line_key=item_key(item_id),
        amount=None if amount is None else amount * factor,
        unit=None if unit is None else Unit(unit),
        attrs=attrs,
        source=source,
    )


def _meal_parts(content: ListContent, list_meal: ListMeal) -> list[Part]:
    source = SourceRef("meal", list_meal.id)
    if (meal := content.live_meal(list_meal)) is not None:
        factor = list_meal.servings / meal.servings
        return [
            _part(
                row.item_id,
                row.amount,
                row.unit,
                content.items[row.item_id].attrs(),
                source,
                factor,
            )
            for row in content.meal_rows.get(meal.id, [])
        ]
    factor = list_meal.servings / list_meal.meal_servings_snapshot
    return [
        _part(row.item_id, row.amount, row.unit, _snapshot_attrs(row), source, factor)
        for row in content.frozen_rows.get(list_meal.id, [])
    ]


def _extra_part(content: ListContent, extra: ListExtraItem) -> Part:
    source = SourceRef("extra", extra.id)
    if extra.item_id is None:
        return Part(line_key=text_key(extra.id), amount=None, unit=None, attrs=None, source=source)
    attrs = extra_attrs(content, extra)
    return _part(extra.item_id, extra.amount, extra.unit, attrs, source)


def parts(content: ListContent, shopping_list: ShoppingList) -> list[Part]:
    """The parts of a list: its meals in the order they were added, then its extra items."""
    meal_parts = [
        part
        for list_meal in content.meals.get(shopping_list.id, [])
        for part in _meal_parts(content, list_meal)
    ]
    extra_parts = [
        _extra_part(content, extra) for extra in content.extras.get(shopping_list.id, [])
    ]
    return meal_parts + extra_parts


def _hidden_keys(content: ListContent, shopping_list: ShoppingList) -> set[str]:
    states = content.states.get(shopping_list.id, {})
    return {key for key, state in states.items() if state.hidden}


def line_count(content: ListContent, shopping_list: ShoppingList) -> int:
    """How many lines the list has that are not hidden."""
    keys = {part.line_key for part in parts(content, shopping_list)}
    return len(keys - _hidden_keys(content, shopping_list))


def meal_name(content: ListContent, list_meal: ListMeal) -> str:
    """The current name of a live meal, else the one it had when it was frozen."""
    meal = content.live_meal(list_meal)
    return list_meal.meal_name_snapshot if meal is None else meal.name


@dataclass(frozen=True)
class _Label:
    """What a line shows: a name, a brand (items only) and a category."""

    name: str
    brand: str | None
    category_id: str


def _snapshot_labels(content: ListContent, shopping_list: ShoppingList) -> dict[str, _Label]:
    """The name, brand and category id of each item line from the first of its parts
    with a snapshot: frozen rows in the order of the meals, then linked extra items (LIST-11).
    Snapshots taken before brands existed have none."""
    labels: dict[str, _Label] = {}
    for list_meal in content.meals.get(shopping_list.id, []):
        for row in content.frozen_rows.get(list_meal.id, []):
            labels.setdefault(
                item_key(row.item_id),
                _Label(
                    row.item_name_snapshot,
                    row.item_brand_snapshot,
                    row.category_id_snapshot,
                ),
            )
    for extra in content.extras.get(shopping_list.id, []):
        if extra.item_id is not None and (snapshot := extra.attrs_snapshot) is not None:
            labels.setdefault(
                item_key(extra.item_id),
                _Label(snapshot["name"], snapshot.get("brand"), snapshot["category_id"]),
            )
    return labels


def _live_keys(content: ListContent, shopping_list: ShoppingList) -> set[str]:
    """The item lines with a part that follows the live item: a row of a live meal,
    or a linked extra item without a snapshot."""
    keys = {
        item_key(row.item_id)
        for list_meal in content.meals.get(shopping_list.id, [])
        if (meal := content.live_meal(list_meal)) is not None
        for row in content.meal_rows.get(meal.id, [])
    }
    keys.update(
        item_key(extra.item_id)
        for extra in content.extras.get(shopping_list.id, [])
        if extra.item_id is not None and extra.attrs_snapshot is None
    )
    return keys


def _by_key(_line_key: str) -> tuple[()]:
    return ()


def current_lines(content: ListContent, shopping_list: ShoppingList) -> dict[str, Line]:
    """The lines of a list as they are now, by key (unsorted: for check-off snapshots)."""
    return {line.line_key: line for line in aggregate(parts(content, shopping_list), _by_key)}


def check_snapshot(line: Line | None, text_extra: ListExtraItem | None) -> dict[str, Any]:
    """What is stored when a line is checked off (plan § 5.7): its totals (none for a key
    without a line right now), and for a free-text line its text and amount."""
    totals = line.totals if line is not None else LineTotals({}, False, False)
    snapshot = CheckSnapshot.of(totals).to_json()
    if text_extra is not None:
        snapshot |= {"text": text_extra.text, "amount_text": text_extra.amount_text}
    return snapshot


@dataclass(frozen=True)
class _CheckState:
    checked: bool = False
    checked_at: datetime | None = None
    checked_by: UserRef | None = None
    new: bool = False
    needs_more: LineNeedsMore | None = None


def _needs_more(
    state: ListLineState, line: Line, text_extra: ListExtraItem | None
) -> LineNeedsMore | None:
    """Why a checked line needs more since it was checked, if it does (LIST-12)."""
    snapshot = state.checked_snapshot or {}
    if text_extra is not None:
        changed = text_changed(
            snapshot.get("text", ""),
            snapshot.get("amount_text"),
            text_extra.text or "",
            text_extra.amount_text,
        )
        if not changed:
            return None
        return LineNeedsMore(grown=[], new_unit=False, new_unspecified=False, changed=True)
    checked = CheckSnapshot.from_json(snapshot)
    result = needs_more(checked, line.totals)
    if not result.needed:
        return None
    return LineNeedsMore(
        grown=[
            DisplayAmountOut(value=item.value, unit=item.unit)
            for item in grown_display(result, checked, line.totals)
        ],
        new_unit=bool(result.new_segments),
        new_unspecified=result.new_unspecified,
        changed=False,
    )


def _check_state(
    shopping_list: ShoppingList,
    state: ListLineState | None,
    line: Line,
    text_extra: ListExtraItem | None,
    refs: Mapping[str, UserRef],
) -> _CheckState:
    """The check state a line is shown with (plan § 5.7); a draft has none."""
    if shopping_list.status == "draft":
        return _CheckState()
    if state is None:
        return _CheckState(new=shopping_list.status == "shopping")
    if not state.checked:
        return _CheckState()
    if (reason := _needs_more(state, line, text_extra)) is not None:
        return _CheckState(needs_more=reason)
    return _CheckState(
        checked=True,
        checked_at=state.checked_at,
        checked_by=None if state.checked_by is None else refs.get(state.checked_by),
    )


def lines(
    content: ListContent,
    shopping_list: ShoppingList,
    *,
    order: WalkingOrder,
    private_meals: Collection[str],
    refs: Mapping[str, UserRef],
) -> list[ListLine]:
    """The aggregated lines of a list, sorted by the viewer's walking `order`, then name and
    brand (AGG-05), with their check state. Sources from the list meals in `private_meals` (ids)
    show no meal name (VIS-06); `refs` has the users who checked lines off."""
    list_meals = {row.id: row for row in content.meals.get(shopping_list.id, [])}
    extras = {row.id: row for row in content.extras.get(shopping_list.id, [])}
    states = content.states.get(shopping_list.id, {})
    other_category_id = content.other_category_id()
    draft = shopping_list.status == "draft"
    labels = _snapshot_labels(content, shopping_list)
    live_keys = _live_keys(content, shopping_list) if draft else set()

    def describe(line_key: str) -> _Label:
        """The name, brand and category id of a line."""
        if line_key.startswith(ITEM_KEY_PREFIX):
            frozen = labels.get(line_key)
            if frozen is not None and not draft:
                return frozen
            item = content.items[line_key.removeprefix(ITEM_KEY_PREFIX)]
            # Only detached meals make this draft line: it keeps their category (REF-01).
            if frozen is not None and line_key not in live_keys:
                return _Label(item.name, item.brand, frozen.category_id)
            return _Label(item.name, item.brand, item.category_id)
        extra = extras[line_key.removeprefix(TEXT_KEY_PREFIX)]
        return _Label(extra.text or "", None, extra.category_id or other_category_id)

    def sort_key(line_key: str) -> tuple[int, bool, str, str, str]:
        label = describe(line_key)
        category = content.categories[label.category_id]
        return (
            *order.sort_key(category.id, category.sort_order, category.deleted_at is not None),
            normalize(label.name),
            normalize(label.brand or ""),
        )

    def source(ref: SourceRef) -> LineSource:
        if ref.kind == "meal":
            list_meal = list_meals[ref.id]
            private = list_meal.id in private_meals
            return LineSource(
                kind="meal",
                list_meal_id=list_meal.id,
                extra_id=None,
                meal_name=None if private else meal_name(content, list_meal),
                private=private,
                servings=list_meal.servings,
                amount=None,
                unit=None,
                amount_text=None,
            )
        extra = extras[ref.id]
        return LineSource(
            kind="extra",
            list_meal_id=None,
            extra_id=extra.id,
            meal_name=None,
            private=False,
            servings=None,
            amount=extra.amount,
            unit=None if extra.unit is None else Unit(extra.unit),
            amount_text=extra.amount_text,
        )

    hidden = _hidden_keys(content, shopping_list)
    result = []
    for line in aggregate(parts(content, shopping_list), sort_key):
        label = describe(line.line_key)
        is_item = line.line_key.startswith(ITEM_KEY_PREFIX)
        text_extra = None if is_item else extras[line.line_key.removeprefix(TEXT_KEY_PREFIX)]
        check = _check_state(shopping_list, states.get(line.line_key), line, text_extra, refs)
        result.append(
            ListLine(
                key=line.line_key,
                kind="item" if is_item else "text",
                item_id=(line.line_key.removeprefix(ITEM_KEY_PREFIX) if is_item else None),
                name=label.name,
                brand=label.brand,
                category_id=label.category_id,
                amounts=[
                    DisplayAmountOut(value=item.value, unit=item.unit) for item in line.display
                ],
                has_unspecified=is_item and line.totals.has_unspecified,
                amount_text=None if text_extra is None else text_extra.amount_text,
                hidden=line.line_key in hidden,
                sources=[source(ref) for ref in line.sources],
                checked=check.checked,
                checked_at=check.checked_at,
                checked_by=check.checked_by,
                new=check.new,
                needs_more=check.needs_more,
            )
        )
    return result
