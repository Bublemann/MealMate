"""Reihenfolge im Laden: a user's own walking order, which their lists follow, moved by its
buttons and by dragging, and back to the admins' order (REF-01, D-48, UI-07).

All tests of a run share one database and another test reorders the categories, so the order is
read from the app; the new user follows the admins' order until they move a category.
"""

from collections.abc import Callable
from itertools import pairwise
from typing import Any

from playwright.sync_api import Locator, Page, expect

from support.a11y import serious_violations
from support.api import Account, Api, sign_in, unique
from support.frontend import TEST_IDS, text
from support.ui import open_settings_page


def neighbours(api: Api, account: Account) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Two categories next to each other in the admins' order that ingredients can be put in,
    and where the first of them is."""
    ordered = api.ordered_categories(account)
    for index, (first, second) in enumerate(pairwise(ordered)):
        if "uncategorized" not in (first["key"], second["key"]):
            return index, first, second
    raise AssertionError("no two pickable categories next to each other")


def headings(page: Page) -> Locator:
    return page.get_by_test_id(TEST_IDS["listLines"]).get_by_role("heading", level=3)


def open_list(page: Page, name: str) -> None:
    """Through the Lists tab, within the app (a reload could show a stale copy)."""
    page.get_by_test_id(TEST_IDS["tabLists"]).click()
    page.get_by_test_id(TEST_IDS["listFeed"]).get_by_test_id(TEST_IDS["listCard"]).filter(
        has_text=name
    ).click()


def test_a_list_follows_the_own_walking_order(
    page: Page, api: Api, invite_user: Callable[..., Account]
) -> None:
    tag = unique("wo")
    anna = invite_user(unique("anna"), unique("Anna"))
    index, first, second = neighbours(api, anna)
    first_name, second_name = first["names"]["en"], second["names"]["en"]
    shopping_list = api.create_list(anna, f"Laden {tag}")
    for name, category in (("Erste", first), ("Zweite", second)):
        ingredient = api.create_ingredient(anna, f"{name} {tag}", category_id=category["id"])
        api.add_extra_item(anna, shopping_list["id"], ingredient_id=ingredient["id"])
    sign_in(page.context, anna)
    page.goto(f"/lists/{shopping_list['id']}")
    expect(headings(page)).to_have_text([first_name, second_name])

    # Moving the second category up keeps the order as Anna's own and turns the switch off.
    screen = open_settings_page(page, "walkingOrder.title", "screenWalkingOrder")
    switch = screen.get_by_role("switch", name=text("walkingOrder.follow"))
    expect(switch).to_be_checked()
    screen.get_by_role("button", name=text("walkingOrder.moveUp", name=second_name)).click()
    expect(switch).not_to_be_checked()
    rows = screen.get_by_test_id(TEST_IDS["walkingOrderList"]).get_by_role("listitem")
    expect(rows.nth(index)).to_have_text(second_name)
    assert serious_violations(page) == []

    open_list(page, shopping_list["name"])
    expect(headings(page)).to_have_text([second_name, first_name])

    # Dragging the second category's handle onto the row below puts it back behind the first.
    screen = open_settings_page(page, "walkingOrder.title", "screenWalkingOrder")
    expect(rows.nth(index)).to_have_text(second_name)
    rows.nth(index).get_by_test_id(TEST_IDS["walkingOrderHandle"]).drag_to(rows.nth(index + 1))
    expect(rows.nth(index)).to_have_text(first_name)
    expect(rows.nth(index + 1)).to_have_text(second_name)

    # Back to the admins' order, after a confirmation; the list follows it again.
    page.get_by_role("button", name=text("walkingOrder.moveUp", name=second_name)).click()
    expect(rows.nth(index)).to_have_text(second_name)
    switch.click()
    dialog = page.get_by_role("alertdialog", name=text("walkingOrder.followTitle"))
    dialog.get_by_role("button", name=text("walkingOrder.followConfirm")).click()
    expect(switch).to_be_checked()
    expect(rows.nth(index)).to_have_text(first_name)
    open_list(page, shopping_list["name"])
    expect(headings(page)).to_have_text([first_name, second_name])
