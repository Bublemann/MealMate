"""items: the ingredients table becomes items, and what points at it item_id

What one buys is now an item (GLOSSARY.md); an ingredient is an item as used in a meal. So the
`ingredients` table becomes `items`, and every column that points at one is renamed for it:
`ingredient_id` becomes `item_id` on meal rows, frozen rows, extra items, hidden due items and
recurring items, and the frozen rows' `ingredient_name_snapshot` and `ingredient_brand_snapshot`
become `item_name_snapshot` and `item_brand_snapshot`. The meal rows keep their tables
(`meal_ingredients`, `list_meal_ingredients`): they are ingredients in the new sense. The
constraint and index names follow the naming convention (`app.db.base`). Nothing else changes:
every row stays as it is, the frozen copies on lists being shopped and done lists included.

SQLite can't rename a constraint, so each table is rebuilt from its own `CREATE TABLE`
statement with the names replaced, and its rows are copied over unchanged; its indexes are
created again under their new names. The downgrade does the same the other way round.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-26 00:00:00+00:00
"""

import re
from collections.abc import Mapping, Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_TABLE, NEW_TABLE = "ingredients", "items"
# The tables whose columns point at an item; their own names stay.
REFERRING_TABLES = (
    "meal_ingredients",
    "list_meal_ingredients",
    "list_extra_items",
    "list_hidden_due_items",
    "recurring_items",
)
COLUMNS = {
    "ingredient_id": "item_id",
    "ingredient_name_snapshot": "item_name_snapshot",
    "ingredient_brand_snapshot": "item_brand_snapshot",
}
# The constraint and index names of the renamed table, `{}` standing for its name.
ITEM_NAMES = (
    "pk_{}",
    "fk_{}_category_id_categories",
    "fk_{}_created_by_users",
    "fk_{}_updated_by_users",
    "ck_{}_base_unit",
    "ck_{}_source",
    "uq_{}_barcode",
    "ix_{}_category_id",
    "ix_{}_created_by",
    "ix_{}_updated_by",
    "ix_{}_name_norm",
    "ix_{}_name_sort",
)
# Whole identifiers in the schema's SQL, old → new.
RENAMES: Mapping[str, str] = {
    OLD_TABLE: NEW_TABLE,
    **{name.format(OLD_TABLE): name.format(NEW_TABLE) for name in ITEM_NAMES},
    **COLUMNS,
    **{f"fk_{t}_ingredient_id_ingredients": f"fk_{t}_item_id_items" for t in REFERRING_TABLES},
    **{f"ix_{t}_ingredient_id": f"ix_{t}_item_id" for t in REFERRING_TABLES},
    "ck_list_extra_items_ingredient_or_text": "ck_list_extra_items_item_or_text",
    "uq_recurring_items_couple_id_ingredient_id": "uq_recurring_items_couple_id_item_id",
    "uq_recurring_items_user_id_ingredient_id": "uq_recurring_items_user_id_item_id",
}  # fmt: skip


def _renamed(sql: str, renames: Mapping[str, str]) -> str:
    # Whole words only, so `meal_ingredients` stays; this would also rewrite a word in a string
    # literal, but no CHECK or index in these tables has one that is renamed.
    return re.sub(r"\w+", lambda word: renames.get(word[0], word[0]), sql)


def _rebuild(table: str, renames: Mapping[str, str]) -> None:
    """Rebuild `table` from its own SQL with the identifiers in `renames` replaced, under its
    new name if it has one, with every row copied as it is (the columns keep their order)."""
    connection = op.get_bind()
    [table_sql] = connection.execute(
        sa.text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = :name"),
        {"name": table},
    ).scalars()
    index_sqls = (
        connection.execute(
            sa.text(
                "SELECT sql FROM sqlite_master"
                " WHERE type = 'index' AND tbl_name = :name AND sql IS NOT NULL ORDER BY name"
            ),
            {"name": table},
        )
        .scalars()
        .all()
    )
    new_name = renames.get(table, table)
    source = table
    if new_name == table:
        # The rebuilt table takes the old one's name: keep the rows in a copy of it meanwhile.
        source = f"_alembic_tmp_{table}"
        temporary = re.sub(rf'^CREATE TABLE "?{table}"?', f'CREATE TABLE "{source}"', table_sql)
        connection.exec_driver_sql(temporary)
        connection.exec_driver_sql(f'INSERT INTO "{source}" SELECT * FROM "{table}"')  # noqa: S608
        connection.exec_driver_sql(f'DROP TABLE "{table}"')
    connection.exec_driver_sql(_renamed(table_sql, renames))
    connection.exec_driver_sql(f'INSERT INTO "{new_name}" SELECT * FROM "{source}"')  # noqa: S608
    connection.exec_driver_sql(f'DROP TABLE "{source}"')
    for index_sql in index_sqls:
        connection.exec_driver_sql(_renamed(index_sql, renames))


def upgrade() -> None:
    for table in (OLD_TABLE, *REFERRING_TABLES):
        _rebuild(table, RENAMES)


def downgrade() -> None:
    back = {new: old for old, new in RENAMES.items()}
    for table in (NEW_TABLE, *REFERRING_TABLES):
        _rebuild(table, back)
