"""Who owns data a couple shares: a user's couple while they are in one, else the user.

Recurring items (D-42) and the walking order (D-48) belong to such an owner, so both partners
of a couple see and change the same data. `services.access.owner_key` resolves a user's
current owner; repositories filter by it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OwnerKey:
    """An accepted couple (`couple_id`) or a user without one (`user_id`): exactly one is set."""

    couple_id: str | None
    user_id: str | None

    def __post_init__(self) -> None:
        if (self.couple_id is None) == (self.user_id is None):
            raise ValueError("an owner is exactly one of a couple and a user")
