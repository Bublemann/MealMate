from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime

CODE_KINDS = ("invite", "reset")


class OneTimeCode(IdMixin, TimestampMixin, Base):
    """An invite (ACC-01..04) or password reset link (ACC-10), stored as its HMAC."""

    __tablename__ = "one_time_codes"
    __table_args__ = (CheckConstraint("kind IN ('invite', 'reset')", name="kind"),)

    kind: Mapped[str] = mapped_column(String(10))
    code_hmac: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Reset codes only: whose password the code resets.
    target_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    used_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Invites only: the Tailscale share link that step 1 of the invite message points to.
    tailscale_share_url: Mapped[str | None] = mapped_column(String(500))
