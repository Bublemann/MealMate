"""axe finds no serious or critical violations on the main screens (A11Y-03)."""

from dataclasses import dataclass
from typing import Literal

import pytest
from playwright.sync_api import Page, expect

from support.a11y import serious_violations
from support.api import CODE_REQUESTS, Account, Api, code_from_link, sign_in, unique
from support.frontend import TEST_IDS, text
from support.images import png

Visitor = Literal["anonymous", "member", "admin"]


@dataclass(frozen=True)
class Screen:
    path: str
    visitor: Visitor
    # Shown once the screen's data has loaded, so the whole screen is checked.
    ready: tuple[str, ...]


SCREENS = [
    Screen("/login", "anonymous", (TEST_IDS["screenLogin"],)),
    # The invite code is appended in the test: /join#<code>.
    Screen("/join", "anonymous", (TEST_IDS["screenJoin"],)),
    # A draft of the member's and another user's public list are created in the test.
    Screen("/lists", "member", (TEST_IDS["listDrafts"], TEST_IDS["othersLists"])),
    # A list with meals, lines and a removed line is created in the test: /lists/<id>.
    Screen(
        "/lists/:id",
        "member",
        (TEST_IDS["listMeals"], TEST_IDS["listLines"], TEST_IDS["hiddenLines"]),
    ),
    # A list being shopped with a checked, a new and a needs-more line: /lists/<id>.
    Screen(
        "/lists/:id/shopping",
        "member",
        (TEST_IDS["syncStatus"], TEST_IDS["shoppingLines"], TEST_IDS["inTheCart"]),
    ),
    # A done list of the member's is created in the test; its week is awaited there.
    Screen("/lists/history", "member", (TEST_IDS["screenHistory"],)),
    Screen("/meals", "member", (TEST_IDS["screenMeals"],)),
    Screen("/ingredients", "member", (TEST_IDS["screenIngredients"],)),
    # An ingredient with a product is created in the test: /ingredients/<id>.
    Screen(
        "/ingredients/:id",
        "member",
        (TEST_IDS["ingredientNutrition"], TEST_IDS["productList"]),
    ),
    Screen("/meals/new", "member", (TEST_IDS["mealForm"], TEST_IDS["ingredientPicker"])),
    # A meal with a photo and ingredient rows is created in the test: /meals/<id>.
    Screen(
        "/meals/:id",
        "member",
        (TEST_IDS["mealPhoto"], TEST_IDS["mealNutrition"], TEST_IDS["mealIngredients"]),
    ),
    Screen("/me", "member", (TEST_IDS["appVersion"], TEST_IDS["sessionList"])),
    Screen("/me/admin/users", "admin", (TEST_IDS["adminUserList"],)),
    Screen("/me/admin/invites", "admin", (TEST_IDS["inviteList"], TEST_IDS["shareLinkUrl"])),
    Screen("/me/admin/categories", "admin", (TEST_IDS["adminCategoryList"],)),
    Screen("/me/admin/events", "admin", (TEST_IDS["eventList"],)),
]


@pytest.mark.parametrize("color_scheme", ["light", "dark"])
@pytest.mark.parametrize("screen", SCREENS, ids=lambda screen: screen.path)
def test_no_serious_violations(
    page: Page,
    request: pytest.FixtureRequest,
    screen: Screen,
    color_scheme: Literal["light", "dark"],
) -> None:
    page.emulate_media(color_scheme=color_scheme)
    path = screen.path
    history_list = ""  # the name of the done list created for the history screen
    if screen.visitor != "anonymous":
        account: Account = request.getfixturevalue(screen.visitor)
        sign_in(page.context, account)
    if path == "/join":
        api: Api = request.getfixturevalue("api")
        link = api.create_invite(request.getfixturevalue("admin"))
        CODE_REQUESTS.reserve()  # the join screen checks the code
        path = f"/join#{code_from_link(link)}"
    if path == "/ingredients/:id":
        api = request.getfixturevalue("api")
        ingredient = api.create_ingredient(account, unique("A11y"), manual={"kcal": 52})
        api.create_product(account, ingredient["id"], name=unique("Product"))
        path = f"/ingredients/{ingredient['id']}"
    if path == "/meals/:id":
        api = request.getfixturevalue("api")
        ingredient = api.create_ingredient(account, unique("A11y"), manual={"kcal": 52})
        meal = api.create_meal(
            account,
            unique("A11y meal"),
            servings=2,
            instructions="Line one.\nLine two.",
            source_url="https://example.org/recipe",
            ingredients=[
                {"ingredient_id": ingredient["id"], "amount": 150, "unit": "g"},
                {"ingredient_id": ingredient["id"], "note": "to taste"},
            ],
        )
        api.upload_meal_photo(account, meal["id"], png())
        path = f"/meals/{meal['id']}"

    if path == "/lists":
        api = request.getfixturevalue("api")
        api.create_list(account, unique("A11y list"))
        # The admin's lists are public: one of them shows under Others' lists.
        api.create_list(request.getfixturevalue("admin"), unique("A11y others"))
    if path == "/lists/:id":
        api = request.getfixturevalue("api")
        onions = api.create_ingredient(
            account, unique("A11y onions"), category_key="fruit_vegetables", piece_weight_g=80
        )
        flour = api.create_ingredient(account, unique("A11y flour"))
        meal = api.create_meal(
            account,
            unique("A11y meal"),
            servings=2,
            ingredients=[
                {"ingredient_id": onions["id"], "amount": 1, "unit": "piece"},
                {"ingredient_id": flour["id"], "amount": 200, "unit": "g"},
            ],
        )
        api.upload_meal_photo(account, meal["id"], png())
        draft = api.create_list(account, unique("A11y list"))
        api.add_list_meal(account, draft["id"], meal["id"], servings=3)
        api.add_extra_item(account, draft["id"], text=unique("A11y item"), amount_text="2")
        api.hide_line(account, draft["id"], f"i:{onions['id']}")
        path = f"/lists/{draft['id']}"
    if path == "/lists/:id/shopping":
        api = request.getfixturevalue("api")
        flour = api.create_ingredient(account, unique("A11y flour"))
        meal = api.create_meal(
            account,
            unique("A11y meal"),
            servings=2,
            ingredients=[{"ingredient_id": flour["id"], "amount": 200, "unit": "g"}],
        )
        shopping = api.create_list(account, unique("A11y shopping"))
        entry = api.add_list_meal(account, shopping["id"], meal["id"])["meals"][0]
        candles = api.add_extra_item(account, shopping["id"], text=unique("A11y candles"))
        api.start_shopping(account, shopping["id"])
        api.check_line(account, shopping["id"], f"x:{candles['extra_items'][0]['id']}")
        api.check_line(account, shopping["id"], f"i:{flour['id']}")
        # More servings: the checked flour needs more (LIST-12); a new free-text line.
        api.set_list_meal_servings(account, shopping["id"], entry["id"], 3)
        api.add_extra_item(account, shopping["id"], text=unique("A11y item"), amount_text="2")
        path = f"/lists/{shopping['id']}"
    if path == "/lists/history":
        api = request.getfixturevalue("api")
        ingredient = api.create_ingredient(account, unique("A11y rice"))
        meal = api.create_meal(
            account,
            unique("A11y meal"),
            servings=2,
            ingredients=[{"ingredient_id": ingredient["id"], "amount": 150, "unit": "g"}],
        )
        done = api.create_list(account, unique("A11y done"))
        api.add_list_meal(account, done["id"], meal["id"])
        api.start_shopping(account, done["id"])
        api.finish_list(account, done["id"])
        history_list = done["name"]

    page.goto(path)
    if screen.path == "/join":
        # The form appears once the code has been checked.
        expect(page.get_by_role("button", name=text("auth.join.submit"))).to_be_visible()
    if screen.path == "/me/admin/invites":
        # Also check the created link with its share button.
        page.get_by_test_id(TEST_IDS["createInviteButton"]).click()
    for test_id in screen.ready:
        expect(page.get_by_test_id(test_id)).to_be_visible()
    if screen.path == "/lists/:id":
        # Also check the removed line with its restore button.
        removed = page.get_by_test_id(TEST_IDS["hiddenLines"])
        removed.get_by_text(text("lists.lines.hidden", count="1"), exact=True).click()
        expect(removed.get_by_role("button", name=text("lists.lines.restore"))).to_be_visible()
    if screen.path == "/lists/history":
        # The member's done lists of all runs are there, maybe in two weeks (the light and the
        # dark run can straddle Sunday midnight): wait for the week with this run's list.
        weeks = page.get_by_test_id(TEST_IDS["historyWeek"])
        expect(weeks.filter(has_text=history_list).get_by_role("heading", level=2)).to_be_visible()
    if screen.path == "/lists/:id/shopping":
        # The new and the needs-more line, and the checked one in the opened cart.
        lines = page.get_by_test_id(TEST_IDS["shoppingLines"])
        expect(lines.get_by_test_id(TEST_IDS["lineNew"])).to_be_visible()
        expect(lines.get_by_test_id(TEST_IDS["lineNeedsMore"])).to_be_visible()
        cart = page.get_by_test_id(TEST_IDS["inTheCart"])
        cart.get_by_text(text("lists.shop.cart", count="1"), exact=True).click()
        expect(cart.get_by_test_id(TEST_IDS["lineCheckedBy"])).to_be_visible()

    assert serious_violations(page) == []
