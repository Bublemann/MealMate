"""Refreshing items from Open Food Facts (BAR-05, BAR-06, BAR-07, plan § 5.9).

An item created from Open Food Facts (`source` off, with its barcode) is refreshed when its
`fetched_at` is older than `MEALMATE_OFF_REFRESH_DAYS`:

- by `mealmate jobs off-refresh` (nightly), oldest first, at most `JOB_MAX_MINUTES` worth of
  requests per run, each item waiting for its turn under the job's rate limit. An
  item that fails with an error (e.g. `database is locked`) is logged by id and counted,
  and the job goes on with the next one. Its `fetched_at` stays, so it is retried on the next
  night, first again; as errors never stop the loop, one that fails every time does not block
  the others;
- in the background when it is opened or scanned (`schedule_if_stale`), after the response and
  at most once at a time per item, only if a request may start right away (lookups, which
  a user waits for, have precedence). An item whose background refresh failed
  (unavailable, not found, an error) is left alone for `RETRY_AFTER_FAILURE_SECONDS`, not asked
  again on every open.

Open Food Facts is asked outside any transaction; each item is then written in its own short
write transaction (plan § 5.1). Unavailable, removed or busy: the values and `fetched_at` stay,
so the next refresh tries again (BAR-07). Found, field by field (BAR-06):

- a value Open Food Facts does not know (any more) never replaces a known one;
- not user-edited: updated silently;
- user-edited (`off_fields.edited_fields`) and different: collected into `pending_update`,
  unless the user ignored this very Open Food Facts version (`ignored_off_modified_at`) or, for
  an item without a version, this very value (the ignored entries kept in `pending_update`, see
  `services.off_fields`);
- nutrients only while Open Food Facts gives them per what the item's are per: 100 g,
  or 100 ml for an ml item (`NUTRITION_BASIS`), and never for a supply, which has none (D-55);
- the kind, category, base unit, piece weight and barcode are never touched.
"""

import logging
import time
from collections import Counter
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from fastapi import BackgroundTasks

from app.core.config import Settings
from app.core.ratelimit import Clock
from app.db.base import utcnow
from app.db.session import Database
from app.domain.catalog import OFF_DATA_FIELDS, SUPPLY
from app.domain.units import NUTRITION_BASIS, BaseUnit
from app.integrations.off import OffClient, OffProduct
from app.models import Item as ItemRow
from app.repositories import items as items_repo
from app.repositories import users as users_repo
from app.schemas.items import Item
from app.services.off_fields import edited_fields, field_value, ignored_entries, set_field_value

logger = logging.getLogger(__name__)

# The name language when the item's creator (or the searching user) is gone.
DEFAULT_LANGUAGE = "de"
# The nightly job asks for at most this many minutes' worth of items at its rate limit, so
# that a large backlog is worked off over several nights instead of running all day.
JOB_MAX_MINUTES = 60
# Background refreshes never wait for their turn under the rate limit.
BACKGROUND_MAX_WAIT_SECONDS = 0.0
# How long the app leaves an item alone after its background refresh failed.
RETRY_AFTER_FAILURE_SECONDS = 60 * 60


class Outcome(StrEnum):
    """What refreshing one item did."""

    UPDATED = "updated"
    PENDING = "pending"
    UNCHANGED = "unchanged"
    UNAVAILABLE = "unavailable"
    NOT_FOUND = "not_found"
    BUSY = "busy"
    SKIPPED = "skipped"
    ERROR = "error"


_NOT_FOUND_OUTCOMES = {
    "not_found": Outcome.NOT_FOUND,
    "unavailable": Outcome.UNAVAILABLE,
    "busy": Outcome.BUSY,
}
# Background refreshes that are not tried again for a while.
_FAILED = frozenset({Outcome.UNAVAILABLE, Outcome.NOT_FOUND, Outcome.ERROR})


def _log_failure(message: str, item_id: str, exc: Exception) -> None:
    """Log a failed refresh by item id and error type only: the error's message may quote
    Open Food Facts' data or SQL parameters."""
    logger.warning(message, extra={"item_id": item_id, "error": type(exc).__name__})


def is_stale(
    source: str, fetched_at: datetime | None, *, now: datetime, max_age: timedelta
) -> bool:
    """An item from Open Food Facts that was fetched longer than `max_age` ago (or
    never)."""
    return source == "off" and (fetched_at is None or fetched_at < now - max_age)


def apply_refresh(row: ItemRow, found: OffProduct, *, language: str, now: datetime) -> Outcome:
    """Merge a product's current Open Food Facts values into the item `row` (BAR-06), see
    the module docstring; runs inside the caller's write transaction."""
    proposed = found.fields(language)
    if row.kind == SUPPLY or found.nutrition_basis != NUTRITION_BASIS[BaseUnit(row.base_unit)]:
        proposed = {field: value for field, value in proposed.items() if field in OFF_DATA_FIELDS}
    edited = set(edited_fields(row))
    ignored = (
        found.last_modified_at is not None and found.last_modified_at == row.ignored_off_modified_at
    )
    ignored_values = ignored_entries(row)
    changed = False
    pending: dict[str, Any] = {}
    for field, value in proposed.items():
        current = field_value(row, field)
        if value == current or value is None:  # an unknown value never replaces a known one
            continue
        if field not in edited:
            set_field_value(row, field, value)
            changed = True
        elif not ignored and ignored_values.get(field, {}).get("proposed") != value:
            pending[field] = {"current": current, "proposed": value}
    row.pending_update = (ignored_values | pending) or None
    row.fetched_at = now
    row.off_last_modified_at = found.last_modified_at
    row.updated_at = now
    if changed:
        return Outcome.UPDATED
    return Outcome.PENDING if pending else Outcome.UNCHANGED


async def refresh_item(
    database: Database,
    off: OffClient,
    item_id: str,
    *,
    now: datetime,
    max_wait: float | None,
    fetched_before: datetime | None = None,
) -> Outcome:
    """Refresh one item from Open Food Facts. Items that are not from Open Food
    Facts (or have no barcode), were deleted meanwhile, or were fetched since `fetched_before`
    are skipped."""
    async with database.read_sessions() as session, session.begin():
        row = await items_repo.get(session, item_id)
        if row is None or row.source != "off" or row.barcode is None:
            return Outcome.SKIPPED
        if fetched_before is not None and row.fetched_at and row.fetched_at >= fetched_before:
            return Outcome.SKIPPED
        barcode = row.barcode
        creator = await users_repo.get(session, row.created_by) if row.created_by else None
        language = creator.language if creator is not None else DEFAULT_LANGUAGE

    response = await off.fetch(barcode, max_wait=max_wait)
    if response.product is None:
        return _NOT_FOUND_OUTCOMES[response.status]

    async with database.write_sessions() as session, session.begin():
        row = await items_repo.get(session, item_id)
        if row is None or row.source != "off" or row.barcode != barcode:
            return Outcome.SKIPPED
        return apply_refresh(row, response.product, language=language, now=now)


async def refresh_stale(
    database: Database,
    off: OffClient,
    *,
    max_age: timedelta,
    max_items: int | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> Counter[Outcome]:
    """`mealmate jobs off-refresh`: refresh the stale items from Open Food Facts (at most
    `max_items`), oldest first, one at a time under the rate limit; returns how often each
    outcome happened. An item that fails is logged and counted as `error`, and the job goes
    on with the next one."""
    fetched_before = clock() - max_age
    async with database.read_sessions() as session, session.begin():
        item_ids = await items_repo.stale_from_off(session, fetched_before, limit=max_items)
    outcomes: Counter[Outcome] = Counter()
    for item_id in item_ids:
        try:
            outcome = await refresh_item(
                database,
                off,
                item_id,
                now=clock(),
                max_wait=None,
                fetched_before=fetched_before,
            )
        except Exception as exc:
            _log_failure("refreshing an item from open food facts failed", item_id, exc)
            outcome = Outcome.ERROR
        outcomes[outcome] += 1
    return outcomes


class OffRefresher:
    """The app's Open Food Facts client and background refreshes (`app.state.off_refresh`).

    `running` holds the items being refreshed, so that each is refreshed at most once at
    a time however often it is opened; `failed` when their background refresh last failed (by
    `clock`), so that they are left alone for `RETRY_AFTER_FAILURE_SECONDS`. Both hold at most
    one entry per item."""

    def __init__(
        self, off: OffClient, *, max_age: timedelta, clock: Clock = time.monotonic
    ) -> None:
        self.off = off
        self.max_age = max_age
        self.clock = clock
        self.running: set[str] = set()
        self.failed: dict[str, float] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> OffRefresher:
        return cls(
            OffClient.from_settings(settings), max_age=timedelta(days=settings.off_refresh_days)
        )

    def recently_failed(self, item_id: str) -> bool:
        """Whether the item's background refresh failed less than
        `RETRY_AFTER_FAILURE_SECONDS` ago."""
        failed_at = self.failed.get(item_id)
        if failed_at is None:
            return False
        if self.clock() - failed_at < RETRY_AFTER_FAILURE_SECONDS:
            return True
        del self.failed[item_id]
        return False

    async def refresh_in_background(self, database: Database, item_id: str, now: datetime) -> None:
        """Refresh an item after a response, if a request may start right away; failures
        are logged and remembered, never raised."""
        try:
            outcome = await refresh_item(
                database,
                self.off,
                item_id,
                now=now,
                max_wait=BACKGROUND_MAX_WAIT_SECONDS,
                fetched_before=now - self.max_age,
            )
        except Exception as exc:
            _log_failure("background refresh from open food facts failed", item_id, exc)
            outcome = Outcome.ERROR
        finally:
            self.running.discard(item_id)
        if outcome in _FAILED:
            self.failed[item_id] = self.clock()


def schedule_if_stale(
    background: BackgroundTasks,
    refresher: OffRefresher,
    database: Database,
    items: Iterable[Item],
    *,
    now: datetime,
) -> None:
    """Refresh each stale item from Open Food Facts after the response (BAR-05), unless it
    is already being refreshed or its last background refresh failed recently."""
    for item in items:
        if (
            item.id in refresher.running
            or item.barcode is None
            or not is_stale(item.source, item.fetched_at, now=now, max_age=refresher.max_age)
            or refresher.recently_failed(item.id)
        ):
            continue
        refresher.running.add(item.id)
        background.add_task(refresher.refresh_in_background, database, item.id, now)
