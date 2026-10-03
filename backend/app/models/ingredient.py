from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime
from app.domain.catalog import (
    BRAND_MAX_LENGTH,
    INGREDIENT_NAME_MAX_LENGTH,
    NAME_NORM_FACTOR,
    QUANTITY_TEXT_MAX_LENGTH,
)
from app.domain.nutrients import NUTRIENT_KEYS
from app.domain.units import IngredientAttrs


class NutrientColumns:
    """One nullable float column per nutrient of the registry, named by its key (MNT-06).

    The columns are added below by looping over the registry, so they are accessed through
    `nutrients()` and `set_nutrient()` rather than as typed attributes.
    """

    def nutrients(self) -> dict[str, float | None]:
        return {key: getattr(self, key) for key in NUTRIENT_KEYS}

    def set_nutrient(self, key: str, value: float | None) -> None:
        if key not in NUTRIENT_KEYS:
            raise KeyError(key)
        setattr(self, key, value)

    def set_nutrients(self, values: Mapping[str, float | None]) -> None:
        for key, value in values.items():
            self.set_nutrient(key, value)


for _key in NUTRIENT_KEYS:
    setattr(NutrientColumns, _key, mapped_column(Float, nullable=True))


class Ingredient(IdMixin, TimestampMixin, NutrientColumns, Base):
    """A shared ingredient, editable by everyone like a wiki (ING-01, ING-02). There is one kind
    of ingredient: typed by hand ("Zwiebeln"), with a brand ("Eier", "REWE"), or scanned and
    taken from Open Food Facts with its barcode.

    The nutrient columns are the ingredient's own values per 100 g, or per 100 ml for base unit
    `ml` (NUT-02); null is unknown. A `piece` ingredient's pieces count through its piece weight
    (NUT-05). Names are not unique: two brands of the same thing are two
    ingredients with the same name. A barcode belongs to at most one ingredient.

    The Open Food Facts columns only matter for `source` off: `user_edited_fields` lists the
    fields a user changed (`name`, `nutrients.kcal`, ...), which a refresh never overwrites
    (BAR-04); `pending_update` holds newer Open Food Facts values for those (BAR-06), see
    `services.off_fields`. `quantity_text`, `pack_quantity` and `pack_unit` are information only.
    """

    __tablename__ = "ingredients"
    __table_args__ = (
        CheckConstraint("base_unit IN ('g', 'ml', 'piece')", name="base_unit"),
        CheckConstraint("source IN ('off', 'manual')", name="source"),
    )

    name: Mapped[str] = mapped_column(String(INGREDIENT_NAME_MAX_LENGTH))
    name_norm: Mapped[str] = mapped_column(
        String(INGREDIENT_NAME_MAX_LENGTH * NAME_NORM_FACTOR), index=True
    )
    # Dictionary order by name, then brand (ING-03, `domain.text.sort_key`).
    name_sort: Mapped[str] = mapped_column(
        String(INGREDIENT_NAME_MAX_LENGTH * NAME_NORM_FACTOR), index=True
    )
    brand: Mapped[str | None] = mapped_column(String(BRAND_MAX_LENGTH))
    brand_norm: Mapped[str | None] = mapped_column(String(BRAND_MAX_LENGTH * NAME_NORM_FACTOR))
    brand_sort: Mapped[str | None] = mapped_column(String(BRAND_MAX_LENGTH * NAME_NORM_FACTOR))
    barcode: Mapped[str | None] = mapped_column(String(14), unique=True)
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    base_unit: Mapped[str] = mapped_column(String(5), default="g")
    # Only used for `piece` (D-32); a g or ml ingredient may still have one from before, and a
    # density, until the base-unit migration (D-34). See `attrs()`.
    piece_weight_g: Mapped[float | None] = mapped_column(Float)
    density_g_per_ml: Mapped[float | None] = mapped_column(Float)
    quantity_text: Mapped[str | None] = mapped_column(String(QUANTITY_TEXT_MAX_LENGTH))
    pack_quantity: Mapped[float | None] = mapped_column(Float)
    pack_unit: Mapped[str | None] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(10), default="manual")
    off_last_modified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    fetched_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    user_edited_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    pending_update: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ignored_off_modified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    def attrs(self) -> IngredientAttrs:
        """What calculations know about the ingredient as it is now (D-32): its base unit, and
        its piece weight when it is counted in pieces; never a density."""
        return IngredientAttrs.live(self.base_unit, self.piece_weight_g)
