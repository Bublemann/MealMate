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


def back_to_settings(page: Page) -> None:
    """Goes back from a Settings page through the strip's back link and waits for the tab."""
    back = page.get_by_test_id(TEST_IDS["detailStrip"]).get_by_test_id(TEST_IDS["backLink"])
    expect(back).to_have_accessible_name(text("nav.me"))
    back.click()
    expect(page.get_by_test_id(TEST_IDS["screenMe"])).to_be_visible()


def open_more_menu(page: Page) -> Locator:
    """Opens the detail screen's ⋯ menu (D-39) and returns it."""
    page.get_by_test_id(TEST_IDS["detailStrip"]).get_by_test_id(TEST_IDS["moreActions"]).click()
    menu = page.get_by_test_id(TEST_IDS["moreMenu"])
    expect(menu).to_be_visible()
    return menu


def choose_from_menu(page: Page, test_id: str) -> None:
    """Opens the ⋯ menu and chooses the item with that test ID (a key of TEST_IDS)."""
    open_more_menu(page).get_by_test_id(TEST_IDS[test_id]).click()


def floating_bar_button(page: Page, test_id: str) -> Locator:
    """The button with that test ID (a key of TEST_IDS) in the bar above the tab bar (D-39)."""
    return page.get_by_test_id(TEST_IDS["floatingBar"]).get_by_test_id(TEST_IDS[test_id])
