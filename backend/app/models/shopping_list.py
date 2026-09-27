from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime
from app.domain.catalog import INGREDIENT_NAME_MAX_LENGTH
from app.domain.lists import (
    AMOUNT_TEXT_MAX_LENGTH,
    EXTRA_TEXT_MAX_LENGTH,
    LINE_KEY_MAX_LENGTH,
    LIST_NAME_MAX_LENGTH,
)
from app.domain.meals import MEAL_NAME_MAX_LENGTH, ROW_NOTE_MAX_LENGTH


class ShoppingList(IdMixin, TimestampMixin, Base):
    """A shopping list of one owner (LIST-01, LIST-10); its partner and other users see it by
    the rules of `services.access` (CPL-02..04, VIS-02/03).

    `name` null shows the translated default name (LIST-02). `version` is incremented in SQL
    (`version + 1`) on every change of the list or anything in it, together with `updated_at`
    ("most recently edited first", UI-02). `reminder_seed` picks the reminder (LIST-14).
    `shopping_started_at` and `finished_at` belong to shopping mode and history (M5b).
    """

    __tablename__ = "shopping_lists"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'shopping', 'done')", name="status"),
        CheckConstraint("version >= 0", name="version"),
        CheckConstraint("reminder_seed >= 0 AND reminder_seed <= 9999", name="reminder_seed"),
    )

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(LIST_NAME_MAX_LENGTH))
    status: Mapped[str] = mapped_column(String(10), default="draft")
    shared_with_partner: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=0)
    reminder_seed: Mapped[int] = mapped_column(Integer)
    shopping_started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ListMeal(IdMixin, TimestampMixin, Base):
    """A meal on a list with its servings (LIST-03/04), at `position` in the order of adding.

    A live list meal (`meal_id` set, `frozen_at` null) contributes the meal's current rows. A
    frozen one contributes its `list_meal_ingredients`; a detached one (LIST-15) is frozen and
    has lost its meal (`meal_id` null, `detached_reason` set). The snapshots are taken when the
    meal is added and refreshed when it is frozen; `meal_owner_id_snapshot` decides who may see
    a detached meal's details (VIS-06). A meal is on a list at most once while it exists.
    `added_by` and `last_added_at` say who added it last and when, also when it was added again
    (LIST-04): the "recently used" meals (MEAL-09).
    """

    __tablename__ = "list_meals"
    __table_args__ = (
        CheckConstraint("servings >= 1 AND servings <= 99", name="servings"),
        CheckConstraint("meal_servings_snapshot >= 1", name="meal_servings_snapshot"),
        CheckConstraint("position >= 0", name="position"),
        CheckConstraint(
            "detached_reason IS NULL OR detached_reason IN ('deleted', 'unavailable')",
            name="detached_reason",
        ),
        Index(
            "uq_list_meals_list_id_meal_id",
            "list_id",
            "meal_id",
            unique=True,
            sqlite_where=text("meal_id IS NOT NULL"),
        ),
    )

    list_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shopping_lists.id", ondelete="CASCADE"), index=True
    )
    meal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("meals.id", ondelete="SET NULL"), index=True
    )
    servings: Mapped[int] = mapped_column(Integer)
    meal_servings_snapshot: Mapped[int] = mapped_column(Integer)
    meal_name_snapshot: Mapped[str] = mapped_column(String(MEAL_NAME_MAX_LENGTH))
    meal_owner_id_snapshot: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    added_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    last_added_at: Mapped[datetime] = mapped_column(UTCDateTime())
    frozen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    detached_reason: Mapped[str | None] = mapped_column(String(12))
    position: Mapped[int] = mapped_column(Integer)


class ListMealIngredient(IdMixin, TimestampMixin, Base):
    """The frozen copy of a meal's row (LIST-11, LIST-15), with the ingredient attributes and
    category it was calculated with. Ingredients referenced here cannot be deleted (ING-05)."""

    __tablename__ = "list_meal_ingredients"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position"),
        CheckConstraint("amount IS NULL OR amount > 0", name="amount"),
        CheckConstraint("unit IS NULL OR amount IS NOT NULL", name="unit_needs_amount"),
        CheckConstraint("base_unit_snapshot IN ('g', 'ml')", name="base_unit_snapshot"),
        UniqueConstraint("list_meal_id", "position"),
    )

    list_meal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("list_meals.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    ingredient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingredients.id", ondelete="RESTRICT"), index=True
    )
    ingredient_name_snapshot: Mapped[str] = mapped_column(String(INGREDIENT_NAME_MAX_LENGTH))
    base_unit_snapshot: Mapped[str] = mapped_column(String(2))
    piece_weight_g_snapshot: Mapped[float | None] = mapped_column(Float)
    density_snapshot: Mapped[float | None] = mapped_column(Float)
    category_id_snapshot: Mapped[str] = mapped_column(
        String(36), ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    amount: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(String(ROW_NOTE_MAX_LENGTH))


class ListExtraItem(IdMixin, TimestampMixin, Base):
    """An extra item on a list (LIST-06): linked to an ingredient (merges with its line, with
    an optional amount and unit) or free text (its own line, with an optional free-text amount
    and a category, *Other* by default).

    The id may come from the client (any UUID), so adding is idempotent. Deleting sets
    `deleted_at` (a tombstone for offline clients, SYNC). `attrs_snapshot` holds the
    ingredient attributes once the list has left `draft` (M5b).
    """

    __tablename__ = "list_extra_items"
    __table_args__ = (
        CheckConstraint("(ingredient_id IS NULL) <> (text IS NULL)", name="ingredient_or_text"),
        CheckConstraint("amount IS NULL OR amount > 0", name="amount"),
        CheckConstraint("unit IS NULL OR amount IS NOT NULL", name="unit_needs_amount"),
        CheckConstraint("amount IS NULL OR amount_text IS NULL", name="amount_or_amount_text"),
    )

    list_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shopping_lists.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ingredients.id", ondelete="RESTRICT"), index=True
    )
    attrs_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    text: Mapped[str | None] = mapped_column(String(EXTRA_TEXT_MAX_LENGTH))
    amount: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(10))
    amount_text: Mapped[str | None] = mapped_column(String(AMOUNT_TEXT_MAX_LENGTH))
    category_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    added_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ListLineState(Base):
    """The state of one line of a list, by line key (plan § 5.7): hidden in the draft
    (LIST-07), and checked off while shopping (M5b). A row may outlive its line, so the state
    comes back with it."""

    __tablename__ = "list_line_states"

    list_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shopping_lists.id", ondelete="CASCADE"), primary_key=True
    )
    line_key: Mapped[str] = mapped_column(String(LINE_KEY_MAX_LENGTH), primary_key=True)
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    checked_op_id: Mapped[str | None] = mapped_column(String(36))
    checked_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    checked_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)


class ProcessedOp(Base):
    """An op of shopping mode that was applied (plan § 5.8): the same user sending it again
    changes nothing (SYNC-05). Op ids are the clients', so they are unique per user only.
    Rejected ops are not recorded, since they may succeed later. Rows older than 30 days are
    pruned by the cleanup job."""

    __tablename__ = "processed_ops"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    op_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    list_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("shopping_lists.id", ondelete="CASCADE"), index=True
    )
    applied_at: Mapped[datetime] = mapped_column(UTCDateTime())
