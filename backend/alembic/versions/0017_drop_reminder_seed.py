"""drop reminder seed: the list reminder is gone, and so is its seed (D-43)

The reminder at the end of a list (LIST-14) is removed (D-43). `shopping_lists.reminder_seed`
only picked which reminder a list showed, so the column goes with its check constraint. Nothing
else on the lists changes (`version` and `updated_at` included: this is nobody's edit).

The seeds were decoration only, so the downgrade doesn't need the old ones back: it adds the
column again with its check constraint and gives every list a new random seed in the old range
(0 to 9999), as creating a list did.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-17 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The range of 0005, as `app.domain.lists.REMINDER_SEED_MAX` had it.
SEED_MAX = 9_999
CONSTRAINT = "ck_shopping_lists_reminder_seed"


def upgrade() -> None:
    with op.batch_alter_table("shopping_lists", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f(CONSTRAINT), type_="check")
        batch_op.drop_column("reminder_seed")


def downgrade() -> None:
    with op.batch_alter_table("shopping_lists", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reminder_seed", sa.Integer(), nullable=True))
    # SQLite's random() is a signed 64-bit integer; this takes it into 0..SEED_MAX, per list.
    op.get_bind().execute(
        sa.text("UPDATE shopping_lists SET reminder_seed = (random() % :count + :count) % :count"),
        {"count": SEED_MAX + 1},
    )
    with op.batch_alter_table("shopping_lists", schema=None) as batch_op:
        batch_op.alter_column("reminder_seed", existing_type=sa.Integer(), nullable=False)
        batch_op.create_check_constraint(
            batch_op.f(CONSTRAINT), f"reminder_seed >= 0 AND reminder_seed <= {SEED_MAX}"
        )
