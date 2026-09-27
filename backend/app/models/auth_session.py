from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, UTCDateTime, utcnow


class AuthSession(IdMixin, Base):
    """One logged-in device (plan § 5.4). `expires_at` slides: last use + SESSION_IDLE_DAYS.

    `parent_session_id` links a session made by a fork to the session it was forked from, so
    that detected token reuse revokes both (see `app.domain.sessions`).
    """

    __tablename__ = "sessions"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    last_used_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    user_agent: Mapped[str | None] = mapped_column(String(200))
    parent_session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="SET NULL"), index=True
    )


class SessionToken(IdMixin, Base):
    """A refresh token of a session, stored as its HMAC (§ 5.4: rotation, grace, fork)."""

    __tablename__ = "session_tokens"

    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    token_hmac: Mapped[str] = mapped_column(String(64), unique=True)
    issued_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    superseded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    forked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
