"""The category guess for a new ingredient from Open Food Facts categories (BAR-03)."""

import pytest

from app.domain.categories import CATEGORY_RULES, guess_category
from app.domain.reference import CATEGORY_KEYS


def test_rules_name_existing_categories_and_tags_once() -> None:
    assert {key for _, key in CATEGORY_RULES} <= set(CATEGORY_KEYS)
    tags = [tag for tag, _ in CATEGORY_RULES]
    assert len(tags) == len(set(tags))
    assert all(tag.startswith("en:") and tag == tag.lower() for tag in tags)


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        # Each rule on its own.
        *(([tag], key) for tag, key in CATEGORY_RULES),
        # Real tag sets (with their parents), where the specific tag must win.
        (["en:dairies", "en:fermented-foods", "en:cheeses", "en:hard-cheeses"], "cheese"),
        (["en:dairies", "en:milks", "en:whole-milks"], "dairy_eggs"),
        (["en:frozen-foods", "en:vegetables", "en:frozen-vegetables"], "frozen"),
        (["en:canned-foods", "en:fishes", "en:canned-fishes", "en:tunas"], "canned_jars"),
        (
            ["en:plant-based-foods-and-beverages", "en:beverages", "en:dairy-substitutes"],
            "plant_based",
        ),
        (["en:plant-based-foods", "en:meat-analogues", "en:meats"], "plant_based"),
        (["en:meats", "en:prepared-meats", "en:hams"], "sausage_deli"),
        (["en:cereals-and-potatoes", "en:breads", "en:wholemeal-breads"], "bread_bakery"),
        (
            ["en:breakfasts", "en:spreads", "en:sweet-spreads", "en:cocoa-and-hazelnuts-spreads"],
            "breakfast_spreads",
        ),
        (["en:cereals-and-potatoes", "en:breakfasts", "en:breakfast-cereals"], "breakfast_spreads"),
        (["en:cereals-and-potatoes", "en:cereal-grains", "en:flours"], "baking"),
        (["en:beverages", "en:fruit-juices", "en:fruits"], "drinks"),
        (["en:snacks", "en:sweet-snacks", "en:chocolates"], "snacks_sweets"),
        (["en:plant-based-foods", "en:fruits", "en:apples"], "fruit_vegetables"),
        (["en:cereals-and-potatoes", "en:pastas", "en:spaghetti"], "pasta_rice_grains"),
        (["en:condiments", "en:sauces", "en:ketchup"], "sauces_spices_oils"),
        ([" EN:Cheeses "], "cheese"),
        # Too broad, unknown or empty: no guess.
        (["en:plant-based-foods-and-beverages", "en:plant-based-foods"], None),
        (["de:unbekannt"], None),
        ([], None),
    ],
)
def test_guess_category(tags: list[str], expected: str | None) -> None:
    assert guess_category(tags) == expected
