"""The own account: profile, settings, password, sessions, security (ACC-09/10/13, VIS-02)."""

import asyncio

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response

from app.models import User
from app.services import hooks
from app.services import me as me_service
from tests.accounts import (
    PASSWORD,
    Account,
    FakeClock,
    error,
    fields,
    login,
    make_user,
    password_hash,
    refresh,
    refresh_cookie,
)

NEW_PASSWORD = "another fine passphrase"  # noqa: S105 -- a test password


async def test_get_me(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna", role="admin", language="en")
    response = await api.get("/api/me", headers=anna.headers)
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["language"] == "en"


async def test_update_me(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna")
    ben = await make_user(app, api, "ben")

    response = await api.patch(
        "/api/me",
        json={
            "display_name": "  Anna Müller ",
            "language": "en",
            "filter_hidden": {"meals": [ben.id, ben.id], "lists": []},
        },
        headers=anna.headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["display_name"] == "Anna Müller"
    assert body["language"] == "en"
    assert body["filter_hidden"] == {"meals": [ben.id], "lists": []}
    assert body["meals_public"] is True
    # Unsent fields stay as they are.
    response = await api.patch("/api/me", json={"language": "de"}, headers=anna.headers)
    assert response.json()["display_name"] == "Anna Müller"
    assert response.json()["filter_hidden"] == {"meals": [ben.id], "lists": []}
    assert (await api.get("/api/me", headers=anna.headers)).json() == response.json()


async def test_keeping_the_own_display_name_is_fine(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna", display_name="Anna")
    response = await api.patch("/api/me", json={"display_name": "ANNA"}, headers=anna.headers)
    assert response.status_code == 200
    assert response.json()["display_name"] == "ANNA"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"display_name": "ben"}, {("body", "display_name"): "taken"}),
        ({"display_name": "   "}, {("body", "display_name"): "too_short"}),
        ({"display_name": "x" * 41}, {("body", "display_name"): "too_long"}),
        ({"display_name": "a\u0000b"}, {("body", "display_name"): "invalid_format"}),
        ({"language": "fr"}, {("body", "language"): "invalid"}),
        ({"meals_public": "maybe"}, {("body", "meals_public"): "invalid"}),
        ({"filter_hidden": {"meals": []}}, {("body", "filter_hidden", "lists"): "required"}),
        (
            {"filter_hidden": {"meals": ["x"] * 501, "lists": []}},
            {("body", "filter_hidden", "meals"): "too_long"},
        ),
    ],
)
async def test_update_me_validation(
    app: FastAPI, api: AsyncClient, body: dict[str, object], expected: dict[tuple[str, ...], str]
) -> None:
    anna = await make_user(app, api, "anna")
    await make_user(app, api, "ben", display_name="Ben")
    response = await api.patch("/api/me", json=body, headers=anna.headers)
    assert response.status_code == 422
    assert fields(response) == expected


async def test_privacy_switches_call_the_hooks_when_turned_off(
    app: FastAPI, api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []

    async def meals_hook(_session: object, user_id: str, **_: object) -> None:
        calls.append(("meals", user_id))

    async def lists_hook(_session: object, user_id: str, **_: object) -> None:
        calls.append(("lists", user_id))

    monkeypatch.setattr(hooks, "on_meals_made_private", meals_hook)
    monkeypatch.setattr(hooks, "on_lists_made_private", lists_hook)
    anna = await make_user(app, api, "anna")

    off = {"meals_public": False, "lists_public": False}
    response = await api.patch("/api/me", json=off, headers=anna.headers)
    assert response.json()["meals_public"] is False
    assert response.json()["lists_public"] is False
    assert calls == [("meals", anna.id), ("lists", anna.id)]

    await api.patch("/api/me", json=off, headers=anna.headers)  # already off: no hook
    on = {"meals_public": True, "lists_public": True}
    response = await api.patch("/api/me", json=on, headers=anna.headers)
    assert response.json()["meals_public"] is True
    assert calls == [("meals", anna.id), ("lists", anna.id)]


async def test_the_real_privacy_hooks_run(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna")
    off = {"meals_public": False, "lists_public": False}
    assert (await api.patch("/api/me", json=off, headers=anna.headers)).status_code == 200


async def test_change_password(
    app: FastAPI, api: AsyncClient, client: AsyncClient, clock: FakeClock
) -> None:
    anna = await make_user(app, api, "anna")
    this_cookie = refresh_cookie(api)
    phone = Account(anna.id, "anna", "Anna")
    await login(client, phone)
    phone_cookie = refresh_cookie(client)
    clock.advance(minutes=1)

    response = await api.post(
        "/api/me/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=anna.headers,
    )

    assert response.status_code == 204
    # This device stays logged in; all others are logged out.
    assert (await api.get("/api/me", headers=anna.headers)).status_code == 200
    assert (await refresh(api, this_cookie)).status_code == 200
    assert error(await api.get("/api/me", headers=phone.headers)) == "auth.session_revoked"
    assert error(await refresh(client, phone_cookie)) == "auth.session_revoked"
    security = (await api.get("/api/me/security", headers=anna.headers)).json()
    assert security == {
        "password_changed_at": "2026-09-27T12:01:00Z",
        "password_reset_at": None,
        "password_reset_by": None,
    }
    await login(api, Account(anna.id, "anna", "Anna"), NEW_PASSWORD)


async def test_change_password_checks_the_current_one(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna")
    response = await api.post(
        "/api/me/password",
        json={"current_password": "not my password", "new_password": NEW_PASSWORD},
        headers=anna.headers,
    )
    assert response.status_code == 403
    assert error(response) == "auth.password_incorrect"


async def change_password(
    api: AsyncClient, user: Account, current_password: str, new_password: str = NEW_PASSWORD
) -> Response:
    return await api.post(
        "/api/me/password",
        json={"current_password": current_password, "new_password": new_password},
        headers=user.headers,
    )


async def test_change_password_is_throttled_like_login(
    app: FastAPI, api: AsyncClient, clock: FakeClock
) -> None:
    """Someone holding a stolen access token cannot guess the current password quickly
    (ACC-11): wrong guesses count towards the user's and the client's login throttle."""
    anna = await make_user(app, api, "anna")
    for index in range(5):
        response = await change_password(api, anna, f"guess number {index}")
        assert response.status_code == 403
        assert error(response) == "auth.password_incorrect"

    # Throttled even with the right password, and so is logging in as anna.
    blocked = await change_password(api, anna, PASSWORD)
    assert blocked.status_code == 429
    assert blocked.json() == {
        "code": "common.rate_limited",
        "params": {"retry_after": 1},
        "fields": [],
    }
    assert blocked.headers["retry-after"] == "1"
    login_blocked = await api.post(
        "/api/auth/login", json={"username": "anna", "password": PASSWORD}
    )
    assert error(login_blocked) == "common.rate_limited"

    clock.advance(seconds=1)
    assert (await change_password(api, anna, PASSWORD)).status_code == 204
    # Success clears the user's failures; the client's stay.
    throttle = app.state.rate_limits.login
    assert "user:anna" not in throttle._failures
    assert len(throttle._failures["ip:127.0.0.1"]) == 5


async def test_parallel_password_guesses_are_throttled(
    app: FastAPI, api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    anna = await make_user(app, api, "anna")
    real_verify = me_service.verify_password
    verified: list[str] = []

    async def slow_verify(password: str, password_hash: str | None, *, rounds: int) -> bool:
        verified.append(password)
        await asyncio.sleep(0.05)  # let every other request reach the throttle meanwhile
        return await real_verify(password, password_hash, rounds=rounds)

    monkeypatch.setattr(me_service, "verify_password", slow_verify)
    responses = await asyncio.gather(
        *(change_password(api, anna, f"guess number {index}") for index in range(10))
    )

    assert len(verified) == 5
    assert sorted(response.status_code for response in responses) == [403] * 5 + [429] * 5


@pytest.mark.parametrize(
    ("new_password", "problem"),
    [("short", "too_short"), ("iloveyou", "too_common"), ("ANNABELLE", "same_as_username")],
)
async def test_change_password_rules(
    app: FastAPI, api: AsyncClient, new_password: str, problem: str
) -> None:
    anna = await make_user(app, api, "annabelle")
    response = await api.post(
        "/api/me/password",
        json={"current_password": PASSWORD, "new_password": new_password},
        headers=anna.headers,
    )
    assert response.status_code == 422
    assert fields(response) == {("body", "new_password"): problem}


async def test_change_password_needs_login(api: AsyncClient) -> None:
    response = await api.post(
        "/api/me/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
    )
    assert error(response) == "common.unauthorized"


async def test_sessions(
    app: FastAPI, api: AsyncClient, client: AsyncClient, clock: FakeClock
) -> None:
    anna = await make_user(app, api, "anna")
    clock.advance(minutes=5)
    phone = Account(anna.id, "anna", "Anna")
    await client.post(
        "/api/auth/login",
        json={"username": "anna", "password": PASSWORD},
        headers={"User-Agent": "iPhone"},
    )
    await login(client, phone)
    ben = await make_user(app, api, "ben")

    response = await api.get("/api/me/sessions", headers=anna.headers)

    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 3
    assert [item["current"] for item in sessions] == [False, False, True]
    assert sessions[2]["created_at"] == "2026-09-27T12:00:00Z"
    assert sessions[0]["last_used_at"] == "2026-09-27T12:05:00Z"
    assert {item["user_agent"] for item in sessions} >= {"iPhone"}
    assert len((await api.get("/api/me/sessions", headers=ben.headers)).json()) == 1

    # Revoke the phone's session.
    phone_session = sessions[0]["id"]
    assert (
        await api.delete(f"/api/me/sessions/{phone_session}", headers=anna.headers)
    ).status_code == 204
    assert error(await api.get("/api/me", headers=phone.headers)) == "auth.session_revoked"
    remaining = (await api.get("/api/me/sessions", headers=anna.headers)).json()
    assert phone_session not in {item["id"] for item in remaining}
    # Revoked, unknown and other users' sessions are not found.
    ben_session = (await api.get("/api/me/sessions", headers=ben.headers)).json()[0]["id"]
    for session_id in (phone_session, "nope", ben_session):
        response = await api.delete(f"/api/me/sessions/{session_id}", headers=anna.headers)
        assert response.status_code == 404
    assert (await api.get("/api/me", headers=ben.headers)).status_code == 200


async def test_revoking_the_current_session_logs_out(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna")
    [session] = (await api.get("/api/me/sessions", headers=anna.headers)).json()
    assert (
        await api.delete(f"/api/me/sessions/{session['id']}", headers=anna.headers)
    ).status_code == 204
    assert error(await api.get("/api/me", headers=anna.headers)) == "auth.session_revoked"


async def test_security_without_events(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna")
    response = await api.get("/api/me/security", headers=anna.headers)
    assert response.json() == {
        "password_changed_at": None,
        "password_reset_at": None,
        "password_reset_by": None,
    }


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/me"),
        ("PATCH", "/api/me"),
        ("GET", "/api/me/sessions"),
        ("DELETE", "/api/me/sessions/x"),
        ("GET", "/api/me/security"),
        ("GET", "/api/couple"),
        ("POST", "/api/couple/requests"),
        ("POST", "/api/couple/requests/x/accept"),
        ("DELETE", "/api/couple"),
        ("GET", "/api/users"),
        ("GET", "/api/users/visible?for=meals"),
        ("GET", "/api/admin/users"),
        ("GET", "/api/admin/events"),
    ],
)
async def test_every_account_route_needs_a_token(api: AsyncClient, method: str, path: str) -> None:
    response = await api.request(method, path, json={})
    assert response.status_code == 401
    assert error(response) == "common.unauthorized"


async def test_password_changed_meanwhile(
    app: FastAPI, api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If a reset lands between checking the current password and saving the new one, the
    change is refused."""
    anna = await make_user(app, api, "anna")
    real_hash = me_service.hash_password

    async def hash_while_reset_happens(password: str, *, rounds: int) -> str:
        async with app.state.database.write_sessions() as session, session.begin():
            user = await session.get(User, anna.id)
            assert user is not None
            user.password_hash = password_hash("reset by an admin")
        return await real_hash(password, rounds=rounds)

    monkeypatch.setattr(me_service, "hash_password", hash_while_reset_happens)
    response = await api.post(
        "/api/me/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=anna.headers,
    )
    assert response.status_code == 403
    assert error(response) == "auth.password_incorrect"
