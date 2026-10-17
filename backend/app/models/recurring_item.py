from datetime import date

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class RecurringItem(IdMixin, TimestampMixin, Base):
    """An ingredient a user, or a couple together, buys again and again (LIST-16, D-42).

    It belongs to one set: an accepted couple's (`couple_id`) or a user's without one
    (`user_id`), and each set holds an ingredient once. `interval_days` is the interval the
    user set, in days, by hand while `interval_manual`; otherwise the average of
    `measured_intervals` serves from two on (`domain.recurring`). Only the last purchase is kept:
    its date in the instance's time zone, its amount and unit when it was one amount, the list
    it came from (so a list counts once), and the last three intervals between purchases, a
    JSON list that is never null.
    """

    __tablename__ = "recurring_items"
    __table_args__ = (
        CheckConstraint("(couple_id IS NULL) <> (user_id IS NULL)", name="one_owner"),
        CheckConstraint("interval_days >= 1", name="interval_days"),
        CheckConstraint("last_amount IS NULL OR last_amount > 0", name="last_amount"),
        CheckConstraint("last_unit IS NULL OR last_amount IS NOT NULL", name="unit_needs_amount"),
        CheckConstraint("json_type(measured_intervals) = 'array'", name="measured_intervals"),
        Index(
            "uq_recurring_items_couple_id_ingredient_id",
            "couple_id",
            "ingredient_id",
            unique=True,
            sqlite_where=text("couple_id IS NOT NULL"),
        ),
        Index(
            "uq_recurring_items_user_id_ingredient_id",
            "user_id",
            "ingredient_id",
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
    ingredient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingredients.id", ondelete="CASCADE"), index=True
    )
    interval_days: Mapped[int] = mapped_column(Integer)
    interval_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    last_purchased_on: Mapped[date] = mapped_column(Date)
    last_amount: Mapped[float | None] = mapped_column(Float)
    last_unit: Mapped[str | None] = mapped_column(String(10))
    measured_intervals: Mapped[list[int]] = mapped_column(JSON, default=list)
    last_list_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("shopping_lists.id", ondelete="SET NULL"), index=True
    )
