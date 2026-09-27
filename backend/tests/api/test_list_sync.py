"""The local copy for offline use: `GET /api/lists/sync` with every list the viewer can edit
in a draft or being shopped, its ETag, and what it costs (SYNC-02, SYNC-10, CPL-02/05,
PERF-02)."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import Connection, event

from app.db.session import Database
from app.schemas.lists import ListsSync
from tests.accounts import Account, FakeClock, error, make_couple, make_user
from tests.catalog import create_ingredient
from tests.lists import (
    added,
    applied,
    check,
    create_list,
    detail,
    extra_added,
    op,
    start_shopping,
)
from tests.meals import create_meal

URL = "/api/lists/sync"


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
async def flour(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Mehl")


async def sync(api: AsyncClient, user: Account, etag: str | None = None) -> Response:
    headers = user.headers if etag is None else user.headers | {"If-None-Match": etag}
    response = await api.get(URL, headers=headers)
    assert response.status_code in (200, 304), response.text
    return response


async def synced(api: AsyncClient, user: Account) -> Any:
    response = await sync(api, user)
    assert response.status_code == 200
    return response.json()


async def synced_ids(api: AsyncClient, user: Account) -> list[str]:
    return [item["id"] for item in (await synced(api, user))["lists"]]


# --- what is in it (SYNC-02, SYNC-10) -------------------------------------------------------


async def test_the_lists_you_can_edit_that_are_open(
    api: AsyncClient,
    anna: Account,
    ben: Account,
    carl: Account,
    flour: Any,
    clock: FakeClock,
) -> None:
    await make_couple(api, anna, ben)
    draft = await create_list(api, anna, "Entwurf")
    clock.advance(minutes=1)
    being_shopped = await create_list(api, anna, "Einkauf")
    await extra_added(api, anna, being_shopped["id"], ingredient_id=flour["id"])
    await start_shopping(api, anna, being_shopped["id"])
    clock.advance(minutes=1)
    bens_shared = await create_list(api, ben, "Geteilt")
    bens_unshared = await create_list(api, ben, "Privat")
    await api.patch(
        f"/api/lists/{bens_unshared['id']}",
        json={"shared_with_partner": False},
        headers=ben.headers,
    )
    carls = await create_list(api, carl, "Öffentlich")  # anna sees it, read-only
    assert (await detail(api, anna, carls["id"]))["can_edit"] is False
    done = await create_list(api, anna, "Fertig")
    await extra_added(api, anna, done["id"], ingredient_id=flour["id"])
    await start_shopping(api, anna, done["id"])
    await applied(api, anna, done["id"], op("list.finish", at=clock.now))
    deleted = await create_list(api, anna, "Weg")
    assert (await api.delete(f"/api/lists/{deleted['id']}", headers=anna.headers)).is_success
    clock.advance(minutes=1)
    await api.patch(f"/api/lists/{draft['id']}", json={"name": "Neu"}, headers=anna.headers)

    response = await sync(api, anna)

    assert response.status_code == 200
    body = response.json()
    ListsSync.model_validate(body)
    assert body["generated_at"] == "2026-09-27T12:03:00Z"
    # Most recently edited first; each list exactly as its own GET shows it.
    ids = [draft["id"], bens_shared["id"], being_shopped["id"]]
    assert [item["id"] for item in body["lists"]] == ids
    assert body["lists"] == [await detail(api, anna, list_id) for list_id in ids]
    assert [item["status"] for item in body["lists"]] == ["draft", "draft", "shopping"]
    assert all(item["can_edit"] for item in body["lists"])
    assert [item["is_owner"] for item in body["lists"]] == [True, False, True]
    # ben's copy: his lists and anna's shared ones.
    assert await synced_ids(api, ben) == [
        draft["id"],
        bens_unshared["id"],
        bens_shared["id"],
        being_shopped["id"],
    ]
    assert await synced_ids(api, carl) == [carls["id"]]


async def test_lists_you_lost_access_to_disappear(
    api: AsyncClient, anna: Account, ben: Account, clock: FakeClock
) -> None:
    """SYNC-10: unshared, or the couple ended (CPL-05): the partner's lists leave the copy."""
    await make_couple(api, anna, ben)
    annas = await create_list(api, anna, "Anna")
    bens = await create_list(api, ben, "Ben")
    unshared = await create_list(api, ben, "Nicht mehr geteilt")
    assert set(await synced_ids(api, anna)) == {annas["id"], bens["id"], unshared["id"]}

    await api.patch(
        f"/api/lists/{unshared['id']}", json={"shared_with_partner": False}, headers=ben.headers
    )
    assert set(await synced_ids(api, anna)) == {annas["id"], bens["id"]}
    assert (await api.delete("/api/couple", headers=anna.headers)).status_code == 204

    assert await synced_ids(api, anna) == [annas["id"]]
    assert set(await synced_ids(api, ben)) == {bens["id"], unshared["id"]}


async def test_an_empty_copy_and_no_session(api: AsyncClient, anna: Account) -> None:
    body = await synced(api, anna)
    assert body == {"lists": [], "generated_at": "2026-09-27T12:00:00Z"}
    assert error(await api.get(URL)) == "common.unauthorized"


# --- the ETag (plan § 5.8) ------------------------------------------------------------------


async def test_the_etag_covers_the_lists_but_not_the_time(
    api: AsyncClient, anna: Account, ben: Account, flour: Any, clock: FakeClock
) -> None:
    await make_couple(api, anna, ben)
    shopping_list = await create_list(api, ben)
    list_id = shopping_list["id"]
    await extra_added(api, ben, list_id, ingredient_id=flour["id"])
    await start_shopping(api, ben, list_id)
    first = await sync(api, anna)
    etag = first.headers["etag"]
    assert etag.startswith('W/"')
    assert first.headers["cache-control"] == "no-cache"

    # Later, with nothing changed: `generated_at` moved on, the tag did not.
    clock.advance(minutes=1)
    again = await sync(api, anna)
    assert (again.headers["etag"], again.json()["generated_at"]) == (
        etag,
        "2026-09-27T12:01:00Z",
    )
    unchanged = await sync(api, anna, etag)
    assert (unchanged.status_code, unchanged.content) == (304, b"")
    assert unchanged.headers["etag"] == etag
    assert (await sync(api, anna, '"other", ' + etag.removeprefix("W/"))).status_code == 304
    # Specific to the viewer.
    assert (await sync(api, ben, etag)).status_code == 200

    # The partner checks a line off: a new tag and body.
    await applied(api, ben, list_id, check(f"i:{flour['id']}", at=clock.now))
    changed = await sync(api, anna, etag)
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag
    [item] = changed.json()["lists"]
    assert item["lines"][0]["checked"] is True
    # A list that leaves the copy changes it too.
    await applied(api, ben, list_id, op("list.finish", at=clock.now))
    gone = await sync(api, anna, changed.headers["etag"])
    assert (gone.status_code, gone.json()["lists"]) == (200, [])


# --- what it costs (PERF-02) ----------------------------------------------------------------


@contextmanager
def counted_queries(app: FastAPI) -> Iterator[list[str]]:
    """The statements the read engine runs meanwhile (authentication included)."""
    database: Database = app.state.database
    statements: list[str] = []

    def record(_conn: Connection, _cursor: object, statement: str, *_: object) -> None:
        statements.append(statement)

    engine = database.read_engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


async def queries_of_a_sync(app: FastAPI, api: AsyncClient, user: Account) -> int:
    with counted_queries(app) as statements:
        await synced(api, user)
    return len(statements)


async def test_one_detail_build_per_list_and_the_cache(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, flour: Any
) -> None:
    """Each list costs the queries of one detail build, whatever it holds; lists that did not
    change since they were last read come from the list cache, shared with polling."""
    await make_couple(api, anna, ben)
    salt = await create_ingredient(api, anna, "Salz")
    rows = [{"ingredient_id": item["id"], "amount": 10, "unit": "g"} for item in (flour, salt)]
    meal = await create_meal(api, anna, "Brot", ingredients=rows)
    empty = await queries_of_a_sync(app, api, anna)

    lists = []
    for index in range(6):
        owner = anna if index % 2 else ben
        shopping_list = await create_list(api, owner, f"Liste {index}")
        await added(api, owner, shopping_list["id"], meal["id"])
        for number in range(index * 5):
            await extra_added(api, owner, shopping_list["id"], text=f"Extra {number}")
        lists.append(shopping_list)
    carl = await make_user(app, api, "carl")
    carls = await create_list(api, carl)
    await added(api, carl, carls["id"], meal["id"])
    await extra_added(api, carl, carls["id"], text="Extra")
    per_list = await queries_of_a_sync(app, api, carl) - empty

    assert await queries_of_a_sync(app, api, anna) == empty + 6 * per_list
    assert per_list <= 10
    # Nothing written since: every list from the cache.
    assert await queries_of_a_sync(app, api, anna) == empty
    # After a write, a list polled since comes from the cache, the others are built again.
    await extra_added(api, anna, lists[1]["id"], text="Noch eins")
    await detail(api, anna, lists[1]["id"])
    assert await queries_of_a_sync(app, api, anna) == empty + 5 * per_list
    assert await queries_of_a_sync(app, api, anna) == empty
