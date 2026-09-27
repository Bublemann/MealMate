"""Steps through the UI that several journeys share."""

import re

from playwright.sync_api import Page, expect

from support.api import Account
from support.frontend import TEST_IDS, text


def log_in(page: Page, account: Account, language: str = "en") -> None:
    """Fills in and sends the login form (the page must show it)."""
    screen = page.get_by_test_id(TEST_IDS["screenLogin"])
    expect(screen).to_be_visible()
    screen.get_by_label(text("auth.field.username", language), exact=True).fill(account.username)
    screen.get_by_label(text("auth.field.password", language), exact=True).fill(account.password)
    screen.get_by_role("button", name=text("auth.login.submit", language)).click()


def log_out(page: Page) -> None:
    """Logs out from Me and waits for the login screen."""
    page.get_by_test_id(TEST_IDS["tabMe"]).click()
    page.get_by_test_id(TEST_IDS["logoutButton"]).click()
    expect(page).to_have_url(re.compile(r"/login$"))
    expect(page.get_by_test_id(TEST_IDS["screenLogin"])).to_be_visible()
