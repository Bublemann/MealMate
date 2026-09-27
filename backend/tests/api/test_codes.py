"""Invites, registration, reset links and code checks (ACC-01..07, ACC-10, SEC-05, SEC-10)."""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from app.models import OneTimeCode, User
from tests.accounts import (
    PASSWORD,
    PUBLIC_URL,
    Account,
    FakeClock,
    cookie_attributes,
    error,
    fields,
    login,
    make_user,
    refresh,
    refresh_cookie,
    scalars,
)

NEW_PASSWORD = "a brand new passphrase"  # noqa: S105 -- a test password


@pytest.fixture
def make_settings(make_settings: Any) -> Any:
    def make(**overrides: Any) -> Any:
        return make_settings(**({"public_url": PUBLIC_URL} | overrides))

    return make


@pytest.fixture
async def admin(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "admin", role="admin", display_name="Admin")


async def create_invite(api: AsyncClient, admin: Account, **body: Any) -> tuple[str, str]:
    """Returns (invite id, code)."""
    response = await api.post("/api/admin/invites", json=body, headers=admin.headers)
    assert response.status_code == 201, response.text
    url: str = response.json()["url"]
    assert url.startswith(f"{PUBLIC_URL}/join#")
    return response.json()["invite"]["id"], url.partition("#")[2]


async def create_reset(api: AsyncClient, admin: Account, user: Account) -> str:
    response = await api.post(f"/api/admin/users/{user.id}/reset-link", headers=admin.headers)
    assert response.status_code == 200, response.text
    url: str = response.json()["url"]
    assert url.startswith(f"{PUBLIC_URL}/reset#")
    return url.partition("#")[2]


def join_body(code: str, **overrides: Any) -> dict[str, Any]:
    return {
        "code": code,
        "username": "dora",
        "display_name": "Dora",
        "password": PASSWORD,
        "language": "en",
    } | overrides


# --- invites ---------------------------------------------------------------------------------


async def test_create_and_list_invites(api: AsyncClient, admin: Account, clock: FakeClock) -> None:
    response = await api.post(
        "/api/admin/invites",
        json={"tailscale_share_url": " https://login.tailscale.com/admin/invite/abc "},
        headers=admin.headers,
    )
    assert response.status_code == 201
    body = response.json()
    invite_id = body["invite"]["id"]
    assert body["invite"] == {
        "id": invite_id,
        "status": "open",
        "created_at": "2026-09-27T12:00:00Z",
        "expires_at": "2026-10-04T12:00:00Z",
        "created_by": {"id": admin.id, "display_name": "Admin", "deactivated": False},
        "used_by": None,
        "tailscale_share_url": "https://login.tailscale.com/admin/invite/abc",
    }
    clock.advance(minutes=1)
    second_id, _ = await create_invite(api, admin)

    listed = await api.get("/api/admin/invites", headers=admin.headers)
    assert [item["id"] for item in listed.json()] == [second_id, invite_id]
    assert listed.json()[0]["tailscale_share_url"] is None


@pytest.mark.parametrize(
    ("url", "problem"),
    [
        ("http://login.tailscale.com/x", "invalid_format"),
        ("javascript:alert(1)", "invalid_format"),
        ("https://", "invalid_format"),
        ("https://x.example/" + "a" * 500, "too_long"),
    ],
)
async def test_invalid_tailscale_share_url(
    api: AsyncClient, admin: Account, url: str, problem: str
) -> None:
    response = await api.post(
        "/api/admin/invites", json={"tailscale_share_url": url}, headers=admin.headers
    )
    assert response.status_code == 422
    assert fields(response) == {("body", "tailscale_share_url"): problem}


async def test_blank_tailscale_share_url_means_none(api: AsyncClient, admin: Account) -> None:
    response = await api.post(
        "/api/admin/invites", json={"tailscale_share_url": "  "}, headers=admin.headers
    )
    assert response.json()["invite"]["tailscale_share_url"] is None


async def test_links_need_a_public_url(app: FastAPI, api: AsyncClient, admin: Account) -> None:
    app.state.auth_config = type(app.state.auth_config)(
        **(vars(app.state.auth_config) | {"public_url": None})
    )
    anna = await make_user(app, api, "anna")
    for path in ("/api/admin/invites", f"/api/admin/users/{anna.id}/reset-link"):
        response = await api.post(path, json={}, headers=admin.headers)
        assert response.status_code == 503
        assert error(response) == "admin.public_url_missing"
    assert await scalars(app, select(OneTimeCode.id)) == []


async def test_codes_are_stored_as_hmacs(app: FastAPI, api: AsyncClient, admin: Account) -> None:
    _, code = await create_invite(api, admin)
    assert len(code) == 43
    [stored] = await scalars(app, select(OneTimeCode.code_hmac))
    assert code not in stored
    assert len(stored) == 64


async def test_revoke_invite(api: AsyncClient, admin: Account, clock: FakeClock) -> None:
    invite_id, code = await create_invite(api, admin)

    response = await api.delete(f"/api/admin/invites/{invite_id}", headers=admin.headers)
    assert response.status_code == 204
    # Idempotent: revoking again changes nothing and logs nothing.
    assert (
        await api.delete(f"/api/admin/invites/{invite_id}", headers=admin.headers)
    ).status_code == 204

    [invite] = (await api.get("/api/admin/invites", headers=admin.headers)).json()
    assert invite["status"] == "revoked"
    check = await api.post("/api/auth/codes/check", json={"code": code})
    assert check.status_code == 404
    assert error(check) == "auth.code_invalid"
    assert error(await api.post("/api/auth/join", json=join_body(code))) == "auth.code_invalid"
    events = (await api.get("/api/admin/events", headers=admin.headers)).json()
    assert [event["action"] for event in events] == ["invite.revoke", "invite.create"]


async def test_revoke_unknown_invite(api: AsyncClient, admin: Account, app: FastAPI) -> None:
    assert (await api.delete("/api/admin/invites/nope", headers=admin.headers)).status_code == 404
    anna = await make_user(app, api, "anna")
    await create_reset(api, admin, anna)
    [reset_id] = await scalars(app, select(OneTimeCode.id))
    response = await api.delete(f"/api/admin/invites/{reset_id}", headers=admin.headers)
    assert error(response) == "common.not_found"


# --- checking and joining --------------------------------------------------------------------


async def test_check_invite_does_not_consume_it(api: AsyncClient, admin: Account) -> None:
    _, code = await create_invite(api, admin)
    for _ in range(2):
        response = await api.post("/api/auth/codes/check", json={"code": code})
        assert response.status_code == 200
        assert response.json() == {
            "kind": "invite",
            "expires_at": "2026-10-04T12:00:00Z",
            "username": None,
        }


async def test_join(app: FastAPI, api: AsyncClient, admin: Account) -> None:
    invite_id, code = await create_invite(api, admin)
    api.cookies.clear()

    response = await api.post(
        "/api/auth/join",
        json=join_body(code, display_name="  Dora Müller "),
        headers={"User-Agent": "Safari"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["username"] == "dora"
    assert body["user"]["display_name"] == "Dora Müller"
    assert body["user"]["role"] == "user"
    assert body["user"]["language"] == "en"
    assert refresh_cookie(api) is not None
    assert cookie_attributes(response.headers["set-cookie"])[1]["httponly"] == ""
    dora = Account(body["user"]["id"], "dora", "Dora Müller")
    dora.authorize(body["access_token"])
    assert (await api.get("/api/me", headers=dora.headers)).status_code == 200
    assert (await refresh(api)).status_code == 200

    [invite] = (await api.get("/api/admin/invites", headers=admin.headers)).json()
    assert invite["id"] == invite_id
    assert invite["status"] == "used"
    assert invite["used_by"] == {"id": dora.id, "display_name": "Dora Müller", "deactivated": False}
    # Single use.
    again = await api.post("/api/auth/join", json=join_body(code, username="eve"))
    assert again.status_code == 404
    assert error(again) == "auth.code_invalid"


async def test_expired_invite(api: AsyncClient, admin: Account, clock: FakeClock) -> None:
    _, code = await create_invite(api, admin)
    clock.advance(days=7)
    assert error(await api.post("/api/auth/codes/check", json={"code": code})) == (
        "auth.code_invalid"
    )
    assert error(await api.post("/api/auth/join", json=join_body(code))) == "auth.code_invalid"
    await login(api, admin)
    [invite] = (await api.get("/api/admin/invites", headers=admin.headers)).json()
    assert invite["status"] == "expired"


@pytest.mark.parametrize("code", ["unknown-code", "x" * 100])
async def test_unknown_code(api: AsyncClient, code: str) -> None:
    for path in ("/api/auth/codes/check", "/api/auth/join", "/api/auth/reset"):
        body = join_body(code) if path.endswith("join") else {"code": code, "password": PASSWORD}
        response = await api.post(path, json=body)
        assert response.status_code == 404, path
        assert error(response) == "auth.code_invalid"


async def test_join_validation(
    app: FastAPI, api: AsyncClient, admin: Account, clock: FakeClock
) -> None:
    _, code = await create_invite(api, admin)
    await make_user(app, api, "anna", display_name="Anna Müller")
    cases = [
        (
            {"username": "Dora", "display_name": "  ", "password": "short"},
            {
                ("body", "username"): "invalid_format",
                ("body", "display_name"): "too_short",
            },
        ),
        ({"username": "do"}, {("body", "username"): "too_short"}),
        ({"password": "qwerty123"}, {("body", "password"): "too_common"}),
        (
            {"password": "DORA_the_dora", "username": "dora_the_dora"},
            {("body", "password"): "same_as_username"},
        ),
        ({"password": "ä" * 40}, {("body", "password"): "too_long"}),
        ({"password": "short"}, {("body", "password"): "too_short"}),
        ({"language": "fr"}, {("body", "language"): "invalid"}),
        ({"username": "ANNA"}, {("body", "username"): "invalid_format"}),
        ({"username": "anna"}, {("body", "username"): "taken"}),
        ({"display_name": "anna mueller"}, {("body", "display_name"): "taken"}),
        (
            {"username": "anna", "display_name": "ANNA MÜLLER"},
            {("body", "username"): "taken", ("body", "display_name"): "taken"},
        ),
    ]
    for overrides, expected in cases:
        clock.advance(seconds=10)  # stay below the rate limit
        response = await api.post("/api/auth/join", json=join_body(code, **overrides))
        assert response.status_code == 422, overrides
        assert error(response) == "common.validation"
        assert fields(response) == expected, overrides
    # None of that used up the invite.
    assert (await api.post("/api/auth/join", json=join_body(code))).status_code == 201


async def test_code_endpoints_are_rate_limited_per_client(
    api: AsyncClient, clock: FakeClock
) -> None:
    for _ in range(10):
        assert (await api.post("/api/auth/codes/check", json={"code": "x"})).status_code == 404
    for path, body in (
        ("/api/auth/codes/check", {"code": "x"}),
        ("/api/auth/join", join_body("x")),
        ("/api/auth/reset", {"code": "x", "password": PASSWORD}),
    ):
        response = await api.post(path, json=body)
        assert response.status_code == 429, path
        assert response.json()["params"] == {"retry_after": 60}
        assert response.headers["retry-after"] == "60"
    clock.advance(seconds=60)
    assert (await api.post("/api/auth/codes/check", json={"code": "x"})).status_code == 404


# --- reset links -----------------------------------------------------------------------------


async def test_reset_password(
    app: FastAPI, api: AsyncClient, admin: Account, client: AsyncClient
) -> None:
    anna = await make_user(app, client, "anna")
    phone_cookie = refresh_cookie(client)
    code = await create_reset(api, admin, anna)

    check = await api.post("/api/auth/codes/check", json={"code": code})
    assert check.json() == {
        "kind": "reset",
        "expires_at": "2026-09-28T12:00:00Z",
        "username": "anna",
    }

    response = await api.post("/api/auth/reset", json={"code": code, "password": NEW_PASSWORD})

    assert response.status_code == 200, response.text
    assert response.json()["user"]["id"] == anna.id
    # Every earlier session of anna has ended.
    assert error(await api.get("/api/me", headers=anna.headers)) == "auth.session_revoked"
    assert error(await refresh(client, phone_cookie)) == "auth.session_revoked"
    # She is logged in with the new session and the new password works; the old one does not.
    new = Account(anna.id, "anna", "Anna")
    new.authorize(response.json()["access_token"])
    security = await api.get("/api/me/security", headers=new.headers)
    assert security.json() == {
        "password_changed_at": "2026-09-27T12:00:00Z",
        "password_reset_at": "2026-09-27T12:00:00Z",
        "password_reset_by": {"id": admin.id, "display_name": "Admin", "deactivated": False},
    }
    old_login = await api.post("/api/auth/login", json={"username": "anna", "password": PASSWORD})
    assert error(old_login) == "auth.invalid_credentials"
    await login(api, new, NEW_PASSWORD)
    # Single use.
    again = await api.post("/api/auth/reset", json={"code": code, "password": NEW_PASSWORD})
    assert error(again) == "auth.code_invalid"
    events = (await api.get("/api/admin/events", headers=admin.headers)).json()
    assert events[0]["action"] == "user.reset_link"
    assert events[0]["target"]["id"] == anna.id


async def test_new_reset_link_revokes_the_older_one(
    app: FastAPI, api: AsyncClient, admin: Account
) -> None:
    anna = await make_user(app, api, "anna")
    first = await create_reset(api, admin, anna)
    second = await create_reset(api, admin, anna)
    assert error(await api.post("/api/auth/codes/check", json={"code": first})) == (
        "auth.code_invalid"
    )
    assert (await api.post("/api/auth/codes/check", json={"code": second})).status_code == 200


async def test_reset_link_expires(
    app: FastAPI, api: AsyncClient, admin: Account, clock: FakeClock
) -> None:
    anna = await make_user(app, api, "anna")
    code = await create_reset(api, admin, anna)
    clock.advance(hours=24)
    response = await api.post("/api/auth/reset", json={"code": code, "password": NEW_PASSWORD})
    assert error(response) == "auth.code_invalid"


async def test_reset_validation(app: FastAPI, api: AsyncClient, admin: Account) -> None:
    anna = await make_user(app, api, "annabelle")
    code = await create_reset(api, admin, anna)
    for password, problem in (("annabelle", "same_as_username"), ("password1", "too_common")):
        response = await api.post("/api/auth/reset", json={"code": code, "password": password})
        assert response.status_code == 422
        assert fields(response) == {("body", "password"): problem}
    # Still usable.
    ok = await api.post("/api/auth/reset", json={"code": code, "password": NEW_PASSWORD})
    assert ok.status_code == 200


async def test_reset_of_a_deactivated_account(
    app: FastAPI, api: AsyncClient, admin: Account
) -> None:
    anna = await make_user(app, api, "anna")
    code = await create_reset(api, admin, anna)
    await api.patch(f"/api/admin/users/{anna.id}", json={"is_active": False}, headers=admin.headers)
    response = await api.post("/api/auth/reset", json={"code": code, "password": NEW_PASSWORD})
    assert response.status_code == 403
    assert error(response) == "auth.account_deactivated"
    # Not consumed: after reactivation the link works.
    await api.patch(f"/api/admin/users/{anna.id}", json={"is_active": True}, headers=admin.headers)
    ok = await api.post("/api/auth/reset", json={"code": code, "password": NEW_PASSWORD})
    assert ok.status_code == 200


async def test_reset_link_for_unknown_user(api: AsyncClient, admin: Account) -> None:
    response = await api.post("/api/admin/users/nope/reset-link", headers=admin.headers)
    assert error(response) == "common.not_found"


async def test_invite_code_cannot_reset_and_reset_code_cannot_join(
    app: FastAPI, api: AsyncClient, admin: Account
) -> None:
    anna = await make_user(app, api, "anna")
    _, invite = await create_invite(api, admin)
    reset = await create_reset(api, admin, anna)
    response = await api.post("/api/auth/reset", json={"code": invite, "password": NEW_PASSWORD})
    assert error(response) == "auth.code_invalid"
    assert error(await api.post("/api/auth/join", json=join_body(reset))) == "auth.code_invalid"


async def test_deleting_a_user_deletes_their_reset_links(
    app: FastAPI, api: AsyncClient, admin: Account
) -> None:
    anna = await make_user(app, api, "anna")
    await create_reset(api, admin, anna)
    _, invite = await create_invite(api, admin)
    await api.post("/api/auth/join", json=join_body(invite))
    [dora_id] = await scalars(app, select(User.id).where(User.username == "dora"))

    assert (
        await api.delete(f"/api/admin/users/{anna.id}", headers=admin.headers)
    ).status_code == 204
    assert (
        await api.delete(f"/api/admin/users/{dora_id}", headers=admin.headers)
    ).status_code == 204

    kinds = await scalars(app, select(OneTimeCode.kind))
    assert kinds == ["invite"]  # the reset link is gone; the used invite stays
    [invite_row] = (await api.get("/api/admin/invites", headers=admin.headers)).json()
    assert invite_row["status"] == "used"
    assert invite_row["used_by"] is None  # "deleted user"
