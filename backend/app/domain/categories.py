"""Guessing an ingredient's category from Open Food Facts categories (BAR-03).

A product's `categories_tags` hold canonical tags such as `en:cheeses`, together with all their
parents (`en:dairies`, `en:fermented-foods`, ...). `CATEGORY_RULES` is checked in order and the
first rule whose tag the product has wins, so specific tags come before broad ones: cheese
before dairy, frozen and canned before whatever is frozen or canned, bread and breakfast cereals
before `en:cereals-and-potatoes`. Broad tags that span several of our categories (e.g.
`en:plant-based-foods`) have no rule. The guess only preselects the category of a new
ingredient; the user can change it.
"""

from collections.abc import Iterable

CATEGORY_RULES: tuple[tuple[str, str], ...] = (
    # How it is stored or packed decides the aisle first.
    ("en:frozen-foods", "frozen"),
    ("en:canned-foods", "canned_jars"),
    # Specific kinds before their broad parents.
    ("en:cheeses", "cheese"),
    ("en:meat-analogues", "plant_based"),
    ("en:tofu", "plant_based"),
    ("en:dairy-substitutes", "plant_based"),
    ("en:sausages", "sausage_deli"),
    ("en:hams", "sausage_deli"),
    ("en:prepared-meats", "sausage_deli"),
    ("en:breads", "bread_bakery"),
    ("en:pastries", "bread_bakery"),
    ("en:breakfasts", "breakfast_spreads"),
    ("en:spreads", "breakfast_spreads"),
    ("en:flours", "baking"),
    ("en:dairies", "dairy_eggs"),
    ("en:eggs", "dairy_eggs"),
    ("en:beverages", "drinks"),
    ("en:meats", "meat_fish"),
    ("en:fishes", "meat_fish"),
    ("en:seafood", "meat_fish"),
    ("en:sauces", "sauces_spices_oils"),
    ("en:condiments", "sauces_spices_oils"),
    ("en:spices", "sauces_spices_oils"),
    ("en:oils", "sauces_spices_oils"),
    ("en:vegetable-oils", "sauces_spices_oils"),
    ("en:snacks", "snacks_sweets"),
    ("en:sweets", "snacks_sweets"),
    ("en:confectioneries", "snacks_sweets"),
    ("en:fruits", "fruit_vegetables"),
    ("en:vegetables", "fruit_vegetables"),
    ("en:pastas", "pasta_rice_grains"),
    ("en:rices", "pasta_rice_grains"),
    ("en:cereals-and-potatoes", "pasta_rice_grains"),
)


def guess_category(tags: Iterable[str]) -> str | None:
    """Our category key for a product with these Open Food Facts category tags, or None."""
    present = {tag.strip().lower() for tag in tags}
    for tag, key in CATEGORY_RULES:
        if tag in present:
            return key
    return None
