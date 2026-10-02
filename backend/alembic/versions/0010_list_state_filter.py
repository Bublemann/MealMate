"""list state filter: the saved filters gain the state filter on Lists (D-26)

The Lists tab gets a state filter next to its user filter (UI-02), saved per user like it in
`users.filter_hidden`: `list_states` names the states it hides (`draft`, `shopping`, `done`).
Every user gets it empty, so every state shows, as before. What the user filters hide (`meals`,
`lists`) stays; no column and no other value changes. The downgrade drops `list_states` again.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-02 00:00:00+00:00
"""

import json
from collections.abc import Callable, Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KEY = "list_states"


def _rewrite(change: Callable[[dict[str, Any]], None]) -> None:
    """Applies `change` to every user's saved filters, writing back only those it changed."""
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, filter_hidden FROM users")).all()
    values = []
    for row_id, stored in rows:
        hidden = json.loads(stored)
        before = dict(hidden)
        change(hidden)
        if hidden != before:
            values.append({"id": row_id, "filter_hidden": json.dumps(hidden)})
    if values:
        connection.execute(
            sa.text("UPDATE users SET filter_hidden = :filter_hidden WHERE id = :id"), values
        )


def upgrade() -> None:
    _rewrite(lambda hidden: hidden.setdefault(KEY, []))


def downgrade() -> None:
    _rewrite(lambda hidden: hidden.pop(KEY, None))
