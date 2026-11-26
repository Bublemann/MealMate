"""leftover meals: list_meals.leftover_of_id (LIST-17, D-57)

A new draft brings along the uneaten meals of the last done list as leftover meals: list meals
that point at the meal on the done list they come from (`leftover_of_id`, deleted with it). A
meal is on a list at most once as a normal meal, but may be there as a leftover too, so the
unique index on `(list_id, meal_id)` leaves leftovers out. No list has leftovers yet, so no
data changes.

The downgrade deletes the leftover meals (they add no lines, so no list's lines change) and
then drops the column; the old index would refuse a leftover next to its normal meal.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-26 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_WHERE = "meal_id IS NOT NULL"
NEW_WHERE = "meal_id IS NOT NULL AND leftover_of_id IS NULL"


def upgrade() -> None:
    with op.batch_alter_table("list_meals", schema=None) as batch_op:
        batch_op.add_column(sa.Column("leftover_of_id", sa.String(length=36), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_list_meals_leftover_of_id"), ["leftover_of_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_list_meals_leftover_of_id_list_meals"),
            "list_meals",
            ["leftover_of_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.drop_index("uq_list_meals_list_id_meal_id", sqlite_where=sa.text(OLD_WHERE))
        batch_op.create_index(
            "uq_list_meals_list_id_meal_id",
            ["list_id", "meal_id"],
            unique=True,
            sqlite_where=sa.text(NEW_WHERE),
        )


def downgrade() -> None:
    op.execute("DELETE FROM list_meals WHERE leftover_of_id IS NOT NULL")
    with op.batch_alter_table("list_meals", schema=None) as batch_op:
        batch_op.drop_index("uq_list_meals_list_id_meal_id", sqlite_where=sa.text(NEW_WHERE))
        batch_op.create_index(
            "uq_list_meals_list_id_meal_id",
            ["list_id", "meal_id"],
            unique=True,
            sqlite_where=sa.text(OLD_WHERE),
        )
        batch_op.drop_constraint(
            batch_op.f("fk_list_meals_leftover_of_id_list_meals"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_list_meals_leftover_of_id"))
        batch_op.drop_column("leftover_of_id")
