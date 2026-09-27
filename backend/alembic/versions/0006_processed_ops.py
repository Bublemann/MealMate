"""processed_ops: the ops of shopping mode that were applied (M5b)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-27 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "processed_ops",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("op_id", sa.String(length=36), nullable=False),
        sa.Column("list_id", sa.String(length=36), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["shopping_lists.id"],
            name=op.f("fk_processed_ops_list_id_shopping_lists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_processed_ops_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "op_id", name=op.f("pk_processed_ops")),
    )
    with op.batch_alter_table("processed_ops", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_processed_ops_list_id"), ["list_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("processed_ops", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_processed_ops_list_id"))

    op.drop_table("processed_ops")
