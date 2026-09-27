"""Ingredients: search, similar hint, products and their average, admin order and merge.

ING-01..05, NUT-02, REF-01 (plan § 12, M3). All tests of a run share one database, so names get
a unique tag; the tag is the same in both spellings of a name, so they stay similar (ING-03).
"""

import re

from playwright.sync_api import Locator, Page, expect

from support.api import Account, Api, new_barcode, sign_in, unique
from support.frontend import TEST_IDS, text


def nutrient_row(page: Page, key: str) -> Locator:
    """The row of nutrient `key` in the nutrition table of the open ingredient."""
    table = page.get_by_test_id(TEST_IDS["ingredientNutrition"])
    return table.get_by_role("row").filter(
        has=page.get_by_role("rowheader", name=text(f"nutrient.{key}"), exact=True)
    )


def add_product(page: Page, barcode: str, name: str, kcal: str) -> None:
    """Adds a product by hand on the open ingredient and waits until the dialog closes."""
    page.get_by_test_id(TEST_IDS["addProduct"]).click()
    dialog = page.get_by_role("dialog", name=text("ingredients.product.createTitle"))
    form = dialog.get_by_test_id(TEST_IDS["productForm"])
    form.get_by_label(text("ingredients.product.barcode"), exact=True).fill(barcode)
    form.get_by_label(text("ingredients.product.name"), exact=True).fill(name)
    form.get_by_label(text("nutrient.kcal"), exact=True).fill(kcal)
    form.get_by_role("button", name=text("ingredients.product.create")).click()
    expect(dialog).to_be_hidden()


def test_member_builds_up_an_ingredient(member_page: Page) -> None:
    """Create, find by another spelling, similar hint, product average, manual value (ING, NUT)."""
    page = member_page
    tag = unique("e2e")
    name = f"Äpfel {tag}"

    page.goto("/ingredients")
    expect(page.get_by_test_id(TEST_IDS["screenIngredients"])).to_be_visible()
    # "New ingredient", or the empty state's action while there are no ingredients yet.
    create = re.compile(
        f"^({re.escape(text('ingredients.new'))}|{re.escape(text('ingredients.empty.action'))})$"
    )
    page.get_by_role("button", name=create).click()
    dialog = page.get_by_role("dialog", name=text("ingredients.form.createTitle"))
    form = dialog.get_by_test_id(TEST_IDS["ingredientForm"])
    form.get_by_label(text("ingredients.field.name"), exact=True).fill(name)
    form.get_by_label(text("ingredients.field.category"), exact=True).select_option(
        label=text("category.fruit_vegetables")
    )
    form.get_by_label(text("ingredients.field.pieceWeight"), exact=True).fill("180")
    form.get_by_role("button", name=text("ingredients.form.create")).click()

    # The new ingredient opens.
    expect(page).to_have_url(re.compile(r"/ingredients/[\w-]+$"))
    detail = page.get_by_test_id(TEST_IDS["screenIngredient"])
    expect(detail.get_by_role("heading", level=1)).to_have_text(name)
    expect(detail).to_contain_text(text("category.fruit_vegetables"))
    ingredient_url = page.url

    # Search ignores umlaut spellings (ING-03).
    page.get_by_test_id(TEST_IDS["tabIngredients"]).click()
    page.get_by_test_id(TEST_IDS["ingredientSearch"]).fill("aepfel")
    results = page.get_by_test_id(TEST_IDS["ingredientList"])
    expect(results.get_by_role("link", name=re.compile(f"^{re.escape(name)}"))).to_be_visible()

    # Creating "Apfel …" points to the existing "Äpfel …".
    page.get_by_test_id(TEST_IDS["newIngredient"]).click()
    dialog = page.get_by_role("dialog", name=text("ingredients.form.createTitle"))
    dialog.get_by_label(text("ingredients.field.name"), exact=True).fill(f"Apfel {tag}")
    hint = dialog.get_by_test_id(TEST_IDS["ingredientSimilar"])
    expect(hint).to_contain_text(text("ingredients.similar.title"))
    expect(hint.get_by_role("link", name=name)).to_be_visible()
    dialog.get_by_role("button", name=text("common.close")).click()
    expect(dialog).to_be_hidden()

    # Two products with different values: the ingredient shows their average (NUT-02).
    page.goto(ingredient_url)
    add_product(page, new_barcode(), f"Elstar {tag}", "50")
    add_product(page, new_barcode(), f"Boskoop {tag}", "55")
    expect(page.get_by_test_id(TEST_IDS["productRow"])).to_have_count(2)
    kcal = nutrient_row(page, "kcal")
    expect(kcal).to_contain_text("52.5 kcal")
    expect(kcal).to_contain_text(text("ingredients.nutrition.source.products_other", count="2"))

    # A manual value wins; the product average stays visible as a hint.
    page.get_by_test_id(TEST_IDS["editIngredient"]).click()
    dialog = page.get_by_role("dialog", name=text("ingredients.form.editTitle", name=name))
    dialog.get_by_label(text("nutrient.kcal"), exact=True).fill("60")
    dialog.get_by_role("button", name=text("common.save")).click()
    expect(dialog).to_be_hidden()
    expect(kcal).to_contain_text("60 kcal")
    expect(kcal).to_contain_text(text("ingredients.nutrition.source.manual"))
    expect(kcal).to_contain_text(text("ingredients.nutrition.productsHint", value="52.5 kcal"))


def test_admin_reorders_categories(page: Page, api: Api, admin: Account) -> None:
    """REF-01: the new order shows on the Ingredients tab."""
    original = [category["id"] for category in api.categories(admin)]
    first, second = api.categories(admin)[:2]
    tag = unique("e2e")
    api.create_ingredient(admin, f"Order A {tag}", category_key=first["key"])
    api.create_ingredient(admin, f"Order B {tag}", category_key=second["key"])
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

        page.get_by_test_id(TEST_IDS["tabIngredients"]).click()
        page.get_by_test_id(TEST_IDS["ingredientSearch"]).fill(tag)
        headings = page.get_by_test_id(TEST_IDS["ingredientList"]).get_by_role("heading", level=2)
        expect(headings).to_have_text([second_name, first_name])
    finally:
        api.order_categories(admin, original)


def test_admin_merges_a_duplicate(page: Page, api: Api, admin: Account) -> None:
    """ING-05: merging moves the duplicate's products to the ingredient that stays."""
    tag = unique("e2e")
    keep = api.create_ingredient(admin, f"Tomaten {tag}", category_key="fruit_vegetables")
    duplicate = api.create_ingredient(admin, f"Tomate {tag}", category_key="fruit_vegetables")
    product_name = f"Rispentomaten {tag}"
    api.create_product(admin, duplicate["id"], name=product_name, nutrients={"kcal": 18})

    sign_in(page.context, admin)
    page.goto(f"/ingredients/{duplicate['id']}")
    expect(page.get_by_test_id(TEST_IDS["productRow"])).to_contain_text(product_name)
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
    expect(page.get_by_test_id(TEST_IDS["productRow"])).to_contain_text(product_name)

    # The duplicate is gone.
    page.goto(f"/ingredients/{duplicate['id']}")
    expect(page.get_by_role("alert")).to_have_text(text("error.common.not_found"))
