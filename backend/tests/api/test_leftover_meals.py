"""Leftover meals (LIST-17, D-58): a new draft brings along the meals of the most recently
finished list one can edit that aren't eaten, if that list was finished at most 14 days ago.
They add no lines; ticking one marks its source meal eaten, which takes it off every draft;
"Doch einkaufen" makes it a normal meal again and "Entfernen" takes it off one draft."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response

from tests.accounts import (
    Account,
    FakeClock,
    error,
    login,
    make_couple,
    make_user,
    set_privacy,
)
from tests.catalog import category_ids, create_item
from tests.lists import (
    added,
    applied,
    create_list,
    detail,
    lines,
    op,
    results,
    send_ops,
    start_shopping,
)
from tests.meals import create_meal


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@pytest.fixture
async def ben(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "ben")


@pytest.fixture
async def meals(api: AsyncClient, anna: Account) -> dict[str, Any]:
    categories = await category_ids(api, anna)
    flour = await create_item(api, anna, "Mehl", category_id=categories["baking"])
    beans = await create_item(api, anna, "Bohnen", category_id=categories["baking"])
    return {
        "Brot": await create_meal(
            api, anna, "Brot", ingredients=[{"item_id": flour["id"], "amount": 500, "unit": "g"}]
        ),
        "Chili": await create_meal(
            api, anna, "Chili", ingredients=[{"item_id": beans["id"], "amount": 400, "unit": "g"}]
        ),
        "Pizza": await create_meal(
            api, anna, "Pizza", ingredients=[{"item_id": flour["id"], "amount": 300, "unit": "g"}]
        ),
    }


async def finished(api: AsyncClient, user: Account, list_id: str) -> Any:
    await start_shopping(api, user, list_id)
    return await applied(api, user, list_id, op("list.finish"))


async def done_list(
    api: AsyncClient, user: Account, meals: list[Any], *, name: str = "Woche"
) -> Any:
    shopping_list = await create_list(api, user, name)
    for meal in meals:
        await added(api, user, shopping_list["id"], meal["id"])
    return await finished(api, user, shopping_list["id"])


def set_eaten(
    api: AsyncClient, user: Account, list_id: str, list_meal_id: str, *, eaten: bool
) -> Any:
    return api.put(
        f"/api/lists/{list_id}/meals/{list_meal_id}/eaten",
        json={"eaten": eaten},
        headers=user.headers,
    )


def shop(api: AsyncClient, user: Account, list_id: str, list_meal_id: str) -> Any:
    return api.post(f"/api/lists/{list_id}/meals/{list_meal_id}/shop", headers=user.headers)


def meal_rows(list_detail: Any) -> list[tuple[str, bool, bool]]:
    """Per meal: its name, whether it is a leftover and whether it is eaten."""
    return [(entry["name"], entry["leftover"], entry["eaten"]) for entry in list_detail["meals"]]


def by_name(list_detail: Any, name: str) -> Any:
    return next(entry for entry in list_detail["meals"] if entry["name"] == name)


async def eat(api: AsyncClient, user: Account, list_detail: Any, name: str) -> Any:
    response: Response = await set_eaten(
        api, user, list_detail["id"], by_name(list_detail, name)["id"], eaten=True
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- carry-over ---------------------------------------------------------------------------


async def test_a_new_draft_brings_the_uneaten_meals_of_the_last_done_list(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    older = await done_list(api, anna, [meals["Pizza"]], name="Vorletzte")
    await eat(api, anna, older, "Pizza")
    done = await done_list(api, anna, [meals["Brot"], meals["Chili"]])
    await eat(api, anna, done, "Brot")

    draft = await create_list(api, anna, "Neu")

    # Only the last done list counts, and only what isn't eaten; it adds no lines.
    assert meal_rows(draft) == [("Chili", True, False)]
    assert draft["lines"] == []
    chili = draft["meals"][0]
    assert (chili["meal_id"], chili["servings"]) == (meals["Chili"]["id"], 1)
    summary = next(
        row
        for row in (await api.get("/api/lists", headers=anna.headers)).json()["lists"]
        if row["id"] == draft["id"]
    )
    assert (summary["meal_count"], summary["line_count"]) == (1, 0)
    # A second draft gets them too; the done lists stay as they were.
    second = await create_list(api, anna, "Noch eine")
    assert meal_rows(second) == [("Chili", True, False)]
    assert meal_rows(await detail(api, anna, done["id"])) == [
        ("Brot", False, True),
        ("Chili", False, False),
    ]
    assert meal_rows(await detail(api, anna, older["id"])) == [("Pizza", False, True)]


async def test_lists_finished_more_than_14_days_ago_bring_nothing(
    api: AsyncClient, anna: Account, clock: FakeClock, meals: dict[str, Any]
) -> None:
    await done_list(api, anna, [meals["Brot"]])

    clock.advance(days=14)
    await login(api, anna)
    assert meal_rows(await create_list(api, anna)) == [("Brot", True, False)]

    clock.advance(seconds=1)
    await login(api, anna)
    assert meal_rows(await create_list(api, anna)) == []


async def test_the_partners_shared_done_list_counts_but_not_an_unshared_one(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock, meals: dict[str, Any]
) -> None:
    await make_couple(api, anna, ben)
    await done_list(api, anna, [meals["Brot"]])
    clock.advance(minutes=1)
    await login(api, anna)
    await login(api, ben)
    unshared = await create_list(api, anna, "Privat")
    assert meal_rows(unshared) == [("Brot", True, False)]
    await api.patch(
        f"/api/lists/{unshared['id']}", json={"shared_with_partner": False}, headers=anna.headers
    )
    await added(api, anna, unshared["id"], meals["Pizza"]["id"])
    await finished(api, anna, unshared["id"])

    # ben can't edit anna's unshared list, so her shared one is his last done list ...
    assert meal_rows(await create_list(api, ben)) == [("Brot", True, False)]
    # ... while hers is the unshared one, with the leftover it got.
    assert meal_rows(await create_list(api, anna)) == [
        ("Brot", True, False),
        ("Pizza", True, False),
    ]


async def test_with_carry_over_off_a_new_draft_starts_empty(
    api: AsyncClient, anna: Account, ben: Account, meals: dict[str, Any]
) -> None:
    await make_couple(api, anna, ben)
    first = await create_list(api, anna, "Woche")
    await added(api, anna, first["id"], meals["Brot"]["id"])
    await added(api, anna, first["id"], meals["Chili"]["id"])
    done = await finished(api, anna, first["id"])
    draft = await create_list(api, anna, "Mit Resten")
    response = await api.patch(
        "/api/me", json={"carry_over_leftovers": False}, headers=anna.headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["carry_over_leftovers"] is False

    # Off: anna's new drafts start empty ...
    assert meal_rows(await create_list(api, anna, "Leer")) == []
    # ... her partner's setting is his own ...
    me = (await api.get("/api/me", headers=ben.headers)).json()
    assert me["carry_over_leftovers"] is True
    assert meal_rows(await create_list(api, ben)) == [
        ("Brot", True, False),
        ("Chili", True, False),
    ]
    # ... and the leftovers that exist and the eaten checkboxes still work.
    assert meal_rows(await detail(api, anna, draft["id"])) == [
        ("Brot", True, False),
        ("Chili", True, False),
    ]
    await eat(api, anna, draft, "Brot")
    await eat(api, anna, done, "Chili")
    assert meal_rows(await detail(api, anna, draft["id"])) == []
    assert meal_rows(await detail(api, anna, done["id"])) == [
        ("Brot", False, True),
        ("Chili", False, True),
    ]
    # On again, new drafts bring the uneaten ones again.
    response = await set_eaten(api, anna, done["id"], by_name(done, "Chili")["id"], eaten=False)
    assert response.status_code == 200, response.text
    await api.patch("/api/me", json={"carry_over_leftovers": True}, headers=anna.headers)
    assert meal_rows(await create_list(api, anna)) == [("Chili", True, False)]


async def test_leftovers_carry_over_again_until_they_are_eaten(
    api: AsyncClient, anna: Account, clock: FakeClock, meals: dict[str, Any]
) -> None:
    first = await done_list(api, anna, [meals["Brot"], meals["Chili"]])
    draft = await create_list(api, anna, "Zweite")
    await added(api, anna, draft["id"], meals["Pizza"]["id"])

    # Shopping keeps the leftovers, still without lines.
    shopping = await start_shopping(api, anna, draft["id"])
    assert meal_rows(shopping) == [
        ("Brot", True, False),
        ("Chili", True, False),
        ("Pizza", False, False),
    ]
    assert list(lines(shopping)) == ["Mehl"]
    assert lines(shopping)["Mehl"][0] == [(300.0, "g")]
    second = await applied(api, anna, draft["id"], op("list.finish"))
    second = await eat(api, anna, second, "Brot")
    # Eating a leftover on a done list marks its source meal.
    assert meal_rows(second) == [
        ("Brot", True, True),
        ("Chili", True, False),
        ("Pizza", False, False),
    ]
    assert meal_rows(await detail(api, anna, first["id"]))[0] == ("Brot", False, True)

    third = await create_list(api, anna, "Dritte")

    assert meal_rows(third) == [("Chili", True, False), ("Pizza", True, False)]
    # Eating Chili on the first list takes it off the third, through the second.
    await eat(api, anna, await detail(api, anna, first["id"]), "Chili")
    assert meal_rows(await detail(api, anna, third["id"])) == [("Pizza", True, False)]


async def test_a_reopened_list_no_longer_feeds_new_drafts(
    api: AsyncClient, anna: Account, clock: FakeClock, meals: dict[str, Any]
) -> None:
    await done_list(api, anna, [meals["Pizza"]], name="Vorletzte")
    clock.advance(minutes=1)
    await login(api, anna)
    done = await done_list(api, anna, [meals["Brot"]])
    draft = await create_list(api, anna)

    reopened = await api.post(f"/api/lists/{done['id']}/reopen", headers=anna.headers)
    assert reopened.status_code == 200, reopened.text

    # The leftovers that exist keep their source; a new draft takes the list before.
    assert meal_rows(await detail(api, anna, draft["id"])) == [
        ("Pizza", True, False),
        ("Brot", True, False),
    ]
    assert meal_rows(await create_list(api, anna)) == [("Pizza", True, False)]


async def test_shop_again_and_copies_are_unchanged(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    await done_list(api, anna, [meals["Brot"]], name="Vorher")
    done = await done_list(api, anna, [meals["Chili"]])
    assert meal_rows(done) == [("Brot", True, False), ("Chili", False, False)]

    for action in ("shop-again", "copy"):
        response = await api.post(f"/api/lists/{done['id']}/{action}", headers=anna.headers)
        assert response.status_code in (200, 201), response.text
        copy = response.json()["list"]
        # Every meal of the list comes as a normal meal, leftovers of their own none.
        assert meal_rows(copy) == [("Brot", False, False), ("Chili", False, False)]
        assert list(lines(copy)) == ["Bohnen", "Mehl"]


# --- ticking ------------------------------------------------------------------------------


async def test_ticking_a_leftover_marks_its_source_eaten_everywhere(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock, meals: dict[str, Any]
) -> None:
    await make_couple(api, anna, ben)
    done = await done_list(api, anna, [meals["Brot"], meals["Chili"]])
    one = await create_list(api, anna, "Eins")
    two = await create_list(api, ben, "Zwei")
    clock.advance(minutes=1)
    await login(api, anna)
    await login(api, ben)

    # ben ticks Chili on his draft: it leaves both drafts and is eaten on the done list.
    response = await set_eaten(api, ben, two["id"], by_name(two, "Chili")["id"], eaten=True)

    assert response.status_code == 200, response.text
    body = response.json()
    assert meal_rows(body) == [("Brot", True, False)]
    assert body["version"] == two["version"] + 1
    after_one = await detail(api, anna, one["id"])
    assert meal_rows(after_one) == [("Brot", True, False)]
    assert after_one["version"] == one["version"] + 1
    after_done = await detail(api, anna, done["id"])
    assert meal_rows(after_done) == [("Brot", False, False), ("Chili", False, True)]
    assert after_done["version"] == done["version"] + 1

    # Unticking (the undo) brings it back on every draft.
    response = await set_eaten(api, ben, two["id"], by_name(two, "Chili")["id"], eaten=False)
    assert meal_rows(response.json()) == [("Brot", True, False), ("Chili", True, False)]
    assert meal_rows(await detail(api, anna, one["id"]))[1] == ("Chili", True, False)

    # Ticking on the done list removes it from every draft too, and changes them.
    before = {
        draft["id"]: (await detail(api, anna, draft["id"]))["version"] for draft in (one, two)
    }
    await eat(api, anna, after_done, "Brot")
    for draft in (one, two):
        now = await detail(api, anna, draft["id"])
        assert (meal_rows(now), now["version"]) == (
            [("Chili", True, False)],
            before[draft["id"]] + 1,
        )


async def test_normal_meals_of_drafts_still_cant_be_eaten(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    await done_list(api, anna, [meals["Brot"]])
    draft = await create_list(api, anna)
    draft = await added(api, anna, draft["id"], meals["Pizza"]["id"])

    response = await set_eaten(api, anna, draft["id"], by_name(draft, "Pizza")["id"], eaten=True)

    assert (response.status_code, error(response)) == (409, "list.not_done")


# --- servings, Doch einkaufen, Entfernen --------------------------------------------------


async def test_a_leftovers_servings_cant_change(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    await done_list(api, anna, [meals["Brot"]])
    draft = await create_list(api, anna)

    response = await api.patch(
        f"/api/lists/{draft['id']}/meals/{draft['meals'][0]['id']}",
        json={"servings": 4},
        headers=anna.headers,
    )

    assert (response.status_code, error(response)) == (409, "list_meal.leftover")


async def test_shopping_for_a_leftover_after_all(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    done = await done_list(api, anna, [meals["Brot"], meals["Chili"]])
    draft = await create_list(api, anna)

    response = await shop(api, anna, draft["id"], by_name(draft, "Chili")["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert meal_rows(body) == [("Brot", True, False), ("Chili", False, False)]
    assert lines(body) == {"Bohnen": ([(400.0, "g")], False)}
    # It is a normal meal now: its servings change, and eating the source no longer hides it.
    await eat(api, anna, done, "Chili")
    assert meal_rows(await detail(api, anna, draft["id"]))[1] == ("Chili", False, False)
    # A normal meal can't be shopped for "again".
    response = await shop(api, anna, draft["id"], by_name(body, "Chili")["id"])
    assert (response.status_code, error(response)) == (409, "list_meal.not_leftover")


async def test_shopping_for_a_leftover_already_on_the_list_raises_its_servings(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    await done_list(api, anna, [meals["Brot"]])
    draft = await create_list(api, anna)
    # Adding the meal itself makes a normal row next to the leftover.
    draft = await added(api, anna, draft["id"], meals["Brot"]["id"], servings=3)
    assert meal_rows(draft) == [("Brot", True, False), ("Brot", False, False)]

    response = await shop(api, anna, draft["id"], draft["meals"][0]["id"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert [(row["name"], row["leftover"], row["servings"]) for row in body["meals"]] == [
        ("Brot", False, 4)
    ]


async def test_shopping_for_a_leftover_while_shopping_freezes_it(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    await done_list(api, anna, [meals["Chili"]])
    draft = await create_list(api, anna)
    await start_shopping(api, anna, draft["id"])

    response = await shop(api, anna, draft["id"], draft["meals"][0]["id"])

    assert response.status_code == 200, response.text
    assert list(lines(response.json())) == ["Bohnen"]
    # Edits of the meal no longer reach the list.
    await api.patch(
        f"/api/meals/{meals['Chili']['id']}", json={"servings": 4}, headers=anna.headers
    )
    assert lines(await detail(api, anna, draft["id"])) == {"Bohnen": ([(400.0, "g")], False)}


async def test_a_deleted_meal_cant_be_shopped_for_again(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    await done_list(api, anna, [meals["Chili"]])
    draft = await create_list(api, anna)
    await api.delete(f"/api/meals/{meals['Chili']['id']}", headers=anna.headers)

    response = await shop(api, anna, draft["id"], draft["meals"][0]["id"])

    assert (response.status_code, error(response)) == (409, "list_meal.unavailable")


async def test_removing_a_leftover_takes_it_off_this_draft_only(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    done = await done_list(api, anna, [meals["Brot"]])
    one = await create_list(api, anna)
    two = await create_list(api, anna)

    response = await api.delete(
        f"/api/lists/{one['id']}/meals/{one['meals'][0]['id']}", headers=anna.headers
    )

    assert response.status_code == 200, response.text
    assert meal_rows(response.json()) == []
    assert meal_rows(await detail(api, anna, two["id"])) == [("Brot", True, False)]
    assert meal_rows(await detail(api, anna, done["id"])) == [("Brot", False, False)]


async def test_a_copy_has_a_meal_on_the_list_twice_once(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    await done_list(api, anna, [meals["Brot"]])
    draft = await create_list(api, anna)
    await added(api, anna, draft["id"], meals["Brot"]["id"], servings=2)

    response = await api.post(f"/api/lists/{draft['id']}/copy", headers=anna.headers)

    assert response.status_code == 201, response.text
    body = response.json()
    assert [(row["name"], row["leftover"], row["servings"]) for row in body["list"]["meals"]] == [
        ("Brot", False, 3)
    ]
    assert body["left_out"] == 0


async def test_ticking_a_leftover_while_shopping_marks_its_source(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    done = await done_list(api, anna, [meals["Brot"]])
    draft = await create_list(api, anna)
    shopping = await start_shopping(api, anna, draft["id"])

    response = await set_eaten(api, anna, draft["id"], shopping["meals"][0]["id"], eaten=True)

    assert response.status_code == 200, response.text
    assert meal_rows(response.json()) == []
    assert meal_rows(await detail(api, anna, done["id"])) == [("Brot", False, True)]


async def test_a_leftover_needs_edit_rights_on_its_source(
    api: AsyncClient, anna: Account, ben: Account, meals: dict[str, Any]
) -> None:
    """Once the couple ended, ben can't mark anna's list eaten through the leftover on his
    draft (CPL-03, CPL-05)."""
    await make_couple(api, anna, ben)
    done = await done_list(api, anna, [meals["Brot"]])
    draft = await create_list(api, ben)
    assert (await api.delete("/api/couple", headers=anna.headers)).status_code == 204

    response = await set_eaten(api, ben, draft["id"], draft["meals"][0]["id"], eaten=True)

    assert (response.status_code, error(response)) == (403, "common.forbidden")
    assert meal_rows(await detail(api, anna, done["id"])) == [("Brot", False, False)]


async def test_a_leftover_of_a_meal_one_can_no_longer_see_cant_be_shopped_for(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, meals: dict[str, Any]
) -> None:
    """A leftover of a meal the viewer may not see is private (VIS-06); it stays a leftover."""
    carl = await make_user(app, api, "carl")
    curry = await create_meal(api, carl, "Curry", ingredients=[])
    await make_couple(api, anna, ben)
    await done_list(api, anna, [curry])
    await set_privacy(api, carl, meals_public=False)
    draft = await create_list(api, ben)
    [entry] = draft["meals"]
    assert (entry["private"], entry["name"], entry["leftover"]) == (True, None, True)

    response = await shop(api, ben, draft["id"], entry["id"])

    assert (response.status_code, error(response)) == (409, "list_meal.unavailable")


async def test_leftovers_go_with_their_source_and_their_lists_change(
    api: AsyncClient, anna: Account, clock: FakeClock, meals: dict[str, Any]
) -> None:
    done = await done_list(api, anna, [meals["Brot"], meals["Chili"]])
    draft = await create_list(api, anna)
    clock.advance(minutes=1)
    await login(api, anna)
    # The source list reopened, one of its meals removed: its leftover goes, the draft changes.
    reopened = (await api.post(f"/api/lists/{done['id']}/reopen", headers=anna.headers)).json()
    response = await api.delete(
        f"/api/lists/{done['id']}/meals/{by_name(reopened, 'Brot')['id']}", headers=anna.headers
    )
    assert response.status_code == 200, response.text
    after = await detail(api, anna, draft["id"])
    assert (meal_rows(after), after["version"]) == ([("Chili", True, False)], draft["version"] + 1)

    response = await api.delete(f"/api/lists/{done['id']}", headers=anna.headers)

    assert response.status_code == 204, response.text
    gone = await detail(api, anna, draft["id"])
    assert (meal_rows(gone), gone["version"]) == ([], after["version"] + 1)


# --- the leftover.eaten op (offline, SYNC-03) ---------------------------------------------


def eaten_op(source_id: str, eaten: bool = True, **options: Any) -> Any:
    return op("leftover.eaten", leftover_of=source_id, eaten=eaten, **options)


async def test_a_leftover_names_its_source_meal(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    """Two drafts' leftovers of one meal have different ids but name the same source, so the
    app can hide it on every local draft at once."""
    done = await done_list(api, anna, [meals["Brot"]])
    one = await create_list(api, anna)
    two = await create_list(api, anna)

    source = by_name(done, "Brot")
    assert source["leftover_of"] is None
    assert one["meals"][0]["id"] != two["meals"][0]["id"]
    assert one["meals"][0]["leftover_of"] == two["meals"][0]["leftover_of"] == source["id"]


async def test_the_op_marks_a_leftovers_source_eaten_everywhere(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock, meals: dict[str, Any]
) -> None:
    await make_couple(api, anna, ben)
    done = await done_list(api, anna, [meals["Brot"], meals["Chili"]])
    one = await create_list(api, anna, "Eins")
    two = await create_list(api, ben, "Zwei")
    clock.advance(minutes=1)
    await login(api, anna)
    await login(api, ben)
    chili = by_name(done, "Chili")["id"]

    body = await applied(api, ben, two["id"], eaten_op(chili))

    assert meal_rows(body) == [("Brot", True, False)]
    assert body["version"] == two["version"] + 1
    after_one = await detail(api, anna, one["id"])
    assert (meal_rows(after_one), after_one["version"]) == (
        [("Brot", True, False)],
        one["version"] + 1,
    )
    after_done = await detail(api, anna, done["id"])
    assert meal_rows(after_done) == [("Brot", False, False), ("Chili", False, True)]
    assert after_done["version"] == done["version"] + 1

    # The undo, also queued: it comes back on every draft.
    body = await applied(api, ben, two["id"], eaten_op(chili, eaten=False))
    assert meal_rows(body) == [("Brot", True, False), ("Chili", True, False)]
    assert meal_rows(await detail(api, anna, one["id"]))[1] == ("Chili", True, False)


async def test_the_op_works_while_shopping_and_changes_nothing_twice(
    api: AsyncClient, anna: Account, meals: dict[str, Any]
) -> None:
    done = await done_list(api, anna, [meals["Brot"]])
    draft = await create_list(api, anna)
    shopping = await start_shopping(api, anna, draft["id"])
    tick = eaten_op(by_name(done, "Brot")["id"])

    body = await applied(api, anna, draft["id"], tick)
    again = await send_ops(api, anna, draft["id"], tick)
    same = await send_ops(api, anna, draft["id"], eaten_op(by_name(done, "Brot")["id"]))

    assert (meal_rows(body), body["version"]) == ([], shopping["version"] + 1)
    assert results(again) == [("duplicate", None)]
    # Already eaten: applied, but the list doesn't change.
    assert results(same) == [("applied", None)]
    assert same.json()["list"]["version"] == body["version"]
    assert meal_rows(await detail(api, anna, done["id"])) == [("Brot", False, True)]


async def test_the_last_change_to_arrive_wins(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock, meals: dict[str, Any]
) -> None:
    """The flag has no dates (D-55): anna's tick made offline before ben's untick still wins
    when it arrives after it."""
    await make_couple(api, anna, ben)
    done = await done_list(api, anna, [meals["Brot"]])
    draft = await create_list(api, anna)
    his = await create_list(api, ben)
    tapped = clock.now
    clock.advance(minutes=30)
    await login(api, anna)
    await login(api, ben)
    brot = by_name(done, "Brot")
    assert (await set_eaten(api, ben, done["id"], brot["id"], eaten=True)).status_code == 200
    assert (await set_eaten(api, ben, done["id"], brot["id"], eaten=False)).status_code == 200

    await applied(api, anna, draft["id"], eaten_op(brot["id"], at=tapped))

    assert meal_rows(await detail(api, ben, done["id"])) == [("Brot", False, True)]

    # Two queued changes from two drafts: the one arriving last wins, whatever its `at`.
    await applied(api, ben, his["id"], eaten_op(brot["id"], eaten=False, at=tapped))
    assert meal_rows(await detail(api, anna, done["id"])) == [("Brot", False, False)]


async def test_the_op_is_rejected_without_the_leftover_or_the_rights_on_its_source(
    api: AsyncClient, anna: Account, ben: Account, meals: dict[str, Any]
) -> None:
    await make_couple(api, anna, ben)
    done = await done_list(api, anna, [meals["Brot"], meals["Chili"]])
    draft = await create_list(api, ben)
    other = await create_list(api, ben)
    brot, chili = by_name(done, "Brot")["id"], by_name(done, "Chili")["id"]
    # Removed from this draft (Entfernen): nothing on it to tick any more.
    gone = by_name(other, "Chili")["id"]
    response = await api.delete(f"/api/lists/{other['id']}/meals/{gone}", headers=ben.headers)
    assert response.status_code == 200, response.text
    assert results(await send_ops(api, ben, other["id"], eaten_op(chili))) == [
        ("rejected", "common.not_found")
    ]
    # A leftover's own id names no source.
    assert results(await send_ops(api, ben, draft["id"], eaten_op(draft["meals"][0]["id"]))) == [
        ("rejected", "common.not_found")
    ]

    # Once the couple ended, ben may no longer mark anna's list (CPL-03, CPL-05).
    assert (await api.delete("/api/couple", headers=anna.headers)).status_code == 204
    response = await send_ops(api, ben, draft["id"], eaten_op(brot))

    assert results(response) == [("rejected", "common.forbidden")]
    assert meal_rows(await detail(api, anna, done["id"])) == [
        ("Brot", False, False),
        ("Chili", False, False),
    ]
