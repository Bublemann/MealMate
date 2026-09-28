from httpx import AsyncClient

from app.main import create_app
from tests.support import ClientFactory, SettingsFactory


def cookie_attributes(set_cookie: str) -> tuple[str, dict[str, str]]:
    pair, *attributes = (part.strip() for part in set_cookie.split(";"))
    parsed = {}
    for attribute in attributes:
        name, _, value = attribute.partition("=")
        parsed[name.lower()] = value
    return pair, parsed


async def test_disabled_by_default(client: AsyncClient) -> None:
    for path in ("/api/auth/diag/set", "/api/auth/diag/check"):
        response = await client.post(path)
        assert response.status_code == 404
        assert response.json()["code"] == "common.not_found"


async def test_sets_a_production_like_cookie(
    make_settings: SettingsFactory, client_for: ClientFactory
) -> None:
    app = create_app(make_settings(diagnostics_enabled=True))
    async with client_for(app) as client:
        response = await client.post("/api/auth/diag/set")

    assert response.status_code == 204
    assert response.content == b""
    [set_cookie] = response.headers.get_list("set-cookie")
    pair, attributes = cookie_attributes(set_cookie)
    assert pair == "mm_diag=1"
    assert attributes == {
        "httponly": "",
        "secure": "",
        "samesite": attributes["samesite"],
        "path": "/api/auth",
        "max-age": str(90 * 24 * 60 * 60),
    }
    assert attributes["samesite"].lower() == "strict"


async def test_cookie_without_secure_for_loopback_e2e(
    make_settings: SettingsFactory, client_for: ClientFactory
) -> None:
    settings = make_settings(
        diagnostics_enabled=True, cookie_secure=False, public_url="http://127.0.0.1:18080"
    )
    async with client_for(create_app(settings)) as client:
        response = await client.post("/api/auth/diag/set")
    _, attributes = cookie_attributes(response.headers["set-cookie"])
    assert "secure" not in attributes
    assert "httponly" in attributes


async def test_check_reports_the_cookie(
    make_settings: SettingsFactory, client_for: ClientFactory
) -> None:
    app = create_app(make_settings(diagnostics_enabled=True))
    async with client_for(app, base_url="https://mealmate.example.ts.net") as client:
        before = await client.post("/api/auth/diag/check")
        await client.post("/api/auth/diag/set")
        after = await client.post("/api/auth/diag/check")
        elsewhere = await client.get("/api/version")

    assert before.json() == {"present": False}
    assert after.json() == {"present": True}
    assert after.headers["cache-control"] == "no-store"
    assert "mm_diag" not in elsewhere.request.headers.get("cookie", "")


async def test_request_echo_disabled_by_default(client: AsyncClient) -> None:
    response = await client.get("/api/auth/diag/request")
    assert response.status_code == 404
    assert response.json()["code"] == "common.not_found"


async def test_request_echo_shows_what_the_app_sees(
    make_settings: SettingsFactory, client_for: ClientFactory
) -> None:
    app = create_app(make_settings(diagnostics_enabled=True))
    async with client_for(app, base_url="https://mealmate.example.ts.net") as client:
        forwarded = await client.get(
            "/api/auth/diag/request",
            headers={"X-Forwarded-For": "100.64.0.7", "X-Forwarded-Proto": "https"},
        )
        plain = await client.get("/api/auth/diag/request")

    # The test transport is not uvicorn, so the forwarded headers are only echoed, not applied.
    assert forwarded.status_code == 200
    assert forwarded.json() == {
        "client_host": "127.0.0.1",
        "scheme": "https",
        "host_header": "mealmate.example.ts.net",
        "x_forwarded_for": "100.64.0.7",
        "x_forwarded_proto": "https",
    }
    assert forwarded.headers["cache-control"] == "no-store"
    assert plain.json()["x_forwarded_for"] is None
    assert plain.json()["x_forwarded_proto"] is None
