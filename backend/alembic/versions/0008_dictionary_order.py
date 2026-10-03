"""dictionary order: sort keys for meals and ingredients (D-27)

Meals and ingredients sort in dictionary order (ING-03, MEAL-09): by a key built from the name
as typed (lowercase, `ä→a ö→o ü→u ß→ss`, accents stripped), so "Äpfel im Schlafrock" sits next
to "Apfelstrudel"; ingredients then by the brand's key. `meals` gains `name_sort`, `ingredients`
`name_sort` and `brand_sort`, filled for every existing row. Only columns are added; no existing
value changes, and the downgrade drops them again.

`sort_key` is copied from `app.domain.text` as it was when this migration was written, so that
later changes there cannot change what it does.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-02 00:00:00+00:00
"""

import unicodedata
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DICTIONARY_FOLDS = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})


def sort_key(text: str) -> str:
    """`app.domain.text.sort_key` as of this revision."""
    folded = unicodedata.normalize("NFKC", text).lower().translate(_DICTIONARY_FOLDS)
    decomposed = unicodedata.normalize("NFKD", folded)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(stripped.split())


def _fill_meals(connection: sa.Connection) -> None:
    rows = connection.execute(sa.text("SELECT id, name FROM meals")).all()
    if rows:
        connection.execute(
            sa.text("UPDATE meals SET name_sort = :name_sort WHERE id = :id"),
            [{"id": row_id, "name_sort": sort_key(name)} for row_id, name in rows],
        )


def _fill_ingredients(connection: sa.Connection) -> None:
    """As `services.off_fields.set_name` and `set_brand` do: no brand, no brand key."""
    rows = connection.execute(sa.text("SELECT id, name, brand FROM ingredients")).all()
    if rows:
        connection.execute(
            sa.text(
                "UPDATE ingredients SET name_sort = :name_sort, brand_sort = :brand_sort "
                "WHERE id = :id"
            ),
            [
                {
                    "id": row_id,
                    "name_sort": sort_key(name),
                    "brand_sort": None if brand is None else sort_key(brand) or None,
                }
                for row_id, name, brand in rows
            ],
        )


def upgrade() -> None:
    with op.batch_alter_table("meals", schema=None) as batch_op:
        batch_op.add_column(sa.Column("name_sort", sa.String(length=320), nullable=True))
    with op.batch_alter_table("ingredients", schema=None) as batch_op:
        batch_op.add_column(sa.Column("name_sort", sa.String(length=240), nullable=True))
        batch_op.add_column(sa.Column("brand_sort", sa.String(length=320), nullable=True))

    connection = op.get_bind()
    _fill_meals(connection)
    _fill_ingredients(connection)

    with op.batch_alter_table("meals", schema=None) as batch_op:
        batch_op.alter_column("name_sort", existing_type=sa.String(length=320), nullable=False)
        batch_op.create_index(batch_op.f("ix_meals_name_sort"), ["name_sort"], unique=False)
    with op.batch_alter_table("ingredients", schema=None) as batch_op:
        batch_op.alter_column("name_sort", existing_type=sa.String(length=240), nullable=False)
        batch_op.create_index(batch_op.f("ix_ingredients_name_sort"), ["name_sort"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ingredients", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ingredients_name_sort"))
        batch_op.drop_column("brand_sort")
        batch_op.drop_column("name_sort")
    with op.batch_alter_table("meals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_meals_name_sort"))
        batch_op.drop_column("name_sort")
