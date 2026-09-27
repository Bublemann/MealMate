"""JSON logging to stdout and the request log (plan § 5.3, SEC-10).

uvicorn runs with `--no-access-log`. The request log names the route *template*
(`/api/lists/{list_id}`), never the concrete path or query string, so invite codes, tokens and
signed-URL parameters cannot reach the logs.
"""

import json
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

UNMATCHED_ROUTE = "<unmatched>"

_STANDARD_RECORD_ATTRIBUTES = frozenset(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "color_message",  # uvicorn's ANSI-coloured duplicate of the message
}

request_logger = logging.getLogger("mealmate.request")


class JsonFormatter(logging.Formatter):
    """One JSON object per line; `extra={...}` fields become top-level keys."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_RECORD_ATTRIBUTES and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


class _StdoutHandler(logging.StreamHandler[Any]):
    """Writes to whatever `sys.stdout` currently is (it may be replaced, e.g. by pytest)."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stdout
        super().emit(record)


def configure_logging(level: str) -> None:
    """Send all logs, including uvicorn's, as JSON to stdout. Safe to call repeatedly."""
    root = logging.getLogger()
    for handler in [h for h in root.handlers if isinstance(h, _StdoutHandler)]:
        root.removeHandler(handler)
    handler = _StdoutHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    # uvicorn's access log has the raw path and query string. It writes it whenever the logger
    # has handlers, including inherited ones, so it is cut off here whatever the CLI flags say.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.propagate = False
    access_logger.disabled = True
    # httpx logs every outgoing URL, query string included, at INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # aiosqlite logs every SQL statement with its bound parameters at DEBUG, which would put
    # personal data into the logs at MEALMATE_LOG_LEVEL=DEBUG. INFO still lets its errors through.
    logging.getLogger("aiosqlite").setLevel(logging.INFO)


def route_template(scope: Scope) -> str:
    """The matched route's path template, e.g. `/api/lists/{list_id}`."""
    path_format = getattr(scope.get("route"), "path_format", None)
    return path_format if isinstance(path_format, str) else UNMATCHED_ROUTE


class RequestLogMiddleware:
    """Logs method, route template, status and duration of every HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status = 500

        async def send_tracking(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_tracking)
        finally:
            request_logger.info(
                "request",
                extra={
                    "method": scope["method"],
                    "route": route_template(scope),
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
