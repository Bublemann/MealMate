import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import Settings, get_settings
from app.main import create_app
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
        values: dict[str, Any] = {"secret_key": TEST_SECRET_KEY, "data_dir": data_dir}
        return Settings(**(values | overrides))

    return make


@pytest.fixture
def settings(make_settings: SettingsFactory) -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client_for() -> ClientFactory:
    return serve


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with serve(app) as client:
        yield client
