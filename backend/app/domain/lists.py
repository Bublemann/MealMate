"""Input rules and line keys of shopping lists (LIST-01..08, LIST-14, plan §§ 5.6 and 5.7).

A line is identified by its key: `i:<ingredient_id>` for an ingredient (all its parts from
meals and linked extra items merge into it, AGG-02), `x:<extra_item_id>` for a free-text extra
item (never merged). Check and hide states (`list_line_states`) are stored per key, so keys
must stay stable (AGG-05).
"""

from typing import Literal

from app.domain.meals import SERVINGS_MAX

LIST_NAME_MAX_LENGTH = 60
EXTRA_TEXT_MAX_LENGTH = 80
AMOUNT_TEXT_MAX_LENGTH = 30
LINE_KEY_MAX_LENGTH = 80
# `reminder_seed` picks the reminder (LIST-14); the frontend shows `reminder.<seed % 10 + 1>`.
REMINDER_SEED_MAX = 9_999
# The meal picker shows this many "recently used" meals first (MEAL-09).
RECENT_MEALS_LIMIT = 10
# At most this many ops per request (plan § 5.8).
OPS_MAX = 100
# The history shows at most this many done lists (SHOP-05).
HISTORY_LIMIT = 200

# Plain aliases (not `type` statements) so the OpenAPI schema inlines the literals.
ListStatus = Literal["draft", "shopping", "done"]
DetachedReason = Literal["deleted", "unavailable"]

INGREDIENT_KEY_PREFIX = "i:"
TEXT_KEY_PREFIX = "x:"
# What a client may send as a line key: a prefix and a UUID as the server writes it.
LINE_KEY_PATTERN = r"^(i|x):[0-9a-f-]{36}$"


def ingredient_key(ingredient_id: str) -> str:
    return INGREDIENT_KEY_PREFIX + ingredient_id


def text_key(extra_item_id: str) -> str:
    return TEXT_KEY_PREFIX + extra_item_id


def raised_servings(current: int, added: int) -> int:
    """Adding a meal that is already on the list raises its servings (LIST-04), at most to
    the maximum."""
    return min(current + added, SERVINGS_MAX)
