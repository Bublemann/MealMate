"""axe finds no serious or critical violations on the main screens (A11Y-03)."""

from typing import Literal

import pytest
from playwright.sync_api import Page, expect

from support.a11y import serious_violations
from support.frontend import TEST_IDS

SCREENS = {
    "/lists": TEST_IDS["screenLists"],
    "/meals": TEST_IDS["screenMeals"],
    "/ingredients": TEST_IDS["screenIngredients"],
    # The version is loaded from the API; wait for it so the whole screen is checked.
    "/me": TEST_IDS["appVersion"],
}


@pytest.mark.parametrize("color_scheme", ["light", "dark"])
@pytest.mark.parametrize("path", list(SCREENS))
def test_no_serious_violations(
    page: Page, path: str, color_scheme: Literal["light", "dark"]
) -> None:
    page.emulate_media(color_scheme=color_scheme)
    page.goto(path)
    expect(page.get_by_test_id(SCREENS[path])).to_be_visible()

    assert serious_violations(page) == []
