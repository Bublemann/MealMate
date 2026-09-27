"""Couple requests and couples (CPL-01, CPL-05, CPL-07).

A user is in at most one couple (enforced by `couple_members`' primary key) and has at most one
outgoing pending request. Accepting cancels every other pending request involving either user.
All checks run inside the write transaction, which holds the write lock (`BEGIN IMMEDIATE`).
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ApiError,
    ErrorCode,
    FieldErrorCode,
    FieldProblem,
    not_found,
    validation_error,
)
from app.models import Couple
from app.repositories import couples as couples_repo
from app.repositories import users as users_repo
from app.schemas.couples import CoupleRequest, CoupleState
from app.services import access, hooks
from app.services.principal import Principal
from app.services.users import user_refs


def _conflict(code: ErrorCode) -> ApiError:
    return ApiError(code, status_code=409)


async def _state(session: AsyncSession, user_id: str) -> CoupleState:
    couple = await couples_repo.accepted_for(session, user_id)
    partner_id = await access.partner_id(session, user_id)
    outgoing = await couples_repo.pending_outgoing(session, user_id)
    incoming = await couples_repo.pending_incoming(session, user_id)
    requests = ([outgoing] if outgoing else []) + list(incoming)
    refs = await user_refs(
        session,
        [partner_id, *(r.requester_id for r in requests), *(r.addressee_id for r in requests)],
    )

    def request(item: Couple) -> CoupleRequest:
        return CoupleRequest(
            id=item.id,
            from_user=refs[item.requester_id],
            to_user=refs[item.addressee_id],
            created_at=item.created_at,
        )

    return CoupleState(
        partner=refs.get(partner_id) if partner_id else None,
        since=couple.accepted_at if couple else None,
        outgoing=request(outgoing) if outgoing else None,
        incoming=[request(item) for item in incoming],
    )


async def get_state(session: AsyncSession, principal: Principal) -> CoupleState:
    async with session.begin():
        return await _state(session, principal.user_id)


async def send_request(
    session: AsyncSession, principal: Principal, target_id: str, *, now: datetime
) -> CoupleState:
    """Ask an active user to form a couple (CPL-01)."""
    if target_id == principal.user_id:
        raise validation_error([FieldProblem(("body", "user_id"), FieldErrorCode.INVALID)])
    async with session.begin():
        if await couples_repo.accepted_for(session, principal.user_id) is not None:
            raise _conflict(ErrorCode.COUPLE_ALREADY_IN_COUPLE)
        target = await users_repo.get(session, target_id)
        if target is None or not target.is_active:
            raise not_found()
        if await couples_repo.accepted_for(session, target.id) is not None:
            raise _conflict(ErrorCode.COUPLE_TARGET_IN_COUPLE)
        if (
            await couples_repo.pending_outgoing(session, principal.user_id) is not None
            or await couples_repo.pending_between(session, principal.user_id, target.id) is not None
        ):
            raise _conflict(ErrorCode.COUPLE_REQUEST_PENDING)
        session.add(
            Couple(
                requester_id=principal.user_id,
                addressee_id=target.id,
                status="pending",
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()
        return await _state(session, principal.user_id)


async def _pending(session: AsyncSession, request_id: str) -> Couple | None:
    request = await couples_repo.get(session, request_id)
    return request if request is not None and request.status == "pending" else None


async def accept(
    session: AsyncSession, principal: Principal, request_id: str, *, now: datetime
) -> CoupleState:
    """The addressee accepts; all other pending requests of both users are cancelled."""
    async with session.begin():
        request = await _pending(session, request_id)
        if request is None or request.addressee_id != principal.user_id:
            raise not_found()
        if await couples_repo.accepted_for(session, principal.user_id) is not None:
            raise _conflict(ErrorCode.COUPLE_ALREADY_IN_COUPLE)
        if await couples_repo.accepted_for(session, request.requester_id) is not None:
            raise _conflict(ErrorCode.COUPLE_TARGET_IN_COUPLE)
        request.status = "accepted"
        request.accepted_at = now
        request.updated_at = now
        await session.flush()
        await couples_repo.delete_pending_involving(
            session, request.requester_id, request.addressee_id
        )
        couples_repo.add_members(session, request)
        await session.flush()
        return await _state(session, principal.user_id)


async def decline(session: AsyncSession, principal: Principal, request_id: str) -> CoupleState:
    """The addressee declines; the request is deleted."""
    async with session.begin():
        request = await _pending(session, request_id)
        if request is None or request.addressee_id != principal.user_id:
            raise not_found()
        await session.delete(request)
        await session.flush()
        return await _state(session, principal.user_id)


async def cancel(session: AsyncSession, principal: Principal, request_id: str) -> CoupleState:
    """The requester withdraws the request."""
    async with session.begin():
        request = await _pending(session, request_id)
        if request is None or request.requester_id != principal.user_id:
            raise not_found()
        await session.delete(request)
        await session.flush()
        return await _state(session, principal.user_id)


async def end_couple(session: AsyncSession, couple: Couple, *, now: datetime) -> None:
    """End a couple inside the caller's transaction (CPL-05): hook first, then the rows."""
    await hooks.on_couple_ended(session, couple.requester_id, couple.addressee_id, now=now)
    await couples_repo.delete_couple(session, couple)


async def end(session: AsyncSession, principal: Principal, *, now: datetime) -> None:
    """Either partner ends the couple, also when the other one is deactivated (CPL-05/07)."""
    async with session.begin():
        couple = await couples_repo.accepted_for(session, principal.user_id)
        if couple is None:
            raise not_found()
        await end_couple(session, couple, now=now)
