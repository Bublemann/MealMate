"""Admin section: users, roles, deactivation, deletion, activity log (ADM-01..04)."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.core.errors import ApiError
from app.models import AdminEvent, AuthSession, Couple, CoupleMember, User
from app.services import admin as admin_service
from app.services import hooks
from tests.accounts import (
    PASSWORD,
    PUBLIC_URL,
    Account,
    FakeClock,
    error,
    login,
    make_user,
    scalars,
)


@pytest.fixture
def make_settings(make_settings: Any) -> Any:
    def make(**overrides: Any) -> Any:
        return make_settings(**({"public_url": PUBLIC_URL} | overrides))

    return make


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin", display_name="Admin")


def ref(user: Account, *, deactivated: bool = False) -> dict[str, Any]:
    return {"id": user.id, "display_name": user.display_name, "deactivated": deactivated}


async def patch_user(api: AsyncClient, actor: Account, user_id: str, **body: Any) -> Any:
    return await api.patch(f"/api/admin/users/{user_id}", json=body, headers=actor.headers)


ADMIN_ROUTES = [
    ("GET", "/api/admin/users"),
    ("PATCH", "/api/admin/users/{id}"),
    ("DELETE", "/api/admin/users/{id}"),
    ("POST", "/api/admin/users/{id}/reset-link"),
    ("GET", "/api/admin/invites"),
    ("POST", "/api/admin/invites"),
    ("DELETE", "/api/admin/invites/{id}"),
    ("GET", "/api/admin/events"),
    ("GET", "/api/admin/system"),
    ("POST", "/api/admin/backup"),
]


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES)
async def test_admin_routes_are_for_admins_only(
    app: FastAPI, api: AsyncClient, admin: Account, method: str, path: str
) -> None:
    anna = await make_user(app, api, "anna")
    response = await api.request(
        method, path.format(id=admin.id), json={"role": "user"}, headers=anna.headers
    )
    assert response.status_code == 403
    assert error(response) == "common.forbidden"
    anonymous = await api.request(method, path.format(id=admin.id), json={})
    assert error(anonymous) == "common.unauthorized"
    assert await scalars(app, select(AdminEvent.id)) == []


async def test_demoted_admin_loses_access_immediately(
    app: FastAPI, api: AsyncClient, admin: Account
) -> None:
    other = await make_user(app, api, "root", role="admin")
    assert (await api.get("/api/admin/users", headers=other.headers)).status_code == 200
    assert (await patch_user(api, admin, other.id, role="user")).status_code == 200
    response = await api.get("/api/admin/users", headers=other.headers)
    assert error(response) == "common.forbidden"


async def test_list_users(app: FastAPI, api: AsyncClient, admin: Account, clock: FakeClock) -> None:
    clock.advance(minutes=3)
    anna = await make_user(app, api, "anna", display_name="anna")
    response = await api.get("/api/admin/users", headers=admin.headers)
    assert response.status_code == 200
    assert response.json() == [
        {
            "id": admin.id,
            "username": "admin",
            "display_name": "Admin",
            "role": "admin",
            "is_active": True,
            "created_at": "2026-09-27T12:00:00Z",
            "last_seen_at": "2026-09-27T12:00:00Z",
        },
        {
            "id": anna.id,
            "username": "anna",
            "display_name": "anna",
            "role": "user",
            "is_active": True,
            "created_at": "2026-09-27T12:00:00Z",
            "last_seen_at": "2026-09-27T12:03:00Z",
        },
    ]


async def test_role_changes(app: FastAPI, api: AsyncClient, admin: Account) -> None:
    anna = await make_user(app, api, "anna")
    response = await patch_user(api, admin, anna.id, role="admin")
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert (await api.get("/api/admin/users", headers=anna.headers)).status_code == 200
    # A no-op change logs nothing.
    await patch_user(api, admin, anna.id, role="admin")
    await patch_user(api, admin, anna.id, role="user")

    events = (await api.get("/api/admin/events", headers=admin.headers)).json()
    assert [(e["action"], e["details"]) for e in events] == [
        ("user.role_change", {"from": "admin", "to": "user"}),
        ("user.role_change", {"from": "user", "to": "admin"}),
    ]
    assert events[0]["actor"] == ref(admin)
    assert events[0]["target"] == ref(anna)


async def test_deactivate_and_reactivate(app: FastAPI, api: AsyncClient, admin: Account) -> None:
    anna = await make_user(app, api, "anna")

    response = await patch_user(api, admin, anna.id, is_active=False)

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    sessions = await scalars(app, select(AuthSession).where(AuthSession.user_id == anna.id))
    assert all(session.revoked_at is not None for session in sessions)
    login_response = await api.post(
        "/api/auth/login", json={"username": "anna", "password": PASSWORD}
    )
    assert error(login_response) == "auth.account_deactivated"

    assert (await patch_user(api, admin, anna.id, is_active=True)).json()["is_active"] is True
    await login(api, anna)
    events = (await api.get("/api/admin/events", headers=admin.headers)).json()
    assert [e["action"] for e in events] == ["user.reactivate", "user.deactivate"]


async def test_admins_cannot_change_or_delete_themselves(api: AsyncClient, admin: Account) -> None:
    for body in ({"is_active": False}, {"role": "user"}, {}):
        response = await patch_user(api, admin, admin.id, **body)
        assert response.status_code == 409
        assert error(response) == "admin.self_forbidden"
    response = await api.delete(f"/api/admin/users/{admin.id}", headers=admin.headers)
    assert error(response) == "admin.self_forbidden"


async def test_unknown_user(api: AsyncClient, admin: Account) -> None:
    assert error(await patch_user(api, admin, "nope", role="admin")) == "common.not_found"
    response = await api.delete("/api/admin/users/nope", headers=admin.headers)
    assert error(response) == "common.not_found"


async def test_invalid_update(api: AsyncClient, admin: Account, app: FastAPI) -> None:
    anna = await make_user(app, api, "anna")
    response = await patch_user(api, admin, anna.id, role="superuser")
    assert response.status_code == 422


async def test_an_active_admin_always_remains(app: FastAPI, admin: Account) -> None:
    """Admins cannot touch themselves, so via the API the rule is a safety net; it is checked
    against the transaction's pending state."""
    database = app.state.database
    async with database.write_sessions() as session:
        transaction = await session.begin()
        user = await session.get(User, admin.id)
        assert user is not None
        user.is_active = False
        with pytest.raises(ApiError) as excinfo:
            await admin_service.ensure_an_active_admin_remains(session)
        await transaction.rollback()
    assert excinfo.value.code == "admin.last_admin"
    assert excinfo.value.status_code == 409
    async with database.write_sessions() as session, session.begin():
        await admin_service.ensure_an_active_admin_remains(session)  # rolled back: fine


async def test_delete_user(
    app: FastAPI, api: AsyncClient, admin: Account, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []

    async def before_user_deleted(_session: object, user_id: str, **_: object) -> None:
        calls.append(("before_user_deleted", user_id))

    async def on_couple_ended(_session: object, user_a: str, user_b: str, **_: object) -> None:
        calls.append(("on_couple_ended", user_a, user_b))

    monkeypatch.setattr(hooks, "before_user_deleted", before_user_deleted)
    monkeypatch.setattr(hooks, "on_couple_ended", on_couple_ended)
    anna = await make_user(app, api, "anna", display_name="Anna")
    ben = await make_user(app, api, "ben")
    carl = await make_user(app, api, "carl")
    request = await api.post("/api/couple/requests", json={"user_id": ben.id}, headers=anna.headers)
    await api.post(
        f"/api/couple/requests/{request.json()['outgoing']['id']}/accept", headers=ben.headers
    )
    await api.post("/api/couple/requests", json={"user_id": anna.id}, headers=carl.headers)
    await api.post(f"/api/admin/users/{anna.id}/reset-link", headers=admin.headers)

    response = await api.delete(f"/api/admin/users/{anna.id}", headers=admin.headers)

    assert response.status_code == 204
    assert calls == [("before_user_deleted", anna.id), ("on_couple_ended", anna.id, ben.id)]
    assert await scalars(app, select(User.id).where(User.id == anna.id)) == []
    assert await scalars(app, select(AuthSession.id).where(AuthSession.user_id == anna.id)) == []
    assert await scalars(app, select(Couple.id)) == []
    assert await scalars(app, select(CoupleMember.user_id)) == []
    assert (await api.get("/api/couple", headers=ben.headers)).json()["partner"] is None
    assert error(await api.get("/api/me", headers=anna.headers)) == "auth.session_revoked"

    events = (await api.get("/api/admin/events", headers=admin.headers)).json()
    assert events[0]["action"] == "user.delete"
    assert events[0]["target"] is None
    assert events[0]["details"] == {"display_name": "Anna"}
    # The reset-link entry for anna now points to a deleted user.
    assert events[1]["action"] == "user.reset_link"
    assert events[1]["target"] is None


async def test_the_real_deletion_hooks_run(app: FastAPI, api: AsyncClient, admin: Account) -> None:
    anna = await make_user(app, api, "anna")
    ben = await make_user(app, api, "ben")
    request = await api.post("/api/couple/requests", json={"user_id": ben.id}, headers=anna.headers)
    await api.post(
        f"/api/couple/requests/{request.json()['outgoing']['id']}/accept", headers=ben.headers
    )
    assert (
        await api.delete(f"/api/admin/users/{anna.id}", headers=admin.headers)
    ).status_code == 204
    assert (await api.delete("/api/couple", headers=ben.headers)).status_code == 404


async def test_deleted_admin_becomes_a_null_actor(
    app: FastAPI, api: AsyncClient, admin: Account
) -> None:
    other = await make_user(app, api, "root", role="admin", display_name="Root")
    anna = await make_user(app, api, "anna")
    reset = await api.post(f"/api/admin/users/{anna.id}/reset-link", headers=other.headers)
    code = reset.json()["url"].partition("#")[2]
    await api.post("/api/auth/reset", json={"code": code, "password": "brand new secret"})

    assert (
        await api.delete(f"/api/admin/users/{other.id}", headers=admin.headers)
    ).status_code == 204

    events = (await api.get("/api/admin/events", headers=admin.headers)).json()
    assert events[1]["action"] == "user.reset_link"
    assert events[1]["actor"] is None
    await login(api, anna, "brand new secret")
    security = (await api.get("/api/me/security", headers=anna.headers)).json()
    assert security["password_reset_by"] is None
    assert security["password_reset_at"] is not None


async def test_events_are_capped(app: FastAPI, api: AsyncClient, admin: Account) -> None:
    anna = await make_user(app, api, "anna")
    database = app.state.database
    async with database.write_sessions() as session, session.begin():
        for _ in range(205):
            session.add(AdminEvent(actor_id=admin.id, action="invite.create", details={}))
    await patch_user(api, admin, anna.id, role="admin")
    events = (await api.get("/api/admin/events", headers=admin.headers)).json()
    assert len(events) == 200
