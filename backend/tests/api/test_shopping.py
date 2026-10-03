"""Shopping mode: starting to shop (freezing, LIST-11), editing while shopping (LIST-12), the
check state of lines with "new" and "needs more", finishing, reopening, shopping again and the
history (LIST-10..12, SHOP-01/04/05/06, CPL-02/05, VIS-06, plan § 5.7)."""

from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update

from app.core.config import Settings
from app.db.session import Database
from app.models import ListExtraItem, ListLineState, ListMeal, ListMealIngredient
from app.services import demo
from app.services.context import AuthConfig
from tests.accounts import (
    PUBLIC_URL,
    START,
    Account,
    FakeClock,
    error,
    login,
    make_couple,
    make_user,
    scalars,
    set_privacy,
)
from tests.catalog import category_ids, create_ingredient, ref, set_stored
from tests.lists import (
    UNCHECKED,
    added,
    applied,
    by_key,
    check,
    create_list,
    detail,
    extra_added,
    line,
    op,
    set_status,
    start_shopping,
    summaries,
)
from tests.meals import create_meal, jpeg, upload
from tests.support import SettingsFactory


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def ben(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "ben")


@pytest.fixture
async def carl(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "carl")


@pytest.fixture
async def dora(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "dora")


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin")


@pytest.fixture
async def categories(api: AsyncClient, anna: Account) -> dict[str, str]:
    return await category_ids(api, anna)


@pytest.fixture
async def flour(api: AsyncClient, anna: Account, categories: dict[str, str]) -> Any:
    return await create_ingredient(api, anna, "Mehl", category_id=categories["baking"])


@pytest.fixture
async def onions(api: AsyncClient, anna: Account, categories: dict[str, str]) -> Any:
    return await create_ingredient(
        api,
        anna,
        "Zwiebeln",
        category_id=categories["fruit_vegetables"],
        base_unit="piece",
        piece_weight_g=150,
    )


@pytest.fixture
async def eggs(api: AsyncClient, anna: Account, categories: dict[str, str]) -> Any:
    """Counted in pieces, without a piece weight."""
    return await create_ingredient(
        api, anna, "Eier", category_id=categories["dairy_eggs"], base_unit="piece"
    )


def row(ingredient: Any, amount: float | None = None, unit: str | None = None) -> dict[str, Any]:
    return {"ingredient_id": ingredient["id"], "amount": amount, "unit": unit}


def key(ingredient: Any) -> str:
    return f"i:{ingredient['id']}"


def shown(list_detail: Any) -> list[tuple[str, str, str, list[Any]]]:
    """Per line: key, name, category and display amounts."""
    return [
        (item["key"], item["name"], item["category_id"], item["amounts"])
        for item in list_detail["lines"]
    ]


async def later(api: AsyncClient, clock: FakeClock, *users: Account, **delta: float) -> None:
    """Move the clock on; the users log in again (their access tokens expire)."""
    clock.advance(**delta)
    for user in users:
        await login(api, user)


async def run_ops(api: AsyncClient, user: Account, list_id: str, *ops: Any) -> Any:
    return await applied(api, user, list_id, *ops)


async def finish(api: AsyncClient, user: Account, list_id: str, at: datetime = START) -> Any:
    return await applied(api, user, list_id, op("list.finish", at=at))


async def done_list(api: AsyncClient, user: Account, name: str, *, meal: Any | None = None) -> Any:
    """A list of `user` that was shopped and finished now."""
    shopping_list = await create_list(api, user, name)
    if meal is not None:
        await added(api, user, shopping_list["id"], meal["id"])
    await start_shopping(api, user, shopping_list["id"])
    return await finish(api, user, shopping_list["id"])


# --- start shopping (LIST-10, LIST-11) ------------------------------------------------------


async def test_start_shopping(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    clock: FakeClock,
    flour: Any,
    onions: Any,
    categories: dict[str, str],
) -> None:
    salt = await create_ingredient(api, anna, "Salz")
    # A g ingredient's piece weight from before D-32 is not copied (LIST-11).
    await set_stored(app, flour["id"], piece_weight_g=1000)
    meal = await create_meal(
        api, anna, "Brot", servings=2, ingredients=[row(flour, 400, "g"), row(onions, 1, "piece")]
    )
    assert (await upload(api, anna, meal["id"], jpeg())).status_code == 200
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await added(api, anna, list_id, meal["id"], servings=4)
    await extra_added(api, anna, list_id, ingredient_id=onions["id"], amount=2)
    await extra_added(api, anna, list_id, text="Kerzen")
    await extra_added(api, anna, list_id, ingredient_id=salt["id"])
    await api.post(f"/api/lists/{list_id}/lines/{key(salt)}/hide", headers=anna.headers)
    draft = await detail(api, anna, list_id)
    clock.advance(minutes=5)

    body = await start_shopping(api, anna, list_id)

    assert (body["status"], body["shopping_started_at"], body["finished_at"]) == (
        "shopping",
        "2026-09-27T12:05:00Z",
        None,
    )
    assert body["version"] > draft["version"]
    assert body["updated_at"] == "2026-09-27T12:05:00Z"
    # The same lines; none of them is new, the hidden one stays hidden.
    assert shown(body) == shown(draft)
    assert [(item["hidden"], item["new"], item["checked"]) for item in body["lines"]] == [
        (item["key"] == key(salt), False, False) for item in draft["lines"]
    ]
    assert line(body, "Zwiebeln")["amounts"] == [{"value": 4, "unit": "piece"}]
    # The meal is frozen, but still linked (and shown with its photo).
    [entry] = body["meals"]
    assert (entry["meal_id"], entry["name"], entry["detached"]) == (meal["id"], "Brot", None)
    assert entry["thumb_url"] is not None
    frozen = await scalars(app, select(ListMeal))
    assert [(item.meal_id, item.frozen_at, item.detached_reason) for item in frozen] == [
        (meal["id"], clock.now, None)
    ]
    rows = await scalars(app, select(ListMealIngredient).order_by(ListMealIngredient.position))
    assert [
        (
            item.ingredient_name_snapshot,
            item.base_unit_snapshot,
            item.piece_weight_g_snapshot,
            item.density_snapshot,
        )
        for item in rows
    ] == [("Mehl", "g", None, None), ("Zwiebeln", "piece", 150, None)]
    snapshots = await scalars(app, select(ListExtraItem.attrs_snapshot).order_by(ListExtraItem.id))
    assert snapshots == [
        {
            "name": "Zwiebeln",
            "brand": None,
            "base_unit": "piece",
            "piece_weight_g": 150,
            "category_id": categories["fruit_vegetables"],
        },
        None,
        {
            "name": "Salz",
            "brand": None,
            "base_unit": "g",
            "piece_weight_g": None,
            "category_id": salt["category_id"],
        },
    ]
    states = await scalars(app, select(ListLineState.line_key))
    assert sorted(states) == sorted(item["key"] for item in draft["lines"])


async def test_starting_needs_a_draft_you_may_edit(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, carl: Account
) -> None:
    await make_couple(api, anna, ben)
    shared = await create_list(api, anna, "Geteilt")
    unshared = await create_list(api, anna, "Privat")
    await api.patch(
        f"/api/lists/{unshared['id']}", json={"shared_with_partner": False}, headers=anna.headers
    )

    def start(user: Account, list_id: str) -> Any:
        return api.post(f"/api/lists/{list_id}/start-shopping", headers=user.headers)

    assert error(await start(ben, unshared["id"])) == "common.forbidden"
    assert error(await start(carl, shared["id"])) == "common.forbidden"  # public, read-only
    await set_privacy(api, anna, lists_public=False)
    assert error(await start(carl, shared["id"])) == "common.not_found"
    assert error(await start(anna, "0190c0de-0000-7000-8000-000000000000")) == "common.not_found"
    assert (await start(ben, shared["id"])).status_code == 200  # the partner may
    response = await start(anna, shared["id"])
    assert (response.status_code, error(response)) == (409, "list.not_draft")
    await set_status(app, unshared["id"], "done")
    assert error(await start(anna, unshared["id"])) == "list.not_draft"


# --- frozen means frozen (LIST-11, LIST-15) -------------------------------------------------


async def test_changes_of_meals_and_ingredients_leave_shopping_lists_alone(
    api: AsyncClient, anna: Account, flour: Any, onions: Any, categories: dict[str, str]
) -> None:
    meal = await create_meal(
        api, anna, "Brot", servings=2, ingredients=[row(flour, 200, "g"), row(onions, 1, "piece")]
    )
    lists = []
    for name in ("Einkauf", "Entwurf"):
        shopping_list = await create_list(api, anna, name)
        await added(api, anna, shopping_list["id"], meal["id"])
        await extra_added(api, anna, shopping_list["id"], ingredient_id=onions["id"], amount=1)
        lists.append(shopping_list["id"])
    shopping_id, draft_id = lists
    before = await start_shopping(api, anna, shopping_id)
    assert line(before, "Zwiebeln")["amounts"] == [{"value": 2, "unit": "piece"}]

    changes = {"name": "Rote Zwiebeln", "category_id": categories["other"], "piece_weight_g": 50}
    await api.patch(f"/api/ingredients/{onions['id']}", json=changes, headers=anna.headers)
    await api.patch(
        f"/api/meals/{meal['id']}",
        json={"name": "Neues Brot", "servings": 4, "ingredients": [row(flour, 500, "g")]},
        headers=anna.headers,
    )

    after = await detail(api, anna, shopping_id)
    assert shown(after) == shown(before)
    assert after["version"] == before["version"]
    [entry] = after["meals"]
    assert (entry["name"], entry["servings"], entry["meal_servings"]) == ("Brot", 2, 2)
    # A draft follows every change.
    draft = await detail(api, anna, draft_id)
    assert [(item["name"], item["category_id"], item["amounts"]) for item in draft["lines"]] == [
        ("Mehl", categories["baking"], [{"value": 250, "unit": "g"}]),
        ("Rote Zwiebeln", categories["other"], [{"value": 1, "unit": "piece"}]),
    ]
    assert draft["meals"][0]["name"] == "Neues Brot"


async def test_a_piece_ingredient_is_frozen_with_its_piece_weight(
    app: FastAPI, api: AsyncClient, anna: Account, categories: dict[str, str]
) -> None:
    """LIST-11: freezing copies the base unit Stück and the piece weight, and the frozen rows
    and extra items keep calculating with them, in whole pieces (AGG-04), however the
    ingredient changes."""
    eggs = await create_ingredient(
        api,
        anna,
        "Eier",
        category_id=categories["dairy_eggs"],
        base_unit="piece",
        piece_weight_g=60,
    )
    meal = await create_meal(api, anna, "Rührei", ingredients=[row(eggs, 2.5, "piece")])
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await added(api, anna, list_id, meal["id"])
    await extra_added(api, anna, list_id, ingredient_id=eggs["id"], amount=1, unit="piece")

    before = await start_shopping(api, anna, list_id)

    assert line(before, "Eier")["amounts"] == [{"value": 4, "unit": "piece"}]
    [frozen] = await scalars(app, select(ListMealIngredient))
    assert (frozen.base_unit_snapshot, frozen.piece_weight_g_snapshot) == ("piece", 60)
    [snapshot] = await scalars(app, select(ListExtraItem.attrs_snapshot))
    assert (snapshot["base_unit"], snapshot["piece_weight_g"]) == ("piece", 60)

    # A checked line that needs another egg says so in pieces (LIST-12).
    await run_ops(api, anna, list_id, check(key(eggs)))
    body = await extra_added(api, anna, list_id, ingredient_id=eggs["id"], amount=1, unit="piece")
    assert line(body, "Eier")["amounts"] == [{"value": 5, "unit": "piece"}]
    assert line(body, "Eier")["needs_more"]["grown"] == [{"value": 1, "unit": "piece"}]

    # The meal's pieces won't fit grams any more (D-33).
    changes = {"name": "Hühnereier", "base_unit": "g", "accept_unit_mismatch": True}
    response = await api.patch(f"/api/ingredients/{eggs['id']}", json=changes, headers=anna.headers)
    assert (response.json()["base_unit"], response.json()["piece_weight_g"]) == ("g", None)
    after = await detail(api, anna, list_id)
    assert shown(after) == shown(body)
    # The items keep fitting the base unit they copied.
    assert [item["unit_fits"] for item in after["extra_items"]] == [True, True]


async def frozen_before_d32(app: FastAPI, ingredient_id: str, **attrs: Any) -> None:
    """Give the frozen rows and extra items of an ingredient the attributes rows frozen before
    D-32 copied: a piece weight with base unit g, a density with ml."""
    database: Database = app.state.database
    async with database.write_sessions() as session, session.begin():
        await session.execute(
            update(ListMealIngredient)
            .where(ListMealIngredient.ingredient_id == ingredient_id)
            .values(
                base_unit_snapshot=attrs["base_unit"],
                piece_weight_g_snapshot=attrs["piece_weight_g"],
                density_snapshot=attrs["density_g_per_ml"],
            )
        )
        extras = await session.scalars(
            select(ListExtraItem).where(ListExtraItem.ingredient_id == ingredient_id)
        )
        for extra in extras:
            extra.attrs_snapshot = {**(extra.attrs_snapshot or {}), **attrs}


async def test_lists_frozen_before_d32_keep_their_conversions(
    app: FastAPI, api: AsyncClient, anna: Account, onions: Any
) -> None:
    """LIST-11, AGG-03, D-08: a list being shopped keeps converting with the piece weight and
    density its rows copied before D-32, and so does the done list; an amount added now, with
    the attributes of now, sits beside them."""
    oil = await create_ingredient(api, anna, "Öl", base_unit="ml")
    meal = await create_meal(
        api, anna, "Pfanne", ingredients=[row(onions, 2, "piece"), row(oil, 2, "tbsp")]
    )
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await added(api, anna, list_id, meal["id"])
    await extra_added(api, anna, list_id, ingredient_id=onions["id"], amount=1)
    await extra_added(api, anna, list_id, ingredient_id=oil["id"], amount=50, unit="ml")
    await start_shopping(api, anna, list_id)
    await frozen_before_d32(
        app, onions["id"], base_unit="g", piece_weight_g=150, density_g_per_ml=None
    )
    await frozen_before_d32(
        app, oil["id"], base_unit="ml", piece_weight_g=None, density_g_per_ml=0.92
    )
    # Extra items added in grams back then.
    database: Database = app.state.database
    async with database.write_sessions() as session, session.begin():
        for ingredient_id, amount in ((onions["id"], 300), (oil["id"], 46)):
            await session.execute(
                update(ListExtraItem)
                .where(ListExtraItem.ingredient_id == ingredient_id)
                .values(amount=amount, unit="g")
            )

    body = await detail(api, anna, list_id)
    # 2 onions of 150 g and 300 g; 46 g of oil are 50 ml, plus 2 tbsp.
    assert line(body, "Zwiebeln")["amounts"] == [{"value": 600, "unit": "g"}]
    assert line(body, "Öl")["amounts"] == [{"value": 80, "unit": "ml"}]
    done = await finish(api, anna, list_id)
    assert shown(done) == shown(body)

    # Shopping again takes the meals and attributes of now: nothing converts across kinds.
    response = await api.post(f"/api/lists/{list_id}/shop-again", headers=anna.headers)
    copy = response.json()["list"]
    assert line(copy, "Zwiebeln")["amounts"] == [
        {"value": 300, "unit": "g"},
        {"value": 2, "unit": "piece"},
    ]
    assert line(copy, "Öl")["amounts"] == [
        {"value": 46, "unit": "g"},
        {"value": 2, "unit": "tbsp"},
    ]
    assert [item["unit_fits"] for item in copy["extra_items"]] == [False, False]


async def test_two_brands_of_the_same_thing_are_two_lines(
    api: AsyncClient, anna: Account, categories: dict[str, str]
) -> None:
    """Different brands are different ingredients, so they stay apart on a list (owner
    decision 2026-09-28), sorted by name, then brand; once shopping started, the lines keep the
    brand they had (LIST-11)."""
    pasta = categories["pasta_rice_grains"]
    barilla = await create_ingredient(api, anna, "Spaghetti", brand="Barilla", category_id=pasta)
    de_cecco = await create_ingredient(api, anna, "Spaghetti", brand="De Cecco", category_id=pasta)
    generic = await create_ingredient(api, anna, "Spaghetti", category_id=pasta)
    bolognese = await create_meal(api, anna, "Bolognese", ingredients=[row(de_cecco, 500, "g")])
    aglio = await create_meal(api, anna, "Aglio e olio", ingredients=[row(barilla, 250, "g")])
    shopping_list = await create_list(api, anna, "Pasta")
    for meal in (bolognese, aglio):
        await added(api, anna, shopping_list["id"], meal["id"])
    await extra_added(
        api, anna, shopping_list["id"], ingredient_id=generic["id"], amount=100, unit="g"
    )
    await extra_added(
        api, anna, shopping_list["id"], ingredient_id=barilla["id"], amount=250, unit="g"
    )

    def spaghetti(body: Any) -> list[tuple[str | None, list[Any]]]:
        return [(item["brand"], item["amounts"]) for item in body["lines"]]

    draft = await detail(api, anna, shopping_list["id"])
    assert spaghetti(draft) == [
        (None, [{"value": 100, "unit": "g"}]),
        ("Barilla", [{"value": 500, "unit": "g"}]),
        ("De Cecco", [{"value": 500, "unit": "g"}]),
    ]

    before = await start_shopping(api, anna, shopping_list["id"])
    for ingredient in (barilla, de_cecco):
        response = await api.patch(
            f"/api/ingredients/{ingredient['id']}", json={"brand": "Neu"}, headers=anna.headers
        )
        assert response.status_code == 200
    after = await detail(api, anna, shopping_list["id"])
    assert spaghetti(after) == spaghetti(before) == spaghetti(draft)


async def test_detach_triggers_leave_shopping_lists_alone(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    ben: Account,
    carl: Account,
    admin: Account,
    flour: Any,
) -> None:
    """LIST-15: meal deletion, privacy, a couple ending and user deletion only detach meals of
    lists that are not frozen yet."""
    await make_couple(api, anna, ben)
    meals = [
        await create_meal(api, user, name, ingredients=[row(flour, 100, "g")])
        for user, name in ((anna, "Brot"), (ben, "Suppe"), (carl, "Curry"))
    ]
    shopping_list = await create_list(api, anna)
    for meal in meals:
        await added(api, anna, shopping_list["id"], meal["id"])
    before = await start_shopping(api, anna, shopping_list["id"])

    await api.delete(f"/api/meals/{meals[0]['id']}", headers=anna.headers)
    await set_privacy(api, carl, meals_public=False)
    await set_privacy(api, ben, meals_public=False)
    await api.delete("/api/couple", headers=anna.headers)
    await api.delete(f"/api/admin/users/{carl.id}", headers=admin.headers)

    after = await detail(api, anna, shopping_list["id"])
    assert shown(after) == shown(before)
    assert [entry["detached"] for entry in after["meals"]] == [None, None, None]
    assert await scalars(app, select(ListMeal.detached_reason)) == [None, None, None]
    # The deleted meal keeps its frozen rows; others' meals are private now (VIS-06).
    assert [(entry["meal_id"], entry["name"]) for entry in after["meals"]] == [
        (None, "Brot"),
        (None, None),
        (None, None),
    ]


# --- editing while shopping (LIST-12) -------------------------------------------------------


async def test_editing_while_shopping(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    ben: Account,
    clock: FakeClock,
    flour: Any,
    onions: Any,
    eggs: Any,
) -> None:
    await make_couple(api, anna, ben)
    bread = await create_meal(api, anna, "Brot", ingredients=[row(flour, 100, "g")])
    soup = await create_meal(api, ben, "Suppe", ingredients=[row(onions, 1, "piece")])
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    [bread_entry] = (await added(api, anna, list_id, bread["id"]))["meals"]
    await start_shopping(api, anna, list_id)
    clock.advance(minutes=1)

    # The partner adds a meal: it is frozen at once, its line is new.
    body = await added(api, ben, list_id, soup["id"], servings=2)
    soup_entry = body["meals"][1]
    frozen = await scalars(app, select(ListMeal.frozen_at).where(ListMeal.id == soup_entry["id"]))
    assert frozen == [clock.now]
    assert [(item["name"], item["new"]) for item in body["lines"]] == [
        ("Zwiebeln", True),
        ("Mehl", False),
    ]

    # Servings change; a linked extra item gets its snapshot at once.
    response = await api.patch(
        f"/api/lists/{list_id}/meals/{bread_entry['id']}", json={"servings": 3}, headers=ben.headers
    )
    assert line(response.json(), "Mehl")["amounts"] == [{"value": 300, "unit": "g"}]
    body = await extra_added(api, ben, list_id, ingredient_id=eggs["id"], amount=2)
    [item] = body["extra_items"]
    assert (await scalars(app, select(ListExtraItem.attrs_snapshot)))[0]["name"] == "Eier"
    assert line(body, "Eier")["new"] is True
    # Moving it to another ingredient takes that one's snapshot.
    response = await api.patch(
        f"/api/lists/{list_id}/extra-items/{item['id']}",
        json={"ingredient_id": onions["id"]},
        headers=anna.headers,
    )
    assert line(response.json(), "Zwiebeln")["amounts"] == [{"value": 4, "unit": "piece"}]
    [snapshot] = await scalars(app, select(ListExtraItem.attrs_snapshot))
    assert (snapshot["name"], snapshot["piece_weight_g"]) == ("Zwiebeln", 150)
    # Changing only the amount keeps the snapshot.
    await api.patch(
        f"/api/ingredients/{onions['id']}", json={"piece_weight_g": 200}, headers=anna.headers
    )
    await api.patch(
        f"/api/lists/{list_id}/extra-items/{item['id']}", json={"amount": 3}, headers=anna.headers
    )
    [snapshot] = await scalars(app, select(ListExtraItem.attrs_snapshot))
    assert snapshot["piece_weight_g"] == 150
    # Free-text items, deleting, removing meals.
    body = await extra_added(api, ben, list_id, text="Kerzen")
    candles = body["extra_items"][1]
    response = await api.patch(
        f"/api/lists/{list_id}/extra-items/{candles['id']}", json={"text": "Teelichter"},
        headers=ben.headers,
    )  # fmt: skip
    assert line(response.json(), "Teelichter")["new"] is True
    response = await api.delete(
        f"/api/lists/{list_id}/extra-items/{candles['id']}", headers=ben.headers
    )
    assert [item["name"] for item in response.json()["lines"]] == ["Zwiebeln", "Mehl"]
    response = await api.delete(
        f"/api/lists/{list_id}/meals/{soup_entry['id']}", headers=anna.headers
    )
    body = response.json()
    assert (body["status"], [entry["name"] for entry in body["meals"]]) == ("shopping", ["Brot"])
    assert line(body, "Zwiebeln")["amounts"] == [{"value": 3, "unit": "piece"}]
    # Adding a meal that is on the list already raises its servings (LIST-04).
    body = await added(api, anna, list_id, bread["id"], servings=2)
    assert [(entry["name"], entry["servings"]) for entry in body["meals"]] == [("Brot", 5)]


# --- check state, "new" and "needs more" (LIST-12, SHOP-01) ---------------------------------


async def test_checked_lines_that_need_more(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock, flour: Any, eggs: Any
) -> None:
    await make_couple(api, anna, ben)
    salt = await create_ingredient(api, anna, "Salz")
    meal = await create_meal(
        api, anna, "Kuchen", ingredients=[row(flour, 300, "g"), row(eggs, 2, "piece")]
    )
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    [entry] = (await added(api, anna, list_id, meal["id"]))["meals"]
    body = await extra_added(api, anna, list_id, text="Kerzen", amount_text="1 Packung")
    candles = body["extra_items"][0]
    await extra_added(api, anna, list_id, ingredient_id=salt["id"])
    await start_shopping(api, anna, list_id)
    candle_key = f"x:{candles['id']}"
    all_keys = (key(flour), key(eggs), key(salt), candle_key)

    body = await run_ops(api, anna, list_id, *(check(line_key) for line_key in all_keys[:3]))
    body = await run_ops(api, ben, list_id, check(candle_key))
    assert all(item["checked"] for item in body["lines"])
    assert line(body, "Kerzen")["checked_by"] == ref(ben)
    assert line(body, "Mehl")["checked_by"] == ref(anna)
    assert line(body, "Mehl")["checked_at"] == "2026-09-27T12:00:00Z"

    async def servings(count: int) -> Any:
        response = await api.patch(
            f"/api/lists/{list_id}/meals/{entry['id']}",
            json={"servings": count},
            headers=anna.headers,
        )
        return response.json()

    # More servings: the grown differences, per unit.
    body = await servings(2)
    flour_line = line(body, "Mehl")
    assert (flour_line["checked"], flour_line["checked_at"], flour_line["checked_by"]) == (
        False,
        None,
        None,
    )
    assert flour_line["needs_more"] == {
        "grown": [{"value": 300, "unit": "g"}],
        "new_unit": False,
        "new_unspecified": False,
        "changed": False,
    }
    assert line(body, "Eier")["needs_more"]["grown"] == [{"value": 2, "unit": "piece"}]
    assert line(body, "Salz")["checked"] is True  # still "some"
    assert line(body, "Salz")["needs_more"] is None
    # A free-text item that was edited is "changed".
    response = await api.patch(
        f"/api/lists/{list_id}/extra-items/{candles['id']}",
        json={"amount_text": "2 Packungen"},
        headers=anna.headers,
    )
    assert line(response.json(), "Kerzen")["needs_more"] == {
        "grown": [],
        "new_unit": False,
        "new_unspecified": False,
        "changed": True,
    }
    # Checking again replaces the snapshot.
    body = await run_ops(api, anna, list_id, *(check(line_key) for line_key in all_keys))
    assert all(item["checked"] and item["needs_more"] is None for item in body["lines"])
    # A new unit (spoons of flour stay spoons), a part without an amount.
    await extra_added(api, anna, list_id, ingredient_id=flour["id"], amount=2, unit="tbsp")
    body = await extra_added(api, anna, list_id, ingredient_id=eggs["id"])
    assert line(body, "Mehl")["needs_more"] == {
        "grown": [],
        "new_unit": True,
        "new_unspecified": False,
        "changed": False,
    }
    assert line(body, "Mehl")["amounts"] == [
        {"value": 600, "unit": "g"},
        {"value": 2, "unit": "tbsp"},
    ]
    assert line(body, "Eier")["needs_more"] == {
        "grown": [],
        "new_unit": False,
        "new_unspecified": True,
        "changed": False,
    }
    # Needing less keeps a line checked.
    body = await run_ops(api, ben, list_id, check(key(flour)), check(key(eggs)))
    body = await servings(1)
    assert [(item["name"], item["checked"]) for item in body["lines"]] == [
        ("Eier", True),
        ("Mehl", True),
        ("Kerzen", True),
        ("Salz", True),
    ]
    assert line(body, "Mehl")["checked_by"] == ref(ben)
    # A new line; checked, it is no longer new.
    clock.advance(minutes=1)
    body = await extra_added(api, ben, list_id, text="Servietten")
    napkins = f"x:{body['extra_items'][-1]['id']}"
    assert (by_key(body, napkins)["new"], by_key(body, napkins)["checked"]) == (True, False)
    body = await run_ops(api, ben, list_id, check(napkins, at=clock.now))
    assert (by_key(body, napkins)["new"], by_key(body, napkins)["checked"]) == (False, True)
    assert by_key(body, napkins)["checked_at"] == "2026-09-27T12:01:00Z"
    # Unchecked lines have nothing to report.
    body = await run_ops(api, ben, list_id, check(napkins, False, at=clock.now))
    assert {k: v for k, v in by_key(body, napkins).items() if k in UNCHECKED} == UNCHECKED


async def test_more_pieces_are_shown_in_pieces(
    api: AsyncClient, anna: Account, onions: Any
) -> None:
    """Compared in pieces, whatever the piece weight: "3 Stk." checked at "2 Stk." needs
    "+1 Stk.", not "+150 g"."""
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await extra_added(api, anna, list_id, ingredient_id=onions["id"], amount=2, unit="piece")
    await start_shopping(api, anna, list_id)
    await run_ops(api, anna, list_id, check(key(onions)))
    body = await extra_added(api, anna, list_id, ingredient_id=onions["id"], amount=1, unit="piece")
    assert line(body, "Zwiebeln")["needs_more"] == {
        "grown": [{"value": 1, "unit": "piece"}],
        "new_unit": False,
        "new_unspecified": False,
        "changed": False,
    }


async def test_a_line_checked_before_it_existed(
    api: AsyncClient, anna: Account, flour: Any, eggs: Any
) -> None:
    """A check-off of a key without a line (e.g. from a stale phone) is kept: when the line
    appears, it needs more (plan § 5.8)."""
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await extra_added(api, anna, list_id, ingredient_id=eggs["id"], amount=1)
    await start_shopping(api, anna, list_id)
    await run_ops(api, anna, list_id, check(key(flour)))
    body = await extra_added(api, anna, list_id, ingredient_id=flour["id"], amount=500, unit="g")
    flour_line = line(body, "Mehl")
    assert (flour_line["new"], flour_line["checked"]) == (False, False)
    assert flour_line["needs_more"] == {
        "grown": [],
        "new_unit": True,
        "new_unspecified": False,
        "changed": False,
    }


# --- finish and reopen (SHOP-04, SHOP-06) ---------------------------------------------------


async def test_finish_and_reopen(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    ben: Account,
    carl: Account,
    clock: FakeClock,
    flour: Any,
) -> None:
    await make_couple(api, anna, ben)
    meal = await create_meal(api, anna, "Brot", ingredients=[row(flour, 100, "g")])
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await added(api, anna, list_id, meal["id"])
    await start_shopping(api, anna, list_id)
    await run_ops(api, anna, list_id, check(key(flour)))
    await later(api, clock, anna, ben, carl, minutes=30)

    body = await finish(api, ben, list_id, clock.now)

    assert (body["status"], body["finished_at"]) == ("done", "2026-09-27T12:30:00Z")
    assert line(body, "Mehl")["checked_by"] == ref(anna)
    # It keeps its place in the feed, marked as done (SHOP-05).
    assert [(item["id"], item["status"]) for item in await summaries(api, anna)] == [
        (list_id, "done")
    ]

    def reopen(user: Account, target: str = list_id) -> Any:
        return api.post(f"/api/lists/{target}/reopen", headers=user.headers)

    assert error(await reopen(carl)) == "common.forbidden"
    clock.advance(minutes=1)
    response = await reopen(ben)
    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["finished_at"], body["updated_at"]) == (
        "shopping",
        None,
        "2026-09-27T12:31:00Z",
    )
    assert line(body, "Mehl")["checked"] is True
    response = await reopen(anna)
    assert (response.status_code, error(response)) == (409, "list.not_done")
    draft = await create_list(api, anna)
    assert error(await reopen(anna, draft["id"])) == "list.not_done"


# --- shop again (SHOP-06, VIS-06) -----------------------------------------------------------


async def test_shop_again(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    ben: Account,
    carl: Account,
    dora: Account,
    clock: FakeClock,
    flour: Any,
    eggs: Any,
) -> None:
    await make_couple(api, anna, ben)
    await set_privacy(api, ben, meals_public=False)
    meals = [
        await create_meal(api, user, name, ingredients=[row(flour, 100, "g")])
        for user, name in ((anna, "Brot"), (ben, "Suppe"), (carl, "Curry"))
    ]
    shopping_list = await create_list(api, anna, "Woche")
    list_id = shopping_list["id"]
    for meal, servings in zip(meals, (3, 1, 2), strict=True):
        await added(api, anna, list_id, meal["id"], servings=servings)
    await extra_added(api, anna, list_id, ingredient_id=eggs["id"], amount=6)
    await extra_added(api, anna, list_id, text="Kerzen", amount_text="1 Packung")
    body = await extra_added(api, anna, list_id, text="Weg")
    gone = body["extra_items"][-1]["id"]
    await api.delete(f"/api/lists/{list_id}/extra-items/{gone}", headers=anna.headers)
    await start_shopping(api, anna, list_id)
    await run_ops(api, anna, list_id, check(key(flour)), check(key(eggs)))

    def again(user: Account, target: str = list_id) -> Any:
        return api.post(f"/api/lists/{target}/shop-again", headers=user.headers)

    response = await again(anna)
    assert (response.status_code, error(response)) == (409, "list.not_done")
    await finish(api, anna, list_id)
    # After finishing: meals change, carl's meals become private.
    await api.patch(f"/api/meals/{meals[0]['id']}", json={"name": "Brot neu"}, headers=anna.headers)
    await set_privacy(api, carl, meals_public=False)
    await later(api, clock, anna, ben, dora, days=7)

    response = await again(anna)

    assert response.status_code == 201
    result = response.json()
    assert result["left_out"] == 1  # carl's private meal
    copy = result["list"]
    assert (copy["name"], copy["status"], copy["owner"], copy["shared_with_partner"]) == (
        "Woche",
        "draft",
        ref(anna),
        True,
    )
    assert copy["created_at"] == "2026-10-04T12:00:00Z"
    assert [(entry["name"], entry["servings"]) for entry in copy["meals"]] == [
        ("Brot neu", 3),
        ("Suppe", 1),
    ]
    assert [(item["text"], item["amount"]) for item in copy["extra_items"]] == [
        (None, 6),
        ("Kerzen", None),
    ]
    assert all(
        {k: v for k, v in item.items() if k in UNCHECKED} == UNCHECKED for item in copy["lines"]
    )
    snapshots = await scalars(
        app, select(ListExtraItem.attrs_snapshot).where(ListExtraItem.list_id == copy["id"])
    )
    assert snapshots == [None, None]
    # The copy is a live draft again.
    await api.patch(f"/api/meals/{meals[0]['id']}", json={"servings": 3}, headers=anna.headers)
    assert line(await detail(api, anna, copy["id"]), "Mehl")["amounts"] == [
        {"value": 200, "unit": "g"}
    ]
    # Anyone who can see the done list can shop it again as their own draft.
    response = await again(dora)
    assert (response.json()["left_out"], response.json()["list"]["owner"]) == (2, ref(dora))
    assert error(await again(anna, copy["id"])) == "list.not_done"
    await set_privacy(api, anna, lists_public=False)
    assert error(await again(dora)) == "common.not_found"
    assert (await again(ben)).status_code == 201  # the partner sees every list


# --- done lists in the feed (SHOP-05, CPL-02, CPL-05, UI-02) -------------------------------


async def test_done_lists_stay_in_the_feed(
    api: AsyncClient,
    anna: Account,
    ben: Account,
    carl: Account,
    clock: FakeClock,
    flour: Any,
) -> None:
    await make_couple(api, anna, ben)
    meal = await create_meal(api, anna, "Brot", ingredients=[row(flour, 100, "g")])
    annas = await done_list(api, anna, "Anna", meal=meal)
    await later(api, clock, anna, ben, carl, days=1)
    await done_list(api, ben, "Ben geteilt")
    await later(api, clock, anna, ben, carl, days=1)
    unshared = await create_list(api, ben, "Ben privat")
    await api.patch(
        f"/api/lists/{unshared['id']}", json={"shared_with_partner": False}, headers=ben.headers
    )
    await start_shopping(api, ben, unshared["id"])
    await finish(api, ben, unshared["id"])
    await later(api, clock, anna, ben, carl, days=1)
    await done_list(api, carl, "Carl")  # public
    await create_list(api, anna, "Entwurf")
    shopping_list = await create_list(api, anna, "Unterwegs")
    await start_shopping(api, anna, shopping_list["id"])

    async def feed(user: Account) -> list[Any]:
        return [
            (item["name"], item["status"], item["is_owner"], item["can_edit"])
            for item in await summaries(api, user)
        ]

    # Newest created first, done lists in their place; Carl's and Ben's unshared ones read-only.
    assert await feed(anna) == [
        ("Unterwegs", "shopping", True, True),
        ("Entwurf", "draft", True, True),
        ("Carl", "done", False, False),
        ("Ben privat", "done", False, False),
        ("Ben geteilt", "done", False, True),
        ("Anna", "done", True, True),
    ]
    items = await summaries(api, anna)
    assert [item["finished_at"] for item in items] == [
        None,
        None,
        "2026-09-30T12:00:00Z",
        "2026-09-29T12:00:00Z",
        "2026-09-28T12:00:00Z",
        "2026-09-27T12:00:00Z",
    ]
    assert (items[5]["id"], items[5]["meal_count"], items[5]["line_count"]) == (annas["id"], 1, 1)
    assert await feed(ben) == [
        ("Unterwegs", "shopping", False, True),
        ("Entwurf", "draft", False, True),
        ("Carl", "done", False, False),
        ("Ben privat", "done", True, True),
        ("Ben geteilt", "done", True, True),
        ("Anna", "done", False, True),
    ]
    assert [(name, can_edit) for name, _, _, can_edit in await feed(carl)] == [
        ("Unterwegs", False),
        ("Entwurf", False),
        ("Carl", True),
        ("Ben privat", False),
        ("Ben geteilt", False),
        ("Anna", False),
    ]

    # CPL-05: when the couple ends, each keeps their own lists; the other's are only there
    # while they are public, read-only.
    await set_privacy(api, ben, lists_public=False)
    await api.delete("/api/couple", headers=ben.headers)
    assert await feed(anna) == [
        ("Unterwegs", "shopping", True, True),
        ("Entwurf", "draft", True, True),
        ("Carl", "done", False, False),
        ("Anna", "done", True, True),
    ]
    assert [(name, can_edit) for name, _, _, can_edit in await feed(ben)] == [
        ("Unterwegs", False),
        ("Entwurf", False),
        ("Carl", False),
        ("Ben privat", True),
        ("Ben geteilt", True),
        ("Anna", False),
    ]


# --- demo data (seed-demo) ------------------------------------------------------------------


async def test_demo_shopping_and_done_lists(
    app: FastAPI, api: AsyncClient, make_settings: SettingsFactory, clock: FakeClock
) -> None:
    settings: Settings = make_settings(public_url=PUBLIC_URL)
    database: Database = app.state.database
    async with database.write_sessions() as session:
        seed = await demo.seed_demo(
            session, AuthConfig.from_settings(settings), app.state.media, now=clock.now
        )
    users = {
        name: Account(id=user_id, username=name, display_name=name.capitalize())
        for name, user_id in seed.user_ids.items()
    }
    for user in users.values():
        await login(api, user, seed.password)
    anna, ben, carl = users["anna"], users["ben"], users["carl"]

    [shopping_list] = [item for item in await summaries(api, anna) if item["status"] == "shopping"]
    body = await detail(api, ben, shopping_list["id"])
    assert (body["name"], body["shared_with_partner"]) == ("Wocheneinkauf", True)
    states = {
        item["name"]: (
            item["checked"],
            None if item["checked_by"] is None else item["checked_by"]["display_name"],
            item["new"],
            item["needs_more"] and item["needs_more"]["grown"],
        )
        for item in body["lines"]
    }
    assert states["Spaghetti"] == (True, "Anna", False, None)
    assert [item["brand"] for item in body["lines"] if item["name"] == "Spaghetti"] == ["Barilla"]
    assert states["Hackfleisch"] == (True, "Ben", False, None)
    assert states["Milch"] == (True, "Anna", False, None)
    # Two onions were checked; ben's meal got more servings: one onion more.
    assert states["Zwiebeln"] == (False, None, False, [{"value": 1, "unit": "piece"}])
    assert states["Kaffee"] == (False, None, True, None)
    assert states["Küchenrolle"] == (False, None, False, None)

    done = [item for item in await summaries(api, ben) if item["status"] == "done"]
    assert [(item["name"], item["owner"]["display_name"], item["can_edit"]) for item in done] == [
        ("Salatabend", "Anna", True),
        ("Vorrat", "Carl", False),
    ]
    salad = done[0]
    assert salad["finished_at"] == (clock.now - timedelta(days=2)).isoformat().replace(
        "+00:00", "Z"
    )
    body = await detail(api, anna, salad["id"])
    assert [(item["name"], item["checked"]) for item in body["lines"] if not item["checked"]] == [
        ("Pfeffer", False)
    ]
    # carl's draft has the Barilla spaghetti of anna's Bolognese and the De Cecco of his own
    # aglio e olio: the same thing in two brands, two lines.
    [grill] = [item for item in await summaries(api, carl) if item["name"] == "Grillabend"]
    grill_lines = (await detail(api, carl, grill["id"]))["lines"]
    assert [
        (item["name"], item["brand"]) for item in grill_lines if item["name"] == "Spaghetti"
    ] == [
        ("Spaghetti", "Barilla"),
        ("Spaghetti", "De Cecco"),
    ]
    [carls] = [
        item for item in await summaries(api, carl) if item["status"] == "done" and item["is_owner"]
    ]
    assert carls["name"] == "Vorrat"
    week = timedelta(days=7)
    assert (clock.now - week).isoformat().replace("+00:00", "Z") > carls["finished_at"]
