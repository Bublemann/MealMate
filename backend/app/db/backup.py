"""Consistent copies of the live database (OPS-01) via the SQLite online backup API."""

import sqlite3
from contextlib import closing
from pathlib import Path


class IntegrityCheckError(RuntimeError):
    def __init__(self, path: Path, problems: list[str]) -> None:
        super().__init__(f"integrity check failed for {path}: {'; '.join(problems)}")
        self.problems = problems


def _uri(path: Path, mode: str) -> str:
    return f"{path.resolve().as_uri()}?mode={mode}"


def integrity_check(path: Path) -> list[str]:
    """`PRAGMA integrity_check` on the file at `path`; `["ok"]` means it is intact."""
    with closing(sqlite3.connect(_uri(path, "ro"), uri=True)) as connection:
        return [row[0] for row in connection.execute("PRAGMA integrity_check")]


def backup_database(source: Path, target: Path) -> None:
    """Copy the database at `source` to `target` while it may be in use.

    The copy is a self-contained file (rollback journal instead of WAL). It is written next to
    `target` and renamed into place only after `PRAGMA integrity_check` returned ok; a rename
    also replaces a symlink at `target` instead of writing through it.
    """
    if not source.is_file():
        raise FileNotFoundError(f"no database at {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.partial")
    partial.unlink(missing_ok=True)
    try:
        # mode=rw: never create an empty database where the source should be.
        with (
            closing(sqlite3.connect(_uri(source, "rw"), uri=True)) as source_db,
            closing(sqlite3.connect(partial)) as target_db,
        ):
            source_db.backup(target_db)
            target_db.execute("PRAGMA journal_mode=DELETE")
        problems = integrity_check(partial)
        if problems != ["ok"]:
            raise IntegrityCheckError(target, problems)
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
