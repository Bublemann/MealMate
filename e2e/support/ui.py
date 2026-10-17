"""Steps through the UI that several journeys share."""

import re

from playwright.sync_api import Locator, Page, expect

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
    """Logs out from the Settings tab and waits for the login screen."""
    page.get_by_test_id(TEST_IDS["tabMe"]).click()
    page.get_by_test_id(TEST_IDS["logoutButton"]).click()
    expect(page).to_have_url(re.compile(r"/login$"))
    expect(page.get_by_test_id(TEST_IDS["screenLogin"])).to_be_visible()


def settings_row(page: Page, label_key: str, language: str = "en") -> Locator:
    """A row of the Settings tab, by the label its name starts with, whatever its value."""
    label = re.escape(text(label_key, language))
    return page.get_by_test_id(TEST_IDS["screenMe"]).get_by_role(
        "link", name=re.compile(f"^{label}")
    )


def open_settings_page(page: Page, label_key: str, screen: str, language: str = "en") -> Locator:
    """Opens a page of the Settings tab through the tab and its row; the page's screen."""
    page.get_by_test_id(TEST_IDS["tabMe"]).click()
    settings_row(page, label_key, language).click()
    page_screen = page.get_by_test_id(TEST_IDS[screen])
    expect(page_screen).to_be_visible()
    return page_screen
