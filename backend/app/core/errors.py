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
    # 409: the request names another user than the one signed in (`X-MealMate-User` of the
    # ops): the phone's session changed hands while ops waited; they stay queued (SYNC-10).
    USER_MISMATCH = "auth.user_mismatch"

    COUPLE_ALREADY_IN_COUPLE = "couple.already_in_couple"
    COUPLE_TARGET_IN_COUPLE = "couple.target_in_couple"
    COUPLE_REQUEST_PENDING = "couple.request_pending"

    ADMIN_SELF_FORBIDDEN = "admin.self_forbidden"
    ADMIN_LAST_ADMIN = "admin.last_admin"
    ADMIN_PUBLIC_URL_MISSING = "admin.public_url_missing"

    # 409: the ingredient is still referenced; `params` counts the references per kind
    # (`meals`, `lists`).
    INGREDIENT_IN_USE = "ingredient.in_use"
    # 409: another ingredient has this barcode; `params.ingredient_id` is that one.
    INGREDIENT_BARCODE_TAKEN = "ingredient.barcode_taken"
    # 409: linking a barcode to an ingredient that already has one (the scanner's "already in
    # MealMate"); linking never replaces a barcode, the edit form changes it on purpose.
    INGREDIENT_HAS_BARCODE = "ingredient.has_barcode"
    # 409: apply or ignore, but the ingredient has no newer Open Food Facts values (BAR-06).
    INGREDIENT_NO_PENDING_UPDATE = "ingredient.no_pending_update"
    # 503: too many Open Food Facts lookups or searches right now (BAR-08); retry or enter the
    # values by hand.
    OFF_BUSY = "off.busy"
    # 503: Open Food Facts could not be asked (slow or unreachable) for a name search; retry.
    OFF_UNAVAILABLE = "off.unavailable"

    # 409: the action is only possible while the list is a draft (e.g. hiding a line, LIST-07).
    LIST_NOT_DRAFT = "list.not_draft"
    # 409: the list is done and read-only (LIST-10); reopen it first (SHOP-06). Also the result
    # of a check-off op made after the list was finished (SYNC-06).
    LIST_DONE = "list.done"
    # 409: only a done list can be reopened or shopped again (SHOP-06).
    LIST_NOT_DONE = "list.not_done"
    # 409: only while shopping (or done): check-off and finish, not in a draft (LIST-10).
    LIST_NOT_SHOPPING = "list.not_shopping"
    # 409, only as an op result: the client's extra item id is already used on another list.
    EXTRA_ID_TAKEN = "extra.id_taken"

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
