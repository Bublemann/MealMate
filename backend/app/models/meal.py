from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.domain.catalog import NAME_NORM_FACTOR
from app.domain.meals import MEAL_NAME_MAX_LENGTH, ROW_NOTE_MAX_LENGTH, SOURCE_URL_MAX_LENGTH

# `photo_key` is a uuid4 in hex; the files are `<key>.webp` and `<key>-thumb.webp` (§ 5.10).
PHOTO_KEY_LENGTH = 32


class Meal(IdMixin, TimestampMixin, Base):
    """A meal of one owner (MEAL-02, CPL-06); others see it by the visibility rules (VIS-01).

    `copied_from_meal_id` remembers the original of a copy ("based on", MEAL-08) and becomes
    null when the original is deleted. The photo files live in the media directory under
    `photo_key`; the cleanup job removes files no meal refers to.
    """

    __tablename__ = "meals"
    __table_args__ = (CheckConstraint("servings >= 1", name="servings"),)

    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(MEAL_NAME_MAX_LENGTH))
    name_norm: Mapped[str] = mapped_column(
        String(MEAL_NAME_MAX_LENGTH * NAME_NORM_FACTOR), index=True
    )
    instructions: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(SOURCE_URL_MAX_LENGTH))
    servings: Mapped[int] = mapped_column(Integer, default=1)
    cuisine_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cuisines.id", ondelete="SET NULL"), index=True
    )
    photo_key: Mapped[str | None] = mapped_column(String(PHOTO_KEY_LENGTH))
    copied_from_meal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("meals.id", ondelete="SET NULL"), index=True
    )


class MealIngredient(IdMixin, TimestampMixin, Base):
    """One ingredient row of a meal, at `position` 0..n-1 (MEAL-02).

    An amount without a unit is stored as pieces; a unit needs an amount. The same ingredient
    may appear in several rows. Ingredients referenced here cannot be deleted (ING-05).
    """

    __tablename__ = "meal_ingredients"
    __table_args__ = (
        CheckConstraint("position >= 0", name="position"),
        CheckConstraint("amount IS NULL OR amount > 0", name="amount"),
        CheckConstraint("unit IS NULL OR amount IS NOT NULL", name="unit_needs_amount"),
        UniqueConstraint("meal_id", "position"),
    )

    meal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meals.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    ingredient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingredients.id", ondelete="RESTRICT"), index=True
    )
    amount: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(String(ROW_NOTE_MAX_LENGTH))


class MealTag(Base):
    """A tag on a meal (REF-04); tags themselves are one shared pool."""

    __tablename__ = "meal_tags"

    meal_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meals.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True
    )
