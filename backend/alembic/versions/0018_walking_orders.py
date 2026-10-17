"""walking orders: walking_order_entries (REF-01, D-48)

A couple, or a user without one, can keep an own walking order instead of following the admins'
one. `walking_order_entries` holds each category's position in such an order, owned by a couple
or by a user without one, with whether an admin added the category since and nobody moved it
("neu"). An owner without entries follows the admins' order, so the table starts empty.

The downgrade refuses with a clear error while the table has rows, rather than dropping what
users set up (plan § 6).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-17 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "walking_order_entries",
        sa.Column("couple_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_new", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(couple_id IS NULL) <> (user_id IS NULL)",
            name=op.f("ck_walking_order_entries_one_owner"),
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_walking_order_entries_position")),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_walking_order_entries_category_id_categories"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["couple_id"],
            ["couples.id"],
            name=op.f("fk_walking_order_entries_couple_id_couples"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_walking_order_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_walking_order_entries")),
    )
    with op.batch_alter_table("walking_order_entries", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_walking_order_entries_category_id"), ["category_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_walking_order_entries_couple_id"), ["couple_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_walking_order_entries_user_id"), ["user_id"], unique=False
        )
        batch_op.create_index(
            "uq_walking_order_entries_couple_id_category_id",
            ["couple_id", "category_id"],
            unique=True,
            sqlite_where=sa.text("couple_id IS NOT NULL"),
        )
        batch_op.create_index(
            "uq_walking_order_entries_user_id_category_id",
            ["user_id", "category_id"],
            unique=True,
            sqlite_where=sa.text("user_id IS NOT NULL"),
        )


class WalkingOrdersError(RuntimeError):
    """The downgrade cannot keep own walking orders."""


def _check_table_is_empty(connection: sa.Connection) -> None:
    entries = connection.execute(sa.text("SELECT count(*) FROM walking_order_entries")).scalar_one()
    if entries:
        raise WalkingOrdersError(
            f"cannot downgrade below 0018: there are own walking orders ({entries} entries), "
            "which don't exist before 0018"
        )


def downgrade() -> None:
    _check_table_is_empty(op.get_bind())
    with op.batch_alter_table("walking_order_entries", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_walking_order_entries_user_id_category_id",
            sqlite_where=sa.text("user_id IS NOT NULL"),
        )
        batch_op.drop_index(
            "uq_walking_order_entries_couple_id_category_id",
            sqlite_where=sa.text("couple_id IS NOT NULL"),
        )
        batch_op.drop_index(batch_op.f("ix_walking_order_entries_user_id"))
        batch_op.drop_index(batch_op.f("ix_walking_order_entries_couple_id"))
        batch_op.drop_index(batch_op.f("ix_walking_order_entries_category_id"))

    op.drop_table("walking_order_entries")
