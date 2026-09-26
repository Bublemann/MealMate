"""Session setup for the end-to-end suite (QA-04, plan § 9).

The app under test:
- E2E_BASE_URL set: that running MealMate is tested as is.
- Otherwise the production image E2E_IMAGE (default `mealmate:e2e`, built by `make e2e`) is started
  on 127.0.0.1:E2E_PORT (default 18080) with an empty in-memory /data. It serves plain HTTP with
  MEALMATE_COOKIE_SECURE=false, because WebKit never stores Secure cookies over HTTP, not even on
  localhost; the production cookie attributes are covered by the backend API tests.

Browsers emulate DEFAULT_DEVICE (an iPhone) with an English locale; `--device "<name>"` picks
another Playwright device. PLAYWRIGHT_CHROMIUM_EXECUTABLE runs a local Chromium build instead of
the one Playwright downloads (`uv run playwright install chromium`).
"""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from support.container import save_logs, start_app, wait_until_healthy

DEFAULT_DEVICE = "iPhone 15"
DEFAULT_IMAGE = "mealmate:e2e"
DEFAULT_PORT = 18080
# Public test-only key (allowlisted in .gitleaks.toml); the app refuses to start without one.
TEST_SECRET_KEY = "e2e-only-insecure-test-key-0000000000000000"  # noqa: S105


@pytest.fixture(scope="session")
def base_url(pytestconfig: pytest.Config) -> Iterator[str]:
    """Origin of the app under test; overrides the fixture of pytest-base-url."""
    if external := os.environ.get("E2E_BASE_URL"):
        yield external.rstrip("/")
        return

    port = int(os.environ.get("E2E_PORT", DEFAULT_PORT))
    origin = f"http://127.0.0.1:{port}"
    app = start_app(
        os.environ.get("E2E_IMAGE", DEFAULT_IMAGE),
        port,
        {
            "MEALMATE_SECRET_KEY": TEST_SECRET_KEY,
            "MEALMATE_PUBLIC_URL": origin,
            "MEALMATE_COOKIE_SECURE": "false",
            "MEALMATE_DIAGNOSTICS_ENABLED": "true",
        },
    )
    try:
        wait_until_healthy(app)
        yield origin
    finally:
        output = Path(pytestconfig.getoption("--output"))
        save_logs(app, output / "app-container.log")
        app.stop()


@pytest.fixture(scope="session")
def device(pytestconfig: pytest.Config) -> str:
    return pytestconfig.getoption("--device") or DEFAULT_DEVICE


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    # A fixed locale makes the initial UI language predictable (English).
    return {**browser_context_args, "locale": "en-GB", "timezone_id": "Europe/Berlin"}


@pytest.fixture(scope="session")
def browser_type_launch_args(
    browser_type_launch_args: dict[str, Any], browser_name: str
) -> dict[str, Any]:
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if browser_name == "chromium" and executable:
        return {**browser_type_launch_args, "executable_path": executable}
    return browser_type_launch_args
