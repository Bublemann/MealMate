"""Offline shopping, reconnect, lie-fi and the logout guard (QA-04 journey 7, plan § 9, M6).

SYNC-01..10, SHOP-03. The phone goes offline with `context.set_offline(True)`; lie-fi is a
connection that carries nothing: every /api request is left unanswered with `page.route`. The
partners use two browser contexts, like two phones. All tests of a run share one database, so
names get a unique tag.

Reloading offline with a service worker is broken in Playwright WebKit (plan O-11), so that step
runs in Chromium only, and only Chromium waits for the service worker to take control; WebKit
covers the offline check-off without a reload, and the lie-fi case by opening the list in a new
page of the same browser context instead of reloading (so the list on screen comes from the
stored copy, not from the previous page's cache). Recheck on every Playwright upgrade.
"""

from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import BrowserContext, Locator, Page, Request, Route, expect

from support.api import Account, Api, sign_in, unique
from support.frontend import TEST_IDS, text

# One polling interval (5 s) plus the time a request and a render take.
POLLED = 10_000
# The client gives up on a read after 8 s (plan § 8); then the indicator says so.
READ_TIMEOUT = 20_000
# The stored list shows "within about 2 s" of opening without a working connection (SYNC-09).
FROM_THE_COPY = 3_000
# How long the service worker may take to install and take control after the first load.
SW_CONTROLS = 15_000
LOCAL_SCHEMES = frozenset({"data", "blob"})
WEBKIT_OFFLINE_RELOAD = (
    "Playwright WebKit offline reload with service worker is broken upstream (plan O-11)"
)

# True once IndexedDB holds the list `id` in the local copy (SYNC-02).
STORED_IN_COPY = """async (id) => new Promise((resolve) => {
    const open = indexedDB.open('mealmate');
    open.onerror = () => resolve(false);
    open.onsuccess = () => {
        const db = open.result;
        if (!db.objectStoreNames.contains('lists')) { db.close(); resolve(false); return; }
        const get = db.transaction('lists').objectStore('lists').get(id);
        get.onsuccess = () => { db.close(); resolve(get.result !== undefined); };
        get.onerror = () => { db.close(); resolve(false); };
    };
})"""


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


def open_cart(page: Page, count: int, timeout: float = POLLED) -> None:
    """Opens the collapsed "In the cart (count)" section once it shows `count` lines."""
    summary = page.get_by_test_id(TEST_IDS["inTheCart"]).get_by_text(
        text("lists.shop.cart", count=str(count)), exact=True
    )
    expect(summary).to_be_visible(timeout=timeout)
    summary.click()


def sync_status(page: Page) -> Locator:
    return page.get_by_test_id(TEST_IDS["syncStatus"])


def waiting(count: int) -> str:
    """The indicator while offline with `count` changes waiting."""
    form = "one" if count == 1 else "other"
    return text(f"lists.sync.offlineWaiting_{form}", count=str(count))


def ready_for_offline(page: Page, list_id: str, browser_name: str) -> None:
    """Waits until the list is in the local copy and, in Chromium, the service worker controls
    the page: only Chromium reloads offline (plan O-11), and in WebKit waiting for the service
    worker can hang, so there the stored copy is all that counts."""
    if browser_name == "chromium":
        page.wait_for_function(
            "() => navigator.serviceWorker.controller !== null", polling=200, timeout=SW_CONTROLS
        )
    page.wait_for_function(STORED_IN_COPY, arg=list_id, polling=200)


def shopping_list(api: Api, owner: Account, tag: str, names: list[str]) -> dict[str, Any]:
    """A list of `owner` being shopped, with one meal that needs an ingredient per name.

    Returns {"list": ListDetail, "ingredients": [Ingredient, …]} in the order of `names`.
    """
    ingredients = [api.create_ingredient(owner, f"{name} {tag}") for name in names]
    meal = api.create_meal(
        owner,
        f"Eintopf {tag}",
        servings=2,
        ingredients=[
            {"ingredient_id": ingredient["id"], "amount": 100, "unit": "g"}
            for ingredient in ingredients
        ],
    )
    created = api.create_list(owner, f"Wochenende {tag}")
    api.add_list_meal(owner, created["id"], meal["id"])
    api.start_shopping(owner, created["id"])
    return {"list": created, "ingredients": ingredients}


def test_offline_check_off_and_reconnect(
    context: BrowserContext,
    new_context: Callable[..., BrowserContext],
    api: Api,
    invite_user: Callable[..., Account],
    make_couple: Callable[[Account, Account], None],
    browser_name: str,
) -> None:
    """Journey 7: offline check-off and a free-text item, reconnect, the partner sees it all."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"))
    ben = invite_user(unique("ben"), unique("Ben"))
    make_couple(anna, ben)
    setup = shopping_list(api, anna, tag, ["Zwiebeln", "Mehl", "Reis"])
    shared = setup["list"]
    assert shared["shared_with_partner"] is True
    onions, flour, _rice = (ingredient["name"] for ingredient in setup["ingredients"])
    napkins = f"Servietten {tag}"
    list_path = f"/lists/{shared['id']}"

    # Anna opens the list with a connection: the phone keeps a copy (SYNC-02).
    page = open_page(context, anna, list_path)
    expect(page.get_by_role("checkbox", name=text("lists.shop.check", name=onions))).to_be_visible()
    expect(sync_status(page)).to_have_text(text("lists.sync.saved"))
    ready_for_offline(page, shared["id"], browser_name)

    # In the shop without signal: two check-offs and a free-text item (SYNC-03).
    context.set_offline(True)
    for name in (onions, flour):
        page.get_by_role("checkbox", name=text("lists.shop.check", name=name)).click()
    page.get_by_test_id(TEST_IDS["extraItemInput"]).fill(napkins)
    page.get_by_role("button", name=text("lists.extra.addLabel", name=napkins)).click()

    expect(sync_status(page)).to_have_text(waiting(3))
    expect(page.get_by_test_id(TEST_IDS["offlineBanner"])).to_have_text(
        text("sync.offline.shopping")
    )
    expect(shopping_line(page, napkins).get_by_test_id(TEST_IDS["linePending"])).to_be_visible()
    open_cart(page, 2)
    for name in (onions, flour):
        # In the cart, faded and saying it was not sent yet (SYNC-07).
        expect(cart_line(page, name).get_by_test_id(TEST_IDS["linePending"])).to_have_text(
            text("lists.sync.pending")
        )

    if browser_name == "chromium":
        # Closing and opening the app offline: the shell comes from the service worker, the list
        # from the copy and the changes from the outbox (SYNC-01/04, SYNC-09).
        page.reload()
        expect(page.get_by_role("navigation")).to_be_visible()
        expect(sync_status(page)).to_have_text(waiting(3))
        open_cart(page, 2, timeout=FROM_THE_COPY)
        for name in (onions, flour):
            expect(cart_line(page, name).get_by_test_id(TEST_IDS["linePending"])).to_be_visible()
        expect(shopping_line(page, napkins)).to_be_visible()
    # WebKit: see the module docstring (plan O-11).

    # Back online: everything is sent in order, and the indicator says "Saved" (SYNC-04).
    context.set_offline(False)
    expect(sync_status(page)).to_have_text(text("lists.sync.saved"), timeout=POLLED)
    expect(page.get_by_test_id(TEST_IDS["linePending"])).to_have_count(0)

    # Ben's phone shows both lines in the cart with Anna's initial, and the new item.
    ben_page = open_page(new_context(), ben, list_path)
    open_cart(ben_page, 2)
    for name in (onions, flour):
        expect(cart_line(ben_page, name).get_by_test_id(TEST_IDS["lineCheckedBy"])).to_have_text(
            anna.display_name[0].upper()
        )
    expect(shopping_line(ben_page, napkins)).to_be_visible()


def leave_unanswered(route: Route) -> None:
    """Lie-fi: the request is never answered (nor failed); the client's deadline decides."""
    del route


def test_lie_fi_shows_the_stored_list(
    page: Page, api: Api, invite_user: Callable[..., Account], base_url: str, browser_name: str
) -> None:
    """SYNC-09: a connection that carries nothing never leaves a blank screen."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"))
    setup = shopping_list(api, anna, tag, ["Zwiebeln"])
    shared = setup["list"]
    onions = setup["ingredients"][0]["name"]
    check_onions = text("lists.shop.check", name=onions)
    sign_in(page.context, anna)
    page.goto(f"/lists/{shared['id']}")
    expect(page.get_by_role("checkbox", name=check_onions)).to_be_visible()
    ready_for_offline(page, shared["id"], browser_name)

    requested: list[str] = []

    def record(request: Request) -> None:
        requested.append(request.url)

    # The whole phone is on lie-fi: no /api request of any page gets an answer.
    page.route("**/api/**", leave_unanswered)
    if browser_name == "chromium":
        shown = page
        shown.on("request", record)
        shown.reload()
    else:
        # Reloading with a service worker is unreliable in Playwright WebKit (plan O-11). A new
        # page of the same context has no query cache: what it shows comes from the stored copy.
        shown = page.context.new_page()
        shown.on("request", record)
        shown.route("**/api/**", leave_unanswered)
        shown.goto(f"/lists/{shared['id']}")

    # The list is on screen from the local copy at once, not a blank screen or a spinner.
    expect(shown.get_by_role("checkbox", name=check_onions)).to_be_visible(timeout=FROM_THE_COPY)
    # Once a request has given up, the indicator says MealMate can't be reached.
    expect(sync_status(shown)).to_have_text(text("lists.sync.unreachable"), timeout=READ_TIMEOUT)
    expect(shown.get_by_role("checkbox", name=check_onions)).to_be_visible()

    # Nothing left the app's origin meanwhile (SEC-08).
    origin = urlsplit(base_url)
    foreign = [
        url
        for url in requested
        if (parts := urlsplit(url)).scheme not in LOCAL_SCHEMES
        and (parts.scheme, parts.netloc) != (origin.scheme, origin.netloc)
    ]
    assert requested
    assert foreign == []
    # The requests left hanging are dropped with the pages, without errors.
    page.unroute_all(behavior="ignoreErrors")
    if shown is not page:
        shown.unroute_all(behavior="ignoreErrors")


def test_logout_asks_about_waiting_changes(
    page: Page, api: Api, invite_user: Callable[..., Account]
) -> None:
    """SYNC-05: logging out with unsent changes asks first; Cancel keeps them."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"))
    # Two lines: checking off the last one would offer to finish.
    setup = shopping_list(api, anna, tag, ["Zwiebeln", "Mehl"])
    shared = setup["list"]
    onions = setup["ingredients"][0]["name"]
    sign_in(page.context, anna)
    page.goto(f"/lists/{shared['id']}")
    page.get_by_role("checkbox", name=text("lists.shop.check", name=onions)).wait_for()

    page.context.set_offline(True)
    page.get_by_role("checkbox", name=text("lists.shop.check", name=onions)).click()
    expect(sync_status(page)).to_have_text(waiting(1))

    page.get_by_test_id(TEST_IDS["tabMe"]).click()
    page.get_by_test_id(TEST_IDS["logoutButton"]).click()
    dialog = page.get_by_role("alertdialog", name=text("me.logoutPending.title_one", count="1"))
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text(text("me.logoutPending.text"))
    dialog.get_by_role("button", name=text("common.cancel")).click()
    expect(dialog).to_be_hidden()
    expect(page.get_by_test_id(TEST_IDS["screenMe"])).to_be_visible()

    # Still waiting, and sent once the connection is back.
    page.get_by_test_id(TEST_IDS["tabLists"]).click()
    expect(sync_status(page)).to_have_text(waiting(1))
    page.context.set_offline(False)
    expect(sync_status(page)).to_have_count(0, timeout=POLLED)
    lines = api.get_list(anna, shared["id"])["lines"]
    assert [line["checked"] for line in lines if line["name"] == onions] == [True]
