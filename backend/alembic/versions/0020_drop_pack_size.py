"""drop pack size: items no longer have a pack size (D-54)

The pack size ("500 g", "6 x 1,5 l") is removed (D-54, replaces D-47): its text
`quantity_text` and its amount `pack_quantity`/`pack_unit` go from `items`, and their values
are lost, as intended. The user-edited marks (`user_edited_fields`) and the pending Open Food
Facts values (`pending_update`, ignored ones included) on these fields go with them; a pending
update left empty becomes null. Nothing else changes (`updated_at` included: this is nobody's
edit). The frozen rows on lists never carried a pack size.

The pack sizes can't come back: the downgrade adds the columns again, empty, as an item without
a pack size has them.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-26 00:00:00+00:00
"""

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The pack size's text and its amount, as 0003 and 0007 added them; marks and pending values
# name them by these column names.
COLUMNS: tuple[tuple[str, sa.types.TypeEngine[Any]], ...] = (
    ("quantity_text", sa.String(length=40)),
    ("pack_quantity", sa.Float()),
    ("pack_unit", sa.String(length=10)),
)
FIELDS = frozenset(name for name, _ in COLUMNS)


def _json(value: str | None) -> Any:
    """A JSON column's value; SQL NULL and JSON null are both None."""
    return None if value is None else json.loads(value)


def _forget_pack_size_fields() -> None:
    """Drop the marks and pending values on the pack size's fields, row by row where any."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, user_edited_fields, pending_update FROM items")
    ).fetchall()
    for row_id, marks_text, pending_text in rows:
        marks: list[str] = _json(marks_text) or []
        pending: dict[str, Any] = _json(pending_text) or {}
        if FIELDS.isdisjoint(marks) and FIELDS.isdisjoint(pending):
            continue
        kept_marks = [field for field in marks if field not in FIELDS]
        kept_pending = {field: entry for field, entry in pending.items() if field not in FIELDS}
        # Unchanged values keep their stored text; an emptied pending update becomes
        # JSON null, as the app stores none.
        new_marks = marks_text if marks == kept_marks else json.dumps(kept_marks)
        new_pending = pending_text if pending == kept_pending else json.dumps(kept_pending or None)
        bind.execute(
            sa.text(
                "UPDATE items SET user_edited_fields = :marks, pending_update = :pending"
                " WHERE id = :id"
            ),
            {
                "id": row_id,
                "marks": new_marks,
                "pending": new_pending,
            },
        )


def upgrade() -> None:
    _forget_pack_size_fields()
    with op.batch_alter_table("items", schema=None) as batch_op:
        for name, _ in reversed(COLUMNS):
            batch_op.drop_column(name)


def downgrade() -> None:
    with op.batch_alter_table("items", schema=None) as batch_op:
        for name, type_ in COLUMNS:
            batch_op.add_column(sa.Column(name, type_, nullable=True))
