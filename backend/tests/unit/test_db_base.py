import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, UTCDateTime
from app.db.ids import new_id


class _TestBase(DeclarativeBase):
    """Separate metadata, so the app's (and Alembic's) view of the schema stays untouched."""


class Thing(_TestBase, IdMixin, TimestampMixin):
    __tablename__ = "things"

    seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://")
    _TestBase.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_new_id_is_uuid7_and_time_ordered() -> None:
    ids = [new_id() for _ in range(100)]
    assert all(uuid.UUID(value).version == 7 for value in ids)
    assert all(len(value) == 36 for value in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_constraint_naming_convention() -> None:
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
    assert "fk" in Base.metadata.naming_convention


def test_mixins_fill_id_and_utc_timestamps(engine: Engine) -> None:
    plus_two = timezone(timedelta(hours=2))
    with Session(engine) as session:
        thing = Thing(seen_at=datetime(2026, 9, 26, 14, 0, tzinfo=plus_two))
        session.add(thing)
        session.commit()
        before_update = thing.updated_at
        thing.seen_at = None
        session.commit()
        session.expunge_all()

        loaded = session.scalars(select(Thing)).one()
        assert uuid.UUID(loaded.id).version == 7
        assert loaded.created_at.tzinfo is UTC
        assert loaded.updated_at >= before_update >= loaded.created_at
        assert loaded.seen_at is None

        loaded.seen_at = datetime(2026, 9, 26, 14, 0, tzinfo=plus_two)
        session.commit()
        session.expunge_all()
        assert session.scalars(select(Thing.seen_at)).one() == datetime(
            2026, 9, 26, 12, 0, tzinfo=UTC
        )


def test_naive_datetimes_are_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(Thing(seen_at=datetime(2026, 9, 26, 12, 0)))
        with pytest.raises(StatementError, match="naive datetime"):
            session.commit()
