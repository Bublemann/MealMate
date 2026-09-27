from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.main import create_app
from app.web.static import IMMUTABLE, NO_CACHE
from tests.support import ClientFactory, SettingsFactory

INDEX = "<!doctype html><title>MealMate</title>"
OUTSIDE = "a file outside the build"


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "icons").mkdir()
    (dist / "index.html").write_text(INDEX)
    (dist / "sw.js").write_text("self.addEventListener('install', () => {});")
    (dist / "manifest.webmanifest").write_text('{"name": "MealMate"}')
    (dist / "assets" / "index-Bx1y2z3.js").write_text("console.log('app');")
    (dist / "icons" / "icon-192.png").write_bytes(b"\x89PNG\r\n")
    (tmp_path / "secret.txt").write_text(OUTSIDE)
    (dist / "leak.txt").symlink_to(tmp_path / "secret.txt")
    return dist


@pytest.fixture
async def client(
    make_settings: SettingsFactory, client_for: ClientFactory, static_dir: Path
) -> AsyncIterator[AsyncClient]:
    async with client_for(create_app(make_settings(static_dir=static_dir))) as client:
        yield client


@pytest.mark.parametrize(
    "path", ["/", "/lists", "/lists/0192a/edit", "/me/", "/x.png", "/" + "a" * 5000]
)
async def test_client_routes_get_index_html(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 200
    assert response.text == INDEX
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == NO_CACHE


async def test_hashed_assets_are_immutable(client: AsyncClient) -> None:
    response = await client.get("/assets/index-Bx1y2z3.js")
    assert response.status_code == 200
    assert response.text == "console.log('app');"
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.headers["cache-control"] == IMMUTABLE


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/index.html", "text/html"),
        ("/sw.js", "text/javascript"),
        ("/manifest.webmanifest", "application/manifest+json"),
        ("/icons/icon-192.png", "image/png"),
    ],
)
async def test_other_files_are_revalidated(
    client: AsyncClient, path: str, content_type: str
) -> None:
    response = await client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(content_type)
    assert response.headers["cache-control"] == NO_CACHE


async def test_logged_with_route_template(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    await client.get("/lists/secret-list-id")
    output = capsys.readouterr().out
    assert '"route": "/{path}"' in output
    assert "secret-list-id" not in output


async def test_security_headers_on_static_files(client: AsyncClient) -> None:
    response = await client.get("/")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("path", ["/assets/index-gone.js", "/assets", "/assets/"])
async def test_missing_asset_is_404_not_index(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 404
    assert response.json()["code"] == "common.not_found"


async def test_head(client: AsyncClient) -> None:
    response = await client.head("/lists")
    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["cache-control"] == NO_CACHE


async def test_other_methods_are_not_allowed(client: AsyncClient) -> None:
    response = await client.post("/lists")
    assert response.status_code == 405
    assert response.json()["code"] == "common.method_not_allowed"


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api"), ("GET", "/api/"), ("GET", "/api/unknown"), ("POST", "/api/unknown")],
)
async def test_api_paths_never_fall_back(client: AsyncClient, method: str, path: str) -> None:
    response = await client.request(method, path, headers={"accept": "text/html"})
    assert response.status_code == 404
    assert response.json()["code"] == "common.not_found"


async def test_api_still_works(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "path",
    [
        "/..%2fsecret.txt",
        "/..%2f..%2f..%2fetc%2fpasswd",
        "/assets/..%2f..%2fsecret.txt",
        "/icons/%2e%2e%2f%2e%2e%2fsecret.txt",
        "/%2fetc%2fpasswd",
        "/leak.txt",
        "/bad%00name",
    ],
)
async def test_traversal_is_rejected(client: AsyncClient, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 404
    assert OUTSIDE not in response.text
    assert "root:" not in response.text


async def test_not_served_without_index_html(
    make_settings: SettingsFactory, client_for: ClientFactory, tmp_path: Path
) -> None:
    for static_dir in (tmp_path / "missing", tmp_path):
        async with client_for(create_app(make_settings(static_dir=static_dir))) as client:
            response = await client.get("/")
        assert response.status_code == 404
