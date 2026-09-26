"""The error envelope every failed request returns (plan § 5.3)."""

from typing import Any

from pydantic import BaseModel

from app.core.errors import ErrorCode, ErrorParam, FieldErrorCode


class FieldError(BaseModel):
    """One rejected request field; `loc` is its path, e.g. `["body", "name"]`."""

    loc: list[str | int]
    code: FieldErrorCode


class ErrorResponse(BaseModel):
    """`params` fill placeholders in the translation; `fields` lists rejected request fields."""

    code: ErrorCode
    params: dict[str, ErrorParam]
    fields: list[FieldError]


# Documented on every API route; any non-2xx status carries the envelope.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    "default": {"model": ErrorResponse, "description": "Error envelope; `code` names the error"},
}
