"""The Settings tab: its rows with their values and the count on the gear (UI-07, D-45, D-51)."""

from collections.abc import Callable
from typing import Literal

import pytest
from playwright.sync_api import Locator, Page, expect

from support.a11y import serious_violations
from support.api import Account, Api, sign_in, unique
from support.frontend import TEST_IDS, text
from support.ui import settings_row

# The largest iPhone text size (53 px body text, simulated as in test_ingredients.py).
LARGEST_TEXT = "html { font-size: 53px !important; }"


def with_a_request(api: Api, invite_user: Callable[..., Account]) -> Account:
    """A new user with a long display name, whom another new user has sent a couple request."""
    anna = invite_user(unique("anna"), unique("Annemarie-Charlotte"))
    ben = invite_user(unique("ben"), unique("Benedikt"))
    api.call("POST", "/api/couple/requests", token=api.token(ben), json={"user_id": anna.id})
    return anna


def box_of(locator: Locator) -> dict[str, float]:
    box = locator.bounding_box()
    assert box is not None
    return box


def inside(inner: dict[str, float], outer: dict[str, float]) -> bool:
    return (
        inner["x"] >= outer["x"] - 0.5
        and inner["y"] >= outer["y"] - 0.5
        and inner["x"] + inner["width"] <= outer["x"] + outer["width"] + 0.5
        and inner["y"] + inner["height"] <= outer["y"] + outer["height"] + 0.5
    )


def overlap(a: dict[str, float], b: dict[str, float]) -> bool:
    return not (
        a["x"] + a["width"] <= b["x"]
        or b["x"] + b["width"] <= a["x"]
        or a["y"] + a["height"] <= b["y"]
        or b["y"] + b["height"] <= a["y"]
    )


def test_settings_rows_fit_the_largest_text_size(
    page: Page, api: Api, invite_user: Callable[..., Account]
) -> None:
    """A11Y-01, A11Y-02: at the largest text size each row's label and value wrap inside the row,
    without clipping, overlap or a horizontal scroll; the gear's count stays inside the tab bar."""
    anna = with_a_request(api, invite_user)
    sign_in(page.context, anna)
    page.goto("/me")
    page.add_style_tag(content=LARGEST_TEXT)
    requests = text("couple.requests_one", count="1")
    couple = settings_row(page, "couple.title")
    expect(couple).to_have_accessible_name(f"{text('couple.title')} {requests}")
    gear = page.get_by_test_id(TEST_IDS["tabMe"])
    expect(gear).to_have_accessible_name(text("nav.meCount_one", count="1"))

    viewport = page.viewport_size
    assert viewport is not None
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
    for key, value in [
        ("me.profile.title", anna.display_name),
        ("couple.title", requests),
        ("me.security.title", None),
    ]:
        row = settings_row(page, key)
        row.scroll_into_view_if_needed()
        row_box = box_of(row)
        assert row_box["height"] >= 44
        assert row_box["x"] >= 0
        assert row_box["x"] + row_box["width"] <= viewport["width"]
        label = box_of(row.get_by_text(text(key), exact=True))
        assert inside(label, row_box), key
        if value is not None:
            shown = box_of(row.get_by_text(value, exact=True))
            assert inside(shown, row_box), key
            assert not overlap(label, shown), key
            # Too long to share the line at this size: the value wraps below the label.
            assert shown["y"] >= label["y"] + label["height"] - 0.5, key

    logout = page.get_by_test_id(TEST_IDS["logoutButton"])
    logout.scroll_into_view_if_needed()
    assert box_of(logout)["height"] >= 44

    # The count stays on the gear, inside the bar, however large the text.
    tab_bar = box_of(page.get_by_role("navigation", name=text("nav.label")))
    count = box_of(gear.get_by_text("1", exact=True))
    assert inside(count, tab_bar)
    assert count["height"] <= 22


@pytest.mark.parametrize("color_scheme", ["light", "dark"])
def test_the_count_and_the_rows_pass_axe(
    page: Page,
    api: Api,
    invite_user: Callable[..., Account],
    color_scheme: Literal["light", "dark"],
) -> None:
    """A11Y-01, A11Y-03: the red count on the gear and the Paar row's value, as test_accessibility
    sees no count (its accounts have no requests), in light and dark mode."""
    page.emulate_media(color_scheme=color_scheme)
    sign_in(page.context, with_a_request(api, invite_user))
    page.goto("/me")
    expect(page.get_by_test_id(TEST_IDS["tabMe"])).to_have_accessible_name(
        text("nav.meCount_one", count="1")
    )
    expect(settings_row(page, "couple.title")).to_contain_text(
        text("couple.requests_one", count="1")
    )

    assert serious_violations(page) == []
