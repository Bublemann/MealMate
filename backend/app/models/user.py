from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime


def empty_filter_hidden() -> dict[str, list[str]]:
    return {"meals": [], "lists": [], "list_states": []}


class User(IdMixin, TimestampMixin, Base):
    """An account (ACC). Usernames log in; display names are what others see."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="role"),
        CheckConstraint("language IN ('de', 'en')", name="language"),
    )

    username: Mapped[str] = mapped_column(String(30))
    username_norm: Mapped[str] = mapped_column(String(30), unique=True)
    display_name: Mapped[str] = mapped_column(String(40))
    display_name_norm: Mapped[str] = mapped_column(String(160), unique=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(10), default="user")
    language: Mapped[str] = mapped_column(String(2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    meals_public: Mapped[bool] = mapped_column(Boolean, default=True)
    lists_public: Mapped[bool] = mapped_column(Boolean, default=True)
    # What this user's saved filters hide (`schemas.users.FilterHidden`, plan § 6):
    # {"meals": [user ids], "lists": [user ids], "list_states": [list states]}.
    filter_hidden: Mapped[dict[str, Any]] = mapped_column(JSON, default=empty_filter_hidden)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    password_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    password_reset_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    password_reset_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
