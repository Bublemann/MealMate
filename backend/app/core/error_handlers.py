"""Render every failure as the error envelope (plan § 5.3).

Exception handlers cover `ApiError`, Starlette's `HTTPException` (unknown paths, wrong methods)
and request validation. `ErrorEnvelopeMiddleware` turns any other exception into a
`common.internal` 500 without details. It sits inside the logging and security-header middleware,
so those responses are logged and carry the same headers as any other.
"""

import logging
from collections.abc import Iterable, Mapping

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import ApiError, ErrorCode, ErrorParam, FieldErrorCode
from app.core.logging import route_template
from app.schemas.errors import ErrorResponse, FieldError

logger = logging.getLogger(__name__)

_STATUS_ERROR_CODES = {
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
    status.HTTP_503_SERVICE_UNAVAILABLE: ErrorCode.SERVICE_UNAVAILABLE,
}

# Pydantic error types (https://docs.pydantic.dev/latest/errors/validation_errors/).
_FIELD_ERROR_CODES = {
    "missing": FieldErrorCode.REQUIRED,
    "string_too_short": FieldErrorCode.TOO_SHORT,
    "too_short": FieldErrorCode.TOO_SHORT,
    "string_too_long": FieldErrorCode.TOO_LONG,
    "too_long": FieldErrorCode.TOO_LONG,
    "multiple_of": FieldErrorCode.OUT_OF_RANGE,
    "string_pattern_mismatch": FieldErrorCode.INVALID_FORMAT,
    "value_error": FieldErrorCode.INVALID_FORMAT,
}
_FIELD_ERROR_PREFIXES = (
    ("greater_than", FieldErrorCode.OUT_OF_RANGE),
    ("less_than", FieldErrorCode.OUT_OF_RANGE),
    ("url_", FieldErrorCode.INVALID_FORMAT),
)


def field_error_code(error_type: str) -> FieldErrorCode:
    if code := _FIELD_ERROR_CODES.get(error_type):
        return code
    for prefix, code in _FIELD_ERROR_PREFIXES:
        if error_type.startswith(prefix):
            return code
    return FieldErrorCode.INVALID


def status_error_code(status_code: int) -> ErrorCode:
    if code := _STATUS_ERROR_CODES.get(status_code):
        return code
    return ErrorCode.INTERNAL if status_code >= 500 else ErrorCode.VALIDATION


def error_response(
    status_code: int,
    code: ErrorCode,
    *,
    params: Mapping[str, ErrorParam] | None = None,
    fields: Iterable[FieldError] = (),
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(code=code, params=dict(params or {}), fields=list(fields))
    return JSONResponse(body.model_dump(mode="json"), status_code=status_code, headers=headers)


def exception_response(exc: Exception) -> JSONResponse:
    match exc:
        case ApiError():
            fields = (FieldError(loc=list(field.loc), code=field.code) for field in exc.fields)
            return error_response(
                exc.status_code, exc.code, params=exc.params, fields=fields, headers=exc.headers
            )
        case RequestValidationError():
            fields = (
                FieldError(loc=list(error["loc"]), code=field_error_code(error["type"]))
                for error in exc.errors()
            )
            return error_response(
                status.HTTP_422_UNPROCESSABLE_CONTENT, ErrorCode.VALIDATION, fields=fields
            )
        case StarletteHTTPException():
            return error_response(
                exc.status_code, status_error_code(exc.status_code), headers=exc.headers
            )
        case _:
            return error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, ErrorCode.INTERNAL)


async def _handle_exception(_request: Request, exc: Exception) -> JSONResponse:
    return exception_response(exc)


def install_exception_handlers(app: FastAPI) -> None:
    for exc_class in (ApiError, RequestValidationError, StarletteHTTPException):
        app.add_exception_handler(exc_class, _handle_exception)
    # Last resort for failures in the outer middleware; ErrorEnvelopeMiddleware handles the rest.
    app.add_exception_handler(Exception, _handle_exception)


class ErrorEnvelopeMiddleware:
    """Answers an unhandled exception with a bare `common.internal` 500 and logs it."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_tracking(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking)
        except Exception:
            logger.exception("unhandled error", extra={"route": route_template(scope)})
            if response_started:
                raise
            response = error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, ErrorCode.INTERNAL)
            await response(scope, receive, send)
