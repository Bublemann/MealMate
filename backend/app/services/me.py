"""The own account: profile, language, privacy, filter chips, password, sessions (ACC-09,
ACC-10, ACC-13, VIS-02, I18N-01)."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, ErrorCode, FieldProblem, not_found, validation_error
from app.core.passwords import hash_password, verify_password
from app.core.ratelimit import LoginThrottle
from app.domain.accounts import clean_display_name, display_name_problem
from app.domain.text import normalize
from app.models import User
from app.repositories import sessions as sessions_repo
from app.repositories import users as users_repo
from app.schemas.users import FilterHidden, Me, MeUpdate, SecurityInfo, SessionInfo
from app.services import accounts, hooks
from app.services.auth import start_attempt
from app.services.context import AuthConfig
from app.services.principal import Principal
from app.services.users import user_ref


async def _user(session: AsyncSession, principal: Principal) -> User:
    user = await users_repo.get(session, principal.user_id)
    if user is None:  # pragma: no cover -- authentication has just loaded this user
        raise ApiError(ErrorCode.SESSION_REVOKED, status_code=401)
    return user


async def get_me(session: AsyncSession, principal: Principal) -> Me:
    async with session.begin():
        return Me.model_validate(await _user(session, principal))


def _dedupe(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def _filter_hidden(value: FilterHidden) -> dict[str, list[str]]:
    return {"meals": _dedupe(value.meals), "lists": _dedupe(value.lists)}


async def update_me(
    session: AsyncSession, principal: Principal, update: MeUpdate, *, now: datetime
) -> Me:
    """Change the fields that were sent. Switching *meals public* or *lists public* off runs the
    matching hook, which later milestones use to detach meals from others' lists (§ 6)."""
    if update.display_name is not None and (problem := display_name_problem(update.display_name)):
        raise validation_error([FieldProblem(("body", "display_name"), problem)])
    async with session.begin():
        user = await _user(session, principal)
        if update.display_name is not None:
            display_name = clean_display_name(update.display_name)
            await accounts.check_display_name_free(session, display_name, except_user_id=user.id)
            user.display_name = display_name
            user.display_name_norm = normalize(display_name)
        if update.language is not None:
            user.language = update.language
        if update.meals_public is not None:
            if user.meals_public and not update.meals_public:
                await hooks.on_meals_made_private(session, user.id)
            user.meals_public = update.meals_public
        if update.lists_public is not None:
            if user.lists_public and not update.lists_public:
                await hooks.on_lists_made_private(session, user.id)
            user.lists_public = update.lists_public
        if update.filter_hidden is not None:
            user.filter_hidden = _filter_hidden(update.filter_hidden)
        user.updated_at = now
        await session.flush()
        return Me.model_validate(user)


async def change_password(
    session: AsyncSession,
    config: AuthConfig,
    throttle: LoginThrottle,
    principal: Principal,
    *,
    current_password: str,
    new_password: str,
    client_ip: str,
    now: datetime,
) -> None:
    """Change the password and log out all *other* devices (ACC-09). Guesses at the current
    password count towards the login throttle of the user and the client (ACC-11)."""
    async with session.begin():
        user = await _user(session, principal)
        old_hash, username = user.password_hash, user.username
    attempt = start_attempt(throttle, username=username, client_ip=client_ip)
    if not await verify_password(current_password, old_hash, rounds=config.bcrypt_rounds):
        raise ApiError(ErrorCode.PASSWORD_INCORRECT, status_code=403)
    attempt.succeeded()
    if problems := accounts.check_password(
        new_password, username=username, loc=("body", "new_password")
    ):
        raise validation_error(problems)
    new_hash = await hash_password(new_password, rounds=config.bcrypt_rounds)

    session.expire_all()
    async with session.begin():
        user = await _user(session, principal)
        if user.password_hash != old_hash:
            # Changed or reset meanwhile; the current password we checked is no longer it.
            raise ApiError(ErrorCode.PASSWORD_INCORRECT, status_code=403)
        user.password_hash = new_hash
        user.password_changed_at = now
        await sessions_repo.revoke_for_user(
            session, user.id, now, except_session_id=principal.session_id
        )


async def list_sessions(
    session: AsyncSession, principal: Principal, *, now: datetime
) -> list[SessionInfo]:
    async with session.begin():
        live = await sessions_repo.live_for_user(session, principal.user_id, now)
    return [
        SessionInfo(
            id=item.id,
            user_agent=item.user_agent,
            created_at=item.created_at,
            last_used_at=item.last_used_at,
            current=item.id == principal.session_id,
        )
        for item in live
    ]


async def revoke_session(
    session: AsyncSession, principal: Principal, session_id: str, *, now: datetime
) -> None:
    """Log out one device; 404 unless it is a live session of the caller."""
    async with session.begin():
        target = await sessions_repo.get(session, session_id)
        if (
            target is None
            or target.user_id != principal.user_id
            or target.revoked_at is not None
            or target.expires_at <= now
        ):
            raise not_found()
        target.revoked_at = now


async def security_info(session: AsyncSession, principal: Principal) -> SecurityInfo:
    async with session.begin():
        user = await _user(session, principal)
        reset_by = None
        if user.password_reset_by is not None:
            admin = await users_repo.get(session, user.password_reset_by)
            reset_by = None if admin is None else user_ref(admin)
        return SecurityInfo(
            password_changed_at=user.password_changed_at,
            password_reset_at=user.password_reset_at,
            password_reset_by=reset_by,
        )
