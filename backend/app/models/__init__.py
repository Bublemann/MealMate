"""SQLAlchemy models, one module per aggregate.

Every model is imported here so that `Base.metadata` is complete for Alembic.
"""

from app.db.base import Base
from app.models.app_meta import AppMeta

__all__ = ["AppMeta", "Base"]
