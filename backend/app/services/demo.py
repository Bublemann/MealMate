"""Demo data for development and the migration tests (`mealmate seed-demo`, plan § 5.11).

M2 part: an admin, a couple, a single user and one open invite. Later milestones add
ingredients, meals, lists and history.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.passwords import hash_password
from app.models import Couple, CoupleMember
from app.repositories import users as users_repo
from app.schemas.users import Language, Role
from app.services import accounts, codes
from app.services.context import AuthConfig

DEMO_USERS: tuple[tuple[str, str, Role, Language], ...] = (
    ("admin", "Admin", "admin", "de"),
    ("anna", "Anna", "user", "de"),
    ("ben", "Ben", "user", "en"),
    ("carl", "Carl", "user", "de"),
)
DEMO_COUPLE = ("anna", "ben")


class DemoRefusedError(RuntimeError):
    """The database already has users; demo data is only for empty installations."""


@dataclass(frozen=True, repr=False)
class DemoSeed:
    password: str
    invite_url: str


async def seed_demo(session: AsyncSession, config: AuthConfig, *, now: datetime) -> DemoSeed:
    codes.require_public_url(config)
    password = secrets.token_urlsafe(12)  # the same random password for every demo user
    password_hash = await hash_password(password, rounds=config.bcrypt_rounds)
    async with session.begin():
        if await users_repo.any_exists(session):
            raise DemoRefusedError("the database already has users")
        ids: dict[str, str] = {}
        for username, display_name, role, language in DEMO_USERS:
            user = await accounts.insert_user(
                session,
                username=username,
                display_name=display_name,
                password_hash=password_hash,
                role=role,
                language=language,
                now=now,
            )
            ids[username] = user.id
        requester, addressee = (ids[name] for name in DEMO_COUPLE)
        couple = Couple(
            requester_id=requester,
            addressee_id=addressee,
            status="accepted",
            accepted_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(couple)
        await session.flush()
        session.add_all(
            [
                CoupleMember(user_id=requester, couple_id=couple.id),
                CoupleMember(user_id=addressee, couple_id=couple.id),
            ]
        )
    invite = await codes.create_invite(
        session, config, actor_id=ids["admin"], tailscale_share_url=None, now=now
    )
    return DemoSeed(password=password, invite_url=invite.url)
