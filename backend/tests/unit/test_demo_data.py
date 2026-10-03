"""The demo data (`mealmate seed-demo`) follows the unit rules, so a fresh demo flags nothing."""

from app.domain.units import fits
from app.services import demo


def base_unit(name: str, brand: str | None) -> str:
    """The base unit of the demo ingredient a row or extra item names (the brand picks one of
    several of the same name)."""
    [item] = [
        item
        for item in demo.DEMO_INGREDIENTS
        if item.name == name and (brand is None or item.brand == brand)
    ]
    return item.base_unit


def test_every_demo_amount_fits_its_ingredient() -> None:
    """REF-02, D-32: meal rows and linked extra items use units that fit."""
    rows = [row for meal in (*demo.DEMO_MEALS, demo.DEMO_DELETED_MEAL) for row in meal.rows]
    extras = [
        extra
        for demo_list in demo.DEMO_LISTS
        for extra in (
            *demo_list.extras,
            *(demo_list.shopping.added if demo_list.shopping else ()),
        )
        if extra.ingredient is not None
    ]
    assert rows
    assert extras
    for row in rows:
        assert fits(row.amount, row.unit, base_unit(row.ingredient, row.brand)), row
    for extra in extras:
        assert extra.ingredient is not None
        assert fits(extra.amount, extra.unit, base_unit(extra.ingredient, extra.brand)), extra


def test_only_demo_ingredients_counted_in_pieces_have_a_piece_weight() -> None:
    """ING-02, D-32."""
    for item in demo.DEMO_INGREDIENTS:
        assert item.piece_weight_g is None or item.base_unit == "piece", item
