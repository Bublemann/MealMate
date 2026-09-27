"""Error codes (I18N-03).

The backend never returns user-facing text. Every error is a code, translated by the frontend
(`error.<code>` in `de.json` / `en.json`). Adding a code: add it here, run `make openapi`, then
add both translations; a frontend test fails until they exist.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
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
    # 413: a request body larger than the server accepts (1 MiB; photos: `media.too_large`).
    PAYLOAD_TOO_LARGE = "common.payload_too_large"

    # 401: wrong username or password.
    INVALID_CREDENTIALS = "auth.invalid_credentials"
    # 403: the password was right, but an admin deactivated the account.
    ACCOUNT_DEACTIVATED = "auth.account_deactivated"
    # 401: the access token expired; the client refreshes it and retries.
    TOKEN_EXPIRED = "auth.token_expired"  # noqa: S105 -- an error code, not a secret
    # 401: no usable refresh cookie (missing, unknown or idle-expired); the client shows login.
    SESSION_EXPIRED = "auth.session_expired"
    # 401: the session was revoked (reuse, logout elsewhere, deactivation); the client wipes
    # its local data (SYNC-10).
    SESSION_REVOKED = "auth.session_revoked"
    # 401: a Home Screen fork was refused; the client shows the login screen once.
    LOGIN_REQUIRED = "auth.login_required"
    # 403: a refresh request without the `X-MealMate-Client` header.
    CSRF = "auth.csrf"
    # 404: an invite or reset code that is unknown, expired, used or revoked.
    CODE_INVALID = "auth.code_invalid"
    # 403: the current password given to change it is wrong.
    PASSWORD_INCORRECT = "auth.password_incorrect"  # noqa: S105 -- an error code

    COUPLE_ALREADY_IN_COUPLE = "couple.already_in_couple"
    COUPLE_TARGET_IN_COUPLE = "couple.target_in_couple"
    COUPLE_REQUEST_PENDING = "couple.request_pending"

    ADMIN_SELF_FORBIDDEN = "admin.self_forbidden"
    ADMIN_LAST_ADMIN = "admin.last_admin"
    ADMIN_PUBLIC_URL_MISSING = "admin.public_url_missing"

    # 409: the base unit cannot change while products are linked (ING-02).
    INGREDIENT_BASE_UNIT_LOCKED = "ingredient.base_unit_locked"
    # 409: the ingredient is still referenced; `params` counts the references per kind
    # (`products`, `meals`; lists join in M5a).
    INGREDIENT_IN_USE = "ingredient.in_use"
    # 409: merging would move products to an ingredient with another base unit.
    INGREDIENT_MERGE_BASE_UNIT_MISMATCH = "ingredient.merge_base_unit_mismatch"
    # 409: a product's nutrition basis must be its ingredient's base unit (ING-04).
    PRODUCT_BASIS_MISMATCH = "product.basis_mismatch"

    # 413: an uploaded photo is larger than 10 MB (SEC-07).
    MEDIA_TOO_LARGE = "media.too_large"
    # 415: an upload that is not a JPEG, PNG or WebP image (whatever its name claims).
    MEDIA_UNSUPPORTED_TYPE = "media.unsupported_type"
    # 422: an image with more than 24 megapixels (SEC-07).
    MEDIA_TOO_MANY_PIXELS = "media.too_many_pixels"


class FieldErrorCode(StrEnum):
    """Why a single request field was rejected (`fields[].code` in the envelope)."""

    REQUIRED = "required"
    INVALID = "invalid"
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    OUT_OF_RANGE = "out_of_range"
    INVALID_FORMAT = "invalid_format"
    TAKEN = "taken"
    TOO_COMMON = "too_common"
    SAME_AS_USERNAME = "same_as_username"


# A plain alias (not a `type` statement) so the OpenAPI schema inlines the union.
ErrorParam = str | int | float | bool


@dataclass(frozen=True)
class FieldProblem:
    """One rejected request field, found by a service rather than by request validation."""

    loc: tuple[str | int, ...]
    code: FieldErrorCode


class ApiError(Exception):
    """An expected failure; rendered as the error envelope with the given status."""

    def __init__(
        self,
        code: ErrorCode,
        *,
        status_code: int,
        params: Mapping[str, ErrorParam] | None = None,
        headers: Mapping[str, str] | None = None,
        fields: Iterable[FieldProblem] = (),
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.params = dict(params or {})
        self.headers = dict(headers or {})
        self.fields = list(fields)


def validation_error(fields: Iterable[FieldProblem]) -> ApiError:
    """A 422 `common.validation` with the given field problems, as request validation sends."""
    return ApiError(ErrorCode.VALIDATION, status_code=422, fields=fields)


def not_found() -> ApiError:
    return ApiError(ErrorCode.NOT_FOUND, status_code=404)


def rate_limited(retry_after: int) -> ApiError:
    """429 `common.rate_limited`; the client may retry after `retry_after` seconds."""
    return ApiError(
        ErrorCode.RATE_LIMITED,
        status_code=429,
        params={"retry_after": retry_after},
        headers={"Retry-After": str(retry_after)},
    )
