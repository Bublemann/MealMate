import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import REPO_URL, Settings, source_url
from app.db.session import Database
from app.main import create_app
from tests.support import ClientFactory, SettingsFactory

SHA = "0123456789abcdef0123456789abcdef01234567"


async def test_health_ok(client: AsyncClient, data_dir: Path) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert (data_dir / "mealmate.db").is_file()


async def test_health_fails_when_database_is_unavailable(
    app: FastAPI, client: AsyncClient, tmp_path: Path
) -> None:
    await app.state.database.dispose()
    # The parent directory does not exist, so SQLite cannot open the file.
    app.state.database = Database(tmp_path / "missing" / "mealmate.db")

    response = await client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"code": "common.service_unavailable", "params": {}, "fields": []}
    await app.state.database.dispose()


async def test_health_fails_when_data_dir_is_not_writable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, data_dir: Path
) -> None:
    real_access = os.access

    def access(path: str | os.PathLike[str], mode: int) -> bool:
        if Path(path) == data_dir and mode == os.W_OK:
            return False
        return real_access(path, mode)

    monkeypatch.setattr(os, "access", access)
    response = await client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["code"] == "common.service_unavailable"


async def test_version_defaults(client: AsyncClient) -> None:
    response = await client.get("/api/version")
    assert response.status_code == 200
    assert response.json() == {"version": "0.0.0-dev", "commit": "unknown", "source_url": REPO_URL}


async def test_version_links_the_exact_commit(
    make_settings: SettingsFactory, client_for: ClientFactory
) -> None:
    app = create_app(make_settings(version="2.0.0-alpha.1", commit=SHA))
    async with client_for(app) as client:
        response = await client.get("/api/version")
    assert response.json() == {
        "version": "2.0.0-alpha.1",
        "commit": SHA,
        "source_url": f"{REPO_URL}/tree/{SHA}",
    }


@pytest.mark.parametrize(
    ("commit", "expected"),
    [
        (SHA, f"{REPO_URL}/tree/{SHA}"),
        ("0123abc", f"{REPO_URL}/tree/0123abc"),
        ("unknown", REPO_URL),
        ("ci", REPO_URL),
        ("", REPO_URL),
        ("0123ABC", REPO_URL),
        ("0123abc/../../evil", REPO_URL),
        (SHA + "0", REPO_URL),
    ],
)
def test_source_url(commit: str, expected: str) -> None:
    assert source_url(commit) == expected


async def test_create_app_reads_the_environment(
    monkeypatch: pytest.MonkeyPatch, secret_key: str, data_dir: Path, client_for: ClientFactory
) -> None:
    monkeypatch.setenv("MEALMATE_SECRET_KEY", secret_key)
    monkeypatch.setenv("MEALMATE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MEALMATE_VERSION", "2.0.0")
    async with client_for(create_app()) as client:
        response = await client.get("/api/version")
    assert response.json()["version"] == "2.0.0"


async def test_runs_under_the_asgi_lifespan_protocol(settings: Settings) -> None:
    """The full stack as uvicorn drives it: lifespan events pass through every middleware."""
    app = create_app(settings)
    to_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    from_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    scope = {"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}}
    lifespan = asyncio.create_task(app(scope, to_app.get, from_app.put))

    await to_app.put({"type": "lifespan.startup"})
    assert (await from_app.get())["type"] == "lifespan.startup.complete"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/api/health")
    await to_app.put({"type": "lifespan.shutdown"})
    assert (await from_app.get())["type"] == "lifespan.shutdown.complete"
    await lifespan

    assert response.json() == {"status": "ok"}


async def test_the_database_is_disposed_of_even_if_closing_open_food_facts_fails(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    disposed: list[Database] = []
    dispose = Database.dispose

    async def recorded_dispose(database: Database) -> None:
        disposed.append(database)
        await dispose(database)

    async def broken_aclose() -> None:
        raise RuntimeError("pool broken")

    monkeypatch.setattr(Database, "dispose", recorded_dispose)
    monkeypatch.setattr(app.state.off_refresh.off, "aclose", broken_aclose)

    with pytest.raises(RuntimeError, match="pool broken"):
        async with app.router.lifespan_context(app):
            pass

    assert disposed == [app.state.database]


def test_create_app_refuses_to_start_without_a_secret_key() -> None:
    with pytest.raises(ValueError, match="secret_key"):
        create_app()
