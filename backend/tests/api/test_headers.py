import httpx
import pytest
from fastapi import APIRouter, FastAPI, Response
from httpx import AsyncClient

from app.main import create_app
from tests.support import ClientFactory, SettingsFactory

CSP = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' blob: data:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; "
    "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)

router = APIRouter(prefix="/api/test")


@router.get("/cached")
async def cached(response: Response) -> dict[str, str]:
    response.headers["Cache-Control"] = "private, max-age=3600"
    return {}


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    app.include_router(router)
    return app


def assert_security_headers(response: httpx.Response) -> None:
    assert response.headers["content-security-policy"] == CSP
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == "camera=(self), microphone=(), geolocation=()"


@pytest.mark.parametrize("path", ["/api/health", "/api/version", "/api/nope", "/elsewhere"])
async def test_security_headers_on_every_response(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert_security_headers(response)
    assert "strict-transport-security" not in response.headers


async def test_hsts_only_over_https(app: FastAPI, client_for: ClientFactory) -> None:
    async with client_for(app, base_url="https://mealmate.example.ts.net") as client:
        response = await client.get("/api/health")
    assert response.headers["strict-transport-security"] == "max-age=31536000"
    assert_security_headers(response)


@pytest.mark.parametrize("path", ["/api/health", "/api/version", "/api/nope"])
async def test_api_responses_are_not_stored(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.headers["cache-control"] == "no-store"


async def test_route_may_set_its_own_cache_control(client: AsyncClient) -> None:
    response = await client.get("/api/test/cached")
    assert response.headers["cache-control"] == "private, max-age=3600"


async def test_no_cache_header_outside_api(client: AsyncClient) -> None:
    response = await client.get("/elsewhere")
    assert "cache-control" not in response.headers


async def test_docs_disabled_by_default(client: AsyncClient) -> None:
    for path in ("/api/docs", "/api/openapi.json", "/api/redoc", "/docs", "/openapi.json"):
        response = await client.get(path)
        assert response.status_code == 404, path


async def test_docs_when_enabled(make_settings: SettingsFactory, client_for: ClientFactory) -> None:
    app = create_app(make_settings(api_docs_enabled=True))
    async with client_for(app) as client:
        docs = await client.get("/api/docs")
        schema = await client.get("/api/openapi.json")
        oauth_redirect = await client.get("/docs/oauth2-redirect")
    assert docs.status_code == 200
    assert "https://cdn.jsdelivr.net" in docs.headers["content-security-policy"]
    assert schema.status_code == 200
    assert schema.headers["content-security-policy"] == CSP
    assert "/api/health" in schema.json()["paths"]
    assert oauth_redirect.status_code == 404
