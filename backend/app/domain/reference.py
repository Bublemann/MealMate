"""Seeded reference data (REF-01, REF-03, requirements appendix A).

The migrations that seed these (0003, 0009 for the category names, 0013 for *Uncategorized*)
spell them out themselves, since migrations are frozen history; a migration test checks both
agree. Adding a cuisine: a new migration that inserts it, the key here, and the translations
`cuisine.<key>` (MNT-06). Category names are data, not translations (I18N-04, D-31).
"""

from typing import NamedTuple


class SeededCategory(NamedTuple):
    key: str
    name_de: str
    name_en: str


# The default walking order of a German supermarket; admins can reorder (ADM-01).
SEEDED_CATEGORIES: tuple[SeededCategory, ...] = (
    SeededCategory("fruit_vegetables", "Obst & Gemüse", "Fruit & vegetables"),
    SeededCategory("bread_bakery", "Brot & Backwaren", "Bread & bakery"),
    SeededCategory("dairy_eggs", "Milchprodukte & Eier", "Dairy & eggs"),
    SeededCategory("cheese", "Käse", "Cheese"),
    SeededCategory("meat_fish", "Fleisch & Fisch", "Meat & fish"),
    SeededCategory("sausage_deli", "Wurst & Aufschnitt", "Sausage & deli"),
    SeededCategory("plant_based", "Tofu & pflanzliche Alternativen", "Tofu & plant-based"),
    SeededCategory("pasta_rice_grains", "Nudeln, Reis & Getreide", "Pasta, rice & grains"),
    SeededCategory("canned_jars", "Konserven & Gläser", "Canned & jarred"),
    SeededCategory("sauces_spices_oils", "Soßen, Gewürze & Öle", "Sauces, spices & oils"),
    SeededCategory("baking", "Backzutaten", "Baking"),
    SeededCategory("breakfast_spreads", "Frühstück & Aufstriche", "Breakfast & spreads"),
    SeededCategory("snacks_sweets", "Süßes & Snacks", "Snacks & sweets"),
    SeededCategory("frozen", "Tiefkühl", "Frozen"),
    SeededCategory("drinks", "Getränke", "Drinks"),
    SeededCategory("household_hygiene", "Drogerie & Haushalt", "Household & toiletries"),
    SeededCategory("other", "Sonstiges", "Other"),
    SeededCategory("uncategorized", "Ohne Kategorie", "Uncategorized"),
)
CATEGORY_KEYS: tuple[str, ...] = tuple(category.key for category in SEEDED_CATEGORIES)
# Both always exist (REF-01). *Other* is the default category of new ingredients and free-text
# items; *Uncategorized* takes the ingredients of a deleted category and is never picked by hand.
OTHER_CATEGORY = "other"
UNCATEGORIZED_CATEGORY = "uncategorized"

# Listed in this order, before cuisines added by users.
CUISINE_KEYS: tuple[str, ...] = (
    "german",
    "italian",
    "french",
    "greek",
    "turkish",
    "mediterranean",
    "american",
    "mexican",
    "indian",
    "chinese",
    "japanese",
    "thai",
    "other",
)
