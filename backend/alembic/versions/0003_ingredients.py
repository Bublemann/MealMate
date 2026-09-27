"""ingredients: categories, cuisines, tags, ingredients, products (M3)

Seeds the categories (default walking order) and cuisines of requirements appendix A. The
nutrient columns are spelled out here (the models generate them from the registry).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-27 00:00:00+00:00
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORY_KEYS = (
    "fruit_vegetables",
    "bread_bakery",
    "dairy_eggs",
    "cheese",
    "meat_fish",
    "sausage_deli",
    "plant_based",
    "pasta_rice_grains",
    "canned_jars",
    "sauces_spices_oils",
    "baking",
    "breakfast_spreads",
    "snacks_sweets",
    "frozen",
    "drinks",
    "household_hygiene",
    "other",
)
CUISINE_KEYS = (
    "german",
    "italian",
    "french",
    "greek",
    "turkish",
    "mediterranean",
    "american",
    "mexican",
    "indian",
    "chinese",
    "japanese",
    "thai",
    "other",
)


def nutrient_columns() -> list[sa.Column[float]]:
    return [
        sa.Column("kcal", sa.Float(), nullable=True),
        sa.Column("protein", sa.Float(), nullable=True),
        sa.Column("carbs", sa.Float(), nullable=True),
        sa.Column("sugar", sa.Float(), nullable=True),
        sa.Column("fat", sa.Float(), nullable=True),
    ]


def seed() -> None:
    # Naive UTC, as the app stores datetimes.
    now = datetime.now(UTC).replace(tzinfo=None)
    categories = sa.table(
        "categories",
        sa.column("id", sa.String()),
        sa.column("key", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        categories,
        [
            {
                "id": str(uuid.uuid7()),
                "key": key,
                "sort_order": position,
                "created_at": now,
                "updated_at": now,
            }
            for position, key in enumerate(CATEGORY_KEYS)
        ],
    )
    cuisines = sa.table(
        "cuisines",
        sa.column("id", sa.String()),
        sa.column("key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("name_norm", sa.String()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        cuisines,
        [
            {
                "id": str(uuid.uuid7()),
                "key": key,
                "name": None,
                "name_norm": key,
                "created_at": now,
                "updated_at": now,
            }
            for key in CUISINE_KEYS
        ],
    )


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
        sa.UniqueConstraint("key", name=op.f("uq_categories_key")),
    )

    op.create_table(
        "tags",
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("name_norm", sa.String(length=120), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("name_norm", name=op.f("uq_tags_name_norm")),
    )

    op.create_table(
        "cuisines",
        sa.Column("key", sa.String(length=40), nullable=True),
        sa.Column("name", sa.String(length=40), nullable=True),
        sa.Column("name_norm", sa.String(length=160), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("(key IS NULL) <> (name IS NULL)", name=op.f("ck_cuisines_key_or_name")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_cuisines_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cuisines")),
        sa.UniqueConstraint("key", name=op.f("uq_cuisines_key")),
        sa.UniqueConstraint("name_norm", name=op.f("uq_cuisines_name_norm")),
    )
    with op.batch_alter_table("cuisines", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_cuisines_created_by"), ["created_by"], unique=False)

    op.create_table(
        "ingredients",
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("name_norm", sa.String(length=240), nullable=False),
        sa.Column("category_id", sa.String(length=36), nullable=False),
        sa.Column("base_unit", sa.String(length=2), nullable=False),
        sa.Column("piece_weight_g", sa.Float(), nullable=True),
        sa.Column("density_g_per_ml", sa.Float(), nullable=True),
        *nutrient_columns(),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("base_unit IN ('g', 'ml')", name=op.f("ck_ingredients_base_unit")),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_ingredients_category_id_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_ingredients_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_ingredients_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingredients")),
        sa.UniqueConstraint("name_norm", name=op.f("uq_ingredients_name_norm")),
    )
    with op.batch_alter_table("ingredients", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_ingredients_category_id"), ["category_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_ingredients_created_by"), ["created_by"], unique=False)
        batch_op.create_index(batch_op.f("ix_ingredients_updated_by"), ["updated_by"], unique=False)

    op.create_table(
        "products",
        sa.Column("barcode", sa.String(length=14), nullable=False),
        sa.Column("ingredient_id", sa.String(length=36), nullable=False),
        sa.Column("nutrition_basis", sa.String(length=2), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("quantity_text", sa.String(length=40), nullable=True),
        sa.Column("pack_quantity", sa.Float(), nullable=True),
        sa.Column("pack_unit", sa.String(length=10), nullable=True),
        *nutrient_columns(),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("off_last_modified_at", sa.DateTime(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=True),
        sa.Column("user_edited_fields", sa.JSON(), nullable=False),
        sa.Column("pending_update", sa.JSON(), nullable=True),
        sa.Column("ignored_off_modified_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "nutrition_basis IN ('g', 'ml')", name=op.f("ck_products_nutrition_basis")
        ),
        sa.CheckConstraint("source IN ('off', 'manual')", name=op.f("ck_products_source")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_products_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["ingredient_id"],
            ["ingredients.id"],
            name=op.f("fk_products_ingredient_id_ingredients"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_products_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("barcode", name=op.f("uq_products_barcode")),
    )
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_products_created_by"), ["created_by"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_products_ingredient_id"), ["ingredient_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_products_updated_by"), ["updated_by"], unique=False)

    seed()


def downgrade() -> None:
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_products_updated_by"))
        batch_op.drop_index(batch_op.f("ix_products_ingredient_id"))
        batch_op.drop_index(batch_op.f("ix_products_created_by"))

    op.drop_table("products")
    with op.batch_alter_table("ingredients", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ingredients_updated_by"))
        batch_op.drop_index(batch_op.f("ix_ingredients_created_by"))
        batch_op.drop_index(batch_op.f("ix_ingredients_category_id"))

    op.drop_table("ingredients")
    with op.batch_alter_table("cuisines", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_cuisines_created_by"))

    op.drop_table("cuisines")
    op.drop_table("tags")
    op.drop_table("categories")
