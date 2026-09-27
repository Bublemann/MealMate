"""Request body limits (SEC-07).

Starlette reads a whole request body (a multipart upload into a temporary file) before any route
code runs, authentication included, so a limit checked in the route comes too late. This
middleware caps bodies before that: photo uploads (`PUT /api/meals/{meal_id}/photo`) at 10 MB
plus 64 KiB for the multipart framing, every other request at 1 MiB. A declared
`Content-Length` above the cap is refused before a byte of the body is read; otherwise the bytes
are counted as they arrive (chunked bodies, a missing or wrong `Content-Length`) and the request
is refused as soon as the count passes the cap.

A refusal is a 413 error envelope (`media.too_large` for photos, `common.payload_too_large`
otherwise) with `Connection: close`, since the rest of the body is never read. The middleware
sits inside the logging, security-header and error-envelope middleware, so those apply as usual.
"""

import re

from fastapi import status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.error_handlers import error_response
from app.core.errors import ErrorCode
from app.media.images import MAX_UPLOAD_BYTES

MAX_BODY_BYTES = 1024 * 1024
MULTIPART_OVERHEAD_BYTES = 64 * 1024
MAX_PHOTO_BODY_BYTES = MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES
_PHOTO_PATH = re.compile(r"/api/meals/[^/]+/photo")


class BodyTooLargeError(Exception):
    """Raised into the app by `receive` once the body has passed its cap."""


def body_limit(method: str, path: str) -> tuple[int, ErrorCode]:
    """The largest body the request may have, and the error code for a larger one."""
    if method == "PUT" and _PHOTO_PATH.fullmatch(path):
        return MAX_PHOTO_BODY_BYTES, ErrorCode.MEDIA_TOO_LARGE
    return MAX_BODY_BYTES, ErrorCode.PAYLOAD_TOO_LARGE


def declared_length(scope: Scope) -> int | None:
    """The request's `Content-Length`, if it has a readable one."""
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class BodySizeLimitMiddleware:
    """Answers a request whose body is over its cap with a 413 instead of reading it all."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit, code = body_limit(scope["method"], scope["path"])
        refusal = error_response(
            status.HTTP_413_CONTENT_TOO_LARGE, code, headers={"Connection": "close"}
        )
        length = declared_length(scope)
        if length is not None and length > limit:
            await refusal(scope, receive, send)
            return

        received = 0
        exceeded = False
        response_started = False

        async def receive_limited() -> Message:
            nonlocal received, exceeded
            if not exceeded:
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                exceeded = received > limit
                if not exceeded:
                    return message
            raise BodyTooLargeError

        async def send_unless_refused(message: Message) -> None:
            nonlocal response_started
            if exceeded and not response_started:
                # The app's answer to a body cut short (usually a 400); the 413 replaces it.
                return
            response_started = True
            await send(message)

        try:
            await self.app(scope, receive_limited, send_unless_refused)
        except Exception:
            # After the status line is out, the only honest option is to abort the response.
            if not exceeded or response_started:
                raise
        if exceeded and not response_started:
            await refusal(scope, receive, send)
