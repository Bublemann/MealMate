"""base unit Stück: ingredients and frozen rows can be counted in pieces (D-32)

An ingredient's base unit (`ingredients.base_unit`) and its copy in frozen rows
(`list_meal_ingredients.base_unit_snapshot`, LIST-11) accept `piece` besides `g` and `ml`. Only
the allowed values widen; no existing value changes. The downgrade refuses while an ingredient
or a frozen row is counted in pieces, since `g` and `ml` can't hold that.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-02 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    ("ingredients", "base_unit"),
    ("list_meal_ingredients", "base_unit_snapshot"),
)


def _base_unit_column(
    table: str, column: str, *, old_length: int, new_length: int, base_units: str
) -> None:
    with op.batch_alter_table(table, schema=None, recreate="always") as batch_op:
        batch_op.drop_constraint(batch_op.f(f"ck_{table}_{column}"), type_="check")
        batch_op.alter_column(
            column,
            existing_type=sa.String(length=old_length),
            type_=sa.String(length=new_length),
            existing_nullable=False,
        )
        batch_op.create_check_constraint(
            batch_op.f(f"ck_{table}_{column}"), f"{column} IN ({base_units})"
        )


def upgrade() -> None:
    for table, column in _TABLES:
        _base_unit_column(
            table, column, old_length=2, new_length=5, base_units="'g', 'ml', 'piece'"
        )


class CountedInPiecesError(RuntimeError):
    """The downgrade cannot hold the base unit `piece`."""


def _counted(number: int, singular: str, plural: str) -> str:
    return f"{number} {singular if number == 1 else plural}"


def _check_nothing_in_pieces(connection: sa.Connection) -> None:
    ingredients = connection.execute(
        sa.text("SELECT count(*) FROM ingredients WHERE base_unit = 'piece'")
    ).scalar_one()
    rows = connection.execute(
        sa.text("SELECT count(*) FROM list_meal_ingredients WHERE base_unit_snapshot = 'piece'")
    ).scalar_one()
    if ingredients or rows:
        raise CountedInPiecesError(
            "cannot downgrade below 0009: "
            f"{_counted(ingredients, 'ingredient', 'ingredients')} and "
            f"{_counted(rows, 'frozen row', 'frozen rows')} are counted in pieces, which the "
            "base units g and ml of 0008 can't hold; give them the base unit g or ml first"
        )


def downgrade() -> None:
    _check_nothing_in_pieces(op.get_bind())
    for table, column in _TABLES:
        _base_unit_column(table, column, old_length=5, new_length=2, base_units="'g', 'ml'")
