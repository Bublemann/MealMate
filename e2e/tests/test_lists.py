"""Draft lists: build a list from meals and extra items (QA-04 journey 6), partners, copies.

LIST-01..08, LIST-14, AGG, CPL-02/03, VIS-03/06 (plan § 12, M5a). All tests of a run share one
database, so names get a unique tag, and the category order is read from the app (another test
reorders the categories).
"""

import re
from collections.abc import Callable

from playwright.sync_api import Locator, Page, expect

from support.api import Account, Api, sign_in, unique
from support.frontend import TEST_IDS, text

LIST_URL = re.compile(r"/lists/([\w-]+)$")


def category_names(api: Api, account: Account, keys: set[str]) -> list[str]:
    """The translated names of the categories `keys`, in the app's current walking order."""
    return [text(f"category.{c['key']}") for c in api.categories(account) if c["key"] in keys]


def line(page: Page, name: str) -> Locator:
    """The line of `name` among the list's (not removed) lines."""
    lines = page.get_by_test_id(TEST_IDS["listLines"])
    return lines.get_by_test_id(TEST_IDS["listLine"]).filter(
        has=page.get_by_role("button", name=re.compile(f"^{re.escape(name)}"))
    )


def add_from_picker(picker: Locator, name: str, clicks: int, button: str) -> None:
    """Adds meal `name` in the open meal picker after `clicks` taps on + or - (`button`)."""
    row = picker.get_by_role("listitem", name=name, exact=True)
    for _ in range(clicks):
        row.get_by_role("button", name=text(button, name=name), exact=True).click()
    row.get_by_role("button", name=text("lists.picker.addLabel", name=name), exact=True).click()
    expect(row).to_contain_text(text("lists.picker.added", name=name))


def test_member_builds_a_list_from_meals_and_extra_items(
    page: Page, api: Api, invite_user: Callable[..., Account]
) -> None:
    """Journey 6: new list, meals with servings, merged lines by category, extras, remove."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"))
    onions = api.create_ingredient(
        anna, f"Zwiebeln {tag}", category_key="fruit_vegetables", piece_weight_g=80
    )
    flour = api.create_ingredient(anna, f"Mehl {tag}", category_key="baking")
    oil = api.create_ingredient(
        anna, f"Öl {tag}", category_key="sauces_spices_oils", base_unit="ml", density_g_per_ml=0.92
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
    # "+ New list" (here the empty state's action) creates a draft and opens the picker.
    page.get_by_test_id(TEST_IDS["newList"]).click()
    expect(page).to_have_url(LIST_URL)
    picker = page.get_by_role("dialog", name=text("lists.picker.title"))
    expect(picker).to_be_visible()

    picker.get_by_label(text("lists.picker.search"), exact=True).fill(tag)
    # The search applies after a short pause; until then the picker lists all meals, which may be
    # just these two. A meal added from there moves into "Recently used", so wait for the search.
    results = picker.get_by_role("list", name=text("lists.picker.results"), exact=True)
    expect(results.get_by_role("listitem")).to_have_count(2)
    # Meal A with 4 servings (2 + 2), meal B with 2 servings (4 - 2).
    add_from_picker(picker, tart["name"], 2, "lists.meals.more")
    add_from_picker(picker, bread["name"], 2, "lists.meals.fewer")
    picker.get_by_role("button", name=text("lists.picker.done"), exact=True).click()
    expect(picker).to_be_hidden()

    meals = page.get_by_test_id(TEST_IDS["listMeals"])
    expect(meals.get_by_test_id(TEST_IDS["listMeal"])).to_have_count(2)
    for meal, servings in ((tart, 4), (bread, 2)):
        group = meals.get_by_role("group", name=text("lists.meals.servingsOf", name=meal["name"]))
        expect(group).to_contain_text(f"{servings} servings")

    # Flour: 200 g x 4/2 + 300 g x 2/4 = 400 g + 150 g = 550 g. Onions: 1 x 4/2 = 2 pieces.
    # Oil: 2 tbsp x 2/4 = 1 tbsp (a line of spoons only stays in tbsp, AGG-04).
    expect(line(page, onions["name"])).to_contain_text("2 pcs")
    expect(line(page, flour["name"])).to_contain_text("550 g")
    expect(line(page, oil["name"])).to_contain_text("1 tbsp")
    lines = page.get_by_test_id(TEST_IDS["listLines"])
    expect(lines.get_by_role("heading", level=3)).to_have_text(
        category_names(api, anna, {"fruit_vegetables", "baking", "sauces_spices_oils"})
    )
    expect(page.get_by_test_id(TEST_IDS["listReminder"])).to_be_visible()

    # A linked extra item merges with the flour of the meals: 550 g + 450 g = 1 kg (LIST-06).
    form = page.get_by_role("form", name=text("lists.extra.label"))
    page.get_by_test_id(TEST_IDS["extraItemInput"]).fill(flour["name"])
    suggestions = form.get_by_role("list", name=text("lists.extra.suggestions"))
    suggestions.get_by_role("button", name=re.compile(f"^{re.escape(flour['name'])}")).click()
    form.get_by_label(text("lists.extra.amount"), exact=True).fill("450")
    expect(form.get_by_label(text("lists.extra.unit"), exact=True)).to_have_value("g")
    form.get_by_role("button", name=text("lists.extra.addLabel", name=flour["name"])).click()
    expect(line(page, flour["name"])).to_contain_text("1 kg")

    # Anything else becomes a free-text item in Other.
    candles = f"Geburtstagskerzen {tag}"
    page.get_by_test_id(TEST_IDS["extraItemInput"]).fill(candles)
    form.get_by_label(text("lists.extra.amountText"), exact=True).fill("2 Packungen")
    page.get_by_test_id(TEST_IDS["extraItemInput"]).press("Enter")
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

    # "Still have oil": removed for this list only, then restored (LIST-07).
    line(page, oil["name"]).get_by_role("button").click()
    sources = page.get_by_role("dialog", name=oil["name"])
    sources.get_by_role("button", name=text("lists.lines.hideLabel", name=oil["name"])).click()
    expect(sources).to_be_hidden()
    expect(line(page, oil["name"])).to_have_count(0)
    removed = page.get_by_test_id(TEST_IDS["hiddenLines"])
    summary = removed.get_by_text(text("lists.lines.hidden", count="1"), exact=True)
    summary.click()
    removed.get_by_role("button", name=text("lists.lines.restoreLabel", name=oil["name"])).click()
    expect(line(page, oil["name"])).to_contain_text("1 tbsp")
    expect(removed).to_have_count(0)

    # Everything was saved on the server (LIST-09).
    page.reload()
    expect(line(page, flour["name"])).to_contain_text("1 kg")
    expect(line(page, candles)).to_be_visible()
    expect(page.get_by_test_id(TEST_IDS["listMeal"])).to_have_count(2)


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
    expect(page.get_by_test_id(TEST_IDS["deleteList"])).to_have_count(0)
    expect(page.get_by_test_id(TEST_IDS["shareListSwitch"])).to_have_count(0)
    expect(page.get_by_test_id(TEST_IDS["listReadOnly"])).to_have_count(0)

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
    expect(page.get_by_test_id(TEST_IDS["addMeals"])).to_have_count(0)
    expect(page.get_by_test_id(TEST_IDS["extraItemInput"])).to_have_count(0)
    expect(page.get_by_text(curry["name"])).to_have_count(0)

    page.get_by_test_id(TEST_IDS["copyList"]).click()
    expect(page).not_to_have_url(re.compile(f"/lists/{party['id']}$"))
    expect(page).to_have_url(LIST_URL)
    expect(page.get_by_test_id(TEST_IDS["listLeftOut"])).to_have_text(
        text("lists.detail.leftOut_one", count="1")
    )
    copied = page.get_by_test_id(TEST_IDS["listMeals"]).get_by_test_id(TEST_IDS["listMeal"])
    expect(copied).to_have_count(1)
    expect(copied).to_contain_text(soup["name"])
    expect(page.get_by_test_id(TEST_IDS["addMeals"])).to_be_visible()
