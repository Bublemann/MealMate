"""Password hashing with bcrypt and the bundled common-password list (plan § 5.4, ACC-06).

bcrypt is deliberately slow, so it runs in a worker thread and never blocks the event loop.
"""

from functools import cache
from importlib import resources

import anyio.to_thread
import bcrypt

from app.domain.accounts import PASSWORD_MAX_BYTES

COMMON_PASSWORDS_RESOURCE = "common-passwords.txt"


@cache
def common_passwords() -> frozenset[str]:
    """The top 10k common passwords, lowercased (`app/core/resources/common-passwords.txt`)."""
    text = resources.files("app.core.resources").joinpath(COMMON_PASSWORDS_RESOURCE).read_text()
    lines = (line.strip() for line in text.splitlines())
    return frozenset(line for line in lines if line and not line.startswith("#"))


def _hash(password: str, rounds: int) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds)).decode()


def _verify(password: str, password_hash: str) -> bool:
    encoded = password.encode()
    if len(encoded) > PASSWORD_MAX_BYTES:
        # bcrypt >= 5 refuses such input; no stored password can be that long anyway.
        return False
    return bcrypt.checkpw(encoded, password_hash.encode())


@cache
def _dummy_hash(rounds: int) -> str:
    return _hash("mealmate-dummy-password", rounds)


def _verify_dummy(password: str, rounds: int) -> bool:
    _verify(password, _dummy_hash(rounds))
    return False


async def hash_password(password: str, *, rounds: int) -> str:
    return await anyio.to_thread.run_sync(_hash, password, rounds)


async def verify_password(password: str, password_hash: str | None, *, rounds: int) -> bool:
    """Whether `password` matches. Without a hash (unknown user) the same work is done against
    a dummy hash, so response times do not reveal which usernames exist."""
    if password_hash is None:
        return await anyio.to_thread.run_sync(_verify_dummy, password, rounds)
    return await anyio.to_thread.run_sync(_verify, password, password_hash)
