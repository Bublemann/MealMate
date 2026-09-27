from collections.abc import Iterator
from typing import Annotated

import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from httpx import AsyncClient
from pydantic import AnyHttpUrl, BaseModel, Field

from app.core.errors import ApiError, ErrorCode
from app.schemas.errors import ERROR_RESPONSES

EMPTY = {"params": {}, "fields": []}


class Body(BaseModel):
    name: str = Field(min_length=2, max_length=5)
    servings: int = Field(ge=1, le=20)
    source: AnyHttpUrl
    code: str = Field(pattern=r"^[0-9]{8}$")
    kind: int


router = APIRouter(prefix="/api/test", responses=ERROR_RESPONSES)


@router.post("/validate")
async def validate(body: Body, limit: Annotated[int, Query(ge=1)] = 10) -> dict[str, str]:
    return {"name": body.name}


@router.get("/forbidden")
async def forbidden() -> None:
    raise ApiError(ErrorCode.FORBIDDEN, status_code=403, params={"reason": "not_owner"})


@router.get("/unauthorized")
async def unauthorized() -> None:
    raise HTTPException(status_code=401)


@router.get("/crash")
async def crash() -> None:
    raise RuntimeError("secret detail /data/mealmate.db")


@router.get("/broken-stream")
async def broken_stream() -> StreamingResponse:
    def chunks() -> Iterator[bytes]:
        yield b"partial"
        raise RuntimeError("failed mid-stream")

    return StreamingResponse(chunks())


@pytest.fixture
def app(app: FastAPI) -> FastAPI:
    app.include_router(router)
    return app


async def test_unknown_api_path_is_a_json_404(client: AsyncClient) -> None:
    for path in ("/api/nope", "/api", "/api/", "/api/health/"):
        response = await client.get(path)
        assert response.status_code == 404, path
        assert response.headers["content-type"] == "application/json"
        assert response.json() == {"code": "common.not_found", **EMPTY}


async def test_unknown_path_outside_api_is_a_json_404_without_frontend(
    client: AsyncClient,
) -> None:
    response = await client.get("/lists")
    assert response.status_code == 404
    assert response.json()["code"] == "common.not_found"


async def test_wrong_method(client: AsyncClient) -> None:
    response = await client.post("/api/version")
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert response.json() == {"code": "common.method_not_allowed", **EMPTY}


async def test_validation_error_lists_field_codes(client: AsyncClient) -> None:
    response = await client.post(
        "/api/test/validate?limit=0",
        json={"name": "x", "servings": 99, "source": "not a url", "code": "12ab"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "common.validation"
    assert body["params"] == {}
    assert {tuple(field["loc"]): field["code"] for field in body["fields"]} == {
        ("query", "limit"): "out_of_range",
        ("body", "name"): "too_short",
        ("body", "servings"): "out_of_range",
        ("body", "source"): "invalid_format",
        ("body", "code"): "invalid_format",
        ("body", "kind"): "required",
    }


async def test_validation_error_for_wrong_types_and_bad_json(client: AsyncClient) -> None:
    valid = {"name": "abc", "servings": 2, "source": "https://example.org", "code": "12345678"}
    response = await client.post("/api/test/validate", json=valid | {"kind": "x", "name": "abcdef"})
    assert {tuple(f["loc"]): f["code"] for f in response.json()["fields"]} == {
        ("body", "kind"): "invalid",
        ("body", "name"): "too_long",
    }

    response = await client.post(
        "/api/test/validate", content=b"{", headers={"content-type": "application/json"}
    )
    assert response.status_code == 422
    assert [field["code"] for field in response.json()["fields"]] == ["invalid"]


async def test_api_error(client: AsyncClient) -> None:
    response = await client.get("/api/test/forbidden")
    assert response.status_code == 403
    assert response.json() == {
        "code": "common.forbidden",
        "params": {"reason": "not_owner"},
        "fields": [],
    }


async def test_http_exception(client: AsyncClient) -> None:
    response = await client.get("/api/test/unauthorized")
    assert response.status_code == 401
    assert response.json() == {"code": "common.unauthorized", **EMPTY}


async def test_unhandled_error_is_a_bare_500(client: AsyncClient) -> None:
    response = await client.get("/api/test/crash")
    assert response.status_code == 500
    assert response.json() == {"code": "common.internal", **EMPTY}
    assert "secret detail" not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "content-security-policy" in response.headers


async def test_error_after_the_response_started_is_not_masked(client: AsyncClient) -> None:
    # The status line is already out; the only honest option is to abort the response.
    with pytest.raises(RuntimeError, match="failed mid-stream"):
        await client.get("/api/test/broken-stream")
