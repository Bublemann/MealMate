"""meals: meals, meal_ingredients, meal_tags (M4)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meals",
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("name_norm", sa.String(length=320), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("source_url", sa.String(length=2000), nullable=True),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("cuisine_id", sa.String(length=36), nullable=True),
        sa.Column("photo_key", sa.String(length=32), nullable=True),
        sa.Column("copied_from_meal_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("servings >= 1", name=op.f("ck_meals_servings")),
        sa.ForeignKeyConstraint(
            ["copied_from_meal_id"],
            ["meals.id"],
            name=op.f("fk_meals_copied_from_meal_id_meals"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["cuisine_id"],
            ["cuisines.id"],
            name=op.f("fk_meals_cuisine_id_cuisines"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            name=op.f("fk_meals_owner_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meals")),
    )
    with op.batch_alter_table("meals", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_meals_copied_from_meal_id"), ["copied_from_meal_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_meals_cuisine_id"), ["cuisine_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_meals_name_norm"), ["name_norm"], unique=False)
        batch_op.create_index(batch_op.f("ix_meals_owner_id"), ["owner_id"], unique=False)

    op.create_table(
        "meal_ingredients",
        sa.Column("meal_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("ingredient_id", sa.String(length=36), nullable=False),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=10), nullable=True),
        sa.Column("note", sa.String(length=80), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name=op.f("ck_meal_ingredients_amount")),
        sa.CheckConstraint("position >= 0", name=op.f("ck_meal_ingredients_position")),
        sa.CheckConstraint(
            "unit IS NULL OR amount IS NOT NULL",
            name=op.f("ck_meal_ingredients_unit_needs_amount"),
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_meal_ingredients_ingredient_id_ingredients"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["meal_id"],
            ["meals.id"],
            name=op.f("fk_meal_ingredients_meal_id_meals"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_meal_ingredients")),
        sa.UniqueConstraint("meal_id", "position", name=op.f("uq_meal_ingredients_meal_id")),
    )
    with op.batch_alter_table("meal_ingredients", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_meal_ingredients_ingredient_id"), ["ingredient_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_meal_ingredients_meal_id"), ["meal_id"], unique=False)

    op.create_table(
        "meal_tags",
        sa.Column("meal_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["meal_id"],
            ["meals.id"],
            name=op.f("fk_meal_tags_meal_id_meals"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tag_id"],
            ["tags.id"],
            name=op.f("fk_meal_tags_tag_id_tags"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("meal_id", "tag_id", name=op.f("pk_meal_tags")),
    )
    with op.batch_alter_table("meal_tags", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_meal_tags_tag_id"), ["tag_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("meal_tags", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_meal_tags_tag_id"))

    op.drop_table("meal_tags")
    with op.batch_alter_table("meal_ingredients", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_meal_ingredients_meal_id"))
        batch_op.drop_index(batch_op.f("ix_meal_ingredients_ingredient_id"))

    op.drop_table("meal_ingredients")
    with op.batch_alter_table("meals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_meals_owner_id"))
        batch_op.drop_index(batch_op.f("ix_meals_name_norm"))
        batch_op.drop_index(batch_op.f("ix_meals_cuisine_id"))
        batch_op.drop_index(batch_op.f("ix_meals_copied_from_meal_id"))

    op.drop_table("meals")
