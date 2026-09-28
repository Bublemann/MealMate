"""Meals: create with nutrition and photo, copy, privacy (QA-04 journeys 4, 5 and 9).

MEAL-01..10, NUT-03..05, VIS-01..05, CPL-04 (plan § 12, M4). All tests of a run share one
database, so names get a unique tag.
"""

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from playwright.sync_api import BrowserContext, Locator, Page, expect

from support.api import Account, Api, sign_in, unique
from support.frontend import TEST_IDS, ingredient_label, text
from support.images import png

MEAL_URL = re.compile(r"/meals/([\w-]+)$")


def nutrient_row(page: Page, key: str) -> Locator:
    """The row of nutrient `key` in the nutrition table of the open meal."""
    table = page.get_by_test_id(TEST_IDS["mealNutrition"])
    return table.get_by_role("row").filter(
        has=page.get_by_role("rowheader", name=text(f"nutrient.{key}"), exact=True)
    )


def add_row(
    page: Page, name: str, amount: str = "", unit: str | None = None, *, brand: str | None = None
) -> Locator:
    """Picks ingredient `name` (of `brand`) in the meal form and fills in its amount and unit."""
    label = ingredient_label(name, brand)
    picker = page.get_by_test_id(TEST_IDS["mealForm"]).get_by_test_id(TEST_IDS["ingredientPicker"])
    picker.get_by_label(text("meals.field.addIngredient"), exact=True).fill(name)
    picker.get_by_role("button", name=re.compile(f"^{re.escape(label)}")).click()
    row = page.get_by_role("listitem", name=text("meals.row.label", name=label), exact=True)
    expect(row).to_be_visible()
    if amount:
        row.get_by_label(text("meals.row.amount"), exact=True).fill(amount)
    if unit:
        row.get_by_label(text("meals.row.unit"), exact=True).select_option(
            label=text(f"unit.{unit}")
        )
    return row


def meal_id(page: Page) -> str:
    """The id of the meal the page shows (from `/meals/<id>`)."""
    match = MEAL_URL.search(urlsplit(page.url).path)
    assert match, page.url
    return match[1]


def based_on_text(name: str, owner: str) -> str:
    """The line "Based on <name> by <owner>" as the meal detail renders it."""
    return text("meals.detail.basedOn").replace("<mealLink/>", name).replace("<owner/>", owner)


def soup(api: Api, owner: Account, tag: str) -> dict[str, Any]:
    """A public meal of `owner` with one ingredient row."""
    lentils = api.create_ingredient(owner, f"Linsen {tag}", nutrients={"kcal": 350})
    return api.create_meal(
        owner,
        f"Linsensuppe {tag}",
        servings=4,
        instructions="Linsen kochen.",
        ingredients=[{"ingredient_id": lentils["id"], "amount": 250, "unit": "g"}],
    )


def test_member_creates_a_meal_with_nutrition_and_photo(
    member_page: Page, api: Api, member: Account, base_url: str
) -> None:
    """Journey 4 (MEAL-01..04, NUT-03/04): rows, nutrition per meal and serving, photo."""
    page = member_page
    tag = unique("e2e")
    flour = api.create_ingredient(member, f"Mehl {tag}", nutrients={"kcal": 364})
    # A brand is part of the name wherever the ingredient shows.
    milk = api.create_ingredient(
        member,
        f"Milch {tag}",
        brand="Weidehof",
        category_key="dairy_eggs",
        base_unit="ml",
        nutrients={"kcal": 64},
    )
    eggs = api.create_ingredient(
        member, f"Eier {tag}", category_key="dairy_eggs", piece_weight_g=60, nutrients={"kcal": 155}
    )
    salt = api.create_ingredient(member, f"Salz {tag}")
    name = f"Pfannkuchen {tag}"

    page.goto("/meals")
    expect(page.get_by_test_id(TEST_IDS["screenMeals"])).to_be_visible()
    # "New meal", or the empty state's action while the member sees no meals yet.
    create = re.compile(
        f"^({re.escape(text('meals.new'))}|{re.escape(text('meals.empty.action'))})$"
    )
    page.get_by_role("button", name=create).click()
    expect(page).to_have_url(re.compile(r"/meals/new$"))

    form = page.get_by_test_id(TEST_IDS["mealForm"])
    form.get_by_label(text("meals.field.name"), exact=True).fill(name)
    form.get_by_role("button", name=text("meals.field.servingsMore"), exact=True).click()
    expect(form.get_by_label(text("meals.field.servings"), exact=True)).to_have_value("2")
    add_row(page, flour["name"], "200", "g")
    add_row(page, milk["name"], "300", "ml", brand="Weidehof")
    add_row(page, eggs["name"], "2", "piece")
    salt_row = add_row(page, salt["name"])
    salt_row.get_by_label(text("meals.row.note"), exact=True).fill("to taste")
    form.get_by_label(text("meals.field.instructions"), exact=True).fill(
        "Alles verrühren.\nIn der Pfanne backen."
    )
    form.get_by_test_id(TEST_IDS["mealPhotoInput"]).set_input_files(
        files=[{"name": "pfannkuchen.png", "mimeType": "image/png", "buffer": png(320, 240)}]
    )
    form.get_by_role("button", name=text("meals.form.create"), exact=True).click()

    # The new meal opens.
    expect(page).to_have_url(MEAL_URL)
    detail = page.get_by_test_id(TEST_IDS["screenMeal"])
    expect(detail.get_by_role("heading", level=1)).to_have_text(name)
    ingredients = page.get_by_test_id(TEST_IDS["mealIngredients"])
    expect(ingredients.get_by_role("listitem")).to_have_count(4)
    expect(
        ingredients.get_by_role("link", name=ingredient_label(milk["name"], "Weidehof"))
    ).to_have_attribute("href", f"/ingredients/{milk['id']}")
    expect(page.get_by_test_id(TEST_IDS["mealInstructions"])).to_have_text(
        "Alles verrühren.\nIn der Pfanne backen."
    )

    # 200 g * 364/100 + 300 ml * 64/100 + 2 * 60 g * 155/100 = 728 + 192 + 186 = 1106 kcal.
    kcal = nutrient_row(page, "kcal")
    expect(kcal).to_contain_text("1,106 kcal")
    expect(kcal).to_contain_text("553 kcal")
    incomplete = page.get_by_test_id(TEST_IDS["mealIncomplete"])
    expect(incomplete).to_contain_text(text("meals.nutrition.reason.no_amount", name=salt["name"]))

    # The photo is shown, loads, and comes from the app's own origin (signed URL, VIS-05).
    photo = page.get_by_test_id(TEST_IDS["mealPhoto"])
    expect(photo).to_be_visible()
    expect(photo).to_have_accessible_name(name)
    page.wait_for_function(
        "img => img.complete && img.naturalWidth > 0", arg=photo.element_handle()
    )
    source = urlsplit(photo.evaluate("img => img.currentSrc"))
    origin = urlsplit(base_url)
    assert (source.scheme, source.netloc) == (origin.scheme, origin.netloc)
    assert source.path.startswith("/api/media/")


def test_copy_someone_elses_meal(page: Page, api: Api, invite_user: Callable[..., Account]) -> None:
    """Journey 5 (MEAL-07, MEAL-08, VIS-04): copy a public meal, edit the copy only."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"))
    ben = invite_user(unique("ben"), unique("Ben"))
    original = soup(api, anna, tag)

    sign_in(page.context, ben)
    page.goto(f"/meals/{original['id']}")
    detail = page.get_by_test_id(TEST_IDS["screenMeal"])
    expect(detail.get_by_role("heading", level=1)).to_have_text(original["name"])
    expect(detail).to_contain_text(text("meals.detail.by", name=anna.display_name))
    # Only the owner edits or deletes (VIS-04).
    expect(page.get_by_test_id(TEST_IDS["copyMeal"])).to_be_visible()
    expect(page.get_by_test_id(TEST_IDS["editMeal"])).to_have_count(0)
    expect(page.get_by_test_id(TEST_IDS["deleteMeal"])).to_have_count(0)

    page.get_by_test_id(TEST_IDS["copyMeal"]).click()

    # Ben lands on his own copy, which remembers the original.
    expect(page).not_to_have_url(re.compile(f"/meals/{original['id']}$"))
    expect(page).to_have_url(MEAL_URL)
    expect(page.get_by_test_id(TEST_IDS["mealBasedOn"])).to_have_text(
        based_on_text(original["name"], anna.display_name)
    )
    expect(page.get_by_test_id(TEST_IDS["mealIngredients"])).to_contain_text(f"Linsen {tag}")
    copy_id = meal_id(page)

    # Ben edits his copy.
    page.get_by_test_id(TEST_IDS["editMeal"]).click()
    expect(page).to_have_url(re.compile(f"/meals/{copy_id}/edit$"))
    form = page.get_by_test_id(TEST_IDS["mealForm"])
    renamed = f"Bens Suppe {tag}"
    name = form.get_by_label(text("meals.field.name"), exact=True)
    expect(name).to_have_value(original["name"])
    name.fill(renamed)
    form.get_by_role("button", name=text("common.save"), exact=True).click()
    expect(page).to_have_url(re.compile(f"/meals/{copy_id}$"))
    expect(detail.get_by_role("heading", level=1)).to_have_text(renamed)

    # Anna's meal is unchanged, and Ben still can't edit it.
    page.goto(f"/meals/{original['id']}")
    expect(detail.get_by_role("heading", level=1)).to_have_text(original["name"])
    expect(page.get_by_test_id(TEST_IDS["copyMeal"])).to_be_visible()
    expect(page.get_by_test_id(TEST_IDS["editMeal"])).to_have_count(0)


def test_private_meals_are_hidden_except_from_the_partner(
    page: Page,
    api: Api,
    new_context: Callable[..., BrowserContext],
    invite_user: Callable[..., Account],
    make_couple: Callable[[Account, Account], None],
) -> None:
    """Journey 9 (VIS-02, CPL-04, MEAL-10): "meals public" off hides meals and chip."""
    tag = unique("e2e")
    anna = invite_user(unique("anna"), unique("Anna"))
    partner = invite_user(unique("paul"), unique("Paul"))
    carl = invite_user(unique("carl"), unique("Carl"))
    make_couple(anna, partner)
    meal = soup(api, anna, tag)
    # Carl's own meal: his list is never empty, whatever other tests left in the database.
    own = api.create_meal(carl, f"Eintopf {tag}")

    # Carl sees Anna's meal and her chip.
    sign_in(page.context, carl)
    page.goto("/meals")
    chips = page.get_by_test_id(TEST_IDS["mealUserChips"])
    expect(chips.get_by_role("button", name=anna.display_name, exact=True)).to_be_visible()
    page.get_by_test_id(TEST_IDS["mealSearch"]).fill(tag)
    cards = page.get_by_test_id(TEST_IDS["mealList"]).get_by_test_id(TEST_IDS["mealCard"])
    expect(cards).to_have_count(2)
    expect(cards.filter(has_text=meal["name"])).to_have_count(1)

    # Anna switches "meals public" off on Me, on her own device.
    anna_context = new_context()
    sign_in(anna_context, anna)
    anna_page = anna_context.new_page()
    anna_page.goto("/me")
    switch = anna_page.get_by_test_id(TEST_IDS["mealsPublicSwitch"])
    expect(switch).to_be_checked()
    switch.click()
    expect(switch).not_to_be_checked()
    expect(switch).to_be_enabled()

    # Carl no longer sees the meal, the chip or the meal's page.
    page.reload()
    expect(page.get_by_test_id(TEST_IDS["screenMeals"])).to_be_visible()
    expect(chips.get_by_role("button", name=text("meals.chips.me"), exact=True)).to_be_visible()
    expect(chips.get_by_role("button", name=anna.display_name, exact=True)).to_have_count(0)
    page.get_by_test_id(TEST_IDS["mealSearch"]).fill(tag)
    expect(cards).to_have_count(1)
    expect(cards).to_contain_text(own["name"])
    page.goto(f"/meals/{meal['id']}")
    expect(page.get_by_role("alert")).to_have_text(text("error.common.not_found"))

    # Her partner still sees it (CPL-04).
    partner_context = new_context()
    sign_in(partner_context, partner)
    partner_page = partner_context.new_page()
    partner_page.goto(f"/meals/{meal['id']}")
    partner_detail = partner_page.get_by_test_id(TEST_IDS["screenMeal"])
    expect(partner_detail.get_by_role("heading", level=1)).to_have_text(meal["name"])
    partner_page.goto("/meals")
    partner_chips = partner_page.get_by_test_id(TEST_IDS["mealUserChips"])
    expect(partner_chips.get_by_role("button", name=anna.display_name, exact=True)).to_be_visible()
