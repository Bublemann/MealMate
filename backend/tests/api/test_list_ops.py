"""The ops endpoint of shopping mode: every op type, access, idempotency, last-write-wins,
the rules for done lists and deleted items, and parallel requests (plan §§ 5.1 and 5.8,
SYNC-05/06, SHOP-02/04)."""

import asyncio
import uuid
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.models import ListExtraItem, ListLineState, ProcessedOp
from tests.accounts import (
    START,
    Account,
    FakeClock,
    error,
    fields,
    login,
    make_couple,
    make_user,
    scalars,
    set_privacy,
)
from tests.catalog import category_ids, create_ingredient, ref
from tests.lists import (
    applied,
    by_key,
    check,
    create_list,
    detail,
    extra_added,
    line,
    op,
    results,
    send_ops,
    set_status,
    start_shopping,
)

APPLIED = ("applied", None)
DUPLICATE = ("duplicate", None)


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


@pytest.fixture
async def salt(api: AsyncClient, anna: Account) -> Any:
    return await create_ingredient(api, anna, "Salz")


@pytest.fixture
async def shopping(api: AsyncClient, anna: Account, flour: Any, salt: Any) -> Any:
    """anna's list being shopped: flour (500 g) and salt."""
    shopping_list = await create_list(api, anna, "Einkauf")
    for ingredient, amount in ((flour, 500), (salt, None)):
        body = {"ingredient_id": ingredient["id"]}
        if amount is not None:
            body |= {"amount": amount, "unit": "g"}
        await extra_added(api, anna, shopping_list["id"], **body)
    return await start_shopping(api, anna, shopping_list["id"])


def key(ingredient: Any) -> str:
    return f"i:{ingredient['id']}"


def op_id(n: int) -> str:
    """Op ids in a known order."""
    return f"0190c0de-0000-7000-8000-{n:012d}"


def state(list_detail: Any, line_key: str) -> tuple[bool, str | None, str | None]:
    item = by_key(list_detail, line_key)
    name = None if item["checked_by"] is None else item["checked_by"]["display_name"]
    return item["checked"], item["checked_at"], name


# --- access and validation ------------------------------------------------------------------


async def test_ops_need_a_list_you_may_edit(
    api: AsyncClient, anna: Account, ben: Account, carl: Account, flour: Any
) -> None:
    await make_couple(api, anna, ben)
    shared = await create_list(api, anna, "Geteilt")
    unshared = await create_list(api, anna, "Privat")
    await api.patch(
        f"/api/lists/{unshared['id']}", json={"shared_with_partner": False}, headers=anna.headers
    )
    finish = op("list.finish")
    for shopping_list in (shared, unshared):
        await start_shopping(api, anna, shopping_list["id"])

    assert error(await send_ops(api, ben, unshared["id"], finish)) == "common.forbidden"
    assert error(await send_ops(api, carl, shared["id"], finish)) == "common.forbidden"
    await set_privacy(api, anna, lists_public=False)
    assert error(await send_ops(api, carl, shared["id"], finish)) == "common.not_found"
    unknown = await send_ops(api, anna, "0190c0de-0000-7000-8000-000000000000", finish)
    assert (unknown.status_code, error(unknown)) == (404, "common.not_found")
    response = await api.post(f"/api/lists/{shared['id']}/ops", json={"ops": [finish]})
    assert response.status_code == 401
    # Nothing happened on the refused requests.
    assert (await detail(api, anna, unshared["id"]))["status"] == "shopping"
    body = await applied(api, ben, shared["id"], check(key(flour)), finish)
    assert (body["status"], body["can_edit"], body["is_owner"]) == ("done", True, False)
    await api.delete(f"/api/lists/{shared['id']}", headers=anna.headers)
    assert error(await send_ops(api, ben, shared["id"], finish)) == "common.not_found"


def first(*loc: str) -> tuple[str | int, ...]:
    """Where a problem of the first op is reported."""
    return ("body", "ops", 0, *loc)


NAIVE = {**op("list.finish"), "at": "2026-09-27T12:00:00"}
NO_PAYLOAD = {"op_id": op_id(1), "type": "list.finish", "at": START.isoformat()}


@pytest.mark.parametrize(
    ("ops", "problem"),
    [
        ([], ("body", "ops")),
        ([op("list.finish")] * 101, ("body", "ops")),
        ([op("list.finish", op_id="nope")], first("list.finish", "op_id")),
        ([NAIVE], first("list.finish", "at")),
        ([{**op("list.finish"), "type": "list.delete"}], first()),
        ([NO_PAYLOAD], first("list.finish", "payload")),
        ([op("extra.add", extra_id=op_id(1), text="")], first("extra.add", "payload", "text")),
        ([op("extra.add", extra_id="x", text="a")], first("extra.add", "payload", "extra_id")),
        (
            [op("extra.update", extra_id=op_id(1), text="a" * 81)],
            first("extra.update", "payload", "text"),
        ),
        ([op("extra.delete")], first("extra.delete", "payload", "extra_id")),
        (
            [op("line.check", line_key="i:" + "a" * 79, checked=True)],
            first("line.check", "payload", "line_key"),
        ),
    ],
)
async def test_malformed_requests_are_refused_as_a_whole(
    api: AsyncClient, anna: Account, shopping: Any, ops: list[Any], problem: tuple[Any, ...]
) -> None:
    response = await send_ops(api, anna, shopping["id"], *ops)
    assert response.status_code == 422
    assert problem in fields(response)
    assert (await detail(api, anna, shopping["id"]))["status"] == "shopping"


# --- line.check -----------------------------------------------------------------------------


async def test_check_and_uncheck(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, flour: Any, salt: Any
) -> None:
    await make_couple(api, anna, ben)
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await extra_added(api, anna, list_id, ingredient_id=flour["id"], amount=500, unit="g")
    before = await start_shopping(api, anna, list_id)
    at = START - timedelta(minutes=3)

    response = await send_ops(api, ben, list_id, check(key(flour), at=at, op_id=op_id(1)))

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == [{"op_id": op_id(1), "status": "applied", "code": None}]
    assert state(body["list"], key(flour)) == (True, "2026-09-27T11:57:00Z", "Ben")
    assert body["list"]["version"] == before["version"] + 1
    [row] = await scalars(app, select(ListLineState).where(ListLineState.line_key == key(flour)))
    assert (row.checked_op_id, row.checked_by) == (op_id(1), ben.id)
    assert row.checked_snapshot == {
        "mass_g": 500,
        "has_unspecified": False,
        "base_total": 500,
        "base_unit": "g",
    }
    # Unchecking keeps the time of the tap (for last-write-wins) but not the rest.
    body = await applied(api, anna, list_id, check(key(flour), False, op_id=op_id(2)))
    assert state(body, key(flour)) == (False, None, None)
    [row] = await scalars(app, select(ListLineState).where(ListLineState.line_key == key(flour)))
    assert (row.checked, row.checked_at, row.checked_op_id) == (False, START, op_id(2))
    assert (row.checked_by, row.checked_snapshot) == (None, None)
    # A key without a line is fine, a key of another form is not.
    response = await send_ops(
        api,
        anna,
        list_id,
        check(key(salt)),
        check(f"i:{flour['id'].upper()}"),
        check("y:abc"),
        check(f"x:{uuid.uuid4()}"),
    )
    assert results(response) == [
        APPLIED,
        ("rejected", "common.validation"),
        ("rejected", "common.validation"),
        APPLIED,
    ]
    # Free-text lines store their text with the check-off.
    body = await extra_added(api, anna, list_id, text="Kerzen", amount_text="1 Packung")
    candles = f"x:{body['extra_items'][-1]['id']}"
    await applied(api, anna, list_id, check(candles))
    [snapshot] = await scalars(
        app, select(ListLineState.checked_snapshot).where(ListLineState.line_key == candles)
    )
    assert snapshot == {"has_unspecified": True, "text": "Kerzen", "amount_text": "1 Packung"}


async def test_the_last_tap_wins(
    api: AsyncClient, anna: Account, shopping: Any, flour: Any, clock: FakeClock
) -> None:
    """SYNC-06: compared by the time of the tap, not of sending; ties by the higher op id."""
    list_id, line_key = shopping["id"], key(flour)
    clock.advance(minutes=10)
    now, early, late = clock.now, START, START + timedelta(minutes=5)

    # A later uncheck arrives first; the earlier check loses (and changes nothing).
    body = await applied(api, anna, list_id, check(line_key, False, at=late, op_id=op_id(1)))
    version = body["version"]
    body = await applied(api, anna, list_id, check(line_key, at=early, op_id=op_id(2)))
    assert state(body, line_key) == (False, None, None)
    assert body["version"] == version
    # A later check wins over an earlier uncheck, in the same request too.
    body = await applied(
        api,
        anna,
        list_id,
        check(line_key, at=now, op_id=op_id(3)),
        check(line_key, False, at=late, op_id=op_id(4)),
    )
    assert state(body, line_key) == (True, "2026-09-27T12:10:00Z", "Anna")
    # At the same time, the higher op id wins, whatever arrives first.
    body = await applied(api, anna, list_id, check(line_key, False, at=now, op_id=op_id(9)))
    assert state(body, line_key)[0] is False
    body = await applied(api, anna, list_id, check(line_key, at=now, op_id=op_id(5)))
    assert state(body, line_key)[0] is False
    body = await applied(api, anna, list_id, check(line_key, at=now, op_id=op_id(10)))
    assert state(body, line_key)[0] is True


async def test_times_from_the_future_are_clamped(
    api: AsyncClient, anna: Account, shopping: Any, flour: Any, clock: FakeClock
) -> None:
    """A phone whose clock is ahead cannot win every later tap: `at` counts as at most five
    minutes after the server's time."""
    list_id, line_key = shopping["id"], key(flour)
    body = await applied(api, anna, list_id, check(line_key, at=START + timedelta(days=1)))
    assert state(body, line_key) == (True, "2026-09-27T12:05:00Z", "Anna")
    clock.advance(minutes=6)
    body = await applied(api, anna, list_id, check(line_key, False, at=clock.now))
    assert state(body, line_key)[0] is False
    # Times in any zone count as the same instant.
    in_berlin = (START + timedelta(minutes=7)).astimezone(ZoneInfo("Europe/Berlin"))
    body = await applied(api, anna, list_id, check(line_key, at=in_berlin))
    assert state(body, line_key) == (True, "2026-09-27T12:07:00Z", "Anna")


async def test_checks_from_before_shopping_started_are_refused(
    api: AsyncClient, anna: Account, shopping: Any, flour: Any, salt: Any, clock: FakeClock
) -> None:
    """A tap before the list was being shopped cannot count (it started at 12:00), while
    shopping and once done; a clock a few minutes behind is fine."""
    list_id = shopping["id"]
    long_before, shortly_before = START - timedelta(minutes=6), START - timedelta(minutes=4)
    response = await send_ops(
        api,
        anna,
        list_id,
        check(key(flour), at=long_before),
        check(key(salt), at=shortly_before),
    )
    assert results(response) == [("rejected", "list.not_shopping"), APPLIED]
    assert state(response.json()["list"], key(flour))[0] is False
    clock.advance(minutes=10)
    await applied(api, anna, list_id, op("list.finish", at=clock.now))
    response = await send_ops(
        api,
        anna,
        list_id,
        check(key(flour), at=long_before),
        check(key(flour), at=START + timedelta(minutes=1)),
    )
    assert results(response) == [("rejected", "list.not_shopping"), APPLIED]


@pytest.mark.parametrize("at", ["9999-12-31T23:00:00-05:00", "0001-01-01T00:30:00+05:00"])
async def test_times_out_of_range_are_invalid(
    api: AsyncClient, anna: Account, shopping: Any, flour: Any, at: str
) -> None:
    """A time that has no UTC time (past the ends of the calendar) makes only its op invalid,
    so the ops after it still count."""
    ops = [
        {**check(key(flour)), "at": at},
        {**op("list.finish"), "at": at},
        check(key(flour), False, at=START),
    ]
    response = await send_ops(api, anna, shopping["id"], *ops)
    assert results(response) == [("rejected", "common.validation")] * 2 + [APPLIED]
    assert response.json()["list"]["status"] == "shopping"


async def test_checks_on_done_lists_and_drafts(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    ben: Account,
    flour: Any,
    salt: Any,
    clock: FakeClock,
) -> None:
    """SYNC-06: taps made before the list was finished still count; later ones do not. A
    draft has nothing to check."""
    await make_couple(api, anna, ben)
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    await extra_added(api, anna, list_id, ingredient_id=flour["id"])
    await extra_added(api, anna, list_id, ingredient_id=salt["id"])
    response = await send_ops(api, anna, list_id, check(key(flour)), op("list.finish"))
    assert results(response) == [("rejected", "list.not_shopping")] * 2
    await start_shopping(api, anna, list_id)
    clock.advance(minutes=2)
    await applied(api, ben, list_id, op("list.finish", at=clock.now))  # finished at 12:02

    response = await send_ops(
        api,
        anna,
        list_id,
        check(key(flour), at=START + timedelta(minutes=1)),
        check(key(salt), at=START + timedelta(minutes=2)),
        check(key(salt), False, at=START + timedelta(minutes=2, seconds=1)),
    )

    assert results(response) == [APPLIED, APPLIED, ("rejected", "list.done")]
    body = response.json()["list"]
    assert (body["status"], state(body, key(salt))[0], state(body, key(flour))[0]) == (
        "done",
        True,
        True,
    )
    # A rejected op is not recorded: after reopening it can be sent again.
    rejected = check(key(salt), False, at=START + timedelta(minutes=3))
    assert results(await send_ops(api, anna, list_id, rejected)) == [("rejected", "list.done")]
    await api.post(f"/api/lists/{list_id}/reopen", headers=anna.headers)
    body = await applied(api, anna, list_id, rejected)
    assert state(body, key(salt))[0] is False
    # A done list without a finishing time (never through the API) takes no check-offs.
    await set_status(app, list_id, "done")
    assert results(await send_ops(api, anna, list_id, check(key(flour)))) == [
        ("rejected", "list.done")
    ]


# --- idempotency (SYNC-05) ------------------------------------------------------------------


async def test_ops_take_effect_once(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    ben: Account,
    shopping: Any,
    flour: Any,
    salt: Any,
) -> None:
    await make_couple(api, anna, ben)
    list_id = shopping["id"]
    ops = [
        check(key(flour), at=START - timedelta(minutes=1)),
        op("extra.add", extra_id=op_id(1), text="Kerzen"),
    ]
    first = await applied(api, anna, list_id, *ops)
    later = check(key(flour), False, at=START)
    await applied(api, anna, list_id, later)

    response = await send_ops(api, anna, list_id, *ops, later)

    assert results(response) == [DUPLICATE] * 3
    body = response.json()["list"]
    assert body["version"] == first["version"] + 1
    assert state(body, key(flour))[0] is False  # the resent check did not come back
    # Twice in one request; on another list of the same user it is still the same op.
    again = check(key(salt))
    assert results(await send_ops(api, anna, list_id, again, again)) == [APPLIED, DUPLICATE]
    mine = await create_list(api, anna)
    await start_shopping(api, anna, mine["id"])
    assert results(await send_ops(api, anna, mine["id"], again)) == [DUPLICATE]
    # Op ids come from the clients: another user's op with the same id is another op.
    other = await create_list(api, ben)
    await extra_added(api, ben, other["id"], ingredient_id=salt["id"])
    await start_shopping(api, ben, other["id"])
    body = await applied(api, ben, other["id"], again)
    assert state(body, key(salt)) == (True, "2026-09-27T12:00:00Z", "Ben")
    assert results(await send_ops(api, ben, other["id"], again)) == [DUPLICATE]
    rows = await scalars(app, select(ProcessedOp).order_by(ProcessedOp.applied_at))
    assert {(row.op_id, row.user_id, row.list_id) for row in rows} == {
        (item["op_id"], anna.id, list_id) for item in (*ops, later, again)
    } | {(again["op_id"], ben.id, other["id"])}
    # They go with the list.
    await api.delete(f"/api/lists/{list_id}", headers=anna.headers)
    assert {(row.user_id, row.list_id) for row in await scalars(app, select(ProcessedOp))} == {
        (ben.id, other["id"])
    }


# --- extra items ----------------------------------------------------------------------------


async def test_add_free_text_items(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account, shopping: Any
) -> None:
    await make_couple(api, anna, ben)
    await api.patch(
        f"/api/lists/{shopping['id']}", json={"shared_with_partner": True}, headers=anna.headers
    )
    categories = await category_ids(api, anna)
    list_id = shopping["id"]
    ids = [str(uuid.uuid7()) for _ in range(4)]

    candles = op(
        "extra.add",
        extra_id=ids[0],
        text=" Kerzen ",
        amount_text="1 Packung",
        category_key="household_hygiene",
    )
    body = await applied(
        api,
        ben,
        list_id,
        candles,
        op("extra.add", extra_id=ids[1].upper(), text="Grillkohle", category_key="nope"),
        op("extra.add", extra_id=ids[2], text="Servietten"),
    )

    items = {item["text"]: item for item in body["extra_items"]}
    assert items["Kerzen"] == {
        "id": ids[0],
        "ingredient_id": None,
        "text": "Kerzen",
        "amount": None,
        "unit": None,
        "amount_text": "1 Packung",
        "category_id": categories["household_hygiene"],
        "added_by": ref(ben),
        "created_at": "2026-09-27T12:00:00Z",
    }
    assert items["Grillkohle"]["id"] == ids[1]
    assert items["Grillkohle"]["category_id"] == items["Servietten"]["category_id"]
    assert items["Servietten"]["category_id"] == categories["other"]
    assert by_key(body, f"x:{ids[0]}")["new"] is True
    # The same id again is a duplicate, on another list it is taken.
    other = await create_list(api, anna)
    response = await send_ops(
        api,
        anna,
        list_id,
        op("extra.add", extra_id=ids[0], text="Anders"),
    )
    assert results(response) == [DUPLICATE]
    assert line(response.json()["list"], "Kerzen")["amount_text"] == "1 Packung"
    response = await send_ops(api, anna, other["id"], op("extra.add", extra_id=ids[0], text="x"))
    assert results(response) == [("rejected", "extra.id_taken")]
    # Drafts take them too, done lists do not.
    body = await applied(api, anna, other["id"], op("extra.add", extra_id=ids[3], text="Brot"))
    assert (line(body, "Brot")["new"], body["status"]) == (False, "draft")
    await applied(api, anna, list_id, op("list.finish"))
    response = await send_ops(api, anna, list_id, op("extra.add", extra_id=op_id(9), text="x"))
    assert results(response) == [("rejected", "list.done")]
    assert await scalars(app, select(ListExtraItem.id).where(ListExtraItem.id == op_id(9))) == []


async def test_update_and_delete_free_text_items(
    api: AsyncClient, anna: Account, shopping: Any, flour: Any
) -> None:
    list_id = shopping["id"]
    candles, napkins = op_id(1), op_id(2)
    await applied(
        api,
        anna,
        list_id,
        op("extra.add", extra_id=candles, text="Kerzen", amount_text="1 Packung"),
        op("extra.add", extra_id=napkins, text="Servietten"),
    )
    [linked] = [item for item in shopping["extra_items"] if item["ingredient_id"] == flour["id"]]
    version = (await detail(api, anna, list_id))["version"]

    body = await applied(
        api, anna, list_id, op("extra.update", extra_id=candles, text="Teelichter")
    )
    assert (line(body, "Teelichter")["amount_text"], body["version"]) == ("1 Packung", version + 1)
    body = await applied(
        api,
        anna,
        list_id,
        op("extra.update", extra_id=candles, text="Teelichter", amount_text=None),
    )
    assert line(body, "Teelichter")["amount_text"] is None
    body = await applied(
        api, anna, list_id, op("extra.update", extra_id=candles, text="Teelichter")
    )
    assert body["version"] == version + 2  # nothing changed
    response = await send_ops(
        api,
        anna,
        list_id,
        op("extra.update", extra_id=op_id(9), text="x"),
        op("extra.update", extra_id=linked["id"], text="x"),
        op("extra.delete", extra_id=op_id(9)),
    )
    assert results(response) == [
        ("rejected", "common.not_found"),
        ("rejected", "common.validation"),
        ("rejected", "common.not_found"),
    ]
    # Delete wins over an update, whatever the order (SYNC-06).
    body = await applied(
        api,
        anna,
        list_id,
        op("extra.delete", extra_id=napkins),
        op("extra.update", extra_id=napkins, text="Tücher"),
        op("extra.delete", extra_id=napkins),
    )
    assert sorted(str(item["text"]) for item in body["extra_items"]) == [
        "None",
        "None",
        "Teelichter",
    ]
    assert [item["name"] for item in body["lines"]] == ["Mehl", "Salz", "Teelichter"]
    # Items of other lists are unknown here; linked items can be deleted.
    other = await create_list(api, anna)
    await applied(api, anna, other["id"], op("extra.add", extra_id=op_id(7), text="x"))
    response = await send_ops(api, anna, list_id, op("extra.delete", extra_id=op_id(7)))
    assert results(response) == [("rejected", "common.not_found")]
    body = await applied(api, anna, list_id, op("extra.delete", extra_id=linked["id"]))
    assert [item["name"] for item in body["lines"]] == ["Salz", "Teelichter"]
    # Not on a done list.
    await applied(api, anna, list_id, op("list.finish"))
    response = await send_ops(
        api,
        anna,
        list_id,
        op("extra.update", extra_id=candles, text="x"),
        op("extra.delete", extra_id=candles),
    )
    assert results(response) == [("rejected", "list.done")] * 2


async def test_checking_after_editing_in_one_request(
    app: FastAPI, api: AsyncClient, anna: Account, shopping: Any
) -> None:
    """Ops see what the ops before them did: a check-off stores the item as it is then."""
    list_id, extra_id = shopping["id"], op_id(1)
    line_key = f"x:{extra_id}"
    body = await applied(
        api,
        anna,
        list_id,
        op("extra.add", extra_id=extra_id, text="Kerzen"),
        check(line_key, op_id=op_id(2)),
        op("extra.update", extra_id=extra_id, text="Teelichter"),
    )
    assert by_key(body, line_key)["needs_more"]["changed"] is True
    body = await applied(api, anna, list_id, check(line_key, op_id=op_id(3)))
    assert by_key(body, line_key)["checked"] is True
    [snapshot] = await scalars(
        app, select(ListLineState.checked_snapshot).where(ListLineState.line_key == line_key)
    )
    assert snapshot["text"] == "Teelichter"


# --- list.finish (SHOP-04) ------------------------------------------------------------------


async def test_finish(api: AsyncClient, anna: Account, shopping: Any, clock: FakeClock) -> None:
    list_id = shopping["id"]
    clock.advance(minutes=3)
    body = await applied(api, anna, list_id, op("list.finish", at=clock.now))
    assert (body["status"], body["finished_at"]) == ("done", "2026-09-27T12:03:00Z")
    assert body["version"] == shopping["version"] + 1
    clock.advance(minutes=3)
    body = await applied(api, anna, list_id, op("list.finish", at=clock.now))
    assert (body["finished_at"], body["version"]) == (
        "2026-09-27T12:03:00Z",
        shopping["version"] + 1,
    )


@pytest.mark.parametrize(
    ("minutes", "finished_at"),
    [
        (30, "2026-09-27T12:30:00Z"),  # sent later, it counts as of the tap
        (-10, "2026-09-27T12:00:00Z"),  # not before shopping started
        (125, "2026-09-27T14:00:00Z"),  # not after the server's time
    ],
)
async def test_lists_are_finished_as_of_the_tap(
    api: AsyncClient, anna: Account, shopping: Any, clock: FakeClock, minutes: int, finished_at: str
) -> None:
    """A finish sent later (from a phone that was offline) lands in the week it happened."""
    clock.advance(hours=2)
    await login(api, anna)
    at = START + timedelta(minutes=minutes)
    body = await applied(api, anna, shopping["id"], op("list.finish", at=at))
    assert (body["status"], body["finished_at"]) == ("done", finished_at)


# --- parallel requests (plan § 5.1, QA-01) --------------------------------------------------


async def test_parallel_batches_lose_nothing(
    app: FastAPI, api: AsyncClient, anna: Account, ben: Account
) -> None:
    """20 requests at once, each with its own ops: all succeed, every op takes effect and the
    version rises once per request."""
    await make_couple(api, anna, ben)
    ingredients = [await create_ingredient(api, anna, f"Zutat {index}") for index in range(20)]
    shopping_list = await create_list(api, anna)
    list_id = shopping_list["id"]
    for ingredient in ingredients:
        await extra_added(api, anna, list_id, ingredient_id=ingredient["id"], amount=1)
    before = await start_shopping(api, anna, list_id)

    def batch(index: int) -> list[Any]:
        return [
            check(key(ingredients[index])),
            op("extra.add", extra_id=op_id(index + 1), text=f"Extra {index}"),
            check(f"x:{op_id(index + 1)}"),
        ]

    responses = await asyncio.gather(
        *(send_ops(api, (anna, ben)[index % 2], list_id, *batch(index)) for index in range(20))
    )

    assert [results(response) for response in responses] == [[APPLIED] * 3] * 20
    body = await detail(api, anna, list_id)
    assert body["version"] == before["version"] + 20
    assert len(body["lines"]) == 40
    assert all(item["checked"] for item in body["lines"])
    assert len(await scalars(app, select(ProcessedOp.op_id))) == 60
