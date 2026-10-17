"""Draft lists: build a list from meals and extra items (QA-04 journey 6), partners, copies; the
Lists tab's headline on a narrow screen.

LIST-01..08, AGG, CPL-02/03, VIS-03/06, UI-01 (plan § 12, M5a). All tests of a run share one
database, so names get a unique tag, and the category order is read from the app (another test
reorders the categories).
"""

import re
from collections.abc import Callable

from playwright.sync_api import Locator, Page, ViewportSize, expect

from support.api import Account, Api, sign_in, unique
from support.frontend import TEST_IDS, text
from support.ui import choose_from_menu, open_more_menu

LIST_URL = re.compile(r"/lists/([\w-]+)$")
# As narrow as an iPhone SE's screen with Display Zoom.
NARROW_SCREEN: ViewportSize = {"width": 320, "height": 568}


def category_names(api: Api, account: Account, keys: set[str]) -> list[str]:
    """The names of the categories `keys`, in the app's current walking order."""
    return [c["names"]["en"] for c in api.categories(account) if c["key"] in keys]


def line(page: Page, name: str) -> Locator:
    """The line of `name` among the list's (not hidden) lines."""
    lines = page.get_by_test_id(TEST_IDS["listLines"])
    return lines.get_by_test_id(TEST_IDS["listLine"]).filter(
        has=page.get_by_role("button", name=re.compile(f"^{re.escape(name)}"))
    )


def add_meal(page: Page, name: str, clicks: int, button: str, *, pick: bool) -> None:
    """Adds meal `name` through the meal field (D-41): typed, then picked from the results
    (`pick`) or taken by "+" as the exact name; in the servings pop-up `clicks` taps on + or -
    (`button`), then "Add". The field is empty and focused again, ready for the next meal."""
    field = page.get_by_test_id(TEST_IDS["mealField"])
    field.fill(name)
    if pick:
        results = page.get_by_test_id(TEST_IDS["mealFieldPanel"]).get_by_role(
            "list", name=text("lists.mealField.results")
        )
        results.get_by_role("button", name=re.compile(f"^{re.escape(name)}")).click()
    else:
        page.get_by_role("button", name=text("lists.addField.plus", name=name)).click()
    dialog = page.get_by_test_id(TEST_IDS["servingsDialog"])
    expect(dialog).to_have_accessible_name(name)
    for _ in range(clicks):
        dialog.get_by_role("button", name=text(button, name=name), exact=True).click()
    dialog.get_by_role("button", name=text("lists.addField.add"), exact=True).click()
    expect(dialog).to_be_hidden()
    expect(field).to_have_value("")
    expect(field).to_be_focused()


def test_member_builds_a_list_from_meals_and_extra_items(
    page: Page, api: Api, invite_user: Callable[..., Account]
) -> None:
    """Journey 6: new list, meals and extras through the two add fields (D-41), merged lines by
    category, hide, remove, a new meal from the list."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"))
    onions = api.create_ingredient(
        anna,
        f"Zwiebeln {tag}",
        category_key="fruit_vegetables",
        base_unit="piece",
        piece_weight_g=80,
    )
    flour = api.create_ingredient(anna, f"Mehl {tag}", category_key="baking")
    oil = api.create_ingredient(
        anna, f"Öl {tag}", category_key="sauces_spices_oils", base_unit="ml"
    )
    # Meal A for 2 servings, meal B for 4.
    tart = api.create_meal(
        anna,
        f"Zwiebelkuchen {tag}",
        servings=2,
        ingredients=[
            {"ingredient_id": onions["id"], "amount": 1, "unit": "piece"},
            {"ingredient_id": flour["id"], "amount": 200, "unit": "g"},
        ],
    )
    bread = api.create_meal(
        anna,
        f"Brot {tag}",
        servings=4,
        ingredients=[
            {"ingredient_id": flour["id"], "amount": 300, "unit": "g"},
            {"ingredient_id": oil["id"], "amount": 2, "unit": "tbsp"},
        ],
    )

    sign_in(page.context, anna)
    page.goto("/lists")
    expect(page.get_by_test_id(TEST_IDS["screenLists"])).to_be_visible()
    # The pinned block's "New list" tile creates a draft and opens it with the meal field's list
    # of meals showing, the keyboard closed (LIST-01, MEAL-09).
    page.get_by_test_id(TEST_IDS["newList"]).click()
    expect(page).to_have_url(LIST_URL)
    meal_field = page.get_by_test_id(TEST_IDS["mealField"])
    expect(page.get_by_test_id(TEST_IDS["mealFieldPanel"])).to_be_visible()
    expect(meal_field).not_to_be_focused()

    # Meal A with 4 servings (2 + 2), picked; meal B with 2 servings (4 - 2), by its exact name.
    add_meal(page, tart["name"], 2, "lists.meals.more", pick=True)
    add_meal(page, bread["name"], 2, "lists.meals.fewer", pick=False)

    meals = page.get_by_test_id(TEST_IDS["listMeals"])
    expect(meals.get_by_test_id(TEST_IDS["listMeal"])).to_have_count(2)
    for meal, servings in ((tart, 4), (bread, 2)):
        group = meals.get_by_role("group", name=text("lists.meals.servingsOf", name=meal["name"]))
        # The compact stepper shows the number; screen readers read "4 servings" (LIST-04).
        read_as = text("lists.meals.servings_other", count=str(servings))
        expect(group.get_by_text(read_as, exact=True)).to_have_count(1)

    # Flour: 200 g x 4/2 + 300 g x 2/4 = 400 g + 150 g = 550 g. Onions: 1 x 4/2 = 2 pieces.
    # Oil: 2 tbsp x 2/4 = 1 tbsp (a line of spoons only stays in tbsp, AGG-04).
    expect(line(page, onions["name"])).to_contain_text("2 pcs")
    expect(line(page, flour["name"])).to_contain_text("550 g")
    expect(line(page, oil["name"])).to_contain_text("1 tbsp")
    lines = page.get_by_test_id(TEST_IDS["listLines"])
    expect(lines.get_by_role("heading", level=3)).to_have_text(
        category_names(api, anna, {"fruit_vegetables", "baking", "sauces_spices_oils"})
    )

    # A linked extra item, picked in the item field, merges with the flour of the meals:
    # 550 g + 450 g = 1 kg (LIST-06, D-41).
    item_field = page.get_by_test_id(TEST_IDS["extraItemInput"])
    item_field.fill(flour["name"])
    results = page.get_by_role("list", name=text("lists.itemField.results"))
    results.get_by_role("button", name=re.compile(f"^{re.escape(flour['name'])}")).click()
    amount_dialog = page.get_by_test_id(TEST_IDS["amountDialog"])
    amount = amount_dialog.get_by_label(text("lists.extra.amount"), exact=True)
    expect(amount).to_be_focused()
    expect(amount_dialog.get_by_label(text("lists.extra.unit"), exact=True)).to_have_value("g")
    amount.fill("450")
    amount_dialog.get_by_role("button", name=text("lists.addField.add"), exact=True).click()
    expect(amount_dialog).to_be_hidden()
    expect(item_field).to_have_value("")
    expect(item_field).to_be_focused()
    expect(line(page, flour["name"])).to_contain_text("1 kg")

    # Anything else becomes a free-text item in Other: Enter without an exact match.
    candles = f"Geburtstagskerzen {tag}"
    item_field.fill(candles)
    item_field.press("Enter")
    free_text = page.get_by_test_id(TEST_IDS["freeTextDialog"])
    expect(free_text).to_have_accessible_name(candles)
    free_text.get_by_label(text("lists.extra.amountText"), exact=True).fill("2 Packungen")
    free_text.get_by_role("button", name=text("lists.addField.add"), exact=True).click()
    expect(free_text).to_be_hidden()
    expect(line(page, candles)).to_contain_text("2 Packungen")
    expect(lines.get_by_role("heading", level=3)).to_have_text(
        category_names(api, anna, {"fruit_vegetables", "baking", "sauces_spices_oils", "other"})
    )

    # Where the flour comes from (LIST-08).
    line(page, flour["name"]).get_by_role("button").click()
    sources = page.get_by_role("dialog", name=flour["name"])
    expect(sources).to_be_visible()
    expect(sources.get_by_role("listitem")).to_have_count(3)
    source_items = sources.get_by_role("listitem")
    # Meals are named with their servings on the list, the extra item with its own amount.
    for meal, servings in ((tart, "4"), (bread, "2")):
        expect(source_items.filter(has_text=meal["name"])).to_have_text(
            text("lists.sources.meal_other", name=meal["name"], count=servings)
        )
    expect(source_items.filter(has_text=text("lists.sources.extra"))).to_contain_text("450 g")
    sources.get_by_role("button", name=text("common.close")).click()
    expect(sources).to_be_hidden()

    # "Still have oil": hidden for this list only, then restored (LIST-07).
    line(page, oil["name"]).get_by_role("button").click()
    sources = page.get_by_role("dialog", name=oil["name"])
    sources.get_by_role("button", name=text("lists.lines.hideLabel", name=oil["name"])).click()
    expect(sources).to_be_hidden()
    expect(line(page, oil["name"])).to_have_count(0)
    hidden = page.get_by_test_id(TEST_IDS["hiddenLines"])
    summary = hidden.get_by_text(text("lists.lines.hidden", count="1"), exact=True)
    summary.click()
    hidden.get_by_role("button", name=text("lists.lines.restoreLabel", name=oil["name"])).click()
    expect(line(page, oil["name"])).to_contain_text("1 tbsp")
    expect(hidden).to_have_count(0)

    # Everything was saved on the server (LIST-09).
    page.reload()
    expect(line(page, flour["name"])).to_contain_text("1 kg")
    expect(line(page, candles)).to_be_visible()
    expect(page.get_by_test_id(TEST_IDS["listMeal"])).to_have_count(2)

    # Meal A down to 3 servings with the compact stepper: flour 200 g x 3/2 + 150 g + 450 g.
    group = meals.get_by_role("group", name=text("lists.meals.servingsOf", name=tart["name"]))
    group.get_by_role("button", name=text("lists.meals.fewer", name=tart["name"])).click()
    read_as = text("lists.meals.servings_other", count="3")
    expect(group.get_by_text(read_as, exact=True)).to_have_count(1)
    expect(line(page, flour["name"])).to_contain_text("900 g")

    # Without swiping (no swipe gestures here), meal B goes with its "Remove", which shows on
    # focus, at once and without a confirmation (LIST-04, D-40): the oil goes with it.
    remove = meals.get_by_role(
        "button", name=text("lists.meals.remove", name=bread["name"]), exact=True
    )
    expect(remove).to_have_text(text("lists.meals.removeAction"))
    remove.focus()
    remove.press("Enter")
    expect(meals.get_by_test_id(TEST_IDS["listMeal"])).to_have_count(1)
    expect(line(page, flour["name"])).to_contain_text("750 g")
    expect(line(page, oil["name"])).to_have_count(0)
    draft = LIST_URL.search(page.url)
    assert draft is not None
    assert [meal["meal_id"] for meal in api.get_list(anna, draft[1])["meals"]] == [tart["id"]]

    # A meal that doesn't exist yet: "+" without an exact match opens the meal form with the typed
    # name; saving puts the meal on this list and comes back here (LIST-03).
    quiche = f"Quiche {tag}"
    meal_field.fill(quiche)
    page.get_by_role("button", name=text("lists.addField.plus", name=quiche)).click()
    form = page.get_by_test_id(TEST_IDS["mealForm"])
    expect(form.get_by_label(text("meals.field.name"), exact=True)).to_have_value(quiche)
    form.get_by_role("button", name=text("meals.form.create"), exact=True).click()
    expect(page).to_have_url(re.compile(f"/lists/{draft[1]}$"))
    expect(meals.get_by_test_id(TEST_IDS["listMeal"]).filter(has_text=quiche)).to_be_visible()
    assert len(api.get_list(anna, draft[1])["meals"]) == 2

    # Renaming and deleting go through the ⋯ menu (D-39, LIST-02, LIST-13).
    new_name = f"Grillabend {tag}"
    choose_from_menu(page, "renameList")
    rename = page.get_by_role("dialog", name=text("lists.detail.renameTitle"))
    rename.get_by_label(text("lists.detail.name"), exact=True).fill(new_name)
    rename.get_by_role("button", name=text("common.save"), exact=True).click()
    expect(rename).to_be_hidden()
    expect(page.get_by_role("heading", level=1)).to_contain_text(new_name)

    # Cancelling the deletion puts the focus back on ⋯; confirming deletes.
    choose_from_menu(page, "deleteList")
    confirm = page.get_by_role("alertdialog")
    confirm.get_by_role("button", name=text("common.cancel"), exact=True).click()
    expect(confirm).to_be_hidden()
    expect(page.get_by_test_id(TEST_IDS["moreActions"])).to_be_focused()
    choose_from_menu(page, "deleteList")
    page.get_by_role("alertdialog").get_by_role(
        "button", name=text("lists.detail.deleteConfirm"), exact=True
    ).click()
    expect(page).to_have_url(re.compile("/lists$"))


def test_partner_edits_a_shared_draft(
    page: Page,
    api: Api,
    invite_user: Callable[..., Account],
    make_couple: Callable[[Account, Account], None],
) -> None:
    """CPL-02/03: a new list of someone in a couple is shared; the partner edits it."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"))
    ben = invite_user(unique("ben"), unique("Ben"))
    make_couple(anna, ben)
    soup = api.create_meal(anna, f"Suppe {tag}", servings=2)
    draft = api.create_list(anna, f"Wochenende {tag}")
    assert draft["shared_with_partner"] is True
    api.add_list_meal(anna, draft["id"], soup["id"])

    sign_in(page.context, ben)
    page.goto("/lists")
    card = (
        page.get_by_test_id(TEST_IDS["listFeed"])
        .get_by_test_id(TEST_IDS["listCard"])
        .filter(has_text=draft["name"])
    )
    # Anna's initial marks it as hers; the shared icon and text say Ben may change it (UI-02).
    expect(card.get_by_role("img", name=anna.display_name)).to_have_text(anna.display_name[0])
    expect(card).to_contain_text(text("lists.card.sharedBy", name=anna.display_name))
    expect(card.get_by_role("img", name=text("lists.card.shared"), exact=True)).to_be_visible()
    expect(card.get_by_role("img", name=text("lists.card.readOnly"), exact=True)).to_have_count(0)
    card.click()
    expect(page).to_have_url(re.compile(f"/lists/{draft['id']}$"))

    # Ben changes the servings; only the owner deletes or switches sharing.
    group = page.get_by_role("group", name=text("lists.meals.servingsOf", name=soup["name"]))
    with page.expect_response(
        lambda response: response.request.method == "PATCH" and "/meals/" in response.url
    ) as saved:
        group.get_by_role("button", name=text("lists.meals.more", name=soup["name"])).click()
    assert saved.value.ok
    expect(group).to_contain_text("3 servings")
    expect(page.get_by_test_id(TEST_IDS["listReadOnly"])).to_have_count(0)
    # His ⋯ menu offers renaming and the export, not deleting or the share switch (D-39).
    menu = open_more_menu(page)
    # The export reads "Share as text" where the browser has a share sheet, else "Copy as text".
    export = "|".join(
        re.escape(text(key)) for key in ("lists.detail.export", "lists.detail.exportCopy")
    )
    expect(menu.get_by_role("menuitem")).to_have_text(
        [text("lists.detail.rename"), re.compile(f"^({export})$")]
    )
    expect(menu.get_by_test_id(TEST_IDS["shareListSwitch"])).to_have_count(0)
    page.keyboard.press("Escape")
    expect(menu).to_be_hidden()

    # Anna's list has changed.
    assert api.get_list(anna, draft["id"])["meals"][0]["servings"] == 3


def test_others_list_is_read_only_and_copies_what_i_can_see(
    page: Page,
    api: Api,
    invite_user: Callable[..., Account],
    make_couple: Callable[[Account, Account], None],
) -> None:
    """VIS-03/06: a public list is read-only for others; its copy leaves out private meals."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"))
    ben = invite_user(unique("ben"), unique("Ben"))
    carl = invite_user(unique("carl"), unique("Carl"))
    make_couple(anna, ben)
    api.update_me(ben, meals_public=False)
    curry = api.create_meal(ben, f"Curry {tag}", servings=2)
    soup = api.create_meal(anna, f"Suppe {tag}", servings=4)
    party = api.create_list(anna, f"Party {tag}")
    # Anna sees her partner's private meal (CPL-04), Carl doesn't.
    api.add_list_meal(anna, party["id"], soup["id"])
    api.add_list_meal(anna, party["id"], curry["id"])

    sign_in(page.context, carl)
    page.goto("/lists")
    card = (
        page.get_by_test_id(TEST_IDS["listFeed"])
        .get_by_test_id(TEST_IDS["listCard"])
        .filter(has_text=party["name"])
    )
    # A read-only list: Anna's marker, "by Anna" and a lock (UI-02).
    expect(card.get_by_role("img", name=anna.display_name)).to_be_visible()
    expect(card).to_contain_text(text("lists.card.by", name=anna.display_name))
    expect(card).not_to_contain_text(text("lists.card.sharedBy", name=anna.display_name))
    expect(card.get_by_role("img", name=text("lists.card.readOnly"), exact=True)).to_be_visible()
    card.click()
    expect(page).to_have_url(re.compile(f"/lists/{party['id']}$"))

    expect(page.get_by_test_id(TEST_IDS["listReadOnly"])).to_contain_text(
        text("lists.detail.readOnly", name=anna.display_name)
    )
    meals = page.get_by_test_id(TEST_IDS["listMeals"]).get_by_test_id(TEST_IDS["listMeal"])
    expect(meals).to_have_count(2)
    expect(meals.nth(0)).to_contain_text(soup["name"])
    expect(meals.nth(1)).to_have_text(text("lists.meals.privateServings_other", count="2"))
    expect(page.get_by_test_id(TEST_IDS["mealField"])).to_have_count(0)
    expect(page.get_by_test_id(TEST_IDS["extraItemInput"])).to_have_count(0)
    expect(page.get_by_text(curry["name"])).to_have_count(0)

    # The note has no button; copying is in the ⋯ menu, next to the export (D-39).
    expect(page.get_by_test_id(TEST_IDS["listReadOnly"]).get_by_role("button")).to_have_count(0)
    expect(page.get_by_test_id(TEST_IDS["floatingBar"])).to_have_count(0)
    choose_from_menu(page, "copyList")
    expect(page).not_to_have_url(re.compile(f"/lists/{party['id']}$"))
    expect(page).to_have_url(LIST_URL)
    expect(page.get_by_test_id(TEST_IDS["listLeftOut"])).to_have_text(
        text("lists.detail.leftOut_one", count="1")
    )
    copied = page.get_by_test_id(TEST_IDS["listMeals"]).get_by_test_id(TEST_IDS["listMeal"])
    expect(copied).to_have_count(1)
    expect(copied).to_contain_text(soup["name"])
    expect(page.get_by_test_id(TEST_IDS["mealField"])).to_be_visible()


def test_pinned_headline_wraps_on_a_narrow_screen(
    page: Page, invite_user: Callable[..., Account]
) -> None:
    """UI-01, D-44: at the largest iPhone text size (53 px body text, simulated here) on a screen
    as narrow as an iPhone SE's with Display Zoom (320 px), "Einkaufslisten" is wider than the
    content column: the headline breaks inside the word, hyphenated where the browser can, instead
    of clipping or widening the page."""
    sign_in(page.context, invite_user(language="de"))
    page.set_viewport_size(NARROW_SCREEN)
    page.goto("/lists")
    page.add_style_tag(content="html { font-size: 53px !important; }")

    block = page.get_by_test_id(TEST_IDS["pinnedBlock"])
    headline = block.get_by_role("heading", level=1, name=text("nav.lists", "de"))
    expect(headline).to_be_visible()
    lines = headline.evaluate(
        """headline => {
          const range = document.createRange();
          range.selectNodeContents(headline);
          return new Set([...range.getClientRects()].map((line) => Math.round(line.top))).size;
        }"""
    )
    assert lines > 1
    assert headline.evaluate("headline => headline.scrollWidth <= headline.clientWidth")
    box = headline.bounding_box()
    assert box is not None
    assert box["x"] >= 0
    assert box["x"] + box["width"] <= NARROW_SCREEN["width"]
