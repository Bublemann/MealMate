from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, UTCDateTime, utcnow


class Notice(IdMixin, Base):
    """A notice for one user, unread until they dismiss it (D-51): its kind and parameters,
    never text, which the frontend words (I18N-03). The first kind says that an admin deleted
    an ingredient the user kept as recurring, with its name and brand copied (ING-05)."""

    __tablename__ = "notices"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    dismissed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
