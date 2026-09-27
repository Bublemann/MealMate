import json
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import iter_route_contexts
from httpx import AsyncClient

from app.core.logging import configure_logging
from app.main import create_app
from tests.support import ClientFactory, SettingsFactory

router = APIRouter(prefix="/api/test")


@router.get("/codes/{code}")
async def lookup_code(code: str) -> dict[str, str]:
    return {}


@router.get("/crash")
async def crash() -> None:
    raise RuntimeError("boom")


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    app.include_router(router)
    return app


def request_logs(output: str) -> list[dict[str, Any]]:
    entries = [json.loads(line) for line in output.splitlines()]
    return [entry for entry in entries if entry["logger"] == "mealmate.request"]


async def test_logs_route_template_not_path_or_query(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    await client.get("/api/test/codes/invite-code-123?token=refresh-token-456")
    await client.get("/api/version?token=refresh-token-456")
    await client.get("/api/unknown-secret-path-789?token=refresh-token-456")
    output = capsys.readouterr().out

    for secret in ("invite-code-123", "refresh-token-456", "unknown-secret-path-789", "token="):
        assert secret not in output
    assert [(e["method"], e["route"], e["status"]) for e in request_logs(output)] == [
        ("GET", "/api/test/codes/{code}", 200),
        ("GET", "/api/version", 200),
        ("GET", "<unmatched>", 404),
    ]
    assert all(isinstance(e["duration_ms"], float) for e in request_logs(output))


async def test_logs_unhandled_errors_with_status_500(
    client: AsyncClient, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    await client.get("/api/test/crash")
    entries = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    error = next(e for e in entries if e["msg"] == "unhandled error")
    assert error["level"] == "ERROR"
    assert error["route"] == "/api/test/crash"
    assert "RuntimeError: boom" in error["exc"]
    assert [
        (e["route"], e["status"]) for e in request_logs("\n".join(map(json.dumps, entries)))
    ] == [("/api/test/crash", 500)]


async def test_debug_logging_leaves_sql_out(
    make_settings: SettingsFactory, client_for: ClientFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    app = create_app(make_settings(log_level="DEBUG"))
    try:
        async with client_for(app) as client:
            capsys.readouterr()
            assert (await client.get("/api/health")).status_code == 200
            entries = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    finally:
        configure_logging("INFO")

    loggers = {entry["logger"] for entry in entries}
    assert "mealmate.request" in loggers
    assert not [name for name in loggers if name.startswith("aiosqlite")]
    assert "SELECT 1" not in json.dumps(entries)


def test_every_route_carries_its_full_template(app: FastAPI) -> None:
    """The log reads the template from the matched route, which knows nothing about prefixes
    added by `include_router(prefix=...)`; routers must carry their full prefix instead."""
    for context in iter_route_contexts(app.routes):
        assert context.path_format == context.original_route.path_format, context.path_format
