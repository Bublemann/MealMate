"""Barcodes: typed into the scanner, looked up at Open Food Facts, saved (QA-04 journey 3).

BAR-01..04, BAR-08..09, SEC-08 (plan § 12, M7). A scanned product opens the ingredient form, and
a product can also be found by name. The camera can't be used in CI, so barcodes are typed into
the scanner's manual input, which is always there (BAR-01). The app asks the fake Open Food Facts
in fake_off/ that conftest serves to the container (`fake_off_app`).
"""

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Locator, Page, Request, expect

from support.api import Account, Api, new_barcode, unique
from support.container import AppContainer
from support.frontend import TEST_IDS, ingredient_label, text

LOCAL_SCHEMES = frozenset({"data", "blob"})
OPEN_FOOD_FACTS_URL = "https://world.openfoodfacts.org"


@dataclass(frozen=True)
class OffProduct:
    """A product of fake_off/fixtures as the app shows it to an English-speaking user."""

    barcode: str
    name: str
    brand: str
    kcal: str
    category_key: str
    base_unit: str


# Saving a product puts its barcode into the database, where the next lookup finds it (BAR-02):
# each browser gets its own product, so that all of them can run against one container.
PRODUCTS = {
    "chromium": OffProduct(
        barcode="2000000000022",
        name="Frische Vollmilch 3,5 %",
        brand="Hof Sonnenschein",
        kcal="64 kcal",
        category_key="dairy_eggs",
        base_unit="ml",
    ),
    "webkit": OffProduct(
        barcode="2000000000015",
        name="Rolled Oats",
        brand="MealMate Test Kitchen",
        kcal="372 kcal",
        category_key="breakfast_spreads",
        base_unit="g",
    ),
    "firefox": OffProduct(
        barcode="2000000000077",
        name="Young Gouda",
        brand="Käserei Testhof",
        kcal="356 kcal",
        category_key="cheese",
        base_unit="g",
    ),
}


def product_for(browser_name: str) -> OffProduct:
    """The browser's own fixture product; another browser's would already be saved."""
    product = PRODUCTS.get(browser_name)
    if product is None:
        pytest.fail(
            f"no fake Open Food Facts product for {browser_name!r}: add a fixture to fake_off/ "
            "and an entry to PRODUCTS (each browser needs its own barcode)"
        )
    return product


def test_each_browser_has_its_own_product() -> None:
    assert len({product.barcode for product in PRODUCTS.values()}) == len(PRODUCTS)
    assert product_for("firefox") is not product_for("chromium")
    with pytest.raises(pytest.fail.Exception, match="no fake Open Food Facts product for 'opera'"):
        product_for("opera")


def look_up(page: Page, barcode: str) -> None:
    """Types `barcode` into the scanner's manual input (the page must show /scan)."""
    scanner = page.get_by_test_id(TEST_IDS["screenScan"])
    scanner.get_by_test_id(TEST_IDS["barcodeInput"]).fill(barcode)
    scanner.get_by_test_id(TEST_IDS["barcodeLookup"]).click()


def expect_attribution(container: Locator) -> None:
    """BAR-09: "Nutrition data: Open Food Facts (ODbL)" with a safe link."""
    attribution = container.get_by_test_id(TEST_IDS["offAttribution"])
    expect(attribution).to_contain_text("(ODbL)")
    link = attribution.get_by_role("link", name=re.compile(r"^Open Food Facts"))
    expect(link).to_have_attribute("href", OPEN_FOOD_FACTS_URL)
    expect(link).to_have_attribute("rel", "noopener noreferrer")
    expect(link).to_have_attribute("target", "_blank")


def test_member_creates_an_ingredient_from_a_typed_barcode(
    fake_off_app: AppContainer,
    member_page: Page,
    member: Account,
    api: Api,
    base_url: str,
    browser_name: str,
) -> None:
    """Journey 3: proposal → prefilled ingredient form → one Save; known and unknown barcodes;
    the scanned ingredient in a meal row."""
    page = member_page
    product = product_for(browser_name)
    requested: list[str] = []

    def record(request: Request) -> None:
        requested.append(request.url)

    # Context-wide, so requests of the service worker count as well.
    page.context.on("request", record)

    # BAR-01: no tab links to the scanner for now, but its address still opens it. Without a
    # camera the decoder isn't loaded (see test_the_decoder_is_the_apps_own_file).
    page.goto("/scan")
    expect(page.get_by_test_id(TEST_IDS["scannerCameraMessage"])).to_be_visible()

    # BAR-03: the ingredient form opens, filled with the proposal, with the attribution.
    look_up(page, product.barcode)
    scan = page.get_by_test_id(TEST_IDS["screenScan"])
    expect(scan.get_by_role("heading", name=text("scanner.form.titleFound"))).to_be_visible()
    form = scan.get_by_test_id(TEST_IDS["ingredientForm"])
    name = form.get_by_label(text("ingredients.field.name"), exact=True)
    expect(name).to_have_value(product.name)
    expect(form.get_by_label(text("ingredients.field.brand"), exact=True)).to_have_value(
        product.brand
    )
    [category_id] = [
        category["id"]
        for category in api.categories(member)
        if category["key"] == product.category_key
    ]
    expect(form.get_by_label(text("ingredients.field.category"), exact=True)).to_have_value(
        category_id
    )
    unit = form.get_by_role("radio", name=text(f"ingredients.baseUnit.{product.base_unit}"))
    expect(unit).to_be_checked()
    expect(form.get_by_label(text("nutrient.kcal"), exact=True)).to_have_value(
        product.kcal.removesuffix(" kcal")
    )
    barcode = form.get_by_label(text("ingredients.field.barcode"), exact=True)
    expect(barcode).to_have_value(product.barcode)
    expect_attribution(form)
    # Everything can be corrected before the one Save (all tests of a run share one database).
    ingredient_name = f"{product.name} {unique('e2e')}"
    name.fill(ingredient_name)
    form.get_by_role("button", name=text("common.save")).click()

    # The new ingredient opens, with its brand, barcode and attribution.
    expect(page).to_have_url(re.compile(r"/ingredients/[\w-]+$"))
    ingredient_url = page.url
    label = ingredient_label(ingredient_name, product.brand)
    detail = page.get_by_test_id(TEST_IDS["screenIngredient"])
    expect(detail.get_by_role("heading", level=1)).to_have_text(label)
    expect(detail).to_contain_text(product.barcode)
    expect(detail).to_contain_text(text("ingredients.detail.source.off"))
    expect(page.get_by_test_id(TEST_IDS["ingredientNutrition"])).to_contain_text(product.kcal)
    expect_attribution(detail)

    # BAR-02: the same barcode again goes straight to its ingredient.
    page.goto("/scan")
    look_up(page, product.barcode)
    expect(page).to_have_url(ingredient_url)

    # Unknown to Open Food Facts: "not found", and the same form with only the barcode.
    unknown = new_barcode()
    page.goto("/scan")
    look_up(page, unknown)
    expect(page.get_by_test_id(TEST_IDS["scanNotice"])).to_have_text(
        text("scanner.notFound", barcode=unknown)
    )
    form = page.get_by_test_id(TEST_IDS["ingredientForm"])
    expect(form.get_by_label(text("ingredients.field.barcode"), exact=True)).to_have_value(unknown)
    expect(form.get_by_test_id(TEST_IDS["offAttribution"])).to_have_count(0)
    manual_name = unique("By hand")
    form.get_by_label(text("ingredients.field.name"), exact=True).fill(manual_name)
    form.get_by_label(text("nutrient.kcal"), exact=True).fill("60")
    form.get_by_role("button", name=text("common.save")).click()
    expect(page.get_by_role("heading", level=1)).to_have_text(manual_name)
    detail = page.get_by_test_id(TEST_IDS["screenIngredient"])
    expect(detail).to_contain_text(unknown)
    expect(detail).to_contain_text(text("ingredients.detail.source.manual"))
    expect(detail.get_by_test_id(TEST_IDS["offAttribution"])).to_have_count(0)

    # The scanned ingredient in a meal: the meal form's scan adds it as a row (MEAL-03).
    page.goto("/meals/new")
    meal_form = page.get_by_test_id(TEST_IDS["mealForm"])
    meal_form.get_by_test_id(TEST_IDS["scanBarcode"]).click()
    dialog = page.get_by_test_id(TEST_IDS["scanDialog"])
    dialog.get_by_test_id(TEST_IDS["barcodeInput"]).fill(product.barcode)
    dialog.get_by_test_id(TEST_IDS["barcodeLookup"]).click()
    expect(dialog).to_be_hidden()
    row = meal_form.get_by_test_id(TEST_IDS["mealIngredientRow"])
    expect(row).to_have_accessible_name(text("meals.row.label", name=label))

    # SEC-08: only the server talks to Open Food Facts.
    assert requested
    assert foreign_requests(requested, base_url) == []


def foreign_requests(urls: list[str], base_url: str) -> list[str]:
    """The URLs that are neither the app's origin nor local (data:, blob:)."""
    origin = urlsplit(base_url)
    return [
        url
        for url in urls
        if (parts := urlsplit(url)).scheme not in LOCAL_SCHEMES
        and (parts.scheme, parts.netloc) != (origin.scheme, origin.netloc)
    ]


# A camera for the test: a canvas stream stands in for getUserMedia, so no fake-device support
# of the browser build is needed (the headless shell used in CI has none that works here).
FAKE_CAMERA = """
navigator.mediaDevices.getUserMedia = async () => {
  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 480;
  const context = canvas.getContext('2d');
  setInterval(() => {
    context.fillStyle = '#ffffff';
    context.fillRect(0, 0, canvas.width, canvas.height);
  }, 100);
  return canvas.captureStream(10);
};
"""


def test_the_decoder_is_the_apps_own_file(
    member_page: Page, browser_name: str, base_url: str
) -> None:
    """SEC-08, BAR-01: once the camera runs, the decoder's wasm comes from the app, no CDN.

    The decoder is loaded only with a camera stream, so the page gets a canvas stream as its
    camera. Only run in Chromium: the other engines' stream and wasm handling is covered by the
    manual iPhone check (QA-06)."""
    if browser_name != "chromium":
        pytest.skip("the canvas camera is only exercised in Chromium")
    page = member_page
    requested: list[str] = []
    page.on("request", lambda request: requested.append(request.url))
    page.add_init_script(FAKE_CAMERA)

    with page.expect_response(re.compile(r"/assets/zxing_reader-[\w-]+\.wasm$")) as wasm:
        page.goto("/scan")

    expect(page.get_by_test_id(TEST_IDS["scannerVideo"])).to_be_visible()
    assert wasm.value.ok
    assert wasm.value.header_value("content-type") == "application/wasm"
    assert urlsplit(wasm.value.url).netloc == urlsplit(base_url).netloc
    # The manual input stays next to the camera (BAR-01).
    expect(page.get_by_test_id(TEST_IDS["barcodeInput"])).to_be_visible()
    assert foreign_requests(requested, base_url) == []


def test_scanning_in_the_meal_form_adds_the_ingredient(
    member_page: Page, member: Account, api: Api
) -> None:
    """BAR-01, MEAL-03: the picker's scan button adds a known barcode's ingredient as a row, and
    a new barcode's ingredient once its form (inside the scan dialog) is saved."""
    page = member_page
    known = api.create_ingredient(
        member, unique("Scanned"), brand=unique("Brand"), barcode=new_barcode()
    )

    page.goto("/meals/new")
    form = page.get_by_test_id(TEST_IDS["mealForm"])
    meal_name = form.get_by_label(text("meals.field.name"), exact=True)
    meal_name.fill(unique("Scan meal"))
    form.get_by_test_id(TEST_IDS["scanBarcode"]).click()
    dialog = page.get_by_test_id(TEST_IDS["scanDialog"])
    dialog.get_by_test_id(TEST_IDS["barcodeInput"]).fill(known["barcode"])
    dialog.get_by_test_id(TEST_IDS["barcodeLookup"]).click()

    expect(dialog).to_be_hidden()
    rows = form.get_by_test_id(TEST_IDS["mealIngredientRow"])
    expect(rows).to_have_count(1)
    expect(rows).to_have_accessible_name(
        text("meals.row.label", name=ingredient_label(known["name"], known["brand"]))
    )

    # A barcode nobody knows: the ingredient form in the dialog, one Save, a second row.
    form.get_by_test_id(TEST_IDS["scanBarcode"]).click()
    dialog.get_by_test_id(TEST_IDS["barcodeInput"]).fill(new_barcode())
    dialog.get_by_test_id(TEST_IDS["barcodeLookup"]).click()
    new_form = dialog.get_by_test_id(TEST_IDS["ingredientForm"])
    new_name = unique("Scanned new")
    new_form.get_by_label(text("ingredients.field.name"), exact=True).fill(new_name)
    new_form.get_by_role("button", name=text("common.save")).click()

    expect(dialog).to_be_hidden()
    expect(rows).to_have_count(2)
    expect(rows.nth(1)).to_have_accessible_name(text("meals.row.label", name=new_name))
    # Saving the ingredient didn't save the meal.
    expect(page).to_have_url(re.compile(r"/meals/new$"))
    expect(meal_name).to_be_visible()


@dataclass(frozen=True)
class SearchedProduct:
    """A product of fake_off/fixtures found by the name search, told apart by its brand."""

    query: str
    brand: str
    barcode: str


# Saving a found product puts its barcode into the database: each browser picks its own.
SEARCHED = {
    "chromium": SearchedProduct("spaghetti", "Pastificio Testa", "2000000000084"),
    "webkit": SearchedProduct("spaghetti", "Nudelwerk Muster", "2000000000091"),
    "firefox": SearchedProduct("tomaten", "Hof Sonnenschein", "2000000000107"),
}


def test_member_finds_a_product_by_name(
    fake_off_app: AppContainer, member_page: Page, browser_name: str
) -> None:
    """Search Open Food Facts by name (only on request, BAR-08) → pick → Save → a meal row;
    searching again shows the product as already in MealMate."""
    page = member_page
    product = SEARCHED.get(browser_name)
    if product is None:
        pytest.fail(f"no searched product for {browser_name!r}: add one to SEARCHED")

    # The meal form's picker creates the ingredient with the same form as everywhere.
    page.goto("/meals/new")
    meal_form = page.get_by_test_id(TEST_IDS["mealForm"])
    meal_form.get_by_label(text("meals.field.name"), exact=True).fill(unique("Pasta"))
    picker = meal_form.get_by_test_id(TEST_IDS["ingredientPicker"])
    picker.get_by_label(text("meals.field.addIngredient"), exact=True).fill(product.query)
    picker.get_by_test_id(TEST_IDS["ingredientPickerCreate"]).click()
    dialog = page.get_by_role("dialog", name=text("ingredients.form.createTitle"))
    dialog.get_by_test_id(TEST_IDS["offSearchButton"]).click()

    search = page.get_by_test_id(TEST_IDS["offSearchDialog"])
    field = search.get_by_label(text("ingredients.offSearch.label"), exact=True)
    expect(field).to_have_value(product.query)
    field.press("Enter")
    results = search.get_by_test_id(TEST_IDS["offSearchResult"])
    ours = results.filter(has_text=f"({product.brand})")
    expect(ours).to_have_count(1)
    expect(ours).to_contain_text("kcal")
    expect_attribution(search)
    ours.click()
    expect(search).to_be_hidden()

    # The form is filled like a scanned product, barcode included; one Save.
    form = dialog.get_by_test_id(TEST_IDS["ingredientForm"])
    expect(form.get_by_label(text("ingredients.field.brand"), exact=True)).to_have_value(
        product.brand
    )
    expect(form.get_by_label(text("ingredients.field.barcode"), exact=True)).to_have_value(
        product.barcode
    )
    expect_attribution(form)
    name = form.get_by_label(text("ingredients.field.name"), exact=True).input_value()
    assert name
    form.get_by_role("button", name=text("common.save")).click()
    expect(dialog).to_be_hidden()

    # It is the meal's new row.
    label = ingredient_label(name, product.brand)
    row = meal_form.get_by_test_id(TEST_IDS["mealIngredientRow"])
    expect(row).to_have_count(1)
    expect(row).to_have_accessible_name(text("meals.row.label", name=label))

    # Searched again from the Ingredients tab, it is already in MealMate and opens.
    page.goto("/ingredients")
    page.get_by_test_id(TEST_IDS["newIngredient"]).click()
    dialog = page.get_by_role("dialog", name=text("ingredients.form.createTitle"))
    dialog.get_by_test_id(TEST_IDS["offSearchButton"]).click()
    search = page.get_by_test_id(TEST_IDS["offSearchDialog"])
    search.get_by_label(text("ingredients.offSearch.label"), exact=True).fill(product.query)
    search.get_by_test_id(TEST_IDS["offSearchSubmit"]).click()
    known = search.get_by_test_id(TEST_IDS["offSearchResult"]).filter(has_text=f"({product.brand})")
    expect(known).to_contain_text(text("ingredients.offSearch.inMealMate"))
    known.click()
    expect(page).to_have_url(re.compile(r"/ingredients/[\w-]+$"))
    expect(page.get_by_role("heading", level=1)).to_have_text(label)
