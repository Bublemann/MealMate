"""Input rules and line keys of shopping lists (LIST-01..08, LIST-14, plan §§ 5.6 and 5.7), and
the pages of the list feed (UI-02).

A line is identified by its key: `i:<ingredient_id>` for an ingredient (all its parts from
meals and linked extra items merge into it, AGG-02), `x:<extra_item_id>` for a free-text extra
item (never merged). Check and hide states (`list_line_states`) are stored per key, so keys
must stay stable (AGG-05).
"""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, get_args

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
# The list feed loads this many lists per page (UI-02).
FEED_PAGE_SIZE = 30
# Longer than any cursor `feed_cursor` makes.
FEED_CURSOR_MAX_LENGTH = 120

# Plain aliases (not `type` statements) so the OpenAPI schema inlines the literals.
ListStatus = Literal["draft", "shopping", "done"]
DetachedReason = Literal["deleted", "unavailable"]
LIST_STATUSES: tuple[ListStatus, ...] = get_args(ListStatus)

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


@dataclass(frozen=True)
class FeedPosition:
    """Where a page of the list feed ends: its last list's creation time and id. The feed is
    ordered newest created first, ties by id, so the next page starts right after this list,
    and lists created or deleted meanwhile never shift it (UI-02)."""

    created_at: datetime
    list_id: str


def feed_cursor(position: FeedPosition) -> str:
    """The opaque `next_cursor` for the page after `position`."""
    raw = f"{position.created_at.isoformat()} {position.list_id}"
    return urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def feed_position(cursor: str) -> FeedPosition | None:
    """The position a cursor of `feed_cursor` stands for; None for anything else."""
    try:
        raw = urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        created_at, list_id = raw.split(" ")
        position = FeedPosition(datetime.fromisoformat(created_at), list_id)
    except ValueError:  # binascii.Error and UnicodeDecodeError too
        return None
    if position.created_at.tzinfo is None or not list_id:
        return None
    return position
