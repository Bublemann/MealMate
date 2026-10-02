from sqlalchemy import CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin
from app.domain.catalog import (
    CATEGORY_NAME_MAX_LENGTH,
    CUISINE_NAME_MAX_LENGTH,
    NAME_NORM_FACTOR,
    TAG_NAME_MAX_LENGTH,
)


class Category(IdMixin, TimestampMixin, Base):
    """A shop category (REF-01), seeded by migration with its `key`, and with one name per UI
    language (I18N-04, D-31). Each name's normalised form is unique in its language: a unique
    index rather than a constraint, so that the rule can come to cover only the categories that
    aren't deleted (plan § 6) without rebuilding the table.

    `sort_order` is kept contiguous (0..n-1) by the service; admins change it (ADM-01).
    """

    __tablename__ = "categories"

    key: Mapped[str] = mapped_column(String(40), unique=True)
    name_de: Mapped[str] = mapped_column(String(CATEGORY_NAME_MAX_LENGTH))
    name_de_norm: Mapped[str] = mapped_column(
        String(CATEGORY_NAME_MAX_LENGTH * NAME_NORM_FACTOR), unique=True, index=True
    )
    name_en: Mapped[str] = mapped_column(String(CATEGORY_NAME_MAX_LENGTH))
    name_en_norm: Mapped[str] = mapped_column(
        String(CATEGORY_NAME_MAX_LENGTH * NAME_NORM_FACTOR), unique=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer)


class Cuisine(IdMixin, TimestampMixin, Base):
    """A cuisine (REF-03): seeded ones have a translation `key`, user-added ones a `name`.

    `name_norm` is the key for seeded rows and the normalised name otherwise, so a user cannot
    add "Italian" twice, nor a second "italian" next to the seeded one.
    """

    __tablename__ = "cuisines"
    __table_args__ = (CheckConstraint("(key IS NULL) <> (name IS NULL)", name="key_or_name"),)

    key: Mapped[str | None] = mapped_column(String(40), unique=True)
    name: Mapped[str | None] = mapped_column(String(CUISINE_NAME_MAX_LENGTH))
    name_norm: Mapped[str] = mapped_column(
        String(CUISINE_NAME_MAX_LENGTH * NAME_NORM_FACTOR), unique=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )


class Tag(IdMixin, TimestampMixin, Base):
    """A free-text meal tag from one shared pool (REF-04), linked to meals by `meal_tags`.

    Tags are created when a meal first uses them and keep the spelling of their creator.
    """

    __tablename__ = "tags"

    name: Mapped[str] = mapped_column(String(TAG_NAME_MAX_LENGTH))
    name_norm: Mapped[str] = mapped_column(
        String(TAG_NAME_MAX_LENGTH * NAME_NORM_FACTOR), unique=True
    )
