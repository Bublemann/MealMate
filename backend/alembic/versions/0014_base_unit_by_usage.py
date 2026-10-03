"""base units by usage: what is counted in pieces becomes Stück; the density goes (D-34)

Since D-32 an ingredient is counted in one base unit, and nothing converts between grams,
millilitres and pieces. The ingredients from before move to it by how they are used, the only
evidence of how people count them:

1. A `g` or `ml` ingredient becomes `piece` when meal rows or linked extra items on drafts use
   it with an amount, and every such amount is in pieces (unit `piece` or none). Rows and extra
   items without an amount don't count, nor do deleted extra items, frozen rows and the extra
   items of lists being shopped and done lists (they keep what they copied, LIST-11). It keeps
   its piece weight. Its values are per 100 g from now on: a former `ml` ingredient with a
   density has them converted from per 100 ml with it (a value above the nutrient's plausible
   maximum becomes unknown, as from Open Food Facts, BAR-10); one without keeps them as they
   are. Either way its pending Open Food Facts nutrients were per 100 ml, so they go, as with a
   base-unit change over the API (ING-02); the ones the user ignored stay remembered.
2. Every other `g` or `ml` ingredient keeps its base unit and loses its piece weight. A `piece`
   ingredient stays as it is.
3. `ingredients.density_g_per_ml` is dropped. Frozen rows keep `piece_weight_g_snapshot` and
   `density_snapshot`, and extra items their `attrs_snapshot`, so lists being shopped and done
   lists don't change (D-08).

Amounts that no longer fit their ingredient stay as they are; the app flags them (D-33). This
is nobody's edit, so `updated_at` and `updated_by` stay, and no list's version changes.

The downgrade can't give back the base units, piece weights, densities and values per 100 ml
this took, so it refuses while there are ingredients; the backup taken before the update is the
way back. Without ingredients it adds the empty column again.

The nutrient keys and maximums are copied from `app.domain.nutrients` as they were when this
migration was written, so that later changes there cannot change what it does.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-03 00:00:00+00:00
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MAX_PER_100 = {"kcal": 900.0, "protein": 100.0, "carbs": 100.0, "sugar": 100.0, "fat": 100.0}
NUTRIENT_FIELDS = {f"nutrients.{key}" for key in MAX_PER_100}
IGNORED = "ignored"

# Every amount of an ingredient that counts (rule 1), with its unit.
_AMOUNTS = """
    SELECT ingredient_id, unit FROM meal_ingredients WHERE amount IS NOT NULL
    UNION ALL
    SELECT list_extra_items.ingredient_id, list_extra_items.unit
    FROM list_extra_items JOIN shopping_lists ON shopping_lists.id = list_extra_items.list_id
    WHERE shopping_lists.status = 'draft' AND list_extra_items.deleted_at IS NULL
        AND list_extra_items.ingredient_id IS NOT NULL AND list_extra_items.amount IS NOT NULL
"""


def _counted_in_pieces(connection: sa.Connection) -> list[sa.RowMapping]:
    """Rule 1: the g and ml ingredients whose amounts are all in pieces, at least one."""
    nutrients = ", ".join(MAX_PER_100)
    query = f"""
        SELECT id, base_unit, density_g_per_ml, pending_update, {nutrients} FROM ingredients
        WHERE base_unit IN ('g', 'ml') AND id IN (
            SELECT ingredient_id FROM ({_AMOUNTS}) GROUP BY ingredient_id
            HAVING sum(unit IS NOT NULL AND unit <> 'piece') = 0
        )
        ORDER BY id
    """  # noqa: S608 -- our own columns
    return list(connection.execute(sa.text(query)).mappings())


def _per_100_g(key: str, value: float | None, density: float) -> float | None:
    if value is None:
        return None
    converted = value / density
    return converted if converted <= MAX_PER_100[key] else None


def _without_pending_nutrients(value: str | None) -> str | None:
    """A pending update without the nutrients the user hasn't ignored."""
    stored = {} if value is None else json.loads(value)
    kept = {
        field: entry
        for field, entry in stored.items()
        if field not in NUTRIENT_FIELDS or entry.get(IGNORED)
    }
    return json.dumps(kept) if kept else None


def _to_pieces(connection: sa.Connection, ingredient: sa.RowMapping) -> None:
    """Rule 1 for one ingredient."""
    values: dict[str, object] = {"base_unit": "piece"}
    if ingredient["base_unit"] == "ml":
        if density := ingredient["density_g_per_ml"]:
            values |= {key: _per_100_g(key, ingredient[key], density) for key in MAX_PER_100}
        values["pending_update"] = _without_pending_nutrients(ingredient["pending_update"])
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    connection.execute(
        sa.text(f"UPDATE ingredients SET {assignments} WHERE id = :id"),  # noqa: S608
        {**values, "id": ingredient["id"]},
    )


def upgrade() -> None:
    connection = op.get_bind()
    for ingredient in _counted_in_pieces(connection):
        _to_pieces(connection, ingredient)
    connection.execute(
        sa.text("UPDATE ingredients SET piece_weight_g = NULL WHERE base_unit IN ('g', 'ml')")
    )
    with op.batch_alter_table("ingredients", schema=None) as batch_op:
        batch_op.drop_column("density_g_per_ml")


class BaseUnitsByUsageError(RuntimeError):
    """The downgrade cannot give back what the upgrade took."""


def downgrade() -> None:
    ingredients = op.get_bind().execute(sa.text("SELECT count(*) FROM ingredients")).scalar_one()
    if ingredients:
        raise BaseUnitsByUsageError(
            "cannot downgrade below 0014: it gave ingredients their base unit by how they were "
            "used and dropped their densities and the piece weights of those counted in g or ml "
            f"(D-34), which can't be given back to the {ingredients} ingredients there are; "
            "restore the backup taken before the update instead"
        )
    with op.batch_alter_table("ingredients", schema=None) as batch_op:
        batch_op.add_column(sa.Column("density_g_per_ml", sa.Float(), nullable=True))
