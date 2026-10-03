"""Barcodes: typed into the scanner, looked up at Open Food Facts, saved (QA-04 journey 3).

BAR-01..04, BAR-08..09, BAR-11, MEAL-03, SEC-08 (plan § 12, M7). Scanning happens inside "Neue
Zutat" and from the meal form's "Barcode scannen" (D-36, D-37); there is no scan page. A product
can also be found by name. The camera can't be used in CI, so barcodes are typed into the
scanner's manual input, which is always there (BAR-01). The app asks the fake Open Food Facts in
fake_off/ that conftest serves to the container (`fake_off_app`).
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


def open_new_ingredient(page: Page) -> Locator:
    """Opens "New ingredient" from the Ingredients tab's tile."""
    page.goto("/ingredients")
    page.get_by_test_id(TEST_IDS["newIngredient"]).click()
    return page.get_by_role("dialog", name=text("ingredients.form.createTitle"))


def type_into_scanner(page: Page, barcode: str) -> None:
    """Types `barcode` into the open scanner's manual input; the scanner closes."""
    scanner = page.get_by_test_id(TEST_IDS["barcodeScanDialog"])
    scanner.get_by_test_id(TEST_IDS["barcodeInput"]).fill(barcode)
    scanner.get_by_test_id(TEST_IDS["barcodeLookup"]).click()
    expect(scanner).to_be_hidden()


def scan_in(page: Page, dialog: Locator, barcode: str) -> None:
    """Taps the scan icon of the ingredient pop-up `dialog` and types `barcode` into the scanner."""
    dialog.get_by_test_id(TEST_IDS["ingredientFormScan"]).click()
    type_into_scanner(page, barcode)


def field(container: Locator, key: str) -> Locator:
    """The ingredient form's field labelled `ingredients.field.<key>`."""
    return container.get_by_label(text(f"ingredients.field.{key}"), exact=True)


def expect_attribution(container: Locator) -> None:
    """BAR-09: "Nutrition data: Open Food Facts (ODbL)" with a safe link."""
    attribution = container.get_by_test_id(TEST_IDS["offAttribution"])
    expect(attribution).to_contain_text("(ODbL)")
    link = attribution.get_by_role("link", name=re.compile(r"^Open Food Facts"))
    expect(link).to_have_attribute("href", OPEN_FOOD_FACTS_URL)
    expect(link).to_have_attribute("rel", "noopener noreferrer")
    expect(link).to_have_attribute("target", "_blank")


def test_member_creates_an_ingredient_by_scanning_in_new_ingredient(
    fake_off_app: AppContainer,
    member_page: Page,
    member: Account,
    api: Api,
    base_url: str,
    browser_name: str,
) -> None:
    """Journey 3 inside "New ingredient" from the Ingredients tile (D-36): a product Open Food
    Facts knows fills the form for one Save; scanned again, its barcode is named as known; a
    barcode nobody knows fills in only the barcode, and "Add the barcode to X" gives it to an
    ingredient typed by hand before."""
    page = member_page
    product = product_for(browser_name)
    requested: list[str] = []

    def record(request: Request) -> None:
        requested.append(request.url)

    # Context-wide, so requests of the service worker count as well.
    page.context.on("request", record)

    # BAR-01: the scan icon opens the scanner; without a camera, the digits are typed. Without
    # a camera the decoder isn't loaded (see test_the_decoder_is_the_apps_own_file).
    dialog = open_new_ingredient(page)
    dialog.get_by_test_id(TEST_IDS["ingredientFormScan"]).click()
    expect(page.get_by_test_id(TEST_IDS["scannerCameraMessage"])).to_be_visible()
    type_into_scanner(page, product.barcode)

    # BAR-03: filled like a chosen search result, with the attribution; the barcode read-only.
    form = dialog.get_by_test_id(TEST_IDS["ingredientForm"])
    name = field(form, "name")
    expect(name).to_have_value(product.name)
    expect(field(form, "brand")).to_have_value(product.brand)
    [category_id] = [
        category["id"]
        for category in api.categories(member)
        if category["key"] == product.category_key
    ]
    expect(field(form, "category")).to_have_value(category_id)
    unit = form.get_by_role("radio", name=text(f"ingredients.baseUnit.{product.base_unit}"))
    expect(unit).to_be_checked()
    expect(form.get_by_label(text("nutrient.kcal"), exact=True)).to_have_value(
        product.kcal.removesuffix(" kcal")
    )
    barcode = field(form, "barcode")
    expect(barcode).to_have_value(product.barcode)
    expect(barcode).to_have_attribute("readonly", "")
    expect_attribution(form)
    # Everything else can be corrected before the one Save (all tests of a run share one
    # database).
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

    # BAR-02: scanned again, the pop-up stays open, names the ingredient and fills in nothing;
    # "open" leads to it.
    dialog = open_new_ingredient(page)
    scan_in(page, dialog, product.barcode)
    notice = dialog.get_by_test_id(TEST_IDS["ingredientScanNotice"])
    expect(notice).to_contain_text(text("ingredients.scan.known", name=label))
    expect(field(dialog, "barcode")).to_have_value("")
    notice.get_by_test_id(TEST_IDS["ingredientScanOpen"]).click()
    expect(page).to_have_url(ingredient_url)
    expect(dialog).to_be_hidden()

    # Unknown to Open Food Facts: only the barcode, with a notice below it. Typed by hand
    # before, the package's ingredient gets it through the similar-ingredients hint (BAR-03,
    # D-36). Each lookup asks Open Food Facts, which the app allows only a few times a minute
    # (BAR-08): one miss serves both.
    oats = api.create_ingredient(member, unique("Haferflocken"))
    unknown = new_barcode()
    dialog = open_new_ingredient(page)
    field(dialog, "name").fill(oats["name"])
    hint = dialog.get_by_test_id(TEST_IDS["ingredientSimilar"])
    # Before a scan, the match is only a link.
    expect(hint.get_by_role("link", name=oats["name"], exact=True)).to_be_visible()
    scan_in(page, dialog, unknown)
    expect(dialog.get_by_test_id(TEST_IDS["ingredientScanNotice"])).to_have_text(
        text("ingredients.scan.notFound")
    )
    form = dialog.get_by_test_id(TEST_IDS["ingredientForm"])
    expect(field(form, "barcode")).to_have_value(unknown)
    expect(field(form, "barcode")).not_to_have_attribute("readonly", "")
    expect(form.get_by_test_id(TEST_IDS["offAttribution"])).to_have_count(0)
    hint.get_by_role("button", name=text("ingredients.similar.attach", name=oats["name"])).click()

    expect(page).to_have_url(re.compile(rf"/ingredients/{oats['id']}$"))
    expect(dialog).to_be_hidden()
    detail = page.get_by_test_id(TEST_IDS["screenIngredient"])
    expect(detail.get_by_role("heading", level=1)).to_have_text(oats["name"])
    expect(detail).to_contain_text(unknown)
    expect(detail).to_contain_text(text("ingredients.detail.source.manual"))

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
    camera, which the scan icon in "New ingredient" starts. Only run in Chromium: the other
    engines' stream and wasm handling is covered by the manual iPhone check (QA-06)."""
    if browser_name != "chromium":
        pytest.skip("the canvas camera is only exercised in Chromium")
    page = member_page
    requested: list[str] = []
    page.on("request", lambda request: requested.append(request.url))
    page.add_init_script(FAKE_CAMERA)

    dialog = open_new_ingredient(page)
    with page.expect_response(re.compile(r"/assets/zxing_reader-[\w-]+\.wasm$")) as wasm:
        dialog.get_by_test_id(TEST_IDS["ingredientFormScan"]).click()

    expect(page.get_by_test_id(TEST_IDS["scannerVideo"])).to_be_visible()
    assert wasm.value.ok
    assert wasm.value.header_value("content-type") == "application/wasm"
    assert urlsplit(wasm.value.url).netloc == urlsplit(base_url).netloc
    # The manual input stays next to the camera (BAR-01).
    expect(page.get_by_test_id(TEST_IDS["barcodeInput"])).to_be_visible()
    assert foreign_requests(requested, base_url) == []


def test_scanning_in_the_meal_form_adds_the_ingredient(
    fake_off_app: AppContainer, member_page: Page, member: Account, api: Api
) -> None:
    """BAR-01, BAR-02, MEAL-03: the meal form's "Scan barcode" adds a known barcode's row at once;
    a new barcode opens "New ingredient", filled as after a scan inside it, whose Save adds the
    row."""
    page = member_page
    known = api.create_ingredient(
        member, unique("Scanned"), brand=unique("Brand"), barcode=new_barcode()
    )

    page.goto("/meals/new")
    form = page.get_by_test_id(TEST_IDS["mealForm"])
    meal_name = form.get_by_label(text("meals.field.name"), exact=True)
    meal_name.fill(unique("Scan meal"))
    form.get_by_test_id(TEST_IDS["scanBarcode"]).click()
    type_into_scanner(page, known["barcode"])

    rows = form.get_by_test_id(TEST_IDS["mealIngredientRow"])
    expect(rows).to_have_count(1)
    expect(rows).to_have_accessible_name(
        text("meals.row.label", name=ingredient_label(known["name"], known["brand"]))
    )
    expect(page.get_by_role("dialog")).to_have_count(0)

    # A barcode nobody knows: "New ingredient" with the barcode and Open Food Facts' answer;
    # one Save adds a second row.
    unknown = new_barcode()
    form.get_by_test_id(TEST_IDS["scanBarcode"]).click()
    type_into_scanner(page, unknown)
    dialog = page.get_by_role("dialog", name=text("ingredients.form.createTitle"))
    expect(dialog.get_by_test_id(TEST_IDS["ingredientScanNotice"])).to_have_text(
        text("ingredients.scan.notFound")
    )
    expect(field(dialog, "barcode")).to_have_value(unknown)
    new_name = unique("Scanned new")
    field(dialog, "name").fill(new_name)
    dialog.get_by_role("button", name=text("common.save")).click()

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

    # The magnifier searches the name typed so far at once (BAR-11).
    search = page.get_by_test_id(TEST_IDS["offSearchDialog"])
    field = search.get_by_label(text("ingredients.offSearch.label"), exact=True)
    expect(field).to_have_value(product.query)
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
    dialog = open_new_ingredient(page)
    dialog.get_by_test_id(TEST_IDS["offSearchButton"]).click()
    # Without a name, the search starts empty.
    search = page.get_by_test_id(TEST_IDS["offSearchDialog"])
    expect(search.get_by_label(text("ingredients.offSearch.label"), exact=True)).to_have_value("")
    search.get_by_label(text("ingredients.offSearch.label"), exact=True).fill(product.query)
    search.get_by_test_id(TEST_IDS["offSearchSubmit"]).click()
    known = search.get_by_test_id(TEST_IDS["offSearchResult"]).filter(has_text=f"({product.brand})")
    expect(known).to_contain_text(text("ingredients.offSearch.inMealMate"))
    known.click()
    expect(page).to_have_url(re.compile(r"/ingredients/[\w-]+$"))
    expect(page.get_by_role("heading", level=1)).to_have_text(label)
