"""carry-over setting: users.carry_over_leftovers (LIST-17, D-59)

A user can turn off that new drafts bring along the leftovers of the last done list.
`users.carry_over_leftovers` holds the switch; every user has it on, so drafts keep getting
leftovers as before. Nothing else changes (`updated_at` included: this is nobody's edit).

The downgrade drops the column, and a switch turned off is lost (leftovers come again).

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-26 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "carry_over_leftovers", sa.Boolean(), server_default=sa.true(), nullable=False
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("carry_over_leftovers")
