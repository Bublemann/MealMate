import asyncio
import shutil
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.core.tokens import create_access_token
from app.main import create_app
from app.models import AuthSession, SessionToken, User
from app.services import auth as auth_service
from tests.accounts import (
    PASSWORD,
    Account,
    FakeClock,
    cookie_attributes,
    error,
    insert_user,
    login,
    make_user,
    refresh,
    refresh_cookie,
    scalars,
    set_refresh_cookie,
)
from tests.accounts import (
    password_hash as password_hash_of,
)
from tests.support import ClientFactory, SettingsFactory

NINETY_DAYS = 90 * 24 * 60 * 60


async def me_status(client: AsyncClient, user: Account) -> tuple[int, str | None]:
    response = await client.get("/api/me", headers=user.headers)
    return response.status_code, None if response.status_code == 200 else error(response)


async def active_tokens(app: FastAPI, session_id: str) -> list[SessionToken]:
    return await scalars(
        app,
        select(SessionToken).where(
            SessionToken.session_id == session_id, SessionToken.superseded_at.is_(None)
        ),
    )


async def sessions_of(app: FastAPI, user: Account) -> list[AuthSession]:
    return await scalars(
        app, select(AuthSession).where(AuthSession.user_id == user.id).order_by(AuthSession.id)
    )


# --- login -----------------------------------------------------------------------------------


async def test_login_returns_tokens_and_sets_the_refresh_cookie(
    app: FastAPI, api: AsyncClient
) -> None:
    anna = await insert_user(app, "anna", display_name="Anna", language="en")

    response = await api.post(
        "/api/auth/login",
        json={"username": "anna", "password": PASSWORD},
        headers={"User-Agent": "Mozilla/5.0 (iPhone) " + "x" * 300},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["expires_in"] == 900
    assert body["user"] == {
        "id": anna.id,
        "username": "anna",
        "display_name": "Anna",
        "role": "user",
        "language": "en",
        "meals_public": True,
        "lists_public": True,
        "filter_hidden": {"meals": [], "lists": []},
        "created_at": "2026-09-27T12:00:00Z",
    }
    pair, attributes = cookie_attributes(response.headers["set-cookie"])
    name, _, value = pair.partition("=")
    assert name == "mm_refresh"
    assert len(value) == 43
    assert attributes == {
        "httponly": "",
        "max-age": str(NINETY_DAYS),
        "path": "/api/auth",
        "samesite": "strict",
        "secure": "",
    }
    [session] = await sessions_of(app, anna)
    assert session.user_agent is not None
    assert len(session.user_agent) == 200
    assert session.expires_at == session.last_used_at + timedelta(days=90)
    # Only the HMAC is stored.
    tokens = await scalars(app, select(SessionToken.token_hmac))
    assert value not in tokens
    assert len(tokens) == 1


async def test_cookie_without_secure_for_loopback_e2e(
    make_settings: SettingsFactory, client_for: ClientFactory, migrated_database: Path
) -> None:
    settings = make_settings(cookie_secure=False, public_url="http://127.0.0.1:8080")
    settings.data_dir.mkdir(parents=True)
    shutil.copyfile(migrated_database, settings.database_path)
    app = create_app(settings)
    async with client_for(app) as client:
        await insert_user(app, "anna")
        response = await client.post(
            "/api/auth/login", json={"username": "anna", "password": PASSWORD}
        )
    _, attributes = cookie_attributes(response.headers["set-cookie"])
    assert "secure" not in attributes
    assert attributes["httponly"] == ""


async def test_login_ignores_username_case(app: FastAPI, api: AsyncClient) -> None:
    await insert_user(app, "anna")
    response = await api.post("/api/auth/login", json={"username": " Anna ", "password": PASSWORD})
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("username", "password"),
    [("anna", "wrong password"), ("nobody", PASSWORD), ("anna", "x" * 100), ("", "")],
)
async def test_wrong_credentials(
    app: FastAPI, api: AsyncClient, username: str, password: str
) -> None:
    await insert_user(app, "anna")
    response = await api.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 401
    assert error(response) == "auth.invalid_credentials"
    assert "set-cookie" not in response.headers


async def test_deactivated_account_only_after_the_right_password(
    app: FastAPI, api: AsyncClient
) -> None:
    await insert_user(app, "anna", active=False)
    wrong = await api.post("/api/auth/login", json={"username": "anna", "password": "nope nope"})
    assert error(wrong) == "auth.invalid_credentials"
    right = await api.post("/api/auth/login", json={"username": "anna", "password": PASSWORD})
    assert right.status_code == 403
    assert error(right) == "auth.account_deactivated"
    assert "set-cookie" not in right.headers


async def test_login_throttle_per_username(
    app: FastAPI, api: AsyncClient, clock: FakeClock
) -> None:
    await insert_user(app, "anna")
    wrong = {"username": "anna", "password": "wrong password"}
    for _ in range(5):
        assert (await api.post("/api/auth/login", json=wrong)).status_code == 401

    # Throttled even with the right password.
    blocked = await api.post("/api/auth/login", json={"username": "anna", "password": PASSWORD})
    assert blocked.status_code == 429
    assert blocked.json() == {
        "code": "common.rate_limited",
        "params": {"retry_after": 1},
        "fields": [],
    }
    assert blocked.headers["retry-after"] == "1"

    clock.advance(seconds=1)
    assert (await api.post("/api/auth/login", json=wrong)).status_code == 401
    blocked = await api.post("/api/auth/login", json=wrong)
    assert blocked.json()["params"] == {"retry_after": 2}

    clock.advance(seconds=2)
    ok = await api.post("/api/auth/login", json={"username": "anna", "password": PASSWORD})
    assert ok.status_code == 200
    # Success clears the username's failures (the client's stay, see below).
    throttle = app.state.rate_limits.login
    assert "user:anna" not in throttle._failures
    assert len(throttle._failures["ip:127.0.0.1"]) == 6


async def test_login_throttle_per_client(app: FastAPI, api: AsyncClient) -> None:
    await insert_user(app, "anna")
    for index in range(5):
        response = await api.post(
            "/api/auth/login", json={"username": f"guess{index}", "password": "whatever1"}
        )
        assert response.status_code == 401
    blocked = await api.post("/api/auth/login", json={"username": "anna", "password": PASSWORD})
    assert error(blocked) == "common.rate_limited"


async def test_own_login_does_not_clear_the_client_throttle(app: FastAPI, api: AsyncClient) -> None:
    """Logging in to an own account between guesses at others buys no extra guesses."""
    await insert_user(app, "anna")
    for index in range(4):
        response = await api.post(
            "/api/auth/login", json={"username": f"guess{index}", "password": "whatever1"}
        )
        assert response.status_code == 401
    ok = await api.post("/api/auth/login", json={"username": "anna", "password": PASSWORD})
    assert ok.status_code == 200

    # The successful login itself does not count as a failure: one more guess is free ...
    guess = await api.post("/api/auth/login", json={"username": "guess4", "password": "x" * 9})
    assert guess.status_code == 401
    # ... and then the client waits, even for the own account.
    for username in ("guess5", "anna"):
        blocked = await api.post(
            "/api/auth/login", json={"username": username, "password": PASSWORD}
        )
        assert error(blocked) == "common.rate_limited"


async def test_parallel_wrong_logins_are_throttled(
    app: FastAPI, api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check and count happen in one step, so parallel requests cannot all get past the check
    while the first ones are still verifying their password."""
    await insert_user(app, "anna")
    real_verify = auth_service.verify_password
    verified: list[str] = []

    async def slow_verify(password: str, password_hash: str | None, *, rounds: int) -> bool:
        verified.append(password)
        await asyncio.sleep(0.05)  # let every other request reach the throttle meanwhile
        return await real_verify(password, password_hash, rounds=rounds)

    monkeypatch.setattr(auth_service, "verify_password", slow_verify)
    responses = await asyncio.gather(
        *(
            api.post("/api/auth/login", json={"username": "anna", "password": f"wrong {index}"})
            for index in range(10)
        )
    )

    assert len(verified) == 5
    assert sorted(response.status_code for response in responses) == [401] * 5 + [429] * 5


async def test_throttle_is_never_a_lockout(
    app: FastAPI, api: AsyncClient, clock: FakeClock
) -> None:
    await insert_user(app, "anna")
    for _ in range(40):
        await api.post("/api/auth/login", json={"username": "anna", "password": "wrong pass"})
        clock.advance(seconds=61)
    response = await api.post("/api/auth/login", json={"username": "anna", "password": PASSWORD})
    assert response.status_code == 200


# --- access tokens ---------------------------------------------------------------------------


async def test_bearer_token_is_required(api: AsyncClient) -> None:
    for headers in ({}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer nonsense"}):
        response = await api.get("/api/me", headers=headers)
        assert response.status_code == 401
        assert error(response) == "common.unauthorized"


async def test_expired_access_token(app: FastAPI, api: AsyncClient, clock: FakeClock) -> None:
    anna = await make_user(app, api, "anna")
    clock.advance(minutes=14, seconds=59)
    assert await me_status(api, anna) == (200, None)
    clock.advance(seconds=1)
    assert await me_status(api, anna) == (401, "auth.token_expired")


async def test_token_for_another_user_is_rejected(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna")
    [session] = await sessions_of(app, anna)
    forged = create_access_token(
        app.state.auth_config.keys.jwt,
        user_id="someone-else",
        session_id=session.id,
        now=app.state.clock(),
    )
    response = await api.get("/api/me", headers={"Authorization": f"Bearer {forged}"})
    assert error(response) == "common.unauthorized"


async def test_access_token_of_an_idle_expired_session(
    app: FastAPI, api: AsyncClient, clock: FakeClock
) -> None:
    anna = await make_user(app, api, "anna")
    [session] = await sessions_of(app, anna)
    token = create_access_token(
        app.state.auth_config.keys.jwt,
        user_id=anna.id,
        session_id=session.id,
        now=clock.now + timedelta(days=90),
    )
    clock.advance(days=90)
    response = await api.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert error(response) == "auth.session_expired"


# --- refresh ---------------------------------------------------------------------------------


async def test_refresh_needs_the_client_header(app: FastAPI, api: AsyncClient) -> None:
    await make_user(app, api, "anna")
    for headers in ({}, {"X-MealMate-Client": "curl"}):
        response = await refresh(api, headers=headers)
        assert response.status_code == 403
        assert error(response) == "auth.csrf"


async def test_refresh_without_a_cookie(api: AsyncClient) -> None:
    response = await refresh(api)
    assert response.status_code == 401
    assert error(response) == "auth.session_expired"


async def test_refresh_with_an_unknown_cookie_clears_it(api: AsyncClient) -> None:
    response = await refresh(api, "not-a-real-token")
    assert response.status_code == 401
    assert error(response) == "auth.session_expired"
    pair, attributes = cookie_attributes(response.headers["set-cookie"])
    assert pair == 'mm_refresh=""'
    assert attributes["max-age"] == "0"
    assert attributes["path"] == "/api/auth"
    assert refresh_cookie(api) is None


async def test_refresh_rotates_the_token(app: FastAPI, api: AsyncClient, clock: FakeClock) -> None:
    anna = await make_user(app, api, "anna")
    first = refresh_cookie(api)
    clock.advance(minutes=10)

    response = await refresh(api)

    assert response.status_code == 200
    second = refresh_cookie(api)
    assert second is not None
    assert second != first
    body = response.json()
    assert body["user"]["id"] == anna.id
    anna.authorize(body["access_token"])
    assert await me_status(api, anna) == (200, None)
    [session] = await sessions_of(app, anna)
    assert session.last_used_at == clock.now
    assert session.expires_at == clock.now + timedelta(days=90)
    assert len(await active_tokens(app, session.id)) == 1


async def test_lost_response_within_the_grace_period(
    app: FastAPI, api: AsyncClient, clock: FakeClock
) -> None:
    anna = await make_user(app, api, "anna")
    old = refresh_cookie(api)
    assert old is not None
    assert (await refresh(api)).status_code == 200  # the client never saw this response

    clock.advance(seconds=59)
    retry = await refresh(api, old)

    assert retry.status_code == 200
    anna.authorize(retry.json()["access_token"])
    assert await me_status(api, anna) == (200, None)
    [session] = await sessions_of(app, anna)
    assert session.revoked_at is None


async def test_parallel_refreshes_leave_one_active_token(
    app: FastAPI, api: AsyncClient, clock: FakeClock
) -> None:
    anna = await make_user(app, api, "anna")
    old = refresh_cookie(api)
    assert old is not None
    first = await refresh(api, old)
    second = await refresh(api, old)
    assert (first.status_code, second.status_code) == (200, 200)
    [session] = await sessions_of(app, anna)
    assert len(await active_tokens(app, session.id)) == 2  # the two grace siblings

    clock.advance(seconds=30)
    assert (await refresh(api)).status_code == 200
    assert len(await active_tokens(app, session.id)) == 1


async def test_reuse_after_the_grace_period_revokes_the_session(
    app: FastAPI, api: AsyncClient, clock: FakeClock
) -> None:
    anna = await make_user(app, api, "anna")
    old = refresh_cookie(api)
    assert old is not None
    rotated = await refresh(api)
    current = refresh_cookie(api)
    assert current is not None
    anna.authorize(rotated.json()["access_token"])

    clock.advance(seconds=60)
    reuse = await refresh(api, old)

    assert reuse.status_code == 401
    assert error(reuse) == "auth.session_revoked"
    assert cookie_attributes(reuse.headers["set-cookie"])[1]["max-age"] == "0"
    # The whole session is gone: the current token and the access token no longer work.
    assert await me_status(api, anna) == (401, "auth.session_revoked")
    assert error(await refresh(api, current)) == "auth.session_revoked"


async def test_sliding_idle_expiry(app: FastAPI, api: AsyncClient, clock: FakeClock) -> None:
    await make_user(app, api, "anna")
    for _ in range(3):
        clock.advance(days=89)
        assert (await refresh(api)).status_code == 200
    clock.advance(days=90)
    response = await refresh(api)
    assert error(response) == "auth.session_expired"


async def test_fork_creates_an_independent_session(
    app: FastAPI, api: AsyncClient, clock: FakeClock
) -> None:
    anna = await make_user(app, api, "anna")
    safari_cookie = refresh_cookie(api)
    assert safari_cookie is not None
    [safari] = await sessions_of(app, anna)

    fork = await refresh(api, fork=True)

    assert fork.status_code == 200
    home_cookie = refresh_cookie(api)
    assert home_cookie not in {None, safari_cookie}
    sessions = await sessions_of(app, anna)
    assert len(sessions) == 2
    assert all(session.revoked_at is None for session in sessions)
    # Safari's token was not rotated and keeps working; the Home Screen app has its own.
    assert (await refresh(api, safari_cookie)).status_code == 200
    assert (await refresh(api, home_cookie)).status_code == 200
    home = Account(anna.id, "anna", "Anna")
    home.authorize(fork.json()["access_token"])
    assert await me_status(api, home) == (200, None)
    assert fork.json()["user"]["id"] == anna.id
    assert safari.id in {session.id for session in sessions}


async def test_second_fork_with_the_same_token_is_refused(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna")
    cookie = refresh_cookie(api)
    assert cookie is not None
    assert (await refresh(api, cookie, fork=True)).status_code == 200

    again = await refresh(api, cookie, fork=True)

    assert again.status_code == 401
    assert error(again) == "auth.login_required"
    assert "set-cookie" not in again.headers
    assert all(session.revoked_at is None for session in await sessions_of(app, anna))
    assert len(await sessions_of(app, anna)) == 2


@pytest.mark.parametrize("seconds_later", [1, 3600])
async def test_fork_with_a_superseded_token_is_refused_without_revoking(
    app: FastAPI, api: AsyncClient, clock: FakeClock, seconds_later: int
) -> None:
    anna = await make_user(app, api, "anna")
    stale = refresh_cookie(api)
    assert stale is not None
    assert (await refresh(api)).status_code == 200
    clock.advance(seconds=seconds_later)

    response = await refresh(api, stale, fork=True)

    assert error(response) == "auth.login_required"
    [session] = await sessions_of(app, anna)
    assert session.revoked_at is None


async def revoked(app: FastAPI, user: Account) -> list[bool]:
    return [session.revoked_at is not None for session in await sessions_of(app, user)]


async def test_fork_records_its_parent(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna")
    [parent] = await sessions_of(app, anna)
    assert parent.parent_session_id is None

    assert (await refresh(api, fork=True)).status_code == 200

    [child] = [session for session in await sessions_of(app, anna) if session.id != parent.id]
    assert child.parent_session_id == parent.id


async def test_reuse_on_the_parent_revokes_the_fork(
    app: FastAPI, api: AsyncClient, clock: FakeClock
) -> None:
    anna = await make_user(app, api, "anna")
    safari = refresh_cookie(api)
    assert safari is not None
    assert (await refresh(api, safari, fork=True)).status_code == 200
    home = refresh_cookie(api)
    assert home is not None
    assert (await refresh(api, safari)).status_code == 200  # rotates the parent's token
    clock.advance(seconds=60)

    reuse = await refresh(api, safari)

    assert error(reuse) == "auth.session_revoked"
    assert await revoked(app, anna) == [True, True]
    assert error(await refresh(api, home)) == "auth.session_revoked"


async def test_reuse_on_the_fork_revokes_the_parent(
    app: FastAPI, api: AsyncClient, clock: FakeClock
) -> None:
    anna = await make_user(app, api, "anna")
    safari = refresh_cookie(api)
    assert safari is not None
    assert (await refresh(api, safari, fork=True)).status_code == 200
    home = refresh_cookie(api)
    assert home is not None
    assert (await refresh(api, home)).status_code == 200  # rotates the fork's token
    clock.advance(seconds=60)

    reuse = await refresh(api, home)

    assert error(reuse) == "auth.session_revoked"
    assert await revoked(app, anna) == [True, True]
    assert error(await refresh(api, safari)) == "auth.session_revoked"


async def test_reuse_revokes_the_whole_fork_family_and_nothing_else(
    app: FastAPI, api: AsyncClient, client: AsyncClient, clock: FakeClock
) -> None:
    """Parent P with forks C and S, and G forked from C: reuse on G reaches all four."""
    anna = await make_user(app, api, "anna")
    other = Account(anna.id, "anna", "Anna")
    await login(client, other)  # an unrelated session of the same user
    ben = await make_user(app, client, "ben")
    p_token = refresh_cookie(api)
    assert p_token is not None
    assert (await refresh(api, p_token, fork=True)).status_code == 200
    c_token = refresh_cookie(api)
    assert c_token is not None
    assert (await refresh(api, c_token, fork=True)).status_code == 200
    g_token = refresh_cookie(api)
    assert g_token is not None
    assert (await refresh(api, p_token)).status_code == 200  # P rotates ...
    p_token = refresh_cookie(api)
    assert p_token is not None
    assert (await refresh(api, p_token, fork=True)).status_code == 200  # ... and forks S
    assert (await refresh(api, g_token)).status_code == 200
    clock.advance(seconds=60)

    assert error(await refresh(api, g_token)) == "auth.session_revoked"

    assert sorted(await revoked(app, anna)) == [False, True, True, True, True]
    assert await me_status(api, other) == (200, None)
    assert await me_status(api, ben) == (200, None)


@pytest.mark.parametrize("log_out", ["parent", "fork"])
async def test_logging_out_one_of_a_fork_family_keeps_the_other(
    app: FastAPI, api: AsyncClient, log_out: str
) -> None:
    await make_user(app, api, "anna")
    safari = refresh_cookie(api)
    assert safari is not None
    assert (await refresh(api, safari, fork=True)).status_code == 200
    home = refresh_cookie(api)
    assert home is not None
    leaving, staying = (safari, home) if log_out == "parent" else (home, safari)

    set_refresh_cookie(api, leaving)
    assert (await api.post("/api/auth/logout")).status_code == 204

    assert error(await refresh(api, leaving)) == "auth.session_revoked"
    assert (await refresh(api, staying)).status_code == 200


# --- logout ----------------------------------------------------------------------------------


async def test_logout_revokes_this_session(app: FastAPI, api: AsyncClient) -> None:
    anna = await make_user(app, api, "anna")
    cookie = refresh_cookie(api)

    response = await api.post("/api/auth/logout")

    assert response.status_code == 204
    assert cookie_attributes(response.headers["set-cookie"])[1]["max-age"] == "0"
    assert refresh_cookie(api) is None
    assert await me_status(api, anna) == (401, "auth.session_revoked")
    assert error(await refresh(api, cookie)) == "auth.session_revoked"


async def test_logout_without_a_session_is_fine(api: AsyncClient) -> None:
    assert (await api.post("/api/auth/logout")).status_code == 204
    assert (await refresh(api, "unknown")).status_code == 401
    assert (await api.post("/api/auth/logout")).status_code == 204


async def test_logout_all(app: FastAPI, api: AsyncClient, client: AsyncClient) -> None:
    anna = await make_user(app, api, "anna")
    phone = Account(anna.id, "anna", "Anna")
    await login(client, phone)
    ben = await make_user(app, client, "ben")

    assert (await api.post("/api/auth/logout-all")).status_code == 401
    response = await api.post("/api/auth/logout-all", headers=anna.headers)

    assert response.status_code == 204
    assert refresh_cookie(api) is None
    assert await me_status(api, anna) == (401, "auth.session_revoked")
    assert await me_status(api, phone) == (401, "auth.session_revoked")
    assert await me_status(api, ben) == (200, None)


async def test_deactivated_user_is_rejected_immediately(app: FastAPI, api: AsyncClient) -> None:
    admin = await make_user(app, api, "admin", role="admin")
    anna = await make_user(app, api, "anna")
    cookie = refresh_cookie(api)
    assert await me_status(api, anna) == (200, None)

    response = await api.patch(
        f"/api/admin/users/{anna.id}", json={"is_active": False}, headers=admin.headers
    )
    assert response.status_code == 200

    assert await me_status(api, anna) == (401, "auth.session_revoked")
    assert error(await refresh(api, cookie)) == "auth.session_revoked"


async def test_deleted_user_token_is_rejected(app: FastAPI, api: AsyncClient) -> None:
    admin = await make_user(app, api, "admin", role="admin")
    anna = await make_user(app, api, "anna")
    response = await api.delete(f"/api/admin/users/{anna.id}", headers=admin.headers)
    assert response.status_code == 204
    assert await me_status(api, anna) == (401, "auth.session_revoked")


async def test_refresh_of_a_user_deactivated_without_revocation(
    app: FastAPI, api: AsyncClient
) -> None:
    """Belt and braces: an inactive user never gets a token, even if a session was left."""
    anna = await make_user(app, api, "anna")
    database = app.state.database
    async with database.write_sessions() as session, session.begin():
        user = await session.get(User, anna.id)
        assert user is not None
        user.is_active = False
    assert error(await refresh(api)) == "auth.session_revoked"
    assert await me_status(api, anna) == (401, "auth.session_revoked")


async def test_login_without_a_user_agent(app: FastAPI, api: AsyncClient) -> None:
    anna = await insert_user(app, "anna")
    response = await api.post(
        "/api/auth/login",
        json={"username": "anna", "password": PASSWORD},
        headers={"User-Agent": "  "},
    )
    assert response.status_code == 200
    [session] = await sessions_of(app, anna)
    assert session.user_agent is None


async def test_password_changed_while_logging_in(
    app: FastAPI, api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The password is checked outside the transaction; if it changed meanwhile, the login
    fails like a wrong password instead of using the stale check."""
    anna = await insert_user(app, "anna")
    real_verify = auth_service.verify_password

    async def verify_then_change(password: str, password_hash: str | None, *, rounds: int) -> bool:
        result = await real_verify(password, password_hash, rounds=rounds)
        async with app.state.database.write_sessions() as session, session.begin():
            user = await session.get(User, anna.id)
            assert user is not None
            user.password_hash = password_hash_of("changed meanwhile")
        return result

    monkeypatch.setattr(auth_service, "verify_password", verify_then_change)
    response = await api.post("/api/auth/login", json={"username": "anna", "password": PASSWORD})
    assert error(response) == "auth.invalid_credentials"
