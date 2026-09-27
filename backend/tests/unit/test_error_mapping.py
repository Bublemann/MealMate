import json

import pytest
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from app.core.error_handlers import exception_response, field_error_code, status_error_code
from app.core.errors import ApiError, ErrorCode, FieldErrorCode


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [
        ("missing", FieldErrorCode.REQUIRED),
        ("string_too_short", FieldErrorCode.TOO_SHORT),
        ("too_short", FieldErrorCode.TOO_SHORT),
        ("string_too_long", FieldErrorCode.TOO_LONG),
        ("too_long", FieldErrorCode.TOO_LONG),
        ("greater_than", FieldErrorCode.OUT_OF_RANGE),
        ("greater_than_equal", FieldErrorCode.OUT_OF_RANGE),
        ("less_than", FieldErrorCode.OUT_OF_RANGE),
        ("less_than_equal", FieldErrorCode.OUT_OF_RANGE),
        ("multiple_of", FieldErrorCode.OUT_OF_RANGE),
        ("url_parsing", FieldErrorCode.INVALID_FORMAT),
        ("url_scheme", FieldErrorCode.INVALID_FORMAT),
        ("string_pattern_mismatch", FieldErrorCode.INVALID_FORMAT),
        ("value_error", FieldErrorCode.INVALID_FORMAT),
        ("int_parsing", FieldErrorCode.INVALID),
        ("json_invalid", FieldErrorCode.INVALID),
        ("literal_error", FieldErrorCode.INVALID),
    ],
)
def test_field_error_codes(error_type: str, expected: FieldErrorCode) -> None:
    assert field_error_code(error_type) is expected


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (400, ErrorCode.VALIDATION),
        (401, ErrorCode.UNAUTHORIZED),
        (403, ErrorCode.FORBIDDEN),
        (404, ErrorCode.NOT_FOUND),
        (405, ErrorCode.METHOD_NOT_ALLOWED),
        (413, ErrorCode.VALIDATION),
        (429, ErrorCode.RATE_LIMITED),
        (500, ErrorCode.INTERNAL),
        (502, ErrorCode.INTERNAL),
        (503, ErrorCode.SERVICE_UNAVAILABLE),
    ],
)
def test_status_error_codes(status_code: int, expected: ErrorCode) -> None:
    assert status_error_code(status_code) is expected


def body(exc: Exception) -> tuple[int, dict[str, object]]:
    response = exception_response(exc)
    return response.status_code, json.loads(response.body)


def test_api_error_keeps_params_and_headers() -> None:
    exc = ApiError(
        ErrorCode.RATE_LIMITED,
        status_code=429,
        params={"seconds": 30},
        headers={"Retry-After": "30"},
    )
    response = exception_response(exc)
    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert json.loads(response.body) == {
        "code": "common.rate_limited",
        "params": {"seconds": 30},
        "fields": [],
    }


def test_validation_error_lists_fields() -> None:
    exc = RequestValidationError(
        [
            {"type": "missing", "loc": ("body", "name"), "msg": "Field required", "input": {}},
            {"type": "too_long", "loc": ("body", "tags", 3), "msg": "...", "input": []},
        ]
    )
    assert body(exc) == (
        422,
        {
            "code": "common.validation",
            "params": {},
            "fields": [
                {"loc": ["body", "name"], "code": "required"},
                {"loc": ["body", "tags", 3], "code": "too_long"},
            ],
        },
    )


def test_http_exception_maps_status() -> None:
    assert body(HTTPException(status_code=401)) == (
        401,
        {"code": "common.unauthorized", "params": {}, "fields": []},
    )


def test_anything_else_is_internal_without_details() -> None:
    status_code, content = body(RuntimeError("secret detail"))
    assert status_code == 500
    assert content == {"code": "common.internal", "params": {}, "fields": []}
