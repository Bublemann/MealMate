"""Couple requests and couples (CPL-01, CPL-05, CPL-07)."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select

from app.models import Couple, CoupleMember
from app.services import hooks
from tests.accounts import Account, FakeClock, error, fields, make_user, scalars


def ref(user: Account, *, deactivated: bool = False) -> dict[str, Any]:
    return {"id": user.id, "display_name": user.display_name, "deactivated": deactivated}


async def send(api: AsyncClient, sender: Account, target: Account | str) -> Response:
    user_id = target if isinstance(target, str) else target.id
    return await api.post("/api/couple/requests", json={"user_id": user_id}, headers=sender.headers)


async def state(api: AsyncClient, user: Account) -> dict[str, Any]:
    response = await api.get("/api/couple", headers=user.headers)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


async def act(api: AsyncClient, user: Account, request_id: str, action: str) -> Response:
    return await api.post(f"/api/couple/requests/{request_id}/{action}", headers=user.headers)


@pytest.fixture
async def people(app: FastAPI, api: AsyncClient) -> dict[str, Account]:
    return {name: await make_user(app, api, name) for name in ("anna", "ben", "carl", "dora")}


async def test_no_couple(people: dict[str, Account], api: AsyncClient) -> None:
    assert await state(api, people["anna"]) == {
        "partner": None,
        "since": None,
        "outgoing": None,
        "incoming": [],
    }


async def test_request_and_accept(
    people: dict[str, Account], api: AsyncClient, clock: FakeClock
) -> None:
    anna, ben = people["anna"], people["ben"]
    response = await send(api, anna, ben)
    assert response.status_code == 201
    outgoing = response.json()["outgoing"]
    assert outgoing == {
        "id": outgoing["id"],
        "from_user": ref(anna),
        "to_user": ref(ben),
        "created_at": "2026-09-27T12:00:00Z",
    }
    assert (await state(api, ben))["incoming"] == [outgoing]

    clock.advance(minutes=1)
    accepted = await act(api, ben, outgoing["id"], "accept")

    assert accepted.status_code == 200
    assert accepted.json() == {
        "partner": ref(anna),
        "since": "2026-09-27T12:01:00Z",
        "outgoing": None,
        "incoming": [],
    }
    anna_state = await state(api, anna)
    assert anna_state["partner"] == ref(ben)
    assert anna_state["outgoing"] is None


async def test_accept_cancels_all_other_pending_requests(
    people: dict[str, Account], api: AsyncClient, app: FastAPI
) -> None:
    anna, ben, carl, dora = people.values()
    from_carl = (await send(api, carl, anna)).json()["outgoing"]["id"]
    assert (await send(api, anna, dora)).status_code == 201
    to_ben = (await send(api, dora, ben)).json()["outgoing"]["id"]
    assert (await send(api, ben, carl)).status_code == 201

    response = await act(api, anna, from_carl, "accept")
    assert response.status_code == 200
    assert response.json()["partner"] == ref(carl)
    # Every pending request that involved anna or carl is gone; dora -> ben stays.
    pending = await scalars(app, select(Couple.id).where(Couple.status == "pending"))
    assert pending == [to_ben]
    members = await scalars(app, select(CoupleMember.user_id))
    assert sorted(members) == sorted([anna.id, carl.id])


async def test_request_rules(people: dict[str, Account], api: AsyncClient, app: FastAPI) -> None:
    anna, ben, carl, dora = people.values()

    myself = await send(api, anna, anna)
    assert myself.status_code == 422
    assert fields(myself) == {("body", "user_id"): "invalid"}
    assert error(await send(api, anna, "nobody")) == "common.not_found"
    inactive = await make_user(app, api, "erik", active=True)
    admin = await make_user(app, api, "admin", role="admin")
    await api.patch(
        f"/api/admin/users/{inactive.id}", json={"is_active": False}, headers=admin.headers
    )
    assert error(await send(api, anna, inactive)) == "common.not_found"

    assert (await send(api, anna, ben)).status_code == 201
    # At most one outgoing request, and no second request between the same two.
    second = await send(api, anna, carl)
    assert second.status_code == 409
    assert error(second) == "couple.request_pending"
    assert error(await send(api, ben, anna)) == "couple.request_pending"

    request_id = (await state(api, ben))["incoming"][0]["id"]
    await act(api, ben, request_id, "accept")
    assert error(await send(api, anna, carl)) == "couple.already_in_couple"
    target = await send(api, carl, anna)
    assert target.status_code == 409
    assert error(target) == "couple.target_in_couple"
    assert (await send(api, carl, dora)).status_code == 201


async def test_decline_and_cancel(people: dict[str, Account], api: AsyncClient) -> None:
    anna, ben, carl, _ = people.values()
    request_id = (await send(api, anna, ben)).json()["outgoing"]["id"]

    # Only the addressee accepts or declines; only the sender cancels.
    for user, action in ((anna, "accept"), (anna, "decline"), (ben, "cancel"), (carl, "accept")):
        response = await act(api, user, request_id, action)
        assert response.status_code == 404, (user.username, action)

    declined = await act(api, ben, request_id, "decline")
    assert declined.status_code == 200
    assert declined.json()["incoming"] == []
    assert (await state(api, anna))["outgoing"] is None
    assert (await act(api, ben, request_id, "accept")).status_code == 404

    request_id = (await send(api, anna, ben)).json()["outgoing"]["id"]
    cancelled = await act(api, anna, request_id, "cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["outgoing"] is None
    assert (await state(api, ben))["incoming"] == []


async def test_accept_after_the_requester_joined_another_couple(
    people: dict[str, Account], api: AsyncClient, app: FastAPI
) -> None:
    """Accepting cancels other requests, so this needs a request that survived somehow."""
    anna, ben, carl, _ = people.values()
    first = (await send(api, anna, ben)).json()["outgoing"]["id"]
    database = app.state.database
    async with database.write_sessions() as session, session.begin():
        # A stale request from carl to anna, as if left over by a concurrent change.
        session.add(Couple(requester_id=carl.id, addressee_id=anna.id, status="pending"))
    await act(api, ben, first, "accept")
    async with database.write_sessions() as session, session.begin():
        stale = Couple(requester_id=anna.id, addressee_id=carl.id, status="pending")
        session.add(stale)
        other = Couple(requester_id=carl.id, addressee_id=ben.id, status="pending")
        session.add(other)
    stale_id, other_id = stale.id, other.id
    assert error(await act(api, carl, stale_id, "accept")) == "couple.target_in_couple"
    assert error(await act(api, ben, other_id, "accept")) == "couple.already_in_couple"


async def test_end_couple(
    people: dict[str, Account], api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []

    async def on_couple_ended(_session: object, user_a: str, user_b: str, **_: object) -> None:
        calls.append((user_a, user_b))

    monkeypatch.setattr(hooks, "on_couple_ended", on_couple_ended)
    anna, ben, *_ = people.values()
    assert error(await api.delete("/api/couple", headers=anna.headers)) == "common.not_found"
    request_id = (await send(api, anna, ben)).json()["outgoing"]["id"]
    await act(api, ben, request_id, "accept")

    response = await api.delete("/api/couple", headers=ben.headers)

    assert response.status_code == 204
    assert calls == [(anna.id, ben.id)]
    assert (await state(api, anna))["partner"] is None
    assert (await state(api, ben))["partner"] is None
    # Both are free again.
    assert (await send(api, anna, ben)).status_code == 201


async def test_deactivated_partner(
    people: dict[str, Account], api: AsyncClient, app: FastAPI
) -> None:
    """CPL-07: the couple stays, the partner is flagged and can still end it; the deactivated
    user's pending requests are cancelled."""
    anna, ben, carl, dora = people.values()
    admin = await make_user(app, api, "admin", role="admin")
    request_id = (await send(api, anna, ben)).json()["outgoing"]["id"]
    await act(api, ben, request_id, "accept")
    await send(api, carl, dora)
    await send(api, dora, carl)  # refused: pending between them already
    await send(api, admin, carl)

    for user in (ben, carl):
        response = await api.patch(
            f"/api/admin/users/{user.id}", json={"is_active": False}, headers=admin.headers
        )
        assert response.status_code == 200

    assert (await state(api, anna))["partner"] == ref(ben, deactivated=True)
    assert (await state(api, dora))["incoming"] == []
    assert (await state(api, admin))["outgoing"] is None
    assert (await api.delete("/api/couple", headers=anna.headers)).status_code == 204
