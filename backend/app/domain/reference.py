"""Seeded reference data (REF-01, REF-03, requirements appendix A).

The migration that seeds these (0003) spells the keys out itself, since migrations are frozen
history; a migration test checks both agree. Adding a category or cuisine: a new migration that
inserts it, the key here, and the translations `category.<key>` / `cuisine.<key>` (MNT-06).
"""

# The default walking order of a German supermarket; admins can reorder (ADM-01).
CATEGORY_KEYS: tuple[str, ...] = (
    "fruit_vegetables",
    "bread_bakery",
    "dairy_eggs",
    "cheese",
    "meat_fish",
    "sausage_deli",
    "plant_based",
    "pasta_rice_grains",
    "canned_jars",
    "sauces_spices_oils",
    "baking",
    "breakfast_spreads",
    "snacks_sweets",
    "frozen",
    "drinks",
    "household_hygiene",
    "other",
)
# Always exists (REF-01); the default category of new ingredients and free-text items.
OTHER_CATEGORY = "other"

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
