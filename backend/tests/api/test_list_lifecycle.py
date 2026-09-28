"""What happens to lists when meals, privacy, couples, users and ingredients change: detaching
(LIST-15), unsharing (CPL-05), moving shared lists (ADM-03), ingredient references and merges
(ING-05), plan §§ 5.7 and 6."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select, update

from app.db.session import Database
from app.models import ListExtraItem, ListLineState, ListMeal, ListMealIngredient, Meal
from tests.accounts import Account, error, make_couple, make_user, scalars, set_privacy
from tests.catalog import create_ingredient, ref
from tests.lists import added, create_list, detail, extra_added, line, lines, summaries
from tests.meals import create_meal


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
async def flour(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Mehl")


async def meal_with(api: AsyncClient, user: Account, name: str, ingredient: Any) -> Any:
    """A meal of one serving with 100 g of the ingredient."""
    rows = [{"ingredient_id": ingredient["id"], "amount": 100, "unit": "g"}]
    return await create_meal(api, user, name, ingredients=rows)


def meal_states(body: Any) -> list[tuple[str | None, bool, str | None]]:
    """Per list meal: its name, whether it is private and why it is detached."""
    return [(entry["name"], entry["private"], entry["detached"]) for entry in body["meals"]]


async def run(app: FastAPI, statement: Any) -> None:
    database: Database = app.state.database
    async with database.write_sessions() as session, session.begin():
        await session.execute(statement)


# --- a meal is deleted (MEAL-07, LIST-15) ---------------------------------------------------


async def test_deleting_a_meal_detaches_it(
    app: FastAPI, api: AsyncClient, anna: Account, carl: Account, flour: Any
) -> None:
    meal = await meal_with(api, anna, "Brot", flour)
    own = await create_list(api, anna)
    others = await create_list(api, carl)
    await added(api, anna, own["id"], meal["id"], servings=3)
    before = await added(api, carl, others["id"], meal["id"])

    assert (await api.delete(f"/api/meals/{meal['id']}", headers=anna.headers)).status_code == 204

    body = await detail(api, carl, others["id"])
    assert meal_states(body) == [("Brot", False, "deleted")]
    assert body["meals"][0]["meal_id"] is None
    assert body["meals"][0]["owner"] == ref(anna)
    assert body["lines"] == before["lines"]
    assert body["version"] == before["version"] + 1
    assert lines(await detail(api, anna, own["id"])) == {"Mehl": ([(300, "g")], False)}
    frozen = await scalars(app, select(ListMealIngredient.ingredient_name_snapshot))
    assert frozen == ["Mehl", "Mehl"]
    # The list owner can remove it.
    entry_id = body["meals"][0]["id"]
    removed = await api.delete(f"/api/lists/{others['id']}/meals/{entry_id}", headers=carl.headers)
    assert (removed.json()["meals"], removed.json()["lines"]) == ([], [])


async def test_frozen_list_meals_are_not_detached(
    app: FastAPI, api: AsyncClient, anna: Account, flour: Any
) -> None:
    """LIST-15: lists that are already frozen (shopping mode, M5b) are unaffected."""
    meal = await meal_with(api, anna, "Brot", flour)
    shopping_list = await create_list(api, anna)
    await added(api, anna, shopping_list["id"], meal["id"])
    frozen_at = datetime(2026, 9, 27, 11, 0, tzinfo=UTC)
    await run(app, update(ListMeal).values(frozen_at=frozen_at))
    version = (await detail(api, anna, shopping_list["id"]))["version"]

    await api.delete(f"/api/meals/{meal['id']}", headers=anna.headers)

    [entry] = (await detail(api, anna, shopping_list["id"]))["meals"]
    assert (entry["meal_id"], entry["detached"]) == (None, None)
    assert (await detail(api, anna, shopping_list["id"]))["version"] == version
    assert await scalars(app, select(ListMeal.frozen_at)) == [frozen_at]


# --- meals made private (VIS-02) ------------------------------------------------------------


async def test_private_meals_leave_other_peoples_lists(
    api: AsyncClient, anna: Account, carl: Account, dora: Account, flour: Any
) -> None:
    await make_couple(api, carl, dora)
    meal = await meal_with(api, carl, "Curry", flour)
    theirs = await create_list(api, anna)
    own = await create_list(api, carl)
    partners = await create_list(api, dora)
    for user, shopping_list in ((anna, theirs), (carl, own), (dora, partners)):
        await added(api, user, shopping_list["id"], meal["id"], servings=2)
    version = (await detail(api, anna, theirs["id"]))["version"]

    await set_privacy(api, carl, meals_public=False)

    body = await detail(api, anna, theirs["id"])
    # anna can no longer see carl's meals: private, no longer available, still counted.
    assert meal_states(body) == [(None, True, "unavailable")]
    assert body["meals"][0]["servings"] == 2
    assert lines(body) == {"Mehl": ([(200, "g")], False)}
    assert body["version"] == version + 1
    for user, shopping_list in ((carl, own), (dora, partners)):
        assert meal_states(await detail(api, user, shopping_list["id"])) == [("Curry", False, None)]
    # carl sees his own detached meal with its name.
    assert meal_states(await detail(api, carl, theirs["id"])) == [("Curry", False, "unavailable")]


async def test_meals_made_private_without_a_partner(
    api: AsyncClient, anna: Account, carl: Account, flour: Any
) -> None:
    meal = await meal_with(api, carl, "Curry", flour)
    shopping_list = await create_list(api, anna)
    await added(api, anna, shopping_list["id"], meal["id"])
    await set_privacy(api, carl, meals_public=False)
    assert meal_states(await detail(api, carl, shopping_list["id"])) == [
        ("Curry", False, "unavailable")
    ]


# --- a couple ends (CPL-05) -----------------------------------------------------------------


async def test_ending_a_couple(
    api: AsyncClient, anna: Account, ben: Account, carl: Account, flour: Any
) -> None:
    await make_couple(api, anna, ben)
    await set_privacy(api, ben, meals_public=False)
    annas_meal = await meal_with(api, anna, "Brot", flour)
    bens_meal = await meal_with(api, ben, "Suppe", flour)
    annas_list = await create_list(api, anna)
    bens_list = await create_list(api, ben)
    carls_list = await create_list(api, carl)
    for shopping_list in (annas_list, bens_list):
        await added(api, anna, shopping_list["id"], annas_meal["id"])
        await added(api, ben, shopping_list["id"], bens_meal["id"])
    await added(api, carl, carls_list["id"], annas_meal["id"])
    before = await detail(api, anna, annas_list["id"])
    assert before["shared_with_partner"] is True

    assert (await api.delete("/api/couple", headers=anna.headers)).status_code == 204

    body = await detail(api, anna, annas_list["id"])
    assert body["shared_with_partner"] is False
    assert meal_states(body) == [("Brot", False, None), (None, True, "unavailable")]
    assert lines(body) == lines(before)
    assert body["version"] > before["version"]
    # anna's meals are public: they stay on ben's list, which ben keeps (unshared).
    body = await detail(api, ben, bens_list["id"])
    assert body["shared_with_partner"] is False
    assert meal_states(body) == [("Brot", False, None), ("Suppe", False, None)]
    assert (await detail(api, carl, carls_list["id"]))["shared_with_partner"] is False
    # Each keeps their own lists; the other's are now only public ones, read-only.
    assert [item["id"] for item in await summaries(api, anna)] == [annas_list["id"]]
    others = await summaries(api, anna, scope="others")
    assert {item["id"] for item in others} == {bens_list["id"], carls_list["id"]}
    response = await api.patch(
        f"/api/lists/{bens_list['id']}", json={"name": "x"}, headers=anna.headers
    )
    assert error(response) == "common.forbidden"


async def test_ending_a_couple_of_private_meals(
    api: AsyncClient, anna: Account, ben: Account, flour: Any
) -> None:
    await make_couple(api, anna, ben)
    for user in (anna, ben):
        await set_privacy(api, user, meals_public=False)
    annas_meal = await meal_with(api, anna, "Brot", flour)
    bens_meal = await meal_with(api, ben, "Suppe", flour)
    annas_list = await create_list(api, anna)
    bens_list = await create_list(api, ben)
    await added(api, anna, bens_list["id"], annas_meal["id"])
    await added(api, ben, annas_list["id"], bens_meal["id"])

    await api.delete("/api/couple", headers=ben.headers)

    assert meal_states(await detail(api, anna, annas_list["id"])) == [(None, True, "unavailable")]
    assert meal_states(await detail(api, ben, bens_list["id"])) == [(None, True, "unavailable")]


# --- a user is deleted (ADM-03) -------------------------------------------------------------


async def test_deleting_a_user(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    ben: Account,
    carl: Account,
    admin: Account,
    flour: Any,
) -> None:
    """ADM-03: the shared draft moves to the partner first, then the deleted user's meals are
    detached from every list they did not own (the moved one included), then the rest goes."""
    await make_couple(api, anna, ben)
    bens_meal = await meal_with(api, ben, "Suppe", flour)
    annas_meal = await meal_with(api, anna, "Brot", flour)
    shared = await create_list(api, ben, "Geteilt")
    await added(api, ben, shared["id"], bens_meal["id"], servings=2)
    await added(api, anna, shared["id"], annas_meal["id"])
    await extra_added(api, ben, shared["id"], text="Kerzen")
    unshared = await create_list(api, ben, "Privat")
    await api.patch(
        f"/api/lists/{unshared['id']}", json={"shared_with_partner": False}, headers=ben.headers
    )
    annas_list = await create_list(api, anna)
    carls_list = await create_list(api, carl)
    await added(api, anna, annas_list["id"], bens_meal["id"])
    await added(api, carl, carls_list["id"], bens_meal["id"])
    before = await detail(api, anna, shared["id"])

    assert (
        await api.delete(f"/api/admin/users/{ben.id}", headers=admin.headers)
    ).status_code == 204

    moved = await detail(api, anna, shared["id"])
    assert (moved["owner"], moved["is_owner"], moved["can_edit"]) == (ref(anna), True, True)
    assert (moved["name"], moved["shared_with_partner"]) == ("Geteilt", False)
    # ben's meal is gone but its ingredients stay; nobody can see a deleted user's meals.
    assert meal_states(moved) == [(None, True, "deleted"), ("Brot", False, None)]
    assert moved["meals"][0]["servings"] == 2
    assert lines(moved) == lines(before)
    assert moved["extra_items"][0]["added_by"] is None
    assert (await api.get(f"/api/lists/{unshared['id']}", headers=anna.headers)).status_code == 404
    for user, shopping_list in ((anna, annas_list), (carl, carls_list)):
        body = await detail(api, user, shopping_list["id"])
        assert meal_states(body) == [(None, True, "deleted")]
        assert lines(body) == {"Mehl": ([(100, "g")], False)}
    assert {item["id"] for item in await summaries(api, anna)} == {shared["id"], annas_list["id"]}
    assert await scalars(app, select(Meal.name)) == ["Brot"]
    assert (await api.post(f"/api/lists/{shared['id']}/copy", headers=anna.headers)).json()[
        "left_out"
    ] == 1


# --- ingredients (ING-05) -------------------------------------------------------------------


async def test_ingredients_on_lists_are_in_use(
    app: FastAPI, api: AsyncClient, anna: Account, admin: Account, flour: Any
) -> None:
    salt = await create_ingredient(api, anna, "Salz")
    meal = await meal_with(api, anna, "Brezel", salt)
    frozen_list = await create_list(api, anna)
    await added(api, anna, frozen_list["id"], meal["id"])
    await api.delete(f"/api/meals/{meal['id']}", headers=anna.headers)
    extra_list = await create_list(api, anna)
    [item] = (await extra_added(api, anna, extra_list["id"], ingredient_id=flour["id"]))[
        "extra_items"
    ]
    other_list = await create_list(api, anna)
    await extra_added(api, anna, other_list["id"], ingredient_id=flour["id"])

    for ingredient, lists_count in ((salt, 1), (flour, 2)):
        response = await api.delete(
            f"/api/admin/ingredients/{ingredient['id']}", headers=admin.headers
        )
        assert response.status_code == 409
        assert response.json()["params"] == {"meals": 0, "lists": lists_count}

    # Deleted extra items do not count; their tombstones go with the ingredient.
    await api.delete(f"/api/lists/{other_list['id']}", headers=anna.headers)
    await api.delete(
        f"/api/lists/{extra_list['id']}/extra-items/{item['id']}", headers=anna.headers
    )
    response = await api.delete(f"/api/admin/ingredients/{flour['id']}", headers=admin.headers)
    assert response.status_code == 204
    assert await scalars(app, select(ListExtraItem.id)) == []


async def test_merging_ingredients(
    app: FastAPI, api: AsyncClient, anna: Account, admin: Account
) -> None:
    duplicate = await create_ingredient(api, anna, "Paradeiser")
    tomatoes = await create_ingredient(api, anna, "Tomaten")
    other = await create_ingredient(api, anna, "Gurken")
    old_key, new_key = f"i:{duplicate['id']}", f"i:{tomatoes['id']}"
    live_meal = await meal_with(api, anna, "Salat", duplicate)
    gone_meal = await meal_with(api, anna, "Suppe", duplicate)
    live = await create_list(api, anna, "Live")
    await added(api, anna, live["id"], live_meal["id"])
    await api.post(f"/api/lists/{live['id']}/lines/{old_key}/hide", headers=anna.headers)
    frozen = await create_list(api, anna, "Frozen")
    await added(api, anna, frozen["id"], gone_meal["id"])
    await api.delete(f"/api/meals/{gone_meal['id']}", headers=anna.headers)
    extras = await create_list(api, anna, "Extras")
    await extra_added(api, anna, extras["id"], ingredient_id=duplicate["id"], amount=1, unit="kg")
    await extra_added(api, anna, extras["id"], ingredient_id=tomatoes["id"], amount=500, unit="g")
    await api.post(f"/api/lists/{extras['id']}/lines/{old_key}/hide", headers=anna.headers)
    shown = await create_list(api, anna, "Shown")
    await extra_added(api, anna, shown["id"], ingredient_id=tomatoes["id"])
    for key, action in ((old_key, "hide"), (new_key, "hide"), (new_key, "unhide")):
        await api.post(f"/api/lists/{shown['id']}/lines/{key}/{action}", headers=anna.headers)
    both_checked = await create_list(api, anna, "Both")
    one_checked = await create_list(api, anna, "One")
    for shopping_list in (both_checked, one_checked):
        for key in (old_key, new_key):
            await api.post(
                f"/api/lists/{shopping_list['id']}/lines/{key}/hide", headers=anna.headers
            )
    await run(
        app,
        update(ListLineState)
        .where(ListLineState.list_id == both_checked["id"])
        .values(checked=True),
    )
    await run(
        app,
        update(ListLineState)
        .where(ListLineState.list_id == one_checked["id"], ListLineState.line_key == old_key)
        .values(checked=True),
    )
    unrelated = await create_list(api, anna, "Unrelated")
    await extra_added(api, anna, unrelated["id"], ingredient_id=other["id"])
    lists = (live, frozen, extras, shown, both_checked, one_checked, unrelated)
    versions = {item["id"]: (await detail(api, anna, item["id"]))["version"] for item in lists}

    response = await api.post(
        f"/api/admin/ingredients/{duplicate['id']}/merge",
        json={"into_id": tomatoes["id"]},
        headers=admin.headers,
    )

    assert response.status_code == 200
    after = {item["id"]: await detail(api, anna, item["id"]) for item in lists}
    assert {list_id: body["version"] - versions[list_id] for list_id, body in after.items()} == {
        live["id"]: 1,
        frozen["id"]: 1,
        extras["id"]: 1,
        shown["id"]: 1,
        both_checked["id"]: 1,
        one_checked["id"]: 1,
        unrelated["id"]: 0,
    }
    assert line(after[live["id"]], "Tomaten")["hidden"] is True
    assert line(after[live["id"]], "Tomaten")["key"] == new_key
    assert lines(after[frozen["id"]]) == {"Tomaten": ([(100, "g")], False)}
    # A line hidden while its target was shown is shown after the merge.
    merged = line(after[extras["id"]], "Tomaten")
    assert (merged["hidden"], merged["amounts"]) == (False, [{"value": 1.5, "unit": "kg"}])
    assert line(after[shown["id"]], "Tomaten")["hidden"] is False
    states = {
        (row.list_id, row.line_key): (row.hidden, row.checked)
        for row in await scalars(app, select(ListLineState))
    }
    assert states == {
        (live["id"], new_key): (True, False),
        (shown["id"], new_key): (False, False),
        (both_checked["id"], new_key): (True, True),
        (one_checked["id"], new_key): (True, False),
    }
    frozen_rows = await scalars(app, select(ListMealIngredient))
    assert [(row.ingredient_id, row.ingredient_name_snapshot) for row in frozen_rows] == [
        (tomatoes["id"], "Paradeiser")
    ]


async def test_merging_line_states_by_the_lines_the_lists_have(
    app: FastAPI, api: AsyncClient, anna: Account, admin: Account
) -> None:
    """A state only counts for an ingredient with a line on the list: a kept state of a line
    that is gone (LIST-07) never hides or shows the merged line."""
    duplicate = await create_ingredient(api, anna, "Paradeiser")
    tomatoes = await create_ingredient(api, anna, "Tomaten")
    old_key, new_key = f"i:{duplicate['id']}", f"i:{tomatoes['id']}"

    async def draft(name: str, *ingredients: Any, **states: bool) -> Any:
        """A list with linked extra items of the ingredients and the given `old`/`new` line
        states (hidden or not)."""
        shopping_list = await create_list(api, anna, name)
        for ingredient in ingredients:
            await extra_added(api, anna, shopping_list["id"], ingredient_id=ingredient["id"])
        for which, hidden in states.items():
            key = old_key if which == "old" else new_key
            for action in ("hide",) if hidden else ("hide", "unhide"):
                await api.post(
                    f"/api/lists/{shopping_list['id']}/lines/{key}/{action}", headers=anna.headers
                )
        return shopping_list

    hidden_source = await draft("Hidden source", duplicate, old=True, new=False)
    bare_source = await draft("Bare source", duplicate, new=True)
    shown_target = await draft("Shown target", tomatoes, old=True)
    both_hidden = await draft("Both hidden", duplicate, tomatoes, old=True, new=True)
    one_hidden = await draft("One hidden", duplicate, tomatoes, old=True, new=False)
    target_only = await draft("Target only", duplicate, tomatoes, new=True)
    both_checked = await draft("Both checked", duplicate, tomatoes, old=False, new=False)
    one_checked = await draft("One checked", duplicate, tomatoes, old=False, new=False)
    checked_at = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)
    check = {
        "checked": True,
        "checked_at": checked_at,
        "checked_by": anna.id,
        "checked_op_id": "0190c0de-0000-7000-8000-0000000000aa",
        "checked_snapshot": {"amounts": []},
    }
    await run(
        app,
        update(ListLineState)
        .where(ListLineState.list_id.in_((both_checked["id"], one_checked["id"])))
        .values(**check),
    )
    await run(
        app,
        update(ListLineState)
        .where(ListLineState.list_id == one_checked["id"], ListLineState.line_key == old_key)
        .values(checked=False, checked_at=None, checked_by=None, checked_op_id=None),
    )

    response = await api.post(
        f"/api/admin/ingredients/{duplicate['id']}/merge",
        json={"into_id": tomatoes["id"]},
        headers=admin.headers,
    )

    assert response.status_code == 200
    lists = (
        hidden_source,
        bare_source,
        shown_target,
        both_hidden,
        one_hidden,
        target_only,
        both_checked,
        one_checked,
    )
    hidden = {
        item["name"]: line(await detail(api, anna, item["id"]), "Tomaten")["hidden"]
        for item in lists
    }
    assert hidden == {
        # Only the source had a line: its state wins over the target's kept state.
        "Hidden source": True,
        "Bare source": False,
        # Only the target had a line: the source's kept state goes.
        "Shown target": False,
        # Both had lines: hidden only if both were.
        "Both hidden": True,
        "One hidden": False,
        "Target only": False,
        "Both checked": False,
        "One checked": False,
    }
    states = {
        (row.list_id, row.line_key): (
            row.hidden,
            row.checked,
            row.checked_at,
            row.checked_by,
            row.checked_op_id,
            row.checked_snapshot,
        )
        for row in await scalars(app, select(ListLineState))
    }
    unchecked = (None, None, None, None)
    assert states == {
        (hidden_source["id"], new_key): (True, False, *unchecked),
        (both_hidden["id"], new_key): (True, False, *unchecked),
        (one_hidden["id"], new_key): (False, False, *unchecked),
        (target_only["id"], new_key): (False, False, *unchecked),
        (both_checked["id"], new_key): (False, *check.values()),
        # Checked only if both were: the check-off details go with it.
        (one_checked["id"], new_key): (False, False, *unchecked),
    }
