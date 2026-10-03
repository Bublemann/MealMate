"""axe finds no serious or critical violations on the main screens (A11Y-03)."""

from dataclasses import dataclass
from typing import Literal

import pytest
from playwright.sync_api import Page, expect

from support.a11y import serious_violations
from support.api import (
    CODE_REQUESTS,
    Account,
    Api,
    code_from_link,
    new_barcode,
    sign_in,
    unique,
)
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
    # A draft and a done list of the member's and another user's public list are created in the
    # test, so the feed shows a row of each kind.
    Screen("/lists", "member", (TEST_IDS["newList"], TEST_IDS["listFeed"])),
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
    # The same while offline (SYNC-03/07): the offline banner and a line waiting to be sent.
    Screen(
        "/lists/:id/offline",
        "member",
        (TEST_IDS["offlineBanner"], TEST_IDS["linePending"], TEST_IDS["syncStatus"]),
    ),
    Screen("/meals", "member", (TEST_IDS["screenMeals"],)),
    Screen("/ingredients", "member", (TEST_IDS["screenIngredients"],)),
    # An ingredient with brand, barcode and package is created in the test: /ingredients/<id>.
    Screen("/ingredients/:id", "member", (TEST_IDS["ingredientNutrition"],)),
    # The ingredient form of "New ingredient", with "More" (the package) opened in the test.
    Screen("/ingredients/new", "member", (TEST_IDS["ingredientForm"],)),
    # The filter panel, opened in the test, with a category ticked.
    Screen("/ingredients/filter", "member", (TEST_IDS["filterPanel"],)),
    Screen("/meals/new", "member", (TEST_IDS["mealForm"], TEST_IDS["ingredientPicker"])),
    # No camera in CI (denied or missing): the scanner shows its manual input (BAR-01).
    Screen("/scan", "member", (TEST_IDS["screenScan"], TEST_IDS["barcodeInput"])),
    # A barcode nobody knows is typed in the test: the notice and the form with the barcode.
    Screen("/scan/new", "member", (TEST_IDS["scanNotice"], TEST_IDS["ingredientForm"])),
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
    # No host status files in E2E: the backup and disk empty states are checked.
    Screen(
        "/me/admin/system",
        "admin",
        (TEST_IDS["systemVersion"], TEST_IDS["backupStatus"], TEST_IDS["diskStatus"]),
    ),
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
    feed_lists: list[str] = []  # the names of the lists created for "/lists"
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
        ingredient = api.create_ingredient(
            account,
            unique("A11y"),
            brand=unique("Brand"),
            barcode=new_barcode(),
            quantity_text="1 kg",
            nutrients={"kcal": 52},
        )
        path = f"/ingredients/{ingredient['id']}"
    if path in ("/ingredients/new", "/ingredients/filter"):
        path = "/ingredients"
    if path == "/scan/new":
        path = "/scan"
    if path == "/meals/:id":
        api = request.getfixturevalue("api")
        ingredient = api.create_ingredient(account, unique("A11y"), nutrients={"kcal": 52})
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
        draft = api.create_list(account, unique("A11y list"))
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
        # The admin's lists are public: one shows as a read-only list, with a lock.
        read_only = api.create_list(request.getfixturevalue("admin"), unique("A11y read-only"))
        feed_lists = [draft["name"], done["name"], read_only["name"]]
    if path == "/lists/:id":
        api = request.getfixturevalue("api")
        onions = api.create_ingredient(
            account,
            unique("A11y onions"),
            category_key="fruit_vegetables",
            base_unit="piece",
            piece_weight_g=80,
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
    offline_line = ""  # the line checked off offline on "/lists/:id/offline"
    if path == "/lists/:id/offline":
        api = request.getfixturevalue("api")
        onions = api.create_ingredient(account, unique("A11y onions"))
        # A second line: checking off the last one would offer to finish.
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
        offline = api.create_list(account, unique("A11y offline"))
        api.add_list_meal(account, offline["id"], meal["id"])
        api.start_shopping(account, offline["id"])
        offline_line = onions["name"]
        path = f"/lists/{offline['id']}"
    page.goto(path)
    if screen.path == "/join":
        # The form appears once the code has been checked.
        expect(page.get_by_role("button", name=text("auth.join.submit"))).to_be_visible()
    if screen.path == "/ingredients/new":
        page.get_by_test_id(TEST_IDS["newIngredient"]).click()
        form = page.get_by_test_id(TEST_IDS["ingredientForm"])
        form.get_by_text(text("ingredients.form.more"), exact=True).click()
        expect(form.get_by_label(text("ingredients.field.packUnit"), exact=True)).to_be_visible()
    if screen.path == "/ingredients/filter":
        page.get_by_test_id(TEST_IDS["filterButton"]).click()
        panel = page.get_by_test_id(TEST_IDS["filterPanel"])
        api = request.getfixturevalue("api")
        other = api.category_name(account, "other")
        panel.get_by_role("checkbox", name=other, exact=True).check()
        # Counted on the button, behind the open panel.
        expect(page.get_by_test_id(TEST_IDS["filterButton"])).to_have_text("1")
    if screen.path == "/scan/new":
        page.get_by_test_id(TEST_IDS["barcodeInput"]).fill(new_barcode())
        page.get_by_test_id(TEST_IDS["barcodeLookup"]).click()
    if screen.path == "/me/admin/invites":
        # Also check the created link with its share button.
        page.get_by_test_id(TEST_IDS["createInviteButton"]).click()
    if screen.path == "/lists/:id/offline":
        # Offline, a check-off waits in the outbox (faded, "not sent yet").
        check = page.get_by_role("checkbox", name=text("lists.shop.check", name=offline_line))
        expect(check).to_be_visible()
        page.context.set_offline(True)
        check.click()
        page.get_by_test_id(TEST_IDS["inTheCart"]).get_by_text(
            text("lists.shop.cart", count="1"), exact=True
        ).click()
    for test_id in screen.ready:
        expect(page.get_by_test_id(test_id)).to_be_visible()
    if screen.path == "/lists/:id":
        # Also check the removed line with its restore button.
        removed = page.get_by_test_id(TEST_IDS["hiddenLines"])
        removed.get_by_text(text("lists.lines.hidden", count="1"), exact=True).click()
        expect(removed.get_by_role("button", name=text("lists.lines.restore"))).to_be_visible()
    if screen.path == "/lists":
        # The newest lists come first: this run's lists are on the first page.
        rows = page.get_by_test_id(TEST_IDS["listFeed"]).get_by_test_id(TEST_IDS["listCard"])
        for name in feed_lists:
            expect(rows.filter(has_text=name)).to_be_visible()
    if screen.path == "/lists/:id/shopping":
        # The new and the needs-more line, and the checked one in the opened cart.
        lines = page.get_by_test_id(TEST_IDS["shoppingLines"])
        expect(lines.get_by_test_id(TEST_IDS["lineNew"])).to_be_visible()
        expect(lines.get_by_test_id(TEST_IDS["lineNeedsMore"])).to_be_visible()
        cart = page.get_by_test_id(TEST_IDS["inTheCart"])
        cart.get_by_text(text("lists.shop.cart", count="1"), exact=True).click()
        expect(cart.get_by_test_id(TEST_IDS["lineCheckedBy"])).to_be_visible()

    assert serious_violations(page) == []
