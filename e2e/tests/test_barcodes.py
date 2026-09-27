"""Barcodes: typed into the scanner, looked up at Open Food Facts, saved (QA-04 journey 3).

BAR-01..04, BAR-09, SEC-08 (plan § 12, M7). The camera can't be used in CI, so barcodes are typed
into the scanner's manual input, which is always there (BAR-01). The app asks the fake Open Food
Facts in fake_off/ that conftest serves to the container (`fake_off_app`).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Locator, Page, Request, expect

from support.api import Account, Api, new_barcode, sign_in, unique
from support.container import AppContainer
from support.frontend import TEST_IDS, text

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
    """Journey 3: proposal → new ingredient → saved product; known and unknown barcodes."""
    page = member_page
    product = product_for(browser_name)
    requested: list[str] = []

    def record(request: Request) -> None:
        requested.append(request.url)

    # Context-wide, so requests of the service worker count as well.
    page.context.on("request", record)

    # BAR-01: the scan button on the Ingredients tab. Without a camera the decoder isn't loaded
    # (see test_the_decoder_is_the_apps_own_file).
    page.goto("/ingredients")
    page.get_by_test_id(TEST_IDS["scanBarcode"]).click()
    expect(page).to_have_url(re.compile(r"/scan$"))
    expect(page.get_by_test_id(TEST_IDS["scannerCameraMessage"])).to_be_visible()

    # BAR-03: the proposal from Open Food Facts, with the attribution.
    look_up(page, product.barcode)
    proposal = page.get_by_test_id(TEST_IDS["scanProposal"])
    expect(proposal.get_by_role("heading", name=product.name, exact=True)).to_be_visible()
    expect(proposal).to_contain_text(product.brand)
    expect(proposal).to_contain_text(product.kcal)
    expect_attribution(proposal)

    # "Which ingredient is this?" → a new one: name from the product, category guessed.
    which = page.get_by_test_id(TEST_IDS["scanWhich"])
    expect(which.get_by_role("heading", name=text("scanner.which.title"))).to_be_visible()
    which.get_by_test_id(TEST_IDS["scanCreateIngredient"]).click()
    dialog = page.get_by_role("dialog", name=text("ingredients.form.createTitle"))
    name = dialog.get_by_label(text("ingredients.field.name"), exact=True)
    expect(name).to_have_value(product.name)
    [category_id] = [
        category["id"]
        for category in api.categories(member)
        if category["key"] == product.category_key
    ]
    expect(dialog.get_by_label(text("ingredients.field.category"), exact=True)).to_have_value(
        category_id
    )
    unit = dialog.get_by_role("radio", name=text(f"ingredients.baseUnit.{product.base_unit}"))
    expect(unit).to_be_checked()
    # All tests of a run share one database.
    ingredient_name = f"{product.name} {unique('e2e')}"
    name.fill(ingredient_name)
    dialog.get_by_role("button", name=text("ingredients.form.create")).click()
    expect(dialog).to_be_hidden()

    # The values could be corrected here; they are saved as proposed.
    form = page.get_by_test_id(TEST_IDS["productForm"])
    expect(form.get_by_label(text("ingredients.product.name"), exact=True)).to_have_value(
        product.name
    )
    form.get_by_role("button", name=text("ingredients.product.create")).click()

    # The new ingredient opens, with the product and its attribution.
    expect(page).to_have_url(re.compile(r"/ingredients/[\w-]+$"))
    ingredient_url = page.url
    detail = page.get_by_test_id(TEST_IDS["screenIngredient"])
    expect(detail.get_by_role("heading", level=1)).to_have_text(ingredient_name)
    row = detail.get_by_test_id(TEST_IDS["productRow"])
    expect(row).to_contain_text(product.name)
    expect(row).to_contain_text(text("ingredients.products.barcode", barcode=product.barcode))
    expect(row).to_contain_text(product.kcal)
    expect_attribution(row)

    # BAR-02: the same barcode again goes straight to its ingredient.
    page.goto("/scan")
    look_up(page, product.barcode)
    expect(page).to_have_url(ingredient_url)

    # Unknown to Open Food Facts: "not found", then a product entered by hand.
    unknown = new_barcode()
    page.goto("/scan")
    look_up(page, unknown)
    expect(page.get_by_test_id(TEST_IDS["scanNotice"])).to_have_text(text("scanner.notFound"))
    expect(page.get_by_test_id(TEST_IDS["scanProposal"])).to_have_count(0)
    which = page.get_by_test_id(TEST_IDS["scanWhich"])
    which.get_by_label(text("scanner.which.search"), exact=True).fill(ingredient_name)
    which.get_by_role("button", name=re.compile(f"^{re.escape(ingredient_name)}")).click()
    form = page.get_by_test_id(TEST_IDS["productForm"])
    barcode = form.get_by_label(text("ingredients.product.barcode"), exact=True)
    expect(barcode).to_have_value(unknown)
    manual_name = unique("By hand")
    form.get_by_label(text("ingredients.product.name"), exact=True).fill(manual_name)
    form.get_by_label(text("nutrient.kcal"), exact=True).fill("60")
    form.get_by_role("button", name=text("ingredients.product.create")).click()
    expect(page).to_have_url(ingredient_url)
    rows = page.get_by_test_id(TEST_IDS["productRow"])
    expect(rows).to_have_count(2)
    manual = rows.filter(has_text=manual_name)
    expect(manual).to_contain_text("60 kcal")
    expect(manual.get_by_test_id(TEST_IDS["offAttribution"])).to_have_count(0)

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


def test_the_decoder_is_the_apps_own_file(
    launch_browser: Callable[..., Browser],
    browser_context_args: dict[str, Any],
    browser_name: str,
    member: Account,
    base_url: str,
) -> None:
    """SEC-08, BAR-01: once the camera runs, the decoder's wasm comes from the app, no CDN.

    The decoder is loaded only with a camera stream; Chromium can fake one
    (`--use-fake-device-for-media-stream`), the other browsers can't."""
    if browser_name != "chromium":
        pytest.skip("only Chromium can fake a camera")
    browser = launch_browser(args=["--use-fake-device-for-media-stream"])
    try:
        context = browser.new_context(**browser_context_args, permissions=["camera"])
        requested: list[str] = []
        context.on("request", lambda request: requested.append(request.url))
        sign_in(context, member)
        page = context.new_page()

        with page.expect_response(re.compile(r"/assets/zxing_reader-[\w-]+\.wasm$")) as wasm:
            page.goto("/scan")

        expect(page.get_by_test_id(TEST_IDS["scannerVideo"])).to_be_visible()
        assert wasm.value.ok
        assert wasm.value.header_value("content-type") == "application/wasm"
        assert urlsplit(wasm.value.url).netloc == urlsplit(base_url).netloc
        # The manual input stays next to the camera (BAR-01).
        expect(page.get_by_test_id(TEST_IDS["barcodeInput"])).to_be_visible()
        assert foreign_requests(requested, base_url) == []
    finally:
        browser.close()


def test_scanning_in_the_meal_form_adds_the_ingredient(
    member_page: Page, member: Account, api: Api
) -> None:
    """BAR-01, MEAL-03: the picker's scan button adds a known product's ingredient as a row."""
    page = member_page
    ingredient = api.create_ingredient(member, unique("Scanned"))
    barcode = api.create_product(member, ingredient["id"], name=unique("Package"))["barcode"]

    page.goto("/meals/new")
    form = page.get_by_test_id(TEST_IDS["mealForm"])
    form.get_by_label(text("meals.field.name"), exact=True).fill(unique("Scan meal"))
    form.get_by_test_id(TEST_IDS["scanBarcode"]).click()
    dialog = page.get_by_test_id(TEST_IDS["scanDialog"])
    dialog.get_by_test_id(TEST_IDS["barcodeInput"]).fill(barcode)
    dialog.get_by_test_id(TEST_IDS["barcodeLookup"]).click()

    expect(dialog).to_be_hidden()
    row = form.get_by_test_id(TEST_IDS["mealIngredientRow"])
    expect(row).to_have_count(1)
    expect(row).to_have_accessible_name(text("meals.row.label", name=ingredient["name"]))
