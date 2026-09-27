from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime

COUPLE_STATUSES = ("pending", "accepted")


class Couple(IdMixin, TimestampMixin, Base):
    """A couple request (`pending`) or a couple (`accepted`) (CPL-01).

    Declined and cancelled requests and ended couples are deleted.
    """

    __tablename__ = "couples"
    __table_args__ = (CheckConstraint("status IN ('pending', 'accepted')", name="status"),)

    requester_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    addressee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(10), default="pending")
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class CoupleMember(Base):
    """Both members of an accepted couple; the primary key enforces one couple per user."""

    __tablename__ = "couple_members"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    couple_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("couples.id", ondelete="CASCADE"), index=True
    )
