"""Database handle and the FastAPI session dependencies."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import DATABASE_FILENAME
from app.db.engine import create_read_engine, create_write_engine


class Database:
    """Both engines of one database file, created at app startup and disposed at shutdown."""

    def __init__(self, database_path: Path) -> None:
        self.path = database_path
        self.write_engine = create_write_engine(database_path)
        self.read_engine = create_read_engine(database_path)
        self.write_sessions = async_sessionmaker(self.write_engine, expire_on_commit=False)
        self.read_sessions = async_sessionmaker(self.read_engine, expire_on_commit=False)

    @classmethod
    def open(cls, data_dir: Path) -> Database:
        """The database in `data_dir`, which is created if missing."""
        data_dir.mkdir(parents=True, exist_ok=True)
        return cls(data_dir / DATABASE_FILENAME)

    async def dispose(self) -> None:
        await self.write_engine.dispose()
        await self.read_engine.dispose()


def get_database(request: Request) -> Database:
    database: Database = request.app.state.database
    return database


async def write_session(request: Request) -> AsyncIterator[AsyncSession]:
    """A session on the write engine. Wrap each unit of work in `async with session.begin()`;
    the write lock is held from its first statement until it commits. No network I/O inside."""
    async with get_database(request).write_sessions() as session:
        yield session


async def read_session(request: Request) -> AsyncIterator[AsyncSession]:
    """A session on the read engine, for requests that only read."""
    async with get_database(request).read_sessions() as session:
        yield session


WriteSession = Annotated[AsyncSession, Depends(write_session)]
ReadSession = Annotated[AsyncSession, Depends(read_session)]
