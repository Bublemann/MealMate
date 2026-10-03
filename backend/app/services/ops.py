"""The ops of shopping mode (plan § 5.8, SYNC-05/06, SHOP-02/04): check-off, free-text extra
items and finishing. The online UI sends them like an offline client (M6) will, so both take
one code path.

A request's ops run in order in one write transaction (`BEGIN IMMEDIATE`), so parallel requests
never lose an update. Each op takes effect at most once: an op id the same user sent before
(found in `processed_ops`) is a `duplicate` and changes nothing. Applied ops are recorded, also
those without effect (a check-off older than the stored one, an update of a deleted item);
rejected ones are not, since they may succeed later (e.g. after the list is reopened). The
list's version goes up once if anything changed.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode
from app.domain.aggregation import Line
from app.domain.lists import LINE_KEY_PATTERN, TEXT_KEY_PREFIX
from app.media.store import MediaStore
from app.models import ListExtraItem, ProcessedOp, ShoppingList
from app.repositories import lists as lists_repo
from app.repositories import reference as reference_repo
from app.schemas.lists import (
    ExtraAddOp,
    ExtraAddPayload,
    ExtraDeleteOp,
    ExtraUpdateOp,
    LineCheckOp,
    ListFinishOp,
    OpResult,
    OpsRequest,
    OpsResponse,
)
from app.services import access, aggregation, lists, reference, shopping
from app.services.principal import Principal

# What an op did: changed the list, took effect without a change, or had been done before.
type Outcome = Literal["changed", "unchanged", "duplicate"]
type AnyOp = LineCheckOp | ExtraAddOp | ExtraUpdateOp | ExtraDeleteOp | ListFinishOp


class OpRejectedError(Exception):
    """The op cannot be applied (now); its result carries the code."""

    def __init__(self, code: ErrorCode) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class _Batch:
    """The list the ops of one request change, and its current lines (loaded when a
    check-off needs them, dropped when an extra item changes)."""

    session: AsyncSession
    shopping_list: ShoppingList
    user_id: str
    now: datetime
    _lines: dict[str, Line] | None = field(default=None, init=False)
    _extras: dict[str, ListExtraItem] = field(default_factory=dict, init=False)

    def content_changed(self) -> None:
        self._lines = None

    async def check_snapshot(self, line_key: str) -> dict[str, Any]:
        """What the line looks like now, as stored with a check-off (plan § 5.7)."""
        if self._lines is None:
            content = await aggregation.load(self.session, [self.shopping_list])
            self._lines = aggregation.current_lines(content, self.shopping_list)
            self._extras = {row.id: row for row in content.extras.get(self.shopping_list.id, [])}
        text_extra = (
            self._extras.get(line_key.removeprefix(TEXT_KEY_PREFIX))
            if line_key.startswith(TEXT_KEY_PREFIX)
            else None
        )
        return aggregation.check_snapshot(self._lines.get(line_key), text_extra)


def _time_of(batch: _Batch, op: LineCheckOp | ListFinishOp) -> datetime:
    """When the op happened, as it counts (`shopping.op_time`); a time without a UTC time
    makes it invalid."""
    at = shopping.op_time(op.at, now=batch.now)
    if at is None:
        raise OpRejectedError(ErrorCode.VALIDATION)
    return at


def _require_not_done(shopping_list: ShoppingList) -> None:
    if shopping_list.status == "done":
        raise OpRejectedError(ErrorCode.LIST_DONE)


async def _check(batch: _Batch, op: LineCheckOp) -> Outcome:
    """Check a line off or uncheck it; the last tap wins (SYNC-06)."""
    line_key = op.payload.line_key
    if re.fullmatch(LINE_KEY_PATTERN, line_key) is None:
        raise OpRejectedError(ErrorCode.VALIDATION)
    at = _time_of(batch, op)
    if (code := shopping.check_refused(batch.shopping_list, at)) is not None:
        raise OpRejectedError(code)
    snapshot = await batch.check_snapshot(line_key) if op.payload.checked else {}
    changed = await shopping.set_checked(
        batch.session,
        batch.shopping_list,
        line_key,
        checked=op.payload.checked,
        snapshot=snapshot,
        user_id=batch.user_id,
        at=at,
        op_id=op.op_id,
    )
    return "changed" if changed else "unchanged"


async def _extra_category_id(session: AsyncSession, payload: ExtraAddPayload) -> str:
    """The category of a free-text item added by op: by id, or by key from app versions before
    D-31; *Other* if it names none, an unknown or a deleted one, or *Uncategorized*, so that the
    op never fails (LIST-06)."""
    category_id = payload.category_id
    if category_id is None and payload.category_key is not None:
        named = await reference_repo.category_by_key(session, payload.category_key)
        category_id = None if named is None else named.id
    category = (
        None if category_id is None else await reference.pickable_category(session, category_id)
    )
    return category.id if category is not None else await lists.other_category_id(session)


async def _add_extra(batch: _Batch, op: ExtraAddOp) -> Outcome:
    """Add a free-text extra item with the client's id (SHOP-02) in its category."""
    _require_not_done(batch.shopping_list)
    payload = op.payload
    if (existing := await lists_repo.get_extra(batch.session, payload.extra_id)) is not None:
        if existing.list_id != batch.shopping_list.id:
            raise OpRejectedError(ErrorCode.EXTRA_ID_TAKEN)
        return "duplicate"
    batch.session.add(
        ListExtraItem(
            id=payload.extra_id,
            list_id=batch.shopping_list.id,
            text=payload.text,
            amount_text=payload.amount_text,
            category_id=await _extra_category_id(batch.session, payload),
            added_by=batch.user_id,
            created_at=batch.now,
            updated_at=batch.now,
        )
    )
    await batch.session.flush()
    batch.content_changed()
    return "changed"


async def _extra_of(batch: _Batch, extra_id: str) -> ListExtraItem:
    """An extra item of the list, deleted or not."""
    extra = await lists_repo.get_extra(batch.session, extra_id)
    if extra is None or extra.list_id != batch.shopping_list.id:
        raise OpRejectedError(ErrorCode.NOT_FOUND)
    return extra


async def _update_extra(batch: _Batch, op: ExtraUpdateOp) -> Outcome:
    """Rename a free-text extra item and change its amount; a deleted one stays deleted
    (delete wins, SYNC-06)."""
    _require_not_done(batch.shopping_list)
    payload = op.payload
    extra = await _extra_of(batch, payload.extra_id)
    if extra.ingredient_id is not None:
        raise OpRejectedError(ErrorCode.VALIDATION)
    amount_text = (
        payload.amount_text if "amount_text" in payload.model_fields_set else extra.amount_text
    )
    if extra.deleted_at is not None or (extra.text, extra.amount_text) == (
        payload.text,
        amount_text,
    ):
        return "unchanged"
    extra.text, extra.amount_text = payload.text, amount_text
    extra.updated_at = batch.now
    batch.content_changed()
    return "changed"


async def _delete_extra(batch: _Batch, op: ExtraDeleteOp) -> Outcome:
    """Delete an extra item (a tombstone stays)."""
    _require_not_done(batch.shopping_list)
    extra = await _extra_of(batch, op.payload.extra_id)
    if extra.deleted_at is not None:
        return "unchanged"
    extra.deleted_at = extra.updated_at = batch.now
    batch.content_changed()
    return "changed"


def _finish(batch: _Batch, op: ListFinishOp) -> Outcome:
    """Finish shopping (SHOP-04), as of the tap; a done list stays as it is."""
    at = _time_of(batch, op)
    if batch.shopping_list.status == "draft":
        raise OpRejectedError(ErrorCode.LIST_NOT_SHOPPING)
    if batch.shopping_list.status == "done":
        return "unchanged"
    shopping.finish(batch.shopping_list, at=at, now=batch.now)
    return "changed"


async def _apply(batch: _Batch, op: AnyOp) -> Outcome:
    match op:
        case LineCheckOp():
            return await _check(batch, op)
        case ExtraAddOp():
            return await _add_extra(batch, op)
        case ExtraUpdateOp():
            return await _update_extra(batch, op)
        case ExtraDeleteOp():
            return await _delete_extra(batch, op)
        case ListFinishOp():
            return _finish(batch, op)


async def apply_ops(
    session: AsyncSession,
    media: MediaStore,
    principal: Principal,
    list_id: str,
    body: OpsRequest,
    *,
    now: datetime,
    expected_user_id: str | None = None,
) -> OpsResponse:
    """Apply the ops in order, in one transaction, on a list the principal may edit (404 or
    403 for the whole request otherwise), and answer with each op's result and the list.

    `expected_user_id`: who made the ops, if the client says so; when that is not the
    principal nothing is applied (409 `auth.user_mismatch`), so ops never count as another
    user's (SYNC-10)."""
    if expected_user_id is not None and expected_user_id != principal.user_id:
        raise ApiError(ErrorCode.USER_MISMATCH, status_code=409)
    async with session.begin():
        shopping_list, rights = await access.require_list_edit(session, principal, list_id)
        processed = await lists_repo.processed_op_ids(
            session, principal.user_id, (op.root.op_id for op in body.ops)
        )
        batch = _Batch(session, shopping_list, principal.user_id, now)
        results: list[OpResult] = []
        changed = False
        for item in body.ops:
            op = item.root
            if op.op_id in processed:
                results.append(OpResult(op_id=op.op_id, status="duplicate", code=None))
                continue
            try:
                outcome = await _apply(batch, op)
            except OpRejectedError as rejected:
                results.append(OpResult(op_id=op.op_id, status="rejected", code=rejected.code))
                continue
            if outcome == "duplicate":
                results.append(OpResult(op_id=op.op_id, status="duplicate", code=None))
                continue
            changed = changed or outcome == "changed"
            processed.add(op.op_id)
            session.add(
                ProcessedOp(
                    op_id=op.op_id, user_id=principal.user_id, list_id=list_id, applied_at=now
                )
            )
            results.append(OpResult(op_id=op.op_id, status="applied", code=None))
        if changed:
            await lists.touch(session, shopping_list, now)
        detail = await lists.list_detail(
            session, media, principal.user_id, shopping_list, rights, now=now
        )
        return OpsResponse(results=results, list=detail)
