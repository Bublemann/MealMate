"""item kind: an item is food or a supply (ING-02, D-54)

`items.kind` says whether an item is food (`food`) or a supply (`supply`, toilet paper or
candles): a supply has no nutrition values and no piece weight and is never an ingredient in a
meal. Every existing item becomes food, so nothing changes until a user switches one; no other
value changes. The downgrade drops the column, so supplies become food again, without
nutrition values, as they were saved before.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-26 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("items", schema=None, recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("kind", sa.String(length=10), nullable=False, server_default="food")
        )
        batch_op.create_check_constraint(batch_op.f("ck_items_kind"), "kind IN ('food', 'supply')")
    # The model sets the kind; the default only filled in the existing items.
    with op.batch_alter_table("items", schema=None, recreate="always") as batch_op:
        batch_op.alter_column(
            "kind",
            existing_type=sa.String(length=10),
            existing_nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    with op.batch_alter_table("items", schema=None, recreate="always") as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_items_kind"), type_="check")
        batch_op.drop_column("kind")
