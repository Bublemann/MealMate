"""lists: shopping_lists, list_meals, list_meal_ingredients, list_extra_items,
list_line_states (M5a)

The columns shopping mode needs (M5b) are created here as well; only `processed_ops` comes later.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-27 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shopping_lists",
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("shared_with_partner", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("reminder_seed", sa.Integer(), nullable=False),
        sa.Column("shopping_started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'shopping', 'done')", name=op.f("ck_shopping_lists_status")
        ),
        sa.CheckConstraint(
            "reminder_seed >= 0 AND reminder_seed <= 9999",
            name=op.f("ck_shopping_lists_reminder_seed"),
        ),
        sa.CheckConstraint("version >= 0", name=op.f("ck_shopping_lists_version")),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_shopping_lists_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_lists")),
    )
    with op.batch_alter_table("shopping_lists", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_shopping_lists_owner_id"), ["owner_id"], unique=False)

    op.create_table(
        "list_extra_items",
        sa.Column("list_id", sa.String(length=36), nullable=False),
        sa.Column("ingredient_id", sa.String(length=36), nullable=True),
        sa.Column("attrs_snapshot", sa.JSON(), nullable=True),
        sa.Column("text", sa.String(length=80), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=10), nullable=True),
        sa.Column("amount_text", sa.String(length=30), nullable=True),
        sa.Column("category_id", sa.String(length=36), nullable=True),
        sa.Column("added_by", sa.String(length=36), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(ingredient_id IS NULL) <> (text IS NULL)",
            name=op.f("ck_list_extra_items_ingredient_or_text"),
        ),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name=op.f("ck_list_extra_items_amount")),
        sa.CheckConstraint(
            "amount IS NULL OR amount_text IS NULL",
            name=op.f("ck_list_extra_items_amount_or_amount_text"),
        ),
        sa.CheckConstraint(
            "unit IS NULL OR amount IS NOT NULL", name=op.f("ck_list_extra_items_unit_needs_amount")
        ),
        sa.ForeignKeyConstraint(
            ["added_by"],
            ["users.id"],
            name=op.f("fk_list_extra_items_added_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_list_extra_items_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_list_extra_items_ingredient_id_ingredients"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["shopping_lists.id"],
            name=op.f("fk_list_extra_items_list_id_shopping_lists"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_list_extra_items")),
    )
    with op.batch_alter_table("list_extra_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_list_extra_items_added_by"), ["added_by"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_list_extra_items_category_id"), ["category_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_list_extra_items_ingredient_id"), ["ingredient_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_list_extra_items_list_id"), ["list_id"], unique=False)

    op.create_table(
        "list_line_states",
        sa.Column("list_id", sa.String(length=36), nullable=False),
        sa.Column("line_key", sa.String(length=80), nullable=False),
        sa.Column("checked", sa.Boolean(), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("checked_op_id", sa.String(length=36), nullable=True),
        sa.Column("checked_by", sa.String(length=36), nullable=True),
        sa.Column("checked_snapshot", sa.JSON(), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["checked_by"],
            ["users.id"],
            name=op.f("fk_list_line_states_checked_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["shopping_lists.id"],
            name=op.f("fk_list_line_states_list_id_shopping_lists"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("list_id", "line_key", name=op.f("pk_list_line_states")),
    )
    with op.batch_alter_table("list_line_states", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_list_line_states_checked_by"), ["checked_by"], unique=False
        )

    op.create_table(
        "list_meals",
        sa.Column("list_id", sa.String(length=36), nullable=False),
        sa.Column("meal_id", sa.String(length=36), nullable=True),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("meal_servings_snapshot", sa.Integer(), nullable=False),
        sa.Column("meal_name_snapshot", sa.String(length=80), nullable=False),
        sa.Column("meal_owner_id_snapshot", sa.String(length=36), nullable=True),
        sa.Column("added_by", sa.String(length=36), nullable=True),
        sa.Column("last_added_at", sa.DateTime(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(), nullable=True),
        sa.Column("detached_reason", sa.String(length=12), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "detached_reason IS NULL OR detached_reason IN ('deleted', 'unavailable')",
            name=op.f("ck_list_meals_detached_reason"),
        ),
        sa.CheckConstraint(
            "meal_servings_snapshot >= 1", name=op.f("ck_list_meals_meal_servings_snapshot")
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_list_meals_position")),
        sa.CheckConstraint("servings >= 1 AND servings <= 99", name=op.f("ck_list_meals_servings")),
        sa.ForeignKeyConstraint(
            ["added_by"],
            ["users.id"],
            name=op.f("fk_list_meals_added_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["list_id"],
            ["shopping_lists.id"],
            name=op.f("fk_list_meals_list_id_shopping_lists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["meal_id"], ["meals.id"], name=op.f("fk_list_meals_meal_id_meals"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["meal_owner_id_snapshot"],
            ["users.id"],
            name=op.f("fk_list_meals_meal_owner_id_snapshot_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_list_meals")),
    )
    with op.batch_alter_table("list_meals", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_list_meals_added_by"), ["added_by"], unique=False)
        batch_op.create_index(batch_op.f("ix_list_meals_list_id"), ["list_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_list_meals_meal_id"), ["meal_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_list_meals_meal_owner_id_snapshot"),
            ["meal_owner_id_snapshot"],
            unique=False,
        )
        batch_op.create_index(
            "uq_list_meals_list_id_meal_id",
            ["list_id", "meal_id"],
            unique=True,
            sqlite_where=sa.text("meal_id IS NOT NULL"),
        )

    op.create_table(
        "list_meal_ingredients",
        sa.Column("list_meal_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.String(length=36), nullable=False),
        sa.Column("ingredient_name_snapshot", sa.String(length=60), nullable=False),
        sa.Column("base_unit_snapshot", sa.String(length=2), nullable=False),
        sa.Column("piece_weight_g_snapshot", sa.Float(), nullable=True),
        sa.Column("density_snapshot", sa.Float(), nullable=True),
        sa.Column("category_id_snapshot", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=10), nullable=True),
        sa.Column("note", sa.String(length=80), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "base_unit_snapshot IN ('g', 'ml')",
            name=op.f("ck_list_meal_ingredients_base_unit_snapshot"),
        ),
        sa.CheckConstraint(
            "amount IS NULL OR amount > 0", name=op.f("ck_list_meal_ingredients_amount")
        ),
        sa.CheckConstraint("position >= 0", name=op.f("ck_list_meal_ingredients_position")),
        sa.CheckConstraint(
            "unit IS NULL OR amount IS NOT NULL",
            name=op.f("ck_list_meal_ingredients_unit_needs_amount"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id_snapshot"],
            ["categories.id"],
            name=op.f("fk_list_meal_ingredients_category_id_snapshot_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_list_meal_ingredients_ingredient_id_ingredients"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["list_meal_id"],
            ["list_meals.id"],
            name=op.f("fk_list_meal_ingredients_list_meal_id_list_meals"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_list_meal_ingredients")),
        sa.UniqueConstraint(
            "list_meal_id", "position", name=op.f("uq_list_meal_ingredients_list_meal_id")
        ),
    )
    with op.batch_alter_table("list_meal_ingredients", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_list_meal_ingredients_category_id_snapshot"),
            ["category_id_snapshot"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_list_meal_ingredients_ingredient_id"), ["ingredient_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_list_meal_ingredients_list_meal_id"), ["list_meal_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("list_meal_ingredients", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_list_meal_ingredients_list_meal_id"))
        batch_op.drop_index(batch_op.f("ix_list_meal_ingredients_ingredient_id"))
        batch_op.drop_index(batch_op.f("ix_list_meal_ingredients_category_id_snapshot"))

    op.drop_table("list_meal_ingredients")
    with op.batch_alter_table("list_meals", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_list_meals_list_id_meal_id", sqlite_where=sa.text("meal_id IS NOT NULL")
        )
        batch_op.drop_index(batch_op.f("ix_list_meals_meal_owner_id_snapshot"))
        batch_op.drop_index(batch_op.f("ix_list_meals_meal_id"))
        batch_op.drop_index(batch_op.f("ix_list_meals_list_id"))
        batch_op.drop_index(batch_op.f("ix_list_meals_added_by"))

    op.drop_table("list_meals")
    with op.batch_alter_table("list_line_states", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_list_line_states_checked_by"))

    op.drop_table("list_line_states")
    with op.batch_alter_table("list_extra_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_list_extra_items_list_id"))
        batch_op.drop_index(batch_op.f("ix_list_extra_items_ingredient_id"))
        batch_op.drop_index(batch_op.f("ix_list_extra_items_category_id"))
        batch_op.drop_index(batch_op.f("ix_list_extra_items_added_by"))

    op.drop_table("list_extra_items")
    with op.batch_alter_table("shopping_lists", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_shopping_lists_owner_id"))

    op.drop_table("shopping_lists")
