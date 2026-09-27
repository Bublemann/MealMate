"""Request body limits: 1 MiB in general, 10 MB plus multipart framing for photos (SEC-07)."""

import json
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import APIRouter, FastAPI, Request
from httpx import AsyncClient

from app.core.bodylimit import MAX_BODY_BYTES, MAX_PHOTO_BODY_BYTES
from app.core.headers import CONTENT_SECURITY_POLICY
from app.schemas.errors import ERROR_RESPONSES
from tests.accounts import Account, error, make_user
from tests.meals import create_meal, get_meal

CHUNK = 64 * 1024
TOO_LARGE = "common.payload_too_large"
PHOTO_TOO_LARGE = "media.too_large"
BOUNDARY = "body-limit-test"

router = APIRouter(prefix="/api/test", responses=ERROR_RESPONSES)


@router.post("/body")
async def body_length(request: Request) -> dict[str, int]:
    return {"length": len(await request.body())}


@router.post("/json")
async def echo_json(body: dict[str, str]) -> dict[str, str]:
    return body


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    app.include_router(router)
    return app


@pytest.fixture
async def anna(app: FastAPI, api: AsyncClient) -> Account:
    return await make_user(app, api, "anna")


@dataclass
class Exchange:
    """What a request sent straight to the ASGI app got back, and how much of its body was read."""

    reads: int = 0
    status: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> Any:
        return json.loads(self.body)


async def exchange(
    app: FastAPI,
    method: str,
    path: str,
    *,
    headers: Iterable[tuple[str, str]] = (),
    chunks: Iterable[bytes] = (),
) -> Exchange:
    """Drives `app` as a server would, sending the body in `chunks`."""
    result = Exchange()
    pending = list(chunks)

    async def receive() -> dict[str, Any]:
        result.reads += 1
        body = pending.pop(0) if pending else b""
        return {"type": "http.request", "body": body, "more_body": bool(pending)}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            result.status = message["status"]
            result.headers = {name.decode(): value.decode() for name, value in message["headers"]}
        else:
            result.body += message.get("body", b"")

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(name.lower().encode(), value.encode()) for name, value in headers],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
        "state": {},
    }
    await app(scope, receive, send)
    return result


def assert_refused(result: Exchange, code: str) -> None:
    assert result.status == 413
    assert result.json() == {"code": code, "params": {}, "fields": []}
    assert result.headers["connection"] == "close"
    assert result.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


async def chunked(content: bytes) -> AsyncIterator[bytes]:
    """`content` in chunks, sent without a Content-Length."""
    for start in range(0, len(content), CHUNK):
        yield content[start : start + CHUNK]


def multipart(size: int) -> tuple[bytes, dict[str, str]]:
    """A photo upload of exactly `size` bytes in total, multipart framing included."""
    head = (
        f"--{BOUNDARY}\r\n"
        'Content-Disposition: form-data; name="file"; filename="photo.jpg"\r\n'
        "Content-Type: image/jpeg\r\n\r\n"
    ).encode()
    tail = f"\r\n--{BOUNDARY}--\r\n".encode()
    content = head + b"\0" * (size - len(head) - len(tail)) + tail
    assert len(content) == size
    return content, {"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"}


# --- declared too large: refused before reading ------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path", "limit", "code"),
    [
        pytest.param("POST", "/api/test/body", MAX_BODY_BYTES, TOO_LARGE, id="api"),
        pytest.param("PATCH", "/api/me", MAX_BODY_BYTES, TOO_LARGE, id="me"),
        pytest.param("POST", "/elsewhere", MAX_BODY_BYTES, TOO_LARGE, id="other"),
        pytest.param(
            "PUT", "/api/meals/x/photo", MAX_PHOTO_BODY_BYTES, PHOTO_TOO_LARGE, id="photo"
        ),
        # Only the upload itself may be large.
        pytest.param("DELETE", "/api/meals/x/photo", MAX_BODY_BYTES, TOO_LARGE, id="delete"),
        pytest.param("PUT", "/api/meals/x/photos", MAX_BODY_BYTES, TOO_LARGE, id="photos"),
    ],
)
async def test_a_declared_length_over_the_limit_is_refused_unread(
    app: FastAPI, client: AsyncClient, method: str, path: str, limit: int, code: str
) -> None:
    result = await exchange(
        app, method, path, headers=[("Content-Length", str(limit + 1))], chunks=[b"x"]
    )

    assert_refused(result, code)
    assert result.reads == 0


async def test_a_declared_length_at_the_limit_is_read(app: FastAPI, client: AsyncClient) -> None:
    result = await exchange(
        app,
        "POST",
        "/api/test/body",
        headers=[("Content-Length", str(MAX_BODY_BYTES))],
        chunks=[b"x" * CHUNK] * (MAX_BODY_BYTES // CHUNK),
    )

    assert result.status == 200
    assert result.json() == {"length": MAX_BODY_BYTES}


# --- counted while streaming ----------------------------------------------------------------


async def test_a_streamed_body_is_cut_off_once_over_the_limit(
    app: FastAPI, client: AsyncClient
) -> None:
    chunk = MAX_BODY_BYTES // 4
    # A Content-Length that lies: the body is far longer than declared.
    result = await exchange(
        app,
        "POST",
        "/api/test/body",
        headers=[("Content-Length", "10")],
        chunks=[b"x" * chunk] * 20,
    )

    assert_refused(result, TOO_LARGE)
    # The fifth chunk passes the limit; nothing after it is read.
    assert result.reads == 5


async def test_a_bad_content_length_is_ignored_and_the_body_counted(
    app: FastAPI, client: AsyncClient
) -> None:
    small = await exchange(
        app, "POST", "/api/test/body", headers=[("Content-Length", "many")], chunks=[b"abc"]
    )
    large = await exchange(
        app,
        "POST",
        "/api/test/body",
        headers=[("Content-Length", "many")],
        chunks=[b"x" * (MAX_BODY_BYTES + 1)],
    )

    assert (small.status, small.json()) == (200, {"length": 3})
    assert_refused(large, TOO_LARGE)


@pytest.mark.parametrize(
    ("size", "status"), [(MAX_BODY_BYTES, 200), (MAX_BODY_BYTES + 1, 413)], ids=["at", "over"]
)
async def test_chunked_bodies_without_a_length(client: AsyncClient, size: int, status: int) -> None:
    response = await client.post("/api/test/body", content=chunked(b"x" * size))

    assert "content-length" not in response.request.headers
    assert response.status_code == status
    if status == 200:
        assert response.json() == {"length": MAX_BODY_BYTES}
    else:
        assert error(response) == TOO_LARGE
        assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


async def test_json_bodies_below_the_limit_are_unaffected(client: AsyncClient) -> None:
    body = {"name": "x" * (MAX_BODY_BYTES - 100)}

    response = await client.post("/api/test/json", json=body)

    assert response.status_code == 200
    assert response.json() == body
    assert (await client.post("/api/test/json", json={"a": "b"})).json() == {"a": "b"}
    assert (await client.get("/api/health")).json() == {"status": "ok"}


async def test_json_bodies_over_the_limit(client: AsyncClient) -> None:
    response = await client.post("/api/test/json", json={"name": "x" * MAX_BODY_BYTES})

    assert response.status_code == 413
    assert error(response) == TOO_LARGE


# --- photo uploads -----------------------------------------------------------------------------


async def test_photo_uploads_are_refused_before_authentication(client: AsyncClient) -> None:
    over, headers = multipart(MAX_PHOTO_BODY_BYTES + 1)
    at, _ = multipart(MAX_PHOTO_BODY_BYTES)

    declared = await client.put("/api/meals/x/photo", content=over, headers=headers)
    streamed = await client.put("/api/meals/x/photo", content=chunked(over), headers=headers)
    at_limit = await client.put("/api/meals/x/photo", content=at, headers=headers)

    for response in (declared, streamed):
        assert response.status_code == 413
        assert error(response) == PHOTO_TOO_LARGE
        assert response.headers["connection"] == "close"
        assert response.headers["cache-control"] == "no-store"
    assert "content-length" not in streamed.request.headers
    # At the limit the body is read, and only then is the missing token noticed.
    assert at_limit.status_code == 401
    assert error(at_limit) == "common.unauthorized"


async def test_photo_uploads_at_the_limit_reach_the_route(api: AsyncClient, anna: Account) -> None:
    meal = await create_meal(api, anna, "Curry")
    content, headers = multipart(MAX_PHOTO_BODY_BYTES)

    response = await api.put(
        f"/api/meals/{meal['id']}/photo", content=content, headers=anna.headers | headers
    )

    # The route's own limit (10 MB of file) answers: the middleware let it through.
    assert response.status_code == 413
    assert error(response) == PHOTO_TOO_LARGE
    assert "connection" not in response.headers
    assert (await get_meal(api, anna, meal["id"])).json()["photo"] is None
