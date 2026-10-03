from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime
from app.domain.catalog import (
    CATEGORY_NAME_MAX_LENGTH,
    CUISINE_NAME_MAX_LENGTH,
    NAME_NORM_FACTOR,
    TAG_NAME_MAX_LENGTH,
)

# Each name is unique among the categories that aren't deleted, so a deleted one's names can be
# used again (REF-01).
_NOT_DELETED = text("deleted_at IS NULL")


class Category(IdMixin, TimestampMixin, Base):
    """A shop category (REF-01) with one name per UI language (I18N-04, D-31). Each name's
    normalised form is unique in its language among the categories that aren't deleted: a
    partial unique index.

    Seeded categories have a `key`, which identifies *Other* and *Uncategorized* and drives the
    Open Food Facts guess; the ones admins add have none. `deleted_at` marks a deleted category
    (D-30): it stays, because lists being shopped and done lists still show it, and keeps its
    last `sort_order`. The service keeps the `sort_order` of the others contiguous (0..n-1);
    admins change it (ADM-01).
    """

    __tablename__ = "categories"
    __table_args__ = (
        Index("ix_categories_name_de_norm", "name_de_norm", unique=True, sqlite_where=_NOT_DELETED),
        Index("ix_categories_name_en_norm", "name_en_norm", unique=True, sqlite_where=_NOT_DELETED),
    )

    key: Mapped[str | None] = mapped_column(String(40), unique=True)
    name_de: Mapped[str] = mapped_column(String(CATEGORY_NAME_MAX_LENGTH))
    name_de_norm: Mapped[str] = mapped_column(String(CATEGORY_NAME_MAX_LENGTH * NAME_NORM_FACTOR))
    name_en: Mapped[str] = mapped_column(String(CATEGORY_NAME_MAX_LENGTH))
    name_en_norm: Mapped[str] = mapped_column(String(CATEGORY_NAME_MAX_LENGTH * NAME_NORM_FACTOR))
    sort_order: Mapped[int] = mapped_column(Integer)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


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
