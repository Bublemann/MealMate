"""Shopping together: check-off, live updates, needs more, finish and history (QA-04 journey 11).

LIST-11/12, SHOP-01/04/05/06, SYNC-06/08 (plan § 12, M5b). The partners use two browser contexts,
like two phones; changes of the other one arrive through polling (every 5 s), never a reload.
All tests of a run share one database, so names get a unique tag.
"""

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import BrowserContext, Locator, Page, expect

from support.api import Account, Api, sign_in, unique
from support.frontend import TEST_IDS, text

# One polling interval (5 s) plus the time a request and a render take.
POLLED = 10_000
# The browsers of the suite run in this time zone (conftest.py).
TIME_ZONE = ZoneInfo("Europe/Berlin")


def open_page(context: BrowserContext, account: Account, path: str) -> Page:
    sign_in(context, account)
    page = context.new_page()
    page.goto(path)
    return page


def shopping_line(page: Page, name: str) -> Locator:
    """The line of `name` among the lines still to buy."""
    lines = page.get_by_test_id(TEST_IDS["shoppingLines"])
    return lines.get_by_test_id(TEST_IDS["shoppingLine"]).filter(has_text=name)


def cart_line(page: Page, name: str) -> Locator:
    """The line of `name` in the "In the cart" section."""
    cart = page.get_by_test_id(TEST_IDS["inTheCart"])
    return cart.get_by_test_id(TEST_IDS["shoppingLine"]).filter(has_text=name)


def open_cart(page: Page, count: int) -> None:
    """Opens the collapsed "In the cart (count)" section once it shows `count` lines."""
    summary = page.get_by_test_id(TEST_IDS["inTheCart"]).get_by_text(
        text("lists.shop.cart", count=str(count)), exact=True
    )
    expect(summary).to_be_visible(timeout=POLLED)
    summary.click()


def history_card(page: Page, name: str) -> Locator:
    screen = page.get_by_test_id(TEST_IDS["screenHistory"])
    return screen.get_by_test_id(TEST_IDS["listCard"]).filter(has_text=name)


def test_couple_shops_together(
    context: BrowserContext,
    new_context: Callable[..., BrowserContext],
    api: Api,
    invite_user: Callable[..., Account],
    make_couple: Callable[[Account, Account], None],
) -> None:
    """Journey 11 (couple part): check-off by the partner, needs more, finish, history."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"))
    ben = invite_user(unique("ben"), unique("Ben"))
    make_couple(anna, ben)
    onions = api.create_ingredient(
        anna, f"Zwiebeln {tag}", category_key="fruit_vegetables", piece_weight_g=80
    )
    flour = api.create_ingredient(anna, f"Mehl {tag}", category_key="baking")
    tart = api.create_meal(
        anna,
        f"Zwiebelkuchen {tag}",
        servings=2,
        ingredients=[
            {"ingredient_id": onions["id"], "amount": 1, "unit": "piece"},
            {"ingredient_id": flour["id"], "amount": 200, "unit": "g"},
        ],
    )
    shared = api.create_list(anna, f"Wochenende {tag}")
    assert shared["shared_with_partner"] is True
    api.add_list_meal(anna, shared["id"], tart["id"])
    list_path = f"/lists/{shared['id']}"

    # Anna starts shopping (LIST-11).
    anna_page = open_page(context, anna, list_path)
    anna_page.get_by_test_id(TEST_IDS["startShopping"]).click()
    check_flour = text("lists.shop.check", name=flour["name"])
    expect(anna_page.get_by_role("checkbox", name=check_flour)).to_be_visible()
    expect(shopping_line(anna_page, flour["name"])).to_contain_text("200 g")
    expect(anna_page.get_by_test_id(TEST_IDS["syncStatus"])).to_have_text(text("lists.sync.saved"))

    # Ben finds it at the top of his Lists and checks the flour off on his phone (SHOP-01).
    ben_page = open_page(new_context(), ben, "/lists")
    ben_page.get_by_test_id(TEST_IDS["continueShopping"]).filter(has_text=shared["name"]).click()
    expect(ben_page).to_have_url(re.compile(f"{list_path}$"))
    ben_page.get_by_role("checkbox", name=check_flour).click()
    open_cart(ben_page, 1)
    expect(
        cart_line(ben_page, flour["name"]).get_by_role(
            "checkbox", name=text("lists.shop.uncheck", name=flour["name"])
        )
    ).to_be_checked()

    # Anna sees it in the cart with Ben's initial, without reloading (SYNC-08).
    open_cart(anna_page, 1)
    in_cart = cart_line(anna_page, flour["name"])
    expect(in_cart.get_by_test_id(TEST_IDS["lineCheckedBy"])).to_have_text(
        ben.display_name[0].upper()
    )
    expect(in_cart).to_contain_text(text("lists.shop.checkedBy", name=ben.display_name))
    expect(shopping_line(anna_page, flour["name"])).to_have_count(0)

    # Anna raises the servings from 2 to 4 while Ben's check-off stands: the flour needs
    # 200 g more (400 g instead of the 200 g Ben put in the cart) and is unchecked for both
    # (LIST-12).
    meals = anna_page.get_by_test_id(TEST_IDS["shoppingMeals"])
    meals.get_by_text(text("lists.meals.titleCount", count="1"), exact=True).click()
    stepper = meals.get_by_role("group", name=text("lists.meals.servingsOf", name=tart["name"]))
    more = stepper.get_by_role("button", name=text("lists.meals.more", name=tart["name"]))
    more.click()
    expect(stepper).to_contain_text("3 servings")
    more.click()
    expect(stepper).to_contain_text("4 servings")
    needs_more = text("lists.shop.more", amount="200 g")
    for page in (anna_page, ben_page):
        flour_line = shopping_line(page, flour["name"])
        expect(flour_line.get_by_test_id(TEST_IDS["lineNeedsMore"])).to_contain_text(
            needs_more, timeout=POLLED
        )
        expect(flour_line).to_contain_text("400 g")
        expect(flour_line.get_by_role("checkbox", name=check_flour)).not_to_be_checked()

    # Anna finishes through the dialog with the reminder (SHOP-04).
    anna_page.get_by_test_id(TEST_IDS["finishShopping"]).click()
    dialog = anna_page.get_by_role("dialog", name=text("lists.shop.finishTitle"))
    expect(dialog).to_contain_text(text("lists.shop.unchecked_other", count="2"))
    expect(dialog).to_contain_text(text(f"reminder.{shared['reminder_seed'] % 10 + 1}"))
    dialog.get_by_role("button", name=text("lists.shop.finishConfirm"), exact=True).click()
    expect(dialog).to_be_hidden()
    expect(anna_page.get_by_test_id(TEST_IDS["listDone"])).to_be_visible()
    # Ben's phone shows it finished too.
    expect(ben_page.get_by_test_id(TEST_IDS["listDone"])).to_be_visible(timeout=POLLED)

    # The list is in both partners' history, under the week it was finished (SHOP-05).
    finished = datetime.fromisoformat(api.get_list(anna, shared["id"])["finished_at"])
    finished = finished.astimezone(TIME_ZONE)
    monday = finished - timedelta(days=finished.weekday())
    week_heading = text("lists.history.week", date=monday.strftime("%d/%m"))
    bought_on = text("lists.card.boughtOn", date=finished.strftime("%d/%m"))
    for page in (anna_page, ben_page):
        page.goto("/lists")
        page.get_by_test_id(TEST_IDS["historyLink"]).click()
        card = history_card(page, shared["name"])
        expect(card).to_contain_text(bought_on)
        week = page.get_by_test_id(TEST_IDS["historyWeek"]).filter(has_text=shared["name"])
        expect(week.get_by_role("heading", level=2)).to_have_text(week_heading)


def test_shop_again_and_reopen(page: Page, api: Api, invite_user: Callable[..., Account]) -> None:
    """SHOP-06: a done list starts a new draft with the same meals, or goes back to shopping."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"))
    rice = api.create_ingredient(anna, f"Reis {tag}")
    curry = api.create_meal(
        anna,
        f"Curry {tag}",
        servings=2,
        ingredients=[{"ingredient_id": rice["id"], "amount": 150, "unit": "g"}],
    )
    done = api.create_list(anna, f"Einkauf {tag}")
    api.add_list_meal(anna, done["id"], curry["id"], servings=4)
    api.start_shopping(anna, done["id"])
    api.check_line(anna, done["id"], f"i:{rice['id']}")
    api.finish_list(anna, done["id"])

    sign_in(page.context, anna)
    page.goto("/lists/history")
    history_card(page, done["name"]).click()
    expect(page).to_have_url(re.compile(f"/lists/{done['id']}$"))
    bought = page.get_by_test_id(TEST_IDS["doneLines"]).get_by_role("listitem")
    expect(bought.filter(has_text=rice["name"])).to_contain_text(f"({text('lists.done.bought')})")

    # Shop again: a new draft with the meal and its servings, nothing checked.
    page.get_by_test_id(TEST_IDS["shopAgain"]).click()
    expect(page).not_to_have_url(re.compile(f"/lists/{done['id']}$"))
    expect(page.get_by_test_id(TEST_IDS["startShopping"])).to_be_visible()
    meals = page.get_by_test_id(TEST_IDS["listMeals"])
    expect(meals.get_by_test_id(TEST_IDS["listMeal"])).to_have_count(1)
    group = meals.get_by_role("group", name=text("lists.meals.servingsOf", name=curry["name"]))
    expect(group).to_contain_text("4 servings")
    expect(page.get_by_test_id(TEST_IDS["listLeftOut"])).to_have_count(0)
    lines = page.get_by_test_id(TEST_IDS["listLines"])
    expect(lines).to_contain_text(rice["name"])
    expect(lines).to_contain_text("300 g")

    # Reopen the done list: shopping again, the rice still in the cart.
    page.goto(f"/lists/{done['id']}")
    page.get_by_test_id(TEST_IDS["reopenList"]).click()
    expect(page.get_by_test_id(TEST_IDS["finishShopping"])).to_be_visible()
    open_cart(page, 1)
    expect(
        cart_line(page, rice["name"]).get_by_role(
            "checkbox", name=text("lists.shop.uncheck", name=rice["name"])
        )
    ).to_be_checked()
    page.goto("/lists")
    expect(
        page.get_by_test_id(TEST_IDS["continueShopping"]).filter(has_text=done["name"])
    ).to_be_visible()
