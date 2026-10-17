"""recurring items: recurring_items and notices (LIST-16, D-42, D-51)

A user, or a couple together, keeps a set of recurring items: ingredients they buy again and
again, due once their interval has passed since the last purchase. `recurring_items` holds them,
owned by a couple or by a user without one, with the set interval, the last purchase and the
last three measured intervals (a JSON list, never null). `notices` holds what a user is told
until they dismiss it, as a kind and parameters (I18N-03); the first kind is a recurring
ingredient an admin deleted (ING-05). Both tables start empty: nothing is seeded.

The downgrade refuses with a clear error while either table has rows, rather than dropping
what users set up (plan § 6).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-16 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notices",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_notices_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notices")),
    )
    with op.batch_alter_table("notices", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_notices_user_id"), ["user_id"], unique=False)

    op.create_table(
        "recurring_items",
        sa.Column("couple_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("ingredient_id", sa.String(length=36), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("interval_manual", sa.Boolean(), nullable=False),
        sa.Column("last_purchased_on", sa.Date(), nullable=False),
        sa.Column("last_amount", sa.Float(), nullable=True),
        sa.Column("last_unit", sa.String(length=10), nullable=True),
        sa.Column("measured_intervals", sa.JSON(), nullable=False),
        sa.Column("last_list_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "json_type(measured_intervals) = 'array'",
            name=op.f("ck_recurring_items_measured_intervals"),
        ),
        sa.CheckConstraint(
            "(couple_id IS NULL) <> (user_id IS NULL)", name=op.f("ck_recurring_items_one_owner")
        ),
        sa.CheckConstraint("interval_days >= 1", name=op.f("ck_recurring_items_interval_days")),
        sa.CheckConstraint(
            "last_amount IS NULL OR last_amount > 0", name=op.f("ck_recurring_items_last_amount")
        ),
        sa.CheckConstraint(
            "last_unit IS NULL OR last_amount IS NOT NULL",
            name=op.f("ck_recurring_items_unit_needs_amount"),
        ),
        sa.ForeignKeyConstraint(
            ["couple_id"],
            ["couples.id"],
            name=op.f("fk_recurring_items_couple_id_couples"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_recurring_items_ingredient_id_ingredients"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_list_id"],
            ["shopping_lists.id"],
            name=op.f("fk_recurring_items_last_list_id_shopping_lists"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recurring_items_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recurring_items")),
    )
    with op.batch_alter_table("recurring_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_recurring_items_couple_id"), ["couple_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_recurring_items_ingredient_id"), ["ingredient_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_recurring_items_last_list_id"), ["last_list_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_recurring_items_user_id"), ["user_id"], unique=False)
        batch_op.create_index(
            "uq_recurring_items_couple_id_ingredient_id",
            ["couple_id", "ingredient_id"],
            unique=True,
            sqlite_where=sa.text("couple_id IS NOT NULL"),
        )
        batch_op.create_index(
            "uq_recurring_items_user_id_ingredient_id",
            ["user_id", "ingredient_id"],
            unique=True,
            sqlite_where=sa.text("user_id IS NOT NULL"),
        )


class RecurringItemsError(RuntimeError):
    """The downgrade cannot keep recurring items or notices."""


def _check_tables_are_empty(connection: sa.Connection) -> None:
    items = connection.execute(sa.text("SELECT count(*) FROM recurring_items")).scalar_one()
    notices = connection.execute(sa.text("SELECT count(*) FROM notices")).scalar_one()
    if items or notices:
        raise RecurringItemsError(
            f"cannot downgrade below 0015: there are recurring items ({items}) and notices "
            f"({notices}), which don't exist before 0015"
        )


def downgrade() -> None:
    _check_tables_are_empty(op.get_bind())
    with op.batch_alter_table("recurring_items", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_recurring_items_user_id_ingredient_id", sqlite_where=sa.text("user_id IS NOT NULL")
        )
        batch_op.drop_index(
            "uq_recurring_items_couple_id_ingredient_id",
            sqlite_where=sa.text("couple_id IS NOT NULL"),
        )
        batch_op.drop_index(batch_op.f("ix_recurring_items_user_id"))
        batch_op.drop_index(batch_op.f("ix_recurring_items_last_list_id"))
        batch_op.drop_index(batch_op.f("ix_recurring_items_ingredient_id"))
        batch_op.drop_index(batch_op.f("ix_recurring_items_couple_id"))

    op.drop_table("recurring_items")
    with op.batch_alter_table("notices", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notices_user_id"))

    op.drop_table("notices")
