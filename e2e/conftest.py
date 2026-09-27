"""Session setup for the end-to-end suite (QA-04, plan § 9).

The app under test:
- E2E_BASE_URL set: that running MealMate is tested as is.
- Otherwise the production image E2E_IMAGE (default `mealmate:e2e`, built by `make e2e`) is started
  on 127.0.0.1:E2E_PORT (default 18080) with an empty in-memory /data. It serves plain HTTP with
  MEALMATE_COOKIE_SECURE=false, because WebKit never stores Secure cookies over HTTP, not even on
  localhost; the production cookie attributes are covered by the backend API tests. Its Open Food
  Facts is the stand-in in fake_off/, served from the host for the whole session (plan § 9) on
  Docker's bridge only (support/fake_off.py).

Accounts (plan § 9, M2): `admin` is created with `mealmate create-admin` inside the container;
`invite_user` and `make_couple` go through the API as that admin. With E2E_BASE_URL there is no
container to run the CLI in: E2E_ADMIN_USERNAME and E2E_ADMIN_PASSWORD then name an existing
admin, and without them every test that needs an account is skipped.

Browsers emulate DEFAULT_DEVICE (an iPhone) with an English locale; `--device "<name>"` picks
another Playwright device. PLAYWRIGHT_CHROMIUM_EXECUTABLE runs a local Chromium build instead of
the one Playwright downloads (`uv run playwright install chromium`).
"""

import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page

from support.api import Account, Api, new_password, sign_in, unique
from support.container import AppContainer, save_logs, start_app, wait_until_healthy
from support.fake_off import CONTAINER_HOST, serve_fake_off

DEFAULT_DEVICE = "iPhone 15"
DEFAULT_IMAGE = "mealmate:e2e"
DEFAULT_PORT = 18080
# Public test-only key (allowlisted in .gitleaks.toml); the app refuses to start without one.
TEST_SECRET_KEY = "e2e-only-insecure-test-key-0000000000000000"  # noqa: S105


@pytest.fixture(scope="session")
def app_container(pytestconfig: pytest.Config) -> Iterator[AppContainer | None]:
    """The container the suite started, or None when testing E2E_BASE_URL."""
    if os.environ.get("E2E_BASE_URL"):
        yield None
        return

    port = int(os.environ.get("E2E_PORT", DEFAULT_PORT))
    origin = f"http://127.0.0.1:{port}"
    with serve_fake_off() as fake_off:
        app = start_app(
            os.environ.get("E2E_IMAGE", DEFAULT_IMAGE),
            port,
            {
                "MEALMATE_SECRET_KEY": TEST_SECRET_KEY,
                "MEALMATE_PUBLIC_URL": origin,
                "MEALMATE_COOKIE_SECURE": "false",
                "MEALMATE_DIAGNOSTICS_ENABLED": "true",
                "MEALMATE_OFF_BASE_URL": fake_off.url_in_container,
            },
            hosts={CONTAINER_HOST: fake_off.host_address},
        )
        try:
            wait_until_healthy(app)
            yield app
        finally:
            output = Path(pytestconfig.getoption("--output"))
            save_logs(app, output / "app-container.log")
            app.stop()


@pytest.fixture(scope="session")
def fake_off_app(app_container: AppContainer | None) -> AppContainer:
    """The started container, whose Open Food Facts is fake_off/ (barcode lookups, M7)."""
    if app_container is None:
        pytest.skip("needs the fake Open Food Facts, which only the suite's own container uses")
    return app_container


@pytest.fixture(scope="session")
def base_url(app_container: AppContainer | None) -> str:
    """Origin of the app under test; overrides the fixture of pytest-base-url."""
    if app_container is None:
        return os.environ["E2E_BASE_URL"].rstrip("/")
    return app_container.base_url


@pytest.fixture(scope="session")
def api(base_url: str) -> Iterator[Api]:
    client = Api(base_url)
    yield client
    client.close()


@pytest.fixture(scope="session")
def admin(app_container: AppContainer | None, api: Api) -> Account:
    """The first admin, created on the command line like on a fresh install (ACC-02)."""
    if app_container is None:
        username = os.environ.get("E2E_ADMIN_USERNAME")
        password = os.environ.get("E2E_ADMIN_PASSWORD")
        if not (username and password):
            pytest.skip(
                "needs `docker exec` into the container the suite starts; with E2E_BASE_URL set "
                "E2E_ADMIN_USERNAME and E2E_ADMIN_PASSWORD to an existing admin"
            )
        user = api.login(username, password)["user"]
        return Account(user["id"], username, user["display_name"], password)

    password = new_password()
    # English, like the browsers' locale, so screens of the admin match the other tests.
    result = app_container.exec(
        "mealmate",
        "create-admin",
        "--username",
        "admin",
        "--display-name",
        "Admin",
        "--language",
        "en",
        "--password-stdin",
        stdin=f"{password}\n",
    )
    if result.returncode != 0:
        raise RuntimeError(f"mealmate create-admin failed:\n{result.stdout}{result.stderr}")
    user = api.login("admin", password)["user"]
    return Account(user["id"], "admin", "Admin", password)


@pytest.fixture
def invite_user(api: Api, admin: Account) -> Callable[..., Account]:
    """`invite_user(username, display_name)`: the admin invites, the new user joins (API).

    Both names default to unique ones; all tests of a run share one database.
    """

    def invite(
        username: str | None = None, display_name: str | None = None, *, language: str = "en"
    ) -> Account:
        return api.invite_user(
            admin,
            username=username or unique("user"),
            display_name=display_name or unique("User"),
            language=language,
        )

    return invite


@pytest.fixture
def make_couple(api: Api) -> Callable[[Account, Account], None]:
    """`make_couple(a, b)`: a sends a couple request, b accepts it (API)."""
    return api.make_couple


@pytest.fixture(scope="session")
def member(api: Api, admin: Account) -> Account:
    """A regular user shared by tests that only look around and change nothing of the account."""
    return api.invite_user(admin, username=unique("member"), display_name=unique("Member"))


@pytest.fixture
def member_page(page: Page, member: Account) -> Page:
    """`page` with `member` logged in: every route except /login, /join, /reset needs a user."""
    sign_in(page.context, member)
    return page


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
