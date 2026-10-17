"""The walking order of a couple or a user without one (REF-01, D-48): following the admins'
order, or an own one.

A user sees and changes one order: their couple's while they are in one, else their own
(`access.owner_key`). Where each category comes, deleted ones included, follows from
`domain.walking_order`.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import FieldErrorCode, FieldProblem, validation_error
from app.domain.owners import OwnerKey
from app.domain.walking_order import WalkingOrder
from app.models import Category, WalkingOrderEntry
from app.repositories import reference as reference_repo
from app.repositories import walking_order as walking_order_repo
from app.schemas.reference import CategoryNames
from app.schemas.walking_order import WalkingOrder as WalkingOrderOut
from app.schemas.walking_order import WalkingOrderCategory, WalkingOrderSave
from app.services import access
from app.services.principal import Principal


def _field(name: str, code: FieldErrorCode) -> FieldProblem:
    return FieldProblem(("body", name), code)


def _order(entries: Sequence[WalkingOrderEntry]) -> WalkingOrder:
    return WalkingOrder({entry.category_id: entry.position for entry in entries})


def _view(categories: Sequence[Category], entries: Sequence[WalkingOrderEntry]) -> WalkingOrderOut:
    """The categories that aren't deleted, in the owner's order."""
    order, new = _order(entries), {entry.category_id for entry in entries if entry.is_new}
    shown = sorted(
        (row for row in categories if row.deleted_at is None),
        key=lambda row: order.sort_key(row.id, row.sort_order, deleted=False),
    )
    return WalkingOrderOut(
        follows_admin=order.follows_admin,
        categories=[
            WalkingOrderCategory(
                id=row.id,
                key=row.key,
                names=CategoryNames(de=row.name_de, en=row.name_en),
                new=row.id in new,
            )
            for row in shown
        ],
    )


async def _current(session: AsyncSession, key: OwnerKey) -> WalkingOrderOut:
    categories = await reference_repo.categories_in_order(session)
    return _view(categories, await walking_order_repo.of_owner(session, key))


async def order_of(session: AsyncSession, key: OwnerKey) -> WalkingOrder:
    """The order the owner's lists are grouped in: their own, else the admins' one."""
    return _order(await walking_order_repo.of_owner(session, key))


async def get_order(session: AsyncSession, principal: Principal) -> WalkingOrderOut:
    """The caller's walking order."""
    async with session.begin():
        return await _current(session, await access.owner_key(session, principal.user_id))


async def save_order(
    session: AsyncSession, principal: Principal, body: WalkingOrderSave, *, now: datetime
) -> WalkingOrderOut:
    """Keep `category_ids` as the caller's own order, which stops following the admins' one
    (D-48). It must name every category that isn't deleted exactly once, *Uncategorized*
    included (422 `invalid` otherwise, as is a `moved_id` that isn't one of them). The moved
    category is no longer new; the positions of deleted categories stay."""
    async with session.begin():
        categories = await reference_repo.categories_in_order(session)
        shown = {row.id for row in categories if row.deleted_at is None}
        if len(body.category_ids) != len(shown) or set(body.category_ids) != shown:
            raise validation_error([_field("category_ids", FieldErrorCode.INVALID)])
        if body.moved_id is not None and body.moved_id not in shown:
            raise validation_error([_field("moved_id", FieldErrorCode.INVALID)])
        key = await access.owner_key(session, principal.user_id)
        entries = {
            entry.category_id: entry for entry in await walking_order_repo.of_owner(session, key)
        }
        for position, category_id in enumerate(body.category_ids):
            entry = entries.get(category_id)
            if entry is None:
                session.add(
                    WalkingOrderEntry(
                        couple_id=key.couple_id,
                        user_id=key.user_id,
                        category_id=category_id,
                        position=position,
                        is_new=False,
                        created_at=now,
                        updated_at=now,
                    )
                )
                continue
            is_new = entry.is_new and category_id != body.moved_id
            if (entry.position, entry.is_new) != (position, is_new):
                entry.position, entry.is_new, entry.updated_at = position, is_new, now
        await session.flush()
        return _view(categories, await walking_order_repo.of_owner(session, key))


async def follow_admin(session: AsyncSession, principal: Principal) -> None:
    """Turn "Reihenfolge der Verwaltung übernehmen" back on: the caller's own order goes, and
    their lists follow the admins' order again (D-48). Changes nothing while it is on."""
    async with session.begin():
        key = await access.owner_key(session, principal.user_id)
        await walking_order_repo.delete_of_owner(session, key)


async def on_category_added(session: AsyncSession, category_id: str, *, now: datetime) -> None:
    """Runs when an admin adds a category, once its row is flushed: it goes to the end of every
    own order, marked new until it is moved (D-48). Orders that follow the admins' one get it
    there, last."""
    for key, size in (await walking_order_repo.sizes(session)).items():
        session.add(
            WalkingOrderEntry(
                couple_id=key.couple_id,
                user_id=key.user_id,
                category_id=category_id,
                position=size,
                is_new=True,
                created_at=now,
                updated_at=now,
            )
        )


async def on_category_deleted(session: AsyncSession, category_id: str, *, now: datetime) -> None:
    """Runs when an admin deletes a category, once it is marked deleted: it leaves every own
    order, but keeps its position there, so lists being shopped and done lists still show it
    right after the category that takes over its place (D-30, D-48). The categories that aren't
    deleted close the gap."""
    for key in await walking_order_repo.owners_with(session, category_id):
        shown = await walking_order_repo.of_owner(session, key, shown_only=True)
        for position, entry in enumerate(shown):
            if entry.position != position:
                entry.position, entry.updated_at = position, now


async def on_couple_accepted(
    session: AsyncSession, requester_id: str, addressee_id: str, *, couple_id: str, now: datetime
) -> None:
    """Runs when a couple forms (CPL-01): the requester's own order becomes the couple's, else
    the addressee's; the other one goes (D-48). Without either, the couple follows the admins'
    order."""
    requester = await walking_order_repo.of_owner(session, OwnerKey(None, requester_id))
    addressee = await walking_order_repo.of_owner(session, OwnerKey(None, addressee_id))
    stays, goes = (requester, addressee) if requester else (addressee, requester)
    for entry in goes:
        await session.delete(entry)
    for entry in stays:
        entry.couple_id, entry.user_id, entry.updated_at = couple_id, None, now


async def on_couple_ended(
    session: AsyncSession, user_ids: Sequence[str], *, couple_id: str, now: datetime
) -> None:
    """Runs when a couple ends, before its rows are deleted (CPL-05): each of them keeps a copy
    of the couple's own order, "neu" marks included, and the couple's goes (D-48)."""
    for entry in await walking_order_repo.of_owner(session, OwnerKey(couple_id, None)):
        session.add_all(
            WalkingOrderEntry(
                user_id=user_id,
                category_id=entry.category_id,
                position=entry.position,
                is_new=entry.is_new,
                created_at=entry.created_at,
                updated_at=now,
            )
            for user_id in user_ids
        )
        await session.delete(entry)
