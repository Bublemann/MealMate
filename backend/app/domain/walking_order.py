"""Where a category comes in a walking order (REF-01, D-48).

Admins keep the default order in the categories' `sort_order`. A couple, or a user without
one, may keep an own order instead, as each category's position in it. Every category that
isn't deleted has a position there (one an admin adds goes to the end); a deleted one keeps
the position it had, or its `sort_order` if it was deleted before the own order was saved. In
both orders the positions of the categories that aren't deleted run 0..n-1, so a deleted
category shares its position with the category that took over its place and comes right after
it (D-30).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class WalkingOrder:
    """A viewer's walking order: the admins' one (no `positions`) or an own one, as each
    category's position by id."""

    positions: Mapping[str, int] = field(default_factory=dict)

    @property
    def follows_admin(self) -> bool:
        return not self.positions

    def sort_key(self, category_id: str, sort_order: int, deleted: bool) -> tuple[int, bool, str]:
        """Where a category comes: by its position (its `sort_order` where this order has none),
        then not deleted before deleted, then by id, so ties break the same way every time
        (AGG-05)."""
        return (self.positions.get(category_id, sort_order), deleted, category_id)


ADMINS_ORDER = WalkingOrder()
