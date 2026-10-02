"""Units and conversion to an ingredient's base unit (REF-02, NUT-05)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.units import (
    BASE_KIND,
    UNIT_FACTOR,
    UNIT_KIND,
    BaseUnit,
    Converted,
    IngredientAttrs,
    Unit,
    UnitKind,
    convert,
    in_kind_base,
)

G = IngredientAttrs(BaseUnit.G, piece_weight_g=None, density_g_per_ml=None)
G_PIECE = IngredientAttrs(BaseUnit.G, piece_weight_g=60, density_g_per_ml=None)
G_DENSE = IngredientAttrs(BaseUnit.G, piece_weight_g=None, density_g_per_ml=0.92)
ML = IngredientAttrs(BaseUnit.ML, piece_weight_g=None, density_g_per_ml=None)
ML_PIECE = IngredientAttrs(BaseUnit.ML, piece_weight_g=1030, density_g_per_ml=None)
ML_FULL = IngredientAttrs(BaseUnit.ML, piece_weight_g=1030, density_g_per_ml=1.03)
G_ZERO = IngredientAttrs(BaseUnit.G, piece_weight_g=0, density_g_per_ml=0)
EGGS = IngredientAttrs(BaseUnit.PIECE, piece_weight_g=60, density_g_per_ml=None)
EGGS_BARE = IngredientAttrs(BaseUnit.PIECE, piece_weight_g=None, density_g_per_ml=None)
EGGS_DENSE = IngredientAttrs(BaseUnit.PIECE, piece_weight_g=60, density_g_per_ml=1.03)


def test_units_in_display_order() -> None:
    assert [unit.value for unit in Unit] == ["g", "kg", "ml", "l", "piece", "tbsp", "tsp"]
    assert set(UNIT_KIND) == set(Unit) == set(UNIT_FACTOR)
    assert [unit for unit in Unit if UNIT_KIND[unit] is UnitKind.VOLUME] == [
        Unit.ML,
        Unit.L,
        Unit.TBSP,
        Unit.TSP,
    ]
    assert [base_unit.value for base_unit in BaseUnit] == ["g", "ml", "piece"]
    assert BASE_KIND == {
        BaseUnit.G: UnitKind.MASS,
        BaseUnit.ML: UnitKind.VOLUME,
        BaseUnit.PIECE: UnitKind.COUNT,
    }


@pytest.mark.parametrize(
    ("amount", "unit", "expected"),
    [(3, Unit.G, 3), (1.5, Unit.KG, 1500), (7, Unit.ML, 7), (0.25, Unit.L, 250),
     (2, Unit.PIECE, 2), (2, Unit.TBSP, 30), (3, Unit.TSP, 15)],
)  # fmt: skip
def test_in_kind_base(amount: float, unit: Unit, expected: float) -> None:
    assert in_kind_base(amount, unit) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("amount", "unit", "attrs", "estimate_allowed", "expected"),
    [
        # g ingredient: mass by factor, volume needs a density, spoons may be estimated.
        (250, Unit.G, G, False, Converted(250, estimate=False)),
        (1.2, Unit.KG, G, False, Converted(1200, estimate=False)),
        (100, Unit.ML, G, True, None),
        (1, Unit.L, G, True, None),
        (2, Unit.TBSP, G, False, None),
        (2, Unit.TBSP, G, True, Converted(30, estimate=True)),
        (1, Unit.TSP, G, True, Converted(5, estimate=True)),
        (2, Unit.PIECE, G, True, None),
        (100, Unit.ML, G_DENSE, False, Converted(92, estimate=False)),
        (1, Unit.TBSP, G_DENSE, True, Converted(13.8, estimate=False)),
        (1, Unit.L, G_DENSE, False, Converted(920, estimate=False)),
        (2, Unit.PIECE, G_PIECE, False, Converted(120, estimate=False)),
        (2, Unit.PIECE, G_DENSE, True, None),
        # ml ingredient: volume by factor, mass needs a density, pieces need both.
        (1, Unit.L, ML, False, Converted(1000, estimate=False)),
        (2, Unit.TBSP, ML, False, Converted(30, estimate=False)),
        (1, Unit.TSP, ML, True, Converted(5, estimate=False)),
        (100, Unit.G, ML, True, None),
        (1, Unit.PIECE, ML_PIECE, True, None),
        (103, Unit.G, ML_FULL, False, Converted(100, estimate=False)),
        (1, Unit.KG, ML_FULL, False, Converted(1000 / 1.03, estimate=False)),
        (1, Unit.PIECE, ML_FULL, False, Converted(1000, estimate=False)),
        # piece ingredient: pieces stay pieces, with or without a piece weight; grams and
        # millilitres don't say how many pieces they are, not even with a density.
        (2, Unit.PIECE, EGGS, False, Converted(2, estimate=False)),
        (0.5, Unit.PIECE, EGGS_BARE, False, Converted(0.5, estimate=False)),
        (120, Unit.G, EGGS, True, None),
        (1, Unit.KG, EGGS_DENSE, True, None),
        (100, Unit.ML, EGGS_DENSE, True, None),
        (1, Unit.TBSP, EGGS, True, None),
        (1, Unit.TSP, EGGS_BARE, True, None),
        # A zero piece weight or density counts as missing.
        (1, Unit.PIECE, G_ZERO, True, None),
        (1, Unit.ML, G_ZERO, False, None),
    ],
)
def test_convert(
    amount: float,
    unit: Unit,
    attrs: IngredientAttrs,
    estimate_allowed: bool,
    expected: Converted | None,
) -> None:
    result = convert(amount, unit, attrs, allow_estimate=estimate_allowed)
    if expected is None:
        assert result is None
    else:
        assert result is not None
        assert result.value == pytest.approx(expected.value)
        assert result.estimate is expected.estimate


@pytest.mark.parametrize(
    ("base_unit", "amount", "unit", "expected"),
    [
        ("g", 2, Unit.PIECE, 120),
        ("g", 1, Unit.L, 1030),
        ("ml", 1, Unit.L, 1000),
        ("ml", 103, Unit.G, 100),
        ("ml", 1, Unit.PIECE, 60 / 1.03),
        ("piece", 3, Unit.PIECE, 3),
    ],
)
def test_base_unit_as_a_plain_string(
    base_unit: str, amount: float, unit: Unit, expected: float
) -> None:
    """Rows and JSON snapshots hold the base unit as a plain string."""
    attrs = IngredientAttrs(base_unit, piece_weight_g=60, density_g_per_ml=1.03)
    assert attrs.base_unit is BaseUnit(base_unit)
    assert attrs == IngredientAttrs(BaseUnit(base_unit), piece_weight_g=60, density_g_per_ml=1.03)
    result = convert(amount, unit, attrs, allow_estimate=False)
    assert result is not None
    assert result.value == pytest.approx(expected)


def test_an_unknown_base_unit_is_refused() -> None:
    with pytest.raises(ValueError, match="'kg' is not a valid BaseUnit"):
        IngredientAttrs("kg", piece_weight_g=None, density_g_per_ml=None)


attrs_strategy = st.builds(
    IngredientAttrs,
    base_unit=st.sampled_from(BaseUnit),
    piece_weight_g=st.none() | st.floats(0.1, 10_000),
    density_g_per_ml=st.none() | st.floats(0.1, 5),
)


@given(
    amount=st.floats(0.001, 100_000),
    factor=st.floats(0.01, 100),
    unit=st.sampled_from(Unit),
    attrs=attrs_strategy,
    estimate_allowed=st.booleans(),
)
def test_conversion_is_linear(
    amount: float, factor: float, unit: Unit, attrs: IngredientAttrs, estimate_allowed: bool
) -> None:
    once = convert(amount, unit, attrs, allow_estimate=estimate_allowed)
    scaled = convert(amount * factor, unit, attrs, allow_estimate=estimate_allowed)
    if once is None:
        assert scaled is None
    else:
        assert scaled is not None
        assert scaled.value == pytest.approx(once.value * factor, rel=1e-9)
        assert scaled.estimate is once.estimate


@given(amount=st.floats(0.001, 100_000), unit=st.sampled_from(Unit), attrs=attrs_strategy)
def test_the_base_kind_always_converts_without_estimate(
    amount: float, unit: Unit, attrs: IngredientAttrs
) -> None:
    result = convert(amount, unit, attrs, allow_estimate=True)
    if UNIT_KIND[unit] is BASE_KIND[attrs.base_unit]:
        assert result == Converted(in_kind_base(amount, unit), estimate=False)
    if result is not None and result.estimate:
        assert unit in {Unit.TBSP, Unit.TSP}
        assert attrs.base_unit is BaseUnit.G


@given(amount=st.floats(0.001, 100_000), unit=st.sampled_from(Unit), attrs=attrs_strategy)
def test_a_piece_ingredient_converts_only_pieces(
    amount: float, unit: Unit, attrs: IngredientAttrs
) -> None:
    """Whatever piece weight and density it has (REF-02, D-32)."""
    piece = IngredientAttrs(BaseUnit.PIECE, attrs.piece_weight_g, attrs.density_g_per_ml)
    result = convert(amount, unit, piece, allow_estimate=True)
    if unit is Unit.PIECE:
        assert result == Converted(amount, estimate=False)
    else:
        assert result is None
