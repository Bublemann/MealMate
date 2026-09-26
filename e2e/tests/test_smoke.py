"""Smoke test of the app shell: tab bar, navigation between the four screens, version and source."""

import re

import pytest
from playwright.sync_api import Page, expect

from support.frontend import TEST_IDS

# (path, tab test ID, screen test ID)
SCREENS = [
    ("/lists", TEST_IDS["tabLists"], TEST_IDS["screenLists"]),
    ("/meals", TEST_IDS["tabMeals"], TEST_IDS["screenMeals"]),
    ("/ingredients", TEST_IDS["tabIngredients"], TEST_IDS["screenIngredients"]),
    ("/me", TEST_IDS["tabMe"], TEST_IDS["screenMe"]),
]


def test_root_opens_lists_with_four_tabs(page: Page) -> None:
    page.goto("/")

    expect(page).to_have_url(re.compile(r"/lists$"))
    expect(page.get_by_test_id(TEST_IDS["screenLists"])).to_be_visible()
    tab_bar = page.get_by_role("navigation")
    expect(tab_bar.get_by_role("link")).to_have_count(len(SCREENS))
    for _, tab, _ in SCREENS:
        expect(tab_bar.get_by_test_id(tab)).to_be_visible()
    expect(page.get_by_test_id(TEST_IDS["tabLists"])).to_have_attribute("aria-current", "page")


def test_tabs_navigate_between_screens(page: Page) -> None:
    page.goto("/lists")

    for path, tab, screen in [*SCREENS[1:], SCREENS[0]]:
        page.get_by_test_id(tab).click()
        expect(page).to_have_url(re.compile(f"{path}$"))
        expect(page.get_by_test_id(screen)).to_be_visible()
        expect(page.get_by_test_id(tab)).to_have_attribute("aria-current", "page")


@pytest.mark.parametrize("path", ["/does-not-exist", "/some/deep/link"])
def test_unknown_routes_fall_back_to_lists(page: Page, path: str) -> None:
    page.goto(path)

    expect(page).to_have_url(re.compile(r"/lists$"))
    expect(page.get_by_test_id(TEST_IDS["screenLists"])).to_be_visible()


def test_me_shows_version_and_source_link(page: Page) -> None:
    """UI-06, LIC-02: the running version and a link to its exact source revision."""
    version = page.request.get("/api/version").json()

    page.goto("/me")

    expect(page.get_by_test_id(TEST_IDS["appVersion"])).to_have_text(version["version"])
    link = page.get_by_test_id(TEST_IDS["sourceLink"])
    expect(link).to_have_attribute("href", version["source_url"])
    expect(link).to_have_attribute("target", "_blank")
    assert {"noopener", "noreferrer"} <= set((link.get_attribute("rel") or "").split())
    assert version["source_url"].startswith("https://github.com/Bublemann/MealMate")
