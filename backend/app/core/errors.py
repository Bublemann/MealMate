"""Error codes (I18N-03).

The backend never returns user-facing text. Every error is a code, translated by the frontend
(`error.<code>` in `de.json` / `en.json`). Adding a code: add it here, run `make openapi`, then
add both translations; a frontend test fails until they exist.
"""

from collections.abc import Mapping
from enum import StrEnum


class ErrorCode(StrEnum):
    """What went wrong; the frontend shows the translation `error.<code>`."""

    INTERNAL = "common.internal"
    NOT_FOUND = "common.not_found"
    METHOD_NOT_ALLOWED = "common.method_not_allowed"
    VALIDATION = "common.validation"
    RATE_LIMITED = "common.rate_limited"
    UNAUTHORIZED = "common.unauthorized"
    FORBIDDEN = "common.forbidden"
    SERVICE_UNAVAILABLE = "common.service_unavailable"


class FieldErrorCode(StrEnum):
    """Why a single request field was rejected (`fields[].code` in the envelope)."""

    REQUIRED = "required"
    INVALID = "invalid"
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    OUT_OF_RANGE = "out_of_range"
    INVALID_FORMAT = "invalid_format"


# A plain alias (not a `type` statement) so the OpenAPI schema inlines the union.
ErrorParam = str | int | float | bool


class ApiError(Exception):
    """An expected failure; rendered as the error envelope with the given status."""

    def __init__(
        self,
        code: ErrorCode,
        *,
        status_code: int,
        params: Mapping[str, ErrorParam] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.params = dict(params or {})
        self.headers = dict(headers or {})
