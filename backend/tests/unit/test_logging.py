import json
import logging
import sys

import pytest

from app.core.logging import JsonFormatter, configure_logging, route_template


def record(**kwargs: object) -> logging.LogRecord:
    values: dict[str, object] = {
        "name": "mealmate.test",
        "levelno": logging.INFO,
        "levelname": "INFO",
        "msg": "hello %s",
        "args": ("world",),
    }
    return logging.makeLogRecord(values | kwargs)


def test_json_formatter_renders_message_and_extras() -> None:
    line = JsonFormatter().format(record(route="/api/health", color_message="\x1b[1mhello"))
    entry = json.loads(line)
    assert entry["msg"] == "hello world"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "mealmate.test"
    assert entry["route"] == "/api/health"
    assert entry["ts"].endswith("+00:00")
    assert "color_message" not in entry
    assert "args" not in entry


def test_json_formatter_includes_exceptions() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        entry = json.loads(JsonFormatter().format(record(exc_info=sys.exc_info())))
    assert "ValueError: boom" in entry["exc"]


def test_configure_logging_is_idempotent(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("DEBUG")
    configure_logging("INFO")
    root = logging.getLogger()
    ours = [h for h in root.handlers if isinstance(h.formatter, JsonFormatter)]
    assert len(ours) == 1
    assert root.level == logging.INFO

    logging.getLogger("uvicorn.error").info("Started server process")
    logging.getLogger("mealmate.test").debug("hidden")
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line)["msg"] for line in lines] == ["Started server process"]
    assert logging.getLogger("uvicorn").handlers == []


def test_uvicorn_access_log_stays_off(capsys: pytest.CaptureFixture[str]) -> None:
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addHandler(logging.StreamHandler())  # as uvicorn's default config does
    configure_logging("INFO")

    # uvicorn only writes access lines when this is true.
    assert not access_logger.hasHandlers()
    access_logger.info('127.0.0.1:1234 - "GET /api/codes/secret?token=x HTTP/1.1" 200')
    assert "secret" not in capsys.readouterr().out


@pytest.mark.parametrize("name", ["aiosqlite", "httpx"])
def test_loggers_with_sensitive_details_stay_quiet_at_debug(name: str) -> None:
    configure_logging("DEBUG")
    try:
        # aiosqlite logs SQL with its parameters, httpx outgoing URLs with their query strings.
        assert not logging.getLogger(name).isEnabledFor(logging.DEBUG)
        assert logging.getLogger("mealmate.test").isEnabledFor(logging.DEBUG)
    finally:
        configure_logging("INFO")


def test_route_template() -> None:
    class Route:
        path_format = "/api/lists/{list_id}"

    assert route_template({"route": Route()}) == "/api/lists/{list_id}"
    assert route_template({}) == "<unmatched>"
