"""unified ingredients: products merged into ingredients (Ingredients v2)

There is one kind of ingredient (owner decision 2026-09-28): `ingredients` gains the product
columns (brand, barcode, pack, source and the Open Food Facts data), its `name_norm` is no
longer unique (two brands of "Milch"), and `products` is dropped. Frozen list rows snapshot the
brand too. Every meal and list keeps working; the data moves by these rules:

1. Every ingredient stays, with its id. Its nutrient columns become its *effective* values
   under the old NUT-02: the manual value, else the average over its products that have one,
   else null. No value is lost or becomes unknown.
2. An ingredient with exactly one product absorbs it: barcode, brand, pack, source, Open Food
   Facts data, user-edited fields and pending update move onto the ingredient. The name stays
   the ingredient's; the nutrients are the manual value if set, else the product's (rule 1).
   On an ingredient from Open Food Facts, the name (when it differs from the product's) and
   each manual nutrient that differs from the product's are marked user-edited, so that a
   refresh never replaces what the user chose. A pending update of the name goes: it proposed
   a new product name, and the ingredient's name never was the product's. So rule 2 keeps the
   ingredient's name and drops the product's own name, and the product's values hidden by
   manual ones; the pre-update backup and the pre-migration snapshot keep them.
3. An ingredient with two or more products keeps its own averaged values and no barcode; each
   product becomes a new ingredient (new UUIDv7) with the product's name, brand, barcode, pack,
   nutrients and Open Food Facts data, and the ingredient's category, base unit, piece weight
   and density. Meals and lists keep pointing at the original ingredient. A product without a
   name takes the ingredient's; so that its ingredients can be told apart, one without a brand
   either is named "<ingredient name> (<last 4 digits of the barcode>)". Such a name was never
   Open Food Facts', so on a product from there it is marked user-edited, and a refresh does
   not silently rename it.

Names are cut at a word boundary to 60 characters, also the proposed name of a pending update
(as the Open Food Facts client cuts them now).

`nutrition_basis` disappears (it always was the ingredient's base unit), also from the
user-edited fields and pending updates.

The downgrade is best-effort: it recreates `products` from the ingredients with a barcode (each
linked to itself, its values staying as the ingredient's manual values, which give the same
effective values), drops the new columns and restores the unique `name_norm`. That is only
possible while no two ingredients share a normalised name; otherwise it fails with a message
naming them, and nothing changes (merge or rename them first).

`normalize` and `cut_at_word` are copied from `app.domain` as they were when this migration was
written, so that later changes there cannot change what it does.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-28 00:00:00+00:00
"""

import json
import math
import unicodedata
import uuid
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NUTRIENTS = ("kcal", "protein", "carbs", "sugar", "fat")
NAME_MAX_LENGTH = 60
# The product fields that stay Open Food Facts fields of an ingredient.
OFF_DATA_FIELDS = ("name", "brand", "quantity_text", "pack_quantity", "pack_unit")
OFF_FIELDS = (*OFF_DATA_FIELDS, *(f"nutrients.{key}" for key in NUTRIENTS))
# Copied as they are from the product (rules 2 and 3).
PRODUCT_COLUMNS = (
    "barcode",
    "brand",
    "quantity_text",
    "pack_quantity",
    "pack_unit",
    "source",
    "off_last_modified_at",
    "fetched_at",
    "ignored_off_modified_at",
)

_GERMAN_FOLDS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def normalize(text: str) -> str:
    """`app.domain.text.normalize` as of this revision."""
    folded = unicodedata.normalize("NFKC", text).lower().translate(_GERMAN_FOLDS)
    decomposed = unicodedata.normalize("NFKD", folded)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.split())


def cut_at_word(text: str, max_length: int) -> str:
    """`app.domain.catalog.cut_at_word` as of this revision."""
    if len(text) <= max_length:
        return text
    hard = text[:max_length].rstrip()
    head = text[: max_length + 1]
    cut = head.rsplit(" ", 1)[0].rstrip(" ,;:-/(") if " " in head else ""
    return cut if len(cut) >= max_length // 2 else hard


def nutrient_columns() -> list[sa.Column[float]]:
    return [sa.Column(key, sa.Float(), nullable=True) for key in NUTRIENTS]


def _brand_norm(brand: str | None) -> str | None:
    return None if brand is None else normalize(brand) or None


def _json(value: str | None) -> Any:
    return None if value is None else json.loads(value)


def _edited_fields(value: str | None) -> list[str]:
    """A product's user-edited fields without `nutrition_basis`, in field order."""
    fields = set(_json(value) or [])
    return [field for field in OFF_FIELDS if field in fields]


def _pending(value: str | None, *, keep_name: bool = True) -> str | None:
    """A product's pending update without `nutrition_basis` (and without the name unless
    `keep_name`), with the proposed name cut like a name from Open Food Facts: applying it
    must not store a longer name than the column holds."""
    stored = _json(value) or {}
    kept = {
        field: entry
        for field, entry in stored.items()
        if field in OFF_FIELDS and (keep_name or field != "name")
    }
    if isinstance(proposed := kept.get("name", {}).get("proposed"), str):
        kept["name"] = kept["name"] | {"proposed": cut_at_word(proposed, NAME_MAX_LENGTH)}
    return json.dumps(kept) if kept else None


def _split_off_name(ingredient: sa.RowMapping, product: sa.RowMapping) -> tuple[str, bool]:
    """Rule 3: the name of a product's own ingredient, and whether it is not the product's
    (so user-edited on a product from Open Food Facts)."""
    if product["name"]:
        return cut_at_word(product["name"], NAME_MAX_LENGTH), False
    if product["brand"]:
        return cut_at_word(ingredient["name"], NAME_MAX_LENGTH), True
    suffix = f" ({product['barcode'][-4:]})"
    return cut_at_word(ingredient["name"], NAME_MAX_LENGTH - len(suffix)) + suffix, True


def _mean(values: list[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


def _add_columns() -> None:
    with op.batch_alter_table("ingredients", schema=None) as batch_op:
        batch_op.add_column(sa.Column("brand", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("brand_norm", sa.String(length=320), nullable=True))
        batch_op.add_column(sa.Column("barcode", sa.String(length=14), nullable=True))
        batch_op.add_column(sa.Column("quantity_text", sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column("pack_quantity", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("pack_unit", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("off_last_modified_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("fetched_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("user_edited_fields", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("pending_update", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("ignored_off_modified_at", sa.DateTime(), nullable=True))


def _move_products(connection: sa.Connection) -> None:
    """Rules 1 to 3 of the module docstring."""
    columns = (
        "id, name, category_id, base_unit, piece_weight_g, density_g_per_ml, "
        f"{', '.join(NUTRIENTS)}"
    )
    query = f"SELECT {columns} FROM ingredients ORDER BY id"  # noqa: S608 -- our own columns
    ingredients = list(connection.execute(sa.text(query)).mappings())
    products: dict[str, list[sa.RowMapping]] = defaultdict(list)
    for product in connection.execute(
        sa.text("SELECT * FROM products ORDER BY created_at, id")
    ).mappings():
        products[product["ingredient_id"]].append(product)
    connection.execute(
        sa.text("UPDATE ingredients SET source = 'manual', user_edited_fields = '[]'")
    )
    for ingredient in ingredients:
        linked = products.get(ingredient["id"], [])
        values = {
            key: ingredient[key]
            if ingredient[key] is not None
            else _mean([product[key] for product in linked if product[key] is not None])
            for key in NUTRIENTS
        }
        if len(linked) == 1:
            _absorb(connection, ingredient, linked[0], values)
        else:
            _set(connection, ingredient["id"], values)
        if len(linked) > 1:
            for product in linked:
                _split_off(connection, ingredient, product)


def _set(connection: sa.Connection, ingredient_id: str, values: dict[str, Any]) -> None:
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    connection.execute(
        sa.text(f"UPDATE ingredients SET {assignments} WHERE id = :id"),  # noqa: S608
        {**values, "id": ingredient_id},
    )


def _absorb(
    connection: sa.Connection,
    ingredient: sa.RowMapping,
    product: sa.RowMapping,
    values: dict[str, Any],
) -> None:
    """Rule 2: the ingredient takes over its only product."""
    edited = _edited_fields(product["user_edited_fields"])
    if product["source"] == "off":
        chosen = []
        if ingredient["name"] != product["name"]:
            chosen.append("name")
        chosen += [
            f"nutrients.{key}"
            for key in NUTRIENTS
            if ingredient[key] is not None and ingredient[key] != product[key]
        ]
        edited = [field for field in OFF_FIELDS if field in {*edited, *chosen}]
    _set(
        connection,
        ingredient["id"],
        {
            **values,
            **{column: product[column] for column in PRODUCT_COLUMNS},
            "brand_norm": _brand_norm(product["brand"]),
            "user_edited_fields": json.dumps(edited),
            "pending_update": _pending(product["pending_update"], keep_name=False),
        },
    )


def _split_off(
    connection: sa.Connection, ingredient: sa.RowMapping, product: sa.RowMapping
) -> None:
    """Rule 3: a product becomes an ingredient of its own."""
    name, not_the_products = _split_off_name(ingredient, product)
    edited = _edited_fields(product["user_edited_fields"])
    if not_the_products and product["source"] == "off":
        edited = [field for field in OFF_FIELDS if field in {*edited, "name"}]
    row = {
        "id": str(uuid.uuid7()),
        "name": name,
        "name_norm": normalize(name),
        "brand_norm": _brand_norm(product["brand"]),
        "category_id": ingredient["category_id"],
        "base_unit": ingredient["base_unit"],
        "piece_weight_g": ingredient["piece_weight_g"],
        "density_g_per_ml": ingredient["density_g_per_ml"],
        **{column: product[column] for column in PRODUCT_COLUMNS},
        **{key: product[key] for key in NUTRIENTS},
        "user_edited_fields": json.dumps(edited),
        "pending_update": _pending(product["pending_update"]),
        "created_by": product["created_by"],
        "updated_by": product["updated_by"],
        "created_at": product["created_at"],
        "updated_at": product["updated_at"],
    }
    columns = ", ".join(row)
    placeholders = ", ".join(f":{column}" for column in row)
    connection.execute(
        sa.text(f"INSERT INTO ingredients ({columns}) VALUES ({placeholders})"),  # noqa: S608
        row,
    )


def upgrade() -> None:
    _add_columns()
    # Names repeat from now on, also while the products move (rule 3).
    with op.batch_alter_table("ingredients", schema=None, recreate="always") as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_ingredients_name_norm"), type_="unique")
    _move_products(op.get_bind())
    with op.batch_alter_table("ingredients", schema=None, recreate="always") as batch_op:
        batch_op.alter_column("source", existing_type=sa.String(length=10), nullable=False)
        batch_op.alter_column("user_edited_fields", existing_type=sa.JSON(), nullable=False)
        batch_op.create_unique_constraint(batch_op.f("uq_ingredients_barcode"), ["barcode"])
        batch_op.create_check_constraint(
            batch_op.f("ck_ingredients_source"), "source IN ('off', 'manual')"
        )
        batch_op.create_index(batch_op.f("ix_ingredients_name_norm"), ["name_norm"], unique=False)

    with op.batch_alter_table("list_meal_ingredients", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("ingredient_brand_snapshot", sa.String(length=80), nullable=True)
        )

    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_products_updated_by"))
        batch_op.drop_index(batch_op.f("ix_products_ingredient_id"))
        batch_op.drop_index(batch_op.f("ix_products_created_by"))
    op.drop_table("products")


class DuplicateNamesError(RuntimeError):
    """The downgrade cannot restore the unique ingredient names."""


def _check_unique_names(connection: sa.Connection) -> None:
    duplicates = connection.execute(
        sa.text(
            "SELECT name_norm FROM ingredients GROUP BY name_norm HAVING count(*) > 1 "
            "ORDER BY name_norm LIMIT 10"
        )
    ).scalars()
    names = list(duplicates)
    if names:
        raise DuplicateNamesError(
            "cannot downgrade below 0007: several ingredients share a name "
            f"({', '.join(repr(name) for name in names)}), but names were unique before; "
            "merge or rename them first"
        )


def _create_products() -> None:
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


def _restore_products(connection: sa.Connection) -> None:
    """Each ingredient with a barcode gets its product back, linked to itself."""
    columns = (
        "id, name, base_unit, barcode, brand, quantity_text, pack_quantity, pack_unit, "
        f"{', '.join(NUTRIENTS)}, source, off_last_modified_at, fetched_at, user_edited_fields, "
        "pending_update, ignored_off_modified_at, created_by, updated_by, created_at, updated_at"
    )
    query = f"SELECT {columns} FROM ingredients WHERE barcode IS NOT NULL ORDER BY id"  # noqa: S608
    rows = list(connection.execute(sa.text(query)).mappings())
    for ingredient in rows:
        product = dict(ingredient)
        product["ingredient_id"] = product.pop("id")
        product["nutrition_basis"] = product.pop("base_unit")
        product["id"] = str(uuid.uuid7())
        columns = ", ".join(product)
        placeholders = ", ".join(f":{column}" for column in product)
        connection.execute(
            sa.text(f"INSERT INTO products ({columns}) VALUES ({placeholders})"),  # noqa: S608
            product,
        )


def downgrade() -> None:
    connection = op.get_bind()
    _check_unique_names(connection)
    _create_products()
    _restore_products(connection)

    with op.batch_alter_table("list_meal_ingredients", schema=None) as batch_op:
        batch_op.drop_column("ingredient_brand_snapshot")

    with op.batch_alter_table("ingredients", schema=None, recreate="always") as batch_op:
        batch_op.drop_index(batch_op.f("ix_ingredients_name_norm"))
        batch_op.drop_constraint(batch_op.f("ck_ingredients_source"), type_="check")
        batch_op.drop_constraint(batch_op.f("uq_ingredients_barcode"), type_="unique")
        batch_op.create_unique_constraint(batch_op.f("uq_ingredients_name_norm"), ["name_norm"])
        batch_op.drop_column("ignored_off_modified_at")
        batch_op.drop_column("pending_update")
        batch_op.drop_column("user_edited_fields")
        batch_op.drop_column("fetched_at")
        batch_op.drop_column("off_last_modified_at")
        batch_op.drop_column("source")
        batch_op.drop_column("pack_unit")
        batch_op.drop_column("pack_quantity")
        batch_op.drop_column("quantity_text")
        batch_op.drop_column("barcode")
        batch_op.drop_column("brand_norm")
        batch_op.drop_column("brand")
