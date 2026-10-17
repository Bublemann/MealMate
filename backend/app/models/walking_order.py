from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class WalkingOrderEntry(IdMixin, TimestampMixin, Base):
    """A category's place in an own walking order (REF-01, D-48).

    The order belongs to an accepted couple (`couple_id`) or to a user without one
    (`user_id`), and holds a category once. An owner without entries follows the admins'
    order. Every category that isn't deleted has an entry, a deleted one keeps the position it
    had (`domain.walking_order`). `is_new`: an admin added the category after the order was
    saved, and nobody has moved it since.
    """

    __tablename__ = "walking_order_entries"
    __table_args__ = (
        CheckConstraint("(couple_id IS NULL) <> (user_id IS NULL)", name="one_owner"),
        CheckConstraint("position >= 0", name="position"),
        Index(
            "uq_walking_order_entries_couple_id_category_id",
            "couple_id",
            "category_id",
            unique=True,
            sqlite_where=text("couple_id IS NOT NULL"),
        ),
        Index(
            "uq_walking_order_entries_user_id_category_id",
            "user_id",
            "category_id",
            unique=True,
            sqlite_where=text("user_id IS NOT NULL"),
        ),
    )

    couple_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("couples.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("categories.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)
