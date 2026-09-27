from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime
from app.domain.catalog import (
    INGREDIENT_NAME_MAX_LENGTH,
    NAME_NORM_FACTOR,
    PRODUCT_BRAND_MAX_LENGTH,
    PRODUCT_NAME_MAX_LENGTH,
    PRODUCT_QUANTITY_TEXT_MAX_LENGTH,
)
from app.domain.nutrients import NUTRIENT_KEYS


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
    """A shared ingredient, editable by everyone like a wiki (ING-01, ING-02).

    The nutrient columns hold manual values (NUT-02). `base_unit` can only change while no
    product is linked.
    """

    __tablename__ = "ingredients"
    __table_args__ = (CheckConstraint("base_unit IN ('g', 'ml')", name="base_unit"),)

    name: Mapped[str] = mapped_column(String(INGREDIENT_NAME_MAX_LENGTH))
    name_norm: Mapped[str] = mapped_column(
        String(INGREDIENT_NAME_MAX_LENGTH * NAME_NORM_FACTOR), unique=True
    )
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    base_unit: Mapped[str] = mapped_column(String(2), default="g")
    piece_weight_g: Mapped[float | None] = mapped_column(Float)
    density_g_per_ml: Mapped[float | None] = mapped_column(Float)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )


class Product(IdMixin, TimestampMixin, NutrientColumns, Base):
    """A barcode linked to exactly one ingredient (ING-04), with nutrition per 100 g/ml.

    `user_edited_fields` lists the fields a user typed or changed (`name`, `nutrients.kcal`,
    ...), which an Open Food Facts refresh never overwrites (BAR-04); `pending_update` holds
    newer OFF values for those (BAR-06, M7). `pack_quantity`/`pack_unit` are kept for the
    postponed pack-rounding feature.
    """

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("nutrition_basis IN ('g', 'ml')", name="nutrition_basis"),
        CheckConstraint("source IN ('off', 'manual')", name="source"),
    )

    barcode: Mapped[str] = mapped_column(String(14), unique=True)
    ingredient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingredients.id", ondelete="RESTRICT"), index=True
    )
    nutrition_basis: Mapped[str] = mapped_column(String(2))
    name: Mapped[str | None] = mapped_column(String(PRODUCT_NAME_MAX_LENGTH))
    brand: Mapped[str | None] = mapped_column(String(PRODUCT_BRAND_MAX_LENGTH))
    quantity_text: Mapped[str | None] = mapped_column(String(PRODUCT_QUANTITY_TEXT_MAX_LENGTH))
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
