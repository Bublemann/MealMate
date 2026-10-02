"""Ingredients: create with brand and barcode, search, similar hint, own values, admin category
order (seen on a shopping list), merge.

ING-01..05, NUT-02, REF-01 (plan § 12, M3; one kind of ingredient since 2026-09-28). All tests of
a run share one database, so names get a unique tag; the tag is the same in both spellings of a
name, so they stay similar (ING-03).
"""

import re

from playwright.sync_api import Locator, Page, expect

from support.api import Account, Api, new_barcode, sign_in, unique
from support.frontend import TEST_IDS, ingredient_label, text


def nutrient_row(page: Page, key: str) -> Locator:
    """The row of nutrient `key` in the nutrition table of the open ingredient."""
    table = page.get_by_test_id(TEST_IDS["ingredientNutrition"])
    return table.get_by_role("row").filter(
        has=page.get_by_role("rowheader", name=text(f"nutrient.{key}"), exact=True)
    )


def test_member_builds_up_an_ingredient(member_page: Page) -> None:
    """Create with brand and barcode, find by brand and by another spelling, similar hint, a
    second brand of the same thing, own nutrition values (ING-01..03, NUT-02)."""
    page = member_page
    tag = unique("e2e")
    name = f"Äpfel {tag}"
    brand = f"Hofgut {tag}"
    barcode = new_barcode()

    page.goto("/ingredients")
    expect(page.get_by_test_id(TEST_IDS["screenIngredients"])).to_be_visible()
    # The "New ingredient" tile, also while there are no ingredients yet (UI-03).
    page.get_by_test_id(TEST_IDS["newIngredient"]).click()
    dialog = page.get_by_role("dialog", name=text("ingredients.form.createTitle"))
    form = dialog.get_by_test_id(TEST_IDS["ingredientForm"])
    form.get_by_label(text("ingredients.field.name"), exact=True).fill(name)
    form.get_by_label(text("ingredients.field.brand"), exact=True).fill(brand)
    form.get_by_label(text("ingredients.field.category"), exact=True).select_option(
        label=text("category.fruit_vegetables")
    )
    form.get_by_label(text("ingredients.field.pieceWeight"), exact=True).fill("180")
    form.get_by_label(text("nutrient.kcal"), exact=True).fill("52")
    form.get_by_label(text("ingredients.field.barcode"), exact=True).fill(barcode)
    # The package is optional, under "More".
    form.get_by_text(text("ingredients.form.more"), exact=True).click()
    form.get_by_label(text("ingredients.field.quantityText"), exact=True).fill("1 kg")
    form.get_by_role("button", name=text("common.save")).click()

    # The new ingredient opens, named with its brand.
    expect(page).to_have_url(re.compile(r"/ingredients/[\w-]+$"))
    detail = page.get_by_test_id(TEST_IDS["screenIngredient"])
    label = ingredient_label(name, brand)
    expect(detail.get_by_role("heading", level=1)).to_have_text(label)
    expect(detail).to_contain_text(text("category.fruit_vegetables"))
    expect(detail).to_contain_text(barcode)
    expect(detail).to_contain_text("1 kg")
    expect(detail).to_contain_text(text("ingredients.detail.source.manual"))
    expect(nutrient_row(page, "kcal")).to_contain_text("52 kcal")
    ingredient_url = page.url

    # Search covers the brand, and ignores umlaut spellings (ING-03).
    page.get_by_test_id(TEST_IDS["tabIngredients"]).click()
    search = page.get_by_test_id(TEST_IDS["ingredientSearch"])
    results = page.get_by_test_id(TEST_IDS["ingredientList"])
    row = results.get_by_role("link", name=re.compile(f"^{re.escape(label)}"))
    search.fill(brand)
    expect(row).to_be_visible()
    expect(row).to_contain_text(text("ingredients.hasBarcode"))
    search.fill(f"aepfel {tag}")
    expect(row).to_be_visible()

    # While a search text is present, the tile offers to create it, with that name (ING-03).
    tile = page.get_by_test_id(TEST_IDS["newIngredient"])
    expect(tile).to_have_text(text("ingredients.createNamed", name=f"aepfel {tag}"))
    tile.click()
    dialog = page.get_by_role("dialog", name=text("ingredients.form.createTitle"))
    name_field = dialog.get_by_label(text("ingredients.field.name"), exact=True)
    expect(name_field).to_have_value(f"aepfel {tag}")

    # Creating "Apfel …" points to the existing "Äpfel …", a hint only: another brand of the
    # same thing is another ingredient, with the same name.
    name_field.fill(f"Apfel {tag}")
    hint = dialog.get_by_test_id(TEST_IDS["ingredientSimilar"])
    expect(hint).to_contain_text(text("ingredients.similar.title"))
    expect(hint.get_by_role("link", name=label)).to_be_visible()
    name_field.fill(name)
    dialog.get_by_label(text("ingredients.field.brand"), exact=True).fill(f"Bio {tag}")
    dialog.get_by_role("button", name=text("common.save")).click()
    other = ingredient_label(name, f"Bio {tag}")
    expect(page.get_by_role("heading", level=1)).to_have_text(other)
    # Back on the tab, the search is still there (UI-01).
    page.get_by_test_id(TEST_IDS["tabIngredients"]).click()
    expect(search).to_have_value(f"aepfel {tag}")
    search.fill(tag)
    expect(
        page.get_by_test_id(TEST_IDS["ingredientList"]).get_by_role(
            "link", name=re.compile(f"^{re.escape(name)} ")
        )
    ).to_have_count(2)

    # Its own values, changed by anyone (ING-01, NUT-02).
    page.goto(ingredient_url)
    page.get_by_test_id(TEST_IDS["editIngredient"]).click()
    dialog = page.get_by_role("dialog", name=text("ingredients.form.editTitle", name=label))
    dialog.get_by_label(text("nutrient.kcal"), exact=True).fill("60")
    dialog.get_by_role("button", name=text("common.save")).click()
    expect(dialog).to_be_hidden()
    expect(nutrient_row(page, "kcal")).to_contain_text("60 kcal")
    expect(nutrient_row(page, "fat")).to_contain_text(text("ingredients.nutrition.noValue"))


def test_pinned_block_fits_the_largest_text_size(member_page: Page) -> None:
    """UI-01: at the largest iPhone text size (53 px body text, simulated here) the pinned block
    wraps a long "Create …" tile instead of clipping it or widening the page, and leaves room for
    the content below it, because its text stops growing at about the first accessibility size
    (D-29)."""
    page = member_page
    page.goto("/ingredients")
    page.add_style_tag(content="html { font-size: 53px !important; }")
    name = f"Quittengelee mit Zimt {unique('aus dem Garten')}"
    page.get_by_test_id(TEST_IDS["ingredientSearch"]).fill(name)

    tile = page.get_by_test_id(TEST_IDS["newIngredient"])
    expect(tile).to_have_text(text("ingredients.createNamed", name=name))
    reset = page.get_by_role("button", name=text("common.resetFilters"))
    expect(reset).to_be_visible()
    viewport = page.viewport_size
    assert viewport is not None
    assert page.evaluate("document.documentElement.scrollWidth") <= viewport["width"]
    assert tile.evaluate("tile => tile.scrollWidth <= tile.clientWidth")
    box = tile.bounding_box()
    assert box is not None
    assert box["x"] + box["width"] <= viewport["width"]
    # The tile is the pinned block's last row: at least a quarter of the screen stays for the
    # content, which a name this long at full text size would cover.
    assert box["y"] + box["height"] < viewport["height"] * 0.75


def test_member_filters_by_categories(member_page: Page, api: Api, member: Account) -> None:
    """UI-01, UI-03, ING-03, D-23: the filter panel lists every category; ticked ones apply at
    once and show the ingredients of any of them; the button counts the group; "Reset" and
    "Reset filters" clear them; the choice stays while the app is open."""
    page = member_page
    tag = unique("e2e")
    for name, category in (
        (f"Kirschen {tag}", "fruit_vegetables"),
        (f"Quark {tag}", "dairy_eggs"),
        (f"Senf {tag}", "sauces_spices_oils"),
    ):
        api.create_ingredient(member, name, category_key=category)
    fruit = text("category.fruit_vegetables")
    dairy = text("category.dairy_eggs")
    sauces = text("category.sauces_spices_oils")

    page.goto("/ingredients")
    page.get_by_test_id(TEST_IDS["ingredientSearch"]).fill(tag)
    rows = page.get_by_test_id(TEST_IDS["ingredientList"]).get_by_test_id(TEST_IDS["ingredientRow"])
    expect(rows).to_have_count(3)
    button = page.get_by_test_id(TEST_IDS["filterButton"])
    expect(button).to_have_accessible_name(text("filter.button"))

    button.click()
    panel = page.get_by_role("dialog", name=text("filter.title"))
    expect(panel).to_have_attribute("data-testid", TEST_IDS["filterPanel"])
    group = panel.get_by_test_id(TEST_IDS["filterGroup"])
    expect(group).to_have_accessible_name(text("ingredients.filter.categories"))
    expect(group.get_by_role("checkbox")).to_have_count(len(api.categories(member)))

    # Each tick applies at once, behind the open panel; several show any of them. The button
    # counts the group (its name is read once the panel, which hides the page from screen
    # readers, is closed).
    group.get_by_role("checkbox", name=fruit, exact=True).check()
    expect(rows).to_have_count(1)
    expect(rows).to_contain_text([f"Kirschen {tag}"])
    expect(button).to_have_text("1")
    group.get_by_role("checkbox", name=dairy, exact=True).check()
    expect(rows).to_contain_text([f"Kirschen {tag}", f"Quark {tag}"])
    expect(button).to_have_text("1")

    # "Reset" unticks every group and keeps the search.
    panel.get_by_role("button", name=text("filter.reset"), exact=True).click()
    expect(group.get_by_role("checkbox", checked=True)).to_have_count(0)
    expect(rows).to_have_count(3)
    expect(button).to_have_text("")

    group.get_by_role("checkbox", name=sauces, exact=True).check()
    panel.get_by_role("button", name=text("filter.done"), exact=True).click()
    expect(panel).to_be_hidden()
    expect(button).to_be_focused()
    expect(button).to_have_accessible_name(text("filter.buttonActive_one", count="1"))
    expect(rows).to_contain_text([f"Senf {tag}"])

    # Kept while the app is open: open the ingredient and come back.
    rows.first.click()
    expect(page.get_by_test_id(TEST_IDS["screenIngredient"])).to_be_visible()
    page.get_by_test_id(TEST_IDS["tabIngredients"]).click()
    expect(button).to_have_accessible_name(text("filter.buttonActive_one", count="1"))
    expect(rows).to_contain_text([f"Senf {tag}"])

    # Nothing in that category matches: "Reset filters" clears the search and the categories.
    page.get_by_test_id(TEST_IDS["ingredientSearch"]).fill(f"Kirschen {tag}")
    expect(page.get_by_text(text("common.noMatches"), exact=True)).to_be_visible()
    page.get_by_role("button", name=text("common.resetFilters")).click()
    expect(page.get_by_test_id(TEST_IDS["ingredientSearch"])).to_have_value("")
    expect(button).to_have_accessible_name(text("filter.button"))
    expect(page.get_by_test_id(TEST_IDS["ingredientList"])).to_be_visible()


def test_filter_panel_fits_the_largest_text_size(
    member_page: Page, api: Api, member: Account
) -> None:
    """UI-01: at the largest iPhone text size (53 px body text, simulated here) the filter
    panel's groups, "Reset" and "Done" wrap instead of being clipped or widening the page, and
    the panel scrolls; its buttons stay in view."""
    page = member_page
    page.goto("/ingredients")
    page.add_style_tag(content="html { font-size: 53px !important; }")
    button = page.get_by_test_id(TEST_IDS["filterButton"])
    search = page.get_by_test_id(TEST_IDS["ingredientSearch"])
    viewport = page.viewport_size
    assert viewport is not None
    # The button sits beside the search field, not below it.
    button_box, search_box = button.bounding_box(), search.bounding_box()
    assert button_box is not None
    assert search_box is not None
    assert button_box["y"] < search_box["y"] + search_box["height"]
    assert button_box["x"] + button_box["width"] <= viewport["width"]

    button.click()
    panel = page.get_by_test_id(TEST_IDS["filterPanel"])
    expect(panel).to_be_visible()
    # Measured once it has slid in.
    panel.evaluate("panel => Promise.all(panel.getAnimations().map((a) => a.finished))")

    assert page.evaluate("document.documentElement.scrollWidth") <= viewport["width"]
    assert panel.evaluate("panel => panel.scrollWidth <= panel.clientWidth")
    assert panel.evaluate("panel => panel.scrollHeight > panel.clientHeight")
    box = panel.bounding_box()
    assert box is not None
    assert box["y"] >= 0
    assert box["y"] + box["height"] <= viewport["height"]
    for name in ("filter.reset", "filter.done"):
        action = panel.get_by_role("button", name=text(name), exact=True)
        expect(action).to_be_in_viewport()
        assert action.evaluate("action => action.scrollWidth <= action.clientWidth")
    # The last category can be scrolled to and ticked; every name wraps within the panel.
    boxes = panel.get_by_role("checkbox")
    boxes.last.check()
    expect(boxes.last).to_be_checked()
    for category in api.categories(member):
        name = panel.get_by_text(text(f"category.{category['key']}"), exact=True)
        assert name.evaluate("name => name.scrollWidth <= name.clientWidth")


def test_filter_panel_does_not_slide_under_reduce_motion(member_page: Page) -> None:
    """UI-01, A11Y-02: the panel slides up, but not under Reduce Motion."""
    page = member_page
    page.goto("/ingredients")
    button = page.get_by_test_id(TEST_IDS["filterButton"])
    panel = page.get_by_test_id(TEST_IDS["filterPanel"])

    button.click()
    expect(panel).to_be_visible()
    assert panel.evaluate("panel => getComputedStyle(panel).animationName") != "none"
    page.keyboard.press("Escape")
    expect(panel).to_be_hidden()

    page.emulate_media(reduced_motion="reduce")
    button.click()
    expect(panel).to_be_visible()
    assert panel.evaluate("panel => getComputedStyle(panel).animationName") == "none"


def test_admin_reorders_categories(page: Page, api: Api, admin: Account) -> None:
    """REF-01: a shopping list's lines follow the new order."""
    original = [category["id"] for category in api.categories(admin)]
    first, second = api.categories(admin)[:2]
    tag = unique("e2e")
    ingredient_a = api.create_ingredient(admin, f"Order A {tag}", category_key=first["key"])
    ingredient_b = api.create_ingredient(admin, f"Order B {tag}", category_key=second["key"])
    draft = api.create_list(admin, f"Order {tag}")
    for ingredient in (ingredient_a, ingredient_b):
        api.add_extra_item(admin, draft["id"], ingredient_id=ingredient["id"], amount=100, unit="g")
    first_name = text(f"category.{first['key']}")
    second_name = text(f"category.{second['key']}")

    try:
        sign_in(page.context, admin)
        page.goto("/me/admin/categories")
        order = page.get_by_test_id(TEST_IDS["adminCategoryList"])
        expect(order.get_by_role("listitem").first).to_contain_text(first_name)
        page.get_by_role("button", name=text("admin.categories.moveUp", name=second_name)).click()
        expect(order.get_by_role("listitem").first).to_contain_text(second_name)
        page.get_by_test_id(TEST_IDS["saveCategoryOrder"]).click()
        expect(page.get_by_role("status")).to_have_text(text("admin.categories.saved"))

        page.goto(f"/lists/{draft['id']}")
        lines = page.get_by_test_id(TEST_IDS["listLines"]).get_by_test_id(TEST_IDS["listLine"])
        expect(lines).to_contain_text([ingredient_b["name"], ingredient_a["name"]])
    finally:
        api.order_categories(admin, original)


def test_admin_merges_a_duplicate(page: Page, api: Api, admin: Account) -> None:
    """ING-05: merging moves the duplicate's meal rows (and its barcode, as the ingredient that
    stays has none) to the ingredient that stays."""
    tag = unique("e2e")
    keep = api.create_ingredient(admin, f"Tomaten {tag}", category_key="fruit_vegetables")
    barcode = new_barcode()
    duplicate = api.create_ingredient(
        admin, f"Tomate {tag}", category_key="fruit_vegetables", barcode=barcode
    )
    meal = api.create_meal(
        admin,
        f"Salat {tag}",
        servings=2,
        ingredients=[{"ingredient_id": duplicate["id"], "amount": 200, "unit": "g"}],
    )

    sign_in(page.context, admin)
    page.goto(f"/ingredients/{duplicate['id']}")
    expect(page.get_by_test_id(TEST_IDS["screenIngredient"])).to_contain_text(barcode)
    page.get_by_test_id(TEST_IDS["mergeIngredient"]).click()
    dialog = page.get_by_role(
        "dialog", name=text("ingredients.admin.mergeTitle", name=duplicate["name"])
    )
    picker = dialog.get_by_test_id(TEST_IDS["ingredientPicker"])
    picker.get_by_label(text("ingredients.admin.mergePicker"), exact=True).fill(keep["name"])
    picker.get_by_role("button", name=re.compile(f"^{re.escape(keep['name'])}")).click()
    confirm = page.get_by_role(
        "alertdialog",
        name=text(
            "ingredients.admin.mergeConfirmTitle",
            **{"from": duplicate["name"], "into": keep["name"]},
        ),
    )
    confirm.get_by_role("button", name=text("ingredients.admin.mergeConfirm")).click()

    expect(page).to_have_url(re.compile(f"/ingredients/{keep['id']}$"))
    detail = page.get_by_test_id(TEST_IDS["screenIngredient"])
    expect(detail.get_by_role("heading", level=1)).to_have_text(keep["name"])
    expect(detail).to_contain_text(barcode)
    expect(detail).to_contain_text(text("ingredients.detail.meals_one", count="1"))

    # The meal uses the ingredient that stays; the duplicate is gone.
    page.goto(f"/meals/{meal['id']}")
    expect(
        page.get_by_test_id(TEST_IDS["mealIngredients"]).get_by_role("link", name=keep["name"])
    ).to_have_attribute("href", f"/ingredients/{keep['id']}")
    page.goto(f"/ingredients/{duplicate['id']}")
    expect(page.get_by_role("alert")).to_have_text(text("error.common.not_found"))
