"""hidden due items: list_hidden_due_items (LIST-16, D-42)

A draft offers the due recurring items of its viewer's set in a "Fällig" box; ✕ hides one on
that list for everyone who sees it, with no undo. `list_hidden_due_items` keeps those hides by
list and ingredient (not by recurring item, so a hide survives a couple forming or ending),
with when and by whom. It goes with its list or ingredient; an ingredient merge moves it. The
table starts empty.

The downgrade refuses with a clear error while the table has rows, rather than dropping what
users hid (plan § 6).

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-17 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "list_hidden_due_items",
        sa.Column("list_id", sa.String(length=36), nullable=False),
        sa.Column("ingredient_id", sa.String(length=36), nullable=False),
        sa.Column("hidden_at", sa.DateTime(), nullable=False),
        sa.Column("hidden_by", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(
            ["hidden_by"],
            ["users.id"],
            name=op.f("fk_list_hidden_due_items_hidden_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_list_hidden_due_items_ingredient_id_ingredients"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["shopping_lists.id"],
            name=op.f("fk_list_hidden_due_items_list_id_shopping_lists"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("list_id", "ingredient_id", name=op.f("pk_list_hidden_due_items")),
    )
    with op.batch_alter_table("list_hidden_due_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_list_hidden_due_items_hidden_by"), ["hidden_by"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_list_hidden_due_items_ingredient_id"), ["ingredient_id"], unique=False
        )


class HiddenDueItemsError(RuntimeError):
    """The downgrade cannot keep hidden due items."""


def _check_table_is_empty(connection: sa.Connection) -> None:
    hidden = connection.execute(sa.text("SELECT count(*) FROM list_hidden_due_items")).scalar_one()
    if hidden:
        raise HiddenDueItemsError(
            f"cannot downgrade below 0016: there are hidden due items ({hidden}), which don't "
            "exist before 0016"
        )


def downgrade() -> None:
    _check_table_is_empty(op.get_bind())
    with op.batch_alter_table("list_hidden_due_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_list_hidden_due_items_ingredient_id"))
        batch_op.drop_index(batch_op.f("ix_list_hidden_due_items_hidden_by"))

    op.drop_table("list_hidden_due_items")
