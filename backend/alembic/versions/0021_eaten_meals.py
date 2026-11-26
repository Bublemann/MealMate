"""eaten meals: list_meals.eaten (SHOP-07, D-55)

A meal on a done list can be marked eaten, and cleared again: an on/off flag with no history.
`list_meals.eaten` holds it; every meal that is on a list now starts not eaten. Nothing else on
the lists changes (`version` and `updated_at` included: this is nobody's edit).

The flag is only a note, so the downgrade drops the column, and what was marked eaten is lost.

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-26 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("list_meals", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("eaten", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("list_meals", schema=None) as batch_op:
        batch_op.drop_column("eaten")
