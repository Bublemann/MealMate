"""Contract check against the real Open Food Facts API (O-4, plan § 9).

Excluded from the normal run (marker `off_contract`); the weekly "Open Food Facts contract" CI
job runs it with `uv run pytest -m off_contract --no-cov`. It asks for one well-known, stable
product with the real client and checks that the pinned API version still answers in the shape
the recorded fixtures assume. A failure means the fixtures or the client need a look; it does not
block anything.
"""

from collections.abc import AsyncIterator

import pytest

from app.core.config import REPO_URL
from app.core.ratelimit import SlidingWindow
from app.domain.units import BaseUnit
from app.integrations.off import SEARCH_PAGE_SIZE, OffClient

pytestmark = pytest.mark.off_contract

# Nutella 400 g (Ferrero): the example of OFF's own documentation, unlikely to go away.
KNOWN_BARCODE = "3017620422003"


@pytest.fixture
async def off() -> AsyncIterator[OffClient]:
    """The real client, closed after the test (it keeps a connection pool)."""
    client = OffClient(
        "https://world.openfoodfacts.org",
        f"MealMate/contract-check ({REPO_URL})",
        rate_limit=SlidingWindow(3),  # at most three requests per test
    )
    yield client
    await client.aclose()


async def test_a_known_product_has_the_expected_shape(off: OffClient) -> None:
    response = await off.fetch(KNOWN_BARCODE, max_wait=None)

    assert response.status == "found"
    product = response.product
    assert product is not None
    assert "nutella" in (product.name("en") or "").lower()
    assert product.brands
    assert product.nutrition_basis is BaseUnit.G
    nutrients = product.nutrients
    assert 450 <= (nutrients["kcal"] or 0) <= 650
    assert sum(value is not None for value in nutrients.values()) >= 4
    assert product.pack[1] is BaseUnit.G
    assert product.categories_tags
    assert product.last_modified_at is not None


async def test_an_unknown_product_is_not_found(off: OffClient) -> None:
    # A valid EAN-13 with a GS1 prefix that is reserved (140-199), so no product has it.
    response = await off.fetch("1400000000007", max_wait=None)

    assert response.status == "not_found"


async def test_the_name_search_has_the_expected_shape(off: OffClient) -> None:
    """The full-text search answers with products sold in Germany in the product read's flat
    shape, with barcodes."""
    response = await off.search("nutella", page=1, language="de", max_wait=None)

    assert response.status == "found"
    assert response.count > 0
    assert response.results
    assert any(product.code for product in response.results)
    assert any("nutella" in (product.name("de") or "").lower() for product in response.results)
    assert any(product.nutrition_basis is BaseUnit.G for product in response.results)


async def test_the_name_search_pages(off: OffClient) -> None:
    """The parameters the search sends still work: pages of `SEARCH_PAGE_SIZE` products that
    follow on from each other (the "more results" button), and a query without a match is an
    empty page, not an error."""
    first = await off.search("milch", page=1, language="de", max_wait=None)
    second = await off.search("milch", page=2, language="de", max_wait=None)
    nothing = await off.search("qqxzqqxz mealmate", page=1, language="de", max_wait=None)

    assert (first.status, second.status) == ("found", "found")
    assert first.count > 2 * SEARCH_PAGE_SIZE
    assert len(first.results) == len(second.results) == SEARCH_PAGE_SIZE
    # Not the first page again (products with as many scans may swap places between pages).
    pages = [{product.code for product in page.results} for page in (first, second)]
    assert pages[0] != pages[1]
    assert (nothing.status, nothing.count, nothing.results) == ("found", 0, ())
