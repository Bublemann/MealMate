"""Platform behaviour the later features rely on: cookies and the offline shell (plan M0/M1)."""

from typing import Any

import pytest
from playwright.sync_api import BrowserContext, Page, expect

from support.frontend import TEST_IDS

DIAG_COOKIE = "mm_diag"
WEBKIT_OFFLINE_SKIP = (
    "Playwright WebKit offline reload with service worker is broken upstream (plan O-11)"
)


def diag(page: Page, action: str) -> Any:
    """POSTs to /api/auth/diag/<action> from the page, as the app's own requests do."""
    return page.evaluate(
        """async (action) => {
            const response = await fetch(`/api/auth/diag/${action}`, { method: 'POST' });
            const body = response.status === 204 ? null : await response.json();
            return { status: response.status, body };
        }""",
        action,
    )


def test_cookie_survives_reload(page: Page, context: BrowserContext) -> None:
    """The refresh cookie's attributes (HttpOnly, SameSite=Strict, Path=/api/auth) persist."""
    page.goto("/me")
    assert diag(page, "check") == {"status": 200, "body": {"present": False}}

    assert diag(page, "set")["status"] == 204
    page.reload()

    assert diag(page, "check") == {"status": 200, "body": {"present": True}}
    [cookie] = [c for c in context.cookies() if c["name"] == DIAG_COOKIE]
    assert cookie["httpOnly"]
    assert cookie["sameSite"] == "Strict"
    assert cookie["path"] == "/api/auth"


def test_shell_loads_offline(page: Page, context: BrowserContext, browser_name: str) -> None:
    """The service worker serves the app shell from its precache (SYNC-01, plan § 8)."""
    if browser_name == "webkit":
        pytest.skip(WEBKIT_OFFLINE_SKIP)

    page.goto("/lists")
    expect(page.get_by_test_id(TEST_IDS["screenLists"])).to_be_visible()
    page.evaluate("async () => { await navigator.serviceWorker.ready; }")
    page.wait_for_function("navigator.serviceWorker.controller !== null")

    context.set_offline(True)
    page.reload()

    expect(page.get_by_role("navigation")).to_be_visible()
    expect(page.get_by_test_id(TEST_IDS["screenLists"])).to_be_visible()
    page.get_by_test_id(TEST_IDS["tabMeals"]).click()
    expect(page.get_by_test_id(TEST_IDS["screenMeals"])).to_be_visible()
