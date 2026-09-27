import os
import shutil
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import DATABASE_FILENAME, Settings, get_settings
from app.core.ratelimit import RateLimits
from app.db.migrations import upgrade_database
from app.main import create_app
from tests.accounts import FakeClock
from tests.support import TEST_SECRET_KEY, ClientFactory, SettingsFactory, serve


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No test sees the developer's MEALMATE_* variables or another test's cached settings."""
    for name in [name for name in os.environ if name.startswith("MEALMATE_")]:
        monkeypatch.delenv(name)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def secret_key() -> str:
    return TEST_SECRET_KEY


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def make_settings(data_dir: Path) -> SettingsFactory:
    def make(**overrides: Any) -> Settings:
        values: dict[str, Any] = {
            "secret_key": TEST_SECRET_KEY,
            "data_dir": data_dir,
            "bcrypt_rounds": 4,
        }
        return Settings(**(values | overrides))

    return make


@pytest.fixture
def settings(make_settings: SettingsFactory) -> Settings:
    return make_settings()


@pytest.fixture(scope="session")
def migrated_database(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A database at the latest revision, migrated once and copied into each test's data dir."""
    directory = tmp_path_factory.mktemp("template")
    upgrade_database(directory)
    return directory / DATABASE_FILENAME


@pytest.fixture
def app(settings: Settings, migrated_database: Path) -> FastAPI:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(migrated_database, settings.database_path)
    return create_app(settings)


@pytest.fixture
def clock(app: FastAPI) -> FakeClock:
    """Controls the app's time: `clock.advance(seconds=61)`."""
    fake = FakeClock()
    app.state.clock = fake
    app.state.rate_limits = RateLimits(clock=fake.monotonic)
    return fake


@pytest.fixture
async def api(app: FastAPI, clock: FakeClock) -> AsyncIterator[AsyncClient]:
    """A client over HTTPS (so it keeps `Secure` cookies), with the fake clock installed."""
    async with serve(app, base_url="https://testserver.local") as client:
        yield client


@pytest.fixture
def client_for() -> ClientFactory:
    return serve


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with serve(app) as client:
        yield client
