"""Refreshing ingredients from Open Food Facts and their pending updates (BAR-04..07)."""

import json
import logging
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import httpx
import pytest
import respx
from fastapi import BackgroundTasks, FastAPI
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.exc import OperationalError

from app.core.ratelimit import SlidingWindow
from app.db.session import Database
from app.models import Ingredient as IngredientRow
from app.schemas.ingredients import Ingredient
from app.services import off_refresh
from app.services.off_refresh import OffRefresher, Outcome
from tests.accounts import Account, FakeClock, error, login, make_user
from tests.catalog import EAN_13, create_from_off, create_ingredient
from tests.off import (
    MILK,
    OATS,
    OFF_URL,
    RECORDED_MODIFIED_AT,
    modified,
    oats,
    product_response,
    recorded,
    refresher,
    route,
)

OATS_NUTRIENTS = {"kcal": 372, "protein": 13.5, "carbs": 58.7, "sugar": 0.7, "fat": 7}


@pytest.fixture
def off_api(app: FastAPI) -> Iterator[respx.MockRouter]:
    app.state.off_refresh = refresher()
    with respx.mock(base_url=OFF_URL, assert_all_called=False) as mock:
        yield mock


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


async def saved_oats(api: AsyncClient, anna: Account, *, edited: list[str], **changes: Any) -> Any:
    """The oats of `tests.off.oats()`, saved from the proposal as of 2026-01-01."""
    values: dict[str, Any] = {
        "name": "Haferflocken",
        "brand": "MealMate Test Kitchen",
        "quantity_text": "500 g",
        "pack_quantity": 500,
        "pack_unit": "g",
        "nutrients": OATS_NUTRIENTS,
    }
    values |= changes
    return await create_from_off(
        api,
        anna,
        values.pop("name"),
        OATS,
        off_last_modified_at=RECORDED_MODIFIED_AT.isoformat(),
        edited_fields=edited,
        **values,
    )


async def saved_milk(api: AsyncClient, anna: Account, barcode: str = MILK) -> Any:
    """Milk from Open Food Facts without any values."""
    return await create_from_off(api, anna, "Milch", barcode, base_unit="ml")


def database(app: FastAPI) -> Database:
    db: Database = app.state.database
    return db


def the_refresher(app: FastAPI) -> OffRefresher:
    refresher_: OffRefresher = app.state.off_refresh
    return refresher_


async def refresh(app: FastAPI, clock: FakeClock, ingredient_id: str, **options: Any) -> Outcome:
    return await off_refresh.refresh_ingredient(
        database(app),
        the_refresher(app).off,
        ingredient_id,
        now=clock.now,
        max_wait=options.pop("max_wait", None),
        **options,
    )


async def later(api: AsyncClient, clock: FakeClock, *users: Account, **delta: float) -> None:
    """Move the clock on; the users log in again, as their access tokens expired."""
    clock.advance(**delta)
    for user in users:
        await login(api, user)


async def get(api: AsyncClient, user: Account, ingredient_id: str) -> Any:
    response = await api.get(f"/api/ingredients/{ingredient_id}", headers=user.headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- one ingredient (BAR-06, BAR-07) --------------------------------------------------------------


async def test_fields_not_edited_update_silently(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await saved_oats(api, anna, edited=[])
    newer = oats(
        product_name_de="Zarte Haferflocken",
        brands=None,
        nutriments={"energy-kcal_100g": 368, "proteins_100g": 13.5, "fat_100g": 6.5},
        last_modified_t=modified(30),
    )
    route(off_api, OATS).respond(json=newer)
    await later(api, clock, anna, days=40)

    assert await refresh(app, clock, product["id"]) == Outcome.UPDATED

    body = await get(api, anna, product["id"])
    # Values Open Food Facts no longer gives (brand, carbs, sugar) are kept.
    assert (body["name"], body["brand"]) == ("Zarte Haferflocken", "MealMate Test Kitchen")
    assert body["nutrients"] == {
        "kcal": 368,
        "protein": 13.5,
        "carbs": 58.7,
        "sugar": 0.7,
        "fat": 6.5,
    }
    assert body["fetched_at"] == "2026-11-06T12:00:00Z"
    assert body["updated_at"] == "2026-11-06T12:00:00Z"
    assert body["updated_by"] == product["updated_by"]
    assert (body["user_edited_fields"], body["pending_update"]) == ([], None)


async def test_user_edited_fields_become_a_pending_update(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await saved_oats(api, anna, edited=["name", "nutrients.kcal"], name="Meine Flocken")
    newer = oats(
        nutriments={**oats()["product"]["nutriments"], "energy-kcal_100g": 158, "fat_100g": 6},
        last_modified_t=modified(30),
    )
    route(off_api, OATS).respond(json=newer)

    assert await refresh(app, clock, product["id"]) == Outcome.UPDATED

    body = await get(api, anna, product["id"])
    assert body["name"] == "Meine Flocken"
    assert body["nutrients"] == OATS_NUTRIENTS | {"fat": 6}  # fat is not user-edited
    assert body["pending_update"] == {
        "fields": [
            {"field": "name", "current": "Meine Flocken", "proposed": "Haferflocken"},
            {"field": "nutrients.kcal", "current": 372, "proposed": 158},
        ],
        "off_last_modified_at": "2026-01-31T00:00:00Z",
    }


async def test_unknown_values_never_replace_known_ones(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    """Open Food Facts no longer knowing a value is no reason to forget it, whether the user
    edited it (then no pending update to nothing) or not."""
    product = await saved_oats(api, anna, edited=["brand", "nutrients.fat"], brand="Hausmarke")
    unknown = oats(
        brands=None,
        quantity=None,
        product_quantity=None,
        nutriments={"energy-kcal_100g": 372, "proteins_100g": "n/a", "fat_100g": None},
        last_modified_t=modified(30),
    )
    route(off_api, OATS).respond(json=unknown)

    assert await refresh(app, clock, product["id"]) == Outcome.UNCHANGED

    body = await get(api, anna, product["id"])
    assert (body["brand"], body["quantity_text"]) == ("Hausmarke", "500 g")
    assert (body["pack_quantity"], body["pack_unit"]) == (500, "g")
    assert body["nutrients"] == OATS_NUTRIENTS
    assert body["pending_update"] is None
    assert body["fetched_at"] == "2026-09-27T12:00:00Z"


async def test_only_pending_changes(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await saved_oats(api, anna, edited=["brand"], brand="Hausmarke")
    route(off_api, OATS).respond(json=oats())

    assert await refresh(app, clock, product["id"]) == Outcome.PENDING
    route(off_api, OATS).respond(json=oats(brands="Hausmarke"))
    assert await refresh(app, clock, product["id"]) == Outcome.UNCHANGED
    assert (await get(api, anna, product["id"]))["pending_update"] is None


async def test_nutrients_on_another_basis_are_left_alone(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await saved_oats(api, anna, edited=[])
    per_ml = oats(
        product_quantity_unit="ml",
        product_quantity=500,
        nutriments={"energy-kcal_100g": 50},
        quantity="0,5 l",
    )
    route(off_api, OATS).respond(json=per_ml)

    assert await refresh(app, clock, product["id"]) == Outcome.UPDATED

    body = await get(api, anna, product["id"])
    assert body["nutrients"] == OATS_NUTRIENTS
    assert (body["quantity_text"], body["pack_unit"]) == ("0,5 l", "ml")


async def test_a_piece_ingredient_refreshes_its_values_per_100_g(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    """Switched to Stück before saving, the proposal's values stay per 100 g (ING-02), so Open
    Food Facts' values per 100 g go on updating them; values per 100 ml don't."""
    product = await saved_oats(api, anna, edited=[], base_unit="piece", piece_weight_g=40)
    assert (product["base_unit"], product["nutrients"]) == ("piece", OATS_NUTRIENTS)
    newer = oats(nutriments={"energy-kcal_100g": 368}, last_modified_t=modified(30))
    route(off_api, OATS).respond(json=newer)

    assert await refresh(app, clock, product["id"]) == Outcome.UPDATED

    body = await get(api, anna, product["id"])
    assert body["nutrients"] == OATS_NUTRIENTS | {"kcal": 368}
    assert (body["base_unit"], body["piece_weight_g"]) == ("piece", 40)

    per_ml = oats(
        product_quantity_unit="ml",
        nutriments={"energy-kcal_100g": 50},
        last_modified_t=modified(60),
    )
    route(off_api, OATS).respond(json=per_ml)
    await refresh(app, clock, product["id"])
    assert (await get(api, anna, product["id"]))["nutrients"]["kcal"] == 368


async def test_lone_surrogates_are_not_stored(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await saved_oats(api, anna, edited=[])
    answer = oats(product_name_de="Hafer\ud800flocken", brands="Neu\udfff")
    route(off_api, OATS).respond(
        content=json.dumps(answer).encode(), headers={"Content-Type": "application/json"}
    )

    assert await refresh(app, clock, product["id"]) == Outcome.UPDATED

    body = await get(api, anna, product["id"])
    assert (body["name"], body["brand"]) == ("Haferflocken", "Neu")


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (httpx.Response(503), Outcome.UNAVAILABLE),
        (httpx.ConnectError("down"), Outcome.UNAVAILABLE),
        (httpx.Response(404, json=recorded("product_not_found")), Outcome.NOT_FOUND),
    ],
)
async def test_unavailable_or_removed_keeps_everything(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
    answer: httpx.Response | Exception,
    outcome: Outcome,
) -> None:
    """The cached values stay, and the next refresh tries again (BAR-07)."""
    product = await saved_oats(api, anna, edited=[])
    if isinstance(answer, Exception):
        route(off_api, OATS).mock(side_effect=answer)
    else:
        route(off_api, OATS).mock(return_value=answer)
    await later(api, clock, anna, days=40)

    assert await refresh(app, clock, product["id"]) == outcome

    assert await get(api, anna, product["id"]) == product


async def test_busy_and_skipped(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await saved_oats(api, anna, edited=[])
    manual = await create_ingredient(api, anna, "Hafer", barcode=EAN_13)
    app.state.off_refresh = refresher(SlidingWindow(1, clock=clock.monotonic))
    the_refresher(app).off.rate_limit.reserve(max_wait=None)

    assert await refresh(app, clock, product["id"], max_wait=0) == Outcome.BUSY
    assert await refresh(app, clock, manual["id"]) == Outcome.SKIPPED
    assert await refresh(app, clock, "no-such-ingredient") == Outcome.SKIPPED
    # Fetched since the job started (e.g. opened meanwhile).
    before = clock.now - timedelta(seconds=1)
    assert await refresh(app, clock, product["id"], fetched_before=before) == Outcome.SKIPPED
    assert not off_api.calls


async def test_a_product_changed_during_the_request_is_skipped(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await saved_oats(api, anna, edited=[])

    def barcode_changes(_request: httpx.Request) -> httpx.Response:
        with closing(sqlite3.connect(database(app).path)) as connection, connection:
            connection.execute("UPDATE ingredients SET barcode = ?", (MILK,))
        return httpx.Response(200, json=oats(brands="Other"))

    route(off_api, OATS).mock(side_effect=barcode_changes)

    assert await refresh(app, clock, product["id"]) == Outcome.SKIPPED
    assert (await get(api, anna, product["id"]))["brand"] == "MealMate Test Kitchen"


async def test_no_transaction_is_held_while_asking(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    """Another writer gets the write lock at once while Open Food Facts is asked (plan § 5.1)."""
    product = await saved_oats(api, anna, edited=[])
    locked: list[bool] = []

    def try_to_write(_request: httpx.Request) -> httpx.Response:
        with closing(sqlite3.connect(database(app).path, timeout=0)) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("ROLLBACK")
                locked.append(False)
            except sqlite3.OperationalError:  # pragma: no cover -- only if the rule is broken
                locked.append(True)
        return httpx.Response(200, json=oats())

    route(off_api, OATS).mock(side_effect=try_to_write)

    await refresh(app, clock, product["id"])

    assert locked == [False]


async def test_the_name_language_is_the_creators(
    app: FastAPI,
    api: AsyncClient,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    ben = await make_user(app, api, "ben", language="en")
    product = await saved_oats(api, ben, edited=[])
    route(off_api, OATS).respond(json=oats())

    await refresh(app, clock, product["id"])
    assert (await get(api, ben, product["id"]))["name"] == "Rolled Oats"

    # A deleted creator: German.
    async with database(app).write_sessions() as session, session.begin():
        await session.execute(update(IngredientRow).values(created_by=None))
    await refresh(app, clock, product["id"])
    assert (await get(api, ben, product["id"]))["name"] == "Haferflocken"


# --- apply and ignore (BAR-06) --------------------------------------------------------------------


async def pending_product(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> Any:
    product = await saved_oats(api, anna, edited=["name", "nutrients.kcal"], name="Meine Flocken")
    newer = oats(
        nutriments={**oats()["product"]["nutriments"], "energy-kcal_100g": 158},
        last_modified_t=modified(30),
    )
    route(off_api, OATS).respond(json=newer)
    assert await refresh(app, clock, product["id"]) == Outcome.PENDING
    return product


async def test_apply(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await pending_product(app, api, anna, off_api, clock)
    ben = await make_user(app, api, "ben")
    clock.advance(minutes=5)

    response = await api.post(
        f"/api/ingredients/{product['id']}/pending-update/apply", headers=ben.headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Haferflocken"
    assert body["nutrients"]["kcal"] == 158
    assert (body["user_edited_fields"], body["pending_update"]) == ([], None)
    assert body["updated_by"]["id"] == ben.id
    assert body["updated_at"] == "2026-09-27T12:05:00Z"
    assert await get(api, anna, product["id"]) == body
    # Applied values are Open Food Facts values again: the next refresh updates them.
    route(off_api, OATS).respond(json=oats(product_name_de="Haferflocken neu"))
    assert await refresh(app, clock, product["id"]) == Outcome.UPDATED


async def test_ignore(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await pending_product(app, api, anna, off_api, clock)

    response = await api.post(
        f"/api/ingredients/{product['id']}/pending-update/ignore", headers=anna.headers
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["name"], body["nutrients"]["kcal"]) == ("Meine Flocken", 372)
    assert body["user_edited_fields"] == ["name", "nutrients.kcal"]
    assert body["pending_update"] is None
    # The same Open Food Facts version is not proposed again ...
    assert await refresh(app, clock, product["id"]) == Outcome.UNCHANGED
    assert (await get(api, anna, product["id"]))["pending_update"] is None
    # ... a newer one is.
    route(off_api, OATS).respond(
        json=oats(nutriments={"energy-kcal_100g": 150}, last_modified_t=modified(60))
    )
    assert await refresh(app, clock, product["id"]) == Outcome.PENDING
    pending = (await get(api, anna, product["id"]))["pending_update"]
    assert pending["fields"] == [
        {"field": "name", "current": "Meine Flocken", "proposed": "Haferflocken"},
        {"field": "nutrients.kcal", "current": 372, "proposed": 150},
    ]
    assert pending["off_last_modified_at"] == "2026-03-02T00:00:00Z"


async def test_ignore_without_an_open_food_facts_version(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    """Without `last_modified_t` the ignored values themselves are remembered: the same pending
    update does not come back, another value for a field does."""
    product = await saved_oats(api, anna, edited=["name", "nutrients.kcal"], name="Meine Flocken")
    unversioned = {**oats()["product"], "last_modified_t": None}
    unversioned["nutriments"] = {**unversioned["nutriments"], "energy-kcal_100g": 158}
    route(off_api, OATS).respond(json=product_response(OATS, **unversioned))
    assert await refresh(app, clock, product["id"]) == Outcome.PENDING
    assert (await get(api, anna, product["id"]))["pending_update"]["off_last_modified_at"] is None
    path = f"/api/ingredients/{product['id']}/pending-update"

    ignored = await api.post(f"{path}/ignore", headers=anna.headers)

    assert ignored.status_code == 200
    assert ignored.json()["pending_update"] is None
    assert await refresh(app, clock, product["id"]) == Outcome.UNCHANGED
    assert (await get(api, anna, product["id"]))["pending_update"] is None
    assert (await api.post(f"{path}/ignore", headers=anna.headers)).status_code == 409
    # Editing another field keeps what was ignored.
    await api.patch(
        f"/api/ingredients/{product['id']}", json={"name": "Flocken"}, headers=anna.headers
    )
    assert await refresh(app, clock, product["id"]) == Outcome.UNCHANGED
    # A new value for one field comes back, the ignored one for the other does not.
    unversioned["nutriments"] = {**unversioned["nutriments"], "energy-kcal_100g": 150}
    route(off_api, OATS).respond(json=product_response(OATS, **unversioned))
    assert await refresh(app, clock, product["id"]) == Outcome.PENDING
    assert (await get(api, anna, product["id"]))["pending_update"]["fields"] == [
        {"field": "nutrients.kcal", "current": 372, "proposed": 150}
    ]
    # Applying it keeps the ignored name remembered.
    applied = await api.post(f"{path}/apply", headers=anna.headers)
    assert applied.json()["nutrients"]["kcal"] == 150
    assert await refresh(app, clock, product["id"]) == Outcome.UNCHANGED
    assert (await get(api, anna, product["id"]))["pending_update"] is None


@pytest.mark.parametrize("action", ["apply", "ignore"])
async def test_nothing_pending(api: AsyncClient, anna: Account, action: str) -> None:
    product = await saved_oats(api, anna, edited=["name"])

    response = await api.post(
        f"/api/ingredients/{product['id']}/pending-update/{action}", headers=anna.headers
    )
    assert response.status_code == 409
    assert error(response) == "ingredient.no_pending_update"
    missing = await api.post(f"/api/ingredients/nope/pending-update/{action}", headers=anna.headers)
    assert missing.status_code == 404


async def test_editing_a_field_settles_its_pending_value(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await pending_product(app, api, anna, off_api, clock)

    changed = await api.patch(
        f"/api/ingredients/{product['id']}", json={"name": "Flocken"}, headers=anna.headers
    )

    assert changed.json()["pending_update"]["fields"] == [
        {"field": "nutrients.kcal", "current": 372, "proposed": 158}
    ]
    # Another base unit settles every pending nutrient (they were per the old one).
    rebased = await api.patch(
        f"/api/ingredients/{product['id']}", json={"base_unit": "ml"}, headers=anna.headers
    )
    assert rebased.json()["pending_update"] is None
    same = await api.patch(
        f"/api/ingredients/{product['id']}", json={"base_unit": "ml"}, headers=anna.headers
    )
    assert same.status_code == 200


# --- in the background (BAR-05) -------------------------------------------------------------------


async def test_opening_a_stale_product_refreshes_it_after_the_response(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await saved_oats(api, anna, edited=[])
    request = route(off_api, OATS).respond(json=oats(brands="Neu"))
    await later(api, clock, anna, days=29)
    assert (await get(api, anna, product["id"]))["brand"] == "MealMate Test Kitchen"
    assert not request.called  # fresh enough

    await later(api, clock, anna, days=2)
    opened = await get(api, anna, product["id"])

    assert opened["brand"] == "MealMate Test Kitchen"  # the response did not wait
    assert request.call_count == 1
    refreshed = await get(api, anna, product["id"])
    assert (refreshed["brand"], refreshed["fetched_at"]) == ("Neu", "2026-10-28T12:00:00Z")
    assert request.call_count == 1
    assert the_refresher(app).running == set()


async def test_scanning_refreshes_a_stale_ingredient(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    product = await saved_oats(api, anna, edited=[])
    manual = await create_ingredient(api, anna, "Hafer", barcode=EAN_13)  # never refreshed
    request = route(off_api, OATS).respond(json=oats(brands="Neu"))
    await later(api, clock, anna, days=31)

    for barcode in (EAN_13, OATS):
        scanned = await api.get(
            "/api/ingredients/lookup", params={"barcode": barcode}, headers=anna.headers
        )
        assert scanned.json()["found_in"] == "db"
    assert scanned.json()["ingredient"]["brand"] == "MealMate Test Kitchen"
    assert request.call_count == 1
    assert (await get(api, anna, product["id"]))["brand"] == "Neu"
    assert (await get(api, anna, manual["id"]))["fetched_at"] is None
    assert request.call_count == 1


async def test_background_refreshes_are_not_repeated_while_running(
    app: FastAPI, api: AsyncClient, anna: Account, clock: FakeClock
) -> None:
    product = Ingredient.model_validate(await saved_oats(api, anna, edited=[]))
    refresher_ = the_refresher(app)
    later = clock.now + timedelta(days=31)
    background = BackgroundTasks()

    for _ in range(2):
        off_refresh.schedule_if_stale(background, refresher_, database(app), [product], now=later)
    off_refresh.schedule_if_stale(background, refresher_, database(app), [product], now=clock.now)

    assert len(background.tasks) == 1
    assert refresher_.running == {product.id}


async def test_background_failures_are_logged(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def broken(*_args: Any, **_kwargs: Any) -> Outcome:
        raise RuntimeError("bug")

    monkeypatch.setattr(off_refresh, "refresh_ingredient", broken)
    product = await saved_oats(api, anna, edited=[])
    await later(api, clock, anna, days=31)

    with caplog.at_level(logging.WARNING):
        assert (await get(api, anna, product["id"]))["id"] == product["id"]

    [record] = [
        record
        for record in caplog.records
        if record.message == "background refresh from open food facts failed"
    ]
    assert (record.__dict__["ingredient_id"], record.__dict__["error"]) == (
        product["id"],
        "RuntimeError",
    )
    assert record.exc_info is None
    assert the_refresher(app).running == set()
    assert set(the_refresher(app).failed) == {product["id"]}


@dataclass
class NoSleep:
    """A rate limit's sleep that records instead of waiting."""

    slept: list[float] = field(default_factory=list)

    async def __call__(self, seconds: float) -> None:
        self.slept.append(seconds)


async def test_background_refreshes_never_wait_for_their_turn(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    """Only a request that may start right away; lookups, which a user waits for, go first."""
    product = await saved_oats(api, anna, edited=[])
    request = route(off_api, OATS).respond(json=oats(brands="Neu"))
    sleep = NoSleep()
    app.state.off_refresh = refresher(
        SlidingWindow(1, clock=clock.monotonic, sleep=sleep), clock=clock.monotonic
    )
    await later(api, clock, anna, days=31)
    the_refresher(app).off.rate_limit.reserve(max_wait=None)
    clock.advance(seconds=56)  # the next start is 4 s away

    assert (await get(api, anna, product["id"]))["brand"] == "MealMate Test Kitchen"

    assert (request.call_count, sleep.slept) == (0, [])
    assert the_refresher(app).failed == {}  # busy is not a failure: tried on the next open
    await later(api, clock, anna, seconds=4)
    await get(api, anna, product["id"])
    assert request.call_count == 1
    assert (await get(api, anna, product["id"]))["brand"] == "Neu"


@pytest.mark.parametrize(
    "answer",
    [httpx.Response(503), httpx.Response(404, json=recorded("product_not_found"))],
)
async def test_failed_background_refreshes_wait_an_hour(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
    answer: httpx.Response,
) -> None:
    """An unavailable or removed product is not asked for again on every open."""
    product = await saved_oats(api, anna, edited=[])
    request = route(off_api, OATS).mock(return_value=answer)
    app.state.off_refresh = refresher(clock=clock.monotonic)
    await later(api, clock, anna, days=31)

    for _ in range(3):
        await get(api, anna, product["id"])
    await later(api, clock, anna, minutes=59)
    await get(api, anna, product["id"])

    assert request.call_count == 1
    await later(api, clock, anna, minutes=1)
    await get(api, anna, product["id"])
    assert request.call_count == 2
    route(off_api, OATS).respond(json=oats(brands="Neu"))
    await later(api, clock, anna, minutes=60)
    await get(api, anna, product["id"])
    assert (await get(api, anna, product["id"]))["brand"] == "Neu"
    assert len(off_api.calls) == 3


# --- the nightly job (BAR-05) ---------------------------------------------------------------------


async def test_refresh_stale_oldest_first(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    older = await saved_oats(api, anna, edited=[])
    await later(api, clock, anna, days=5)
    newer = await saved_milk(api, anna)
    await create_ingredient(api, anna, "Hafer", barcode=EAN_13)
    never = await saved_milk(api, anna, "2000000000039")
    async with database(app).write_sessions() as session, session.begin():
        await session.execute(
            update(IngredientRow).where(IngredientRow.id == never["id"]).values(fetched_at=None)
        )
    route(off_api, OATS).respond(json=oats(brands="Neu"))
    route(off_api, MILK).respond(503)
    route(off_api, "2000000000039").respond(json=product_response("2000000000039"))
    await later(api, clock, anna, days=31)

    outcomes = await off_refresh.refresh_stale(
        database(app), the_refresher(app).off, max_age=timedelta(days=30), clock=clock
    )

    assert outcomes == {Outcome.UPDATED: 1, Outcome.UNAVAILABLE: 1, Outcome.UNCHANGED: 1}
    assert [call.request.url.path.rsplit("/", 1)[-1] for call in off_api.calls] == [
        "2000000000039",
        OATS,
        MILK,
    ]
    assert (await get(api, anna, newer["id"]))["fetched_at"] == "2026-10-02T12:00:00Z"
    assert (await get(api, anna, older["id"]))["brand"] == "Neu"


async def test_the_job_goes_on_after_an_error(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An ingredient that fails (here: the database stays locked) is logged by id, never with its
    data, counted, and left for the next run; the others are refreshed."""
    failing = await saved_oats(api, anna, edited=[])
    other = await saved_milk(api, anna)
    route(off_api, OATS).respond(json=oats(brands="Geheimrezept"))
    route(off_api, MILK).respond(json=product_response(MILK, brands="Neu"))
    apply_refresh = off_refresh.apply_refresh

    def locked(row: IngredientRow, found: Any, **options: Any) -> Outcome:
        if row.barcode == OATS:
            raise OperationalError(
                "UPDATE ingredients SET brand=?",
                ("Geheimrezept",),
                sqlite3.OperationalError("database is locked"),
            )
        return apply_refresh(row, found, **options)

    monkeypatch.setattr(off_refresh, "apply_refresh", locked)
    await later(api, clock, anna, days=31)

    with caplog.at_level(logging.WARNING):
        outcomes = await off_refresh.refresh_stale(
            database(app), the_refresher(app).off, max_age=timedelta(days=30), clock=clock
        )

    assert outcomes == {Outcome.ERROR: 1, Outcome.UPDATED: 1}
    assert (await get(api, anna, other["id"]))["brand"] == "Neu"
    assert await get(api, anna, failing["id"]) == failing
    [record] = [
        record
        for record in caplog.records
        if record.message == "refreshing an ingredient from open food facts failed"
    ]
    assert (record.__dict__["ingredient_id"], record.__dict__["error"]) == (
        failing["id"],
        "OperationalError",
    )
    assert record.exc_info is None
    assert "Geheimrezept" not in caplog.text
    # The next run tries it again (first, as the oldest), and still goes on.
    monkeypatch.setattr(off_refresh, "apply_refresh", apply_refresh)
    await later(api, clock, anna, days=31)
    outcomes = await off_refresh.refresh_stale(
        database(app), the_refresher(app).off, max_age=timedelta(days=30), clock=clock
    )
    assert outcomes == {Outcome.UPDATED: 1, Outcome.UNCHANGED: 1}
    assert (await get(api, anna, failing["id"]))["brand"] == "Geheimrezept"


async def test_the_job_refreshes_at_most_max_ingredients(
    app: FastAPI,
    api: AsyncClient,
    anna: Account,
    off_api: respx.MockRouter,
    clock: FakeClock,
) -> None:
    """The oldest first; the rest waits for the next run."""
    oldest = await saved_oats(api, anna, edited=[])
    await later(api, clock, anna, days=1)
    newest = await saved_milk(api, anna)
    route(off_api, OATS).respond(json=oats(brands="Neu"))
    route(off_api, MILK).respond(json=product_response(MILK, brands="Neu"))
    await later(api, clock, anna, days=31)

    outcomes = await off_refresh.refresh_stale(
        database(app),
        the_refresher(app).off,
        max_age=timedelta(days=30),
        max_ingredients=1,
        clock=clock,
    )

    assert outcomes == {Outcome.UPDATED: 1}
    assert (await get(api, anna, oldest["id"]))["brand"] == "Neu"
    assert (await get(api, anna, newest["id"]))["brand"] is None
