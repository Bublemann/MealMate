"""Smoke test of the app shell: tab bar, navigation between the four screens, version and source."""

import re

import pytest
from playwright.sync_api import Page, expect

from support.frontend import TEST_IDS, text

# The screens need a signed-in user; the route guard itself is tested in test_accounts.py.
pytestmark = pytest.mark.usefixtures("member_page")

# (path, tab test ID, screen test ID, headline key)
SCREENS = [
    ("/lists", TEST_IDS["tabLists"], TEST_IDS["screenLists"], "nav.lists"),
    ("/meals", TEST_IDS["tabMeals"], TEST_IDS["screenMeals"], "nav.meals"),
    ("/ingredients", TEST_IDS["tabIngredients"], TEST_IDS["screenIngredients"], "nav.ingredients"),
    ("/me", TEST_IDS["tabMe"], TEST_IDS["screenMe"], "nav.me"),
]


def test_root_opens_lists_with_four_tabs(page: Page) -> None:
    page.goto("/")

    expect(page).to_have_url(re.compile(r"/lists$"))
    expect(page.get_by_test_id(TEST_IDS["screenLists"])).to_be_visible()
    tab_bar = page.get_by_role("navigation")
    expect(tab_bar.get_by_role("link")).to_have_count(len(SCREENS))
    for _, tab, _, _ in SCREENS:
        expect(tab_bar.get_by_test_id(tab)).to_be_visible()
    expect(page.get_by_test_id(TEST_IDS["tabLists"])).to_have_attribute("aria-current", "page")


def test_tabs_navigate_between_screens(page: Page) -> None:
    """UI-01, D-44: each tab opens its screen, which shows the tab's name as its headline."""
    page.goto("/lists")

    for path, tab, screen, headline in [*SCREENS[1:], SCREENS[0]]:
        page.get_by_test_id(tab).click()
        expect(page).to_have_url(re.compile(f"{path}$"))
        expect(page.get_by_test_id(screen)).to_be_visible()
        expect(page.get_by_test_id(tab)).to_have_attribute("aria-current", "page")
        expect(page.get_by_test_id(tab)).to_have_text(text(headline))
        heading = page.get_by_role("heading", level=1)
        expect(heading).to_have_count(1)
        expect(page.get_by_test_id(screen).get_by_role("heading", level=1)).to_have_text(
            text(headline)
        )
        # Playwright counts a heading only screen readers get as visible too: it is 1 px high.
        box = heading.bounding_box()
        assert box is not None
        assert box["height"] > 24, f"{text(headline)!r} is {box['height']} px high"


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
