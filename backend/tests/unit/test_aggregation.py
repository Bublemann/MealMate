"""Aggregation into lines, display rounding and "needs more" (AGG-02..05, LIST-12)."""

from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.aggregation import (
    CheckSnapshot,
    DisplayAmount,
    Line,
    LineTotals,
    NeedsMore,
    Part,
    SourceRef,
    aggregate,
    display,
    grown_display,
    needs_more,
    text_changed,
    totals,
)
from app.domain.units import BASE_KIND, BaseUnit, IngredientAttrs, Unit, UnitKind

MASS, VOLUME, COUNT = UnitKind.MASS, UnitKind.VOLUME, UnitKind.COUNT
PLAIN = IngredientAttrs(BaseUnit.G, piece_weight_g=None, density_g_per_ml=None)
ONION = IngredientAttrs(BaseUnit.G, piece_weight_g=150, density_g_per_ml=None)
OIL = IngredientAttrs(BaseUnit.ML, piece_weight_g=None, density_g_per_ml=0.92)
MILK = IngredientAttrs(BaseUnit.ML, piece_weight_g=1030, density_g_per_ml=1.03)
APPLES = IngredientAttrs(BaseUnit.G, piece_weight_g=180, density_g_per_ml=None)
APPLES_ML = IngredientAttrs(BaseUnit.ML, piece_weight_g=180, density_g_per_ml=1.0)
HEAVY_APPLES = IngredientAttrs(BaseUnit.G, piece_weight_g=200, density_g_per_ml=None)
HONEY = IngredientAttrs(BaseUnit.G, piece_weight_g=None, density_g_per_ml=1.4)
EGGS = IngredientAttrs(BaseUnit.PIECE, piece_weight_g=60, density_g_per_ml=None)
APPLE_PIECES = IngredientAttrs(BaseUnit.PIECE, piece_weight_g=180, density_g_per_ml=None)
MEAL = SourceRef("meal", "m1")


def part(
    amount: float | None,
    unit: Unit | None,
    attrs: IngredientAttrs | None = PLAIN,
    key: str = "i:1",
    source: SourceRef = MEAL,
) -> Part:
    return Part(key, amount, unit, attrs, source)


def seg(**values: float) -> dict[UnitKind, float]:
    names = {"mass": MASS, "volume": VOLUME, "count": COUNT}
    return {names[name]: value for name, value in values.items()}


# --- totals (AGG-03) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("parts", "segments", "unspecified", "spoons_only"),
    [
        ([], {}, False, False),
        ([part(None, None)], {}, True, False),
        ([part(500, Unit.G), part(0.5, Unit.KG)], seg(mass=1000), False, False),
        # One kind: nothing is converted, pieces stay pieces and spoons stay a volume.
        ([part(1, Unit.PIECE, ONION), part(2, Unit.PIECE, ONION)], seg(count=3), False, False),
        ([part(1, Unit.TBSP), part(3, Unit.TSP)], seg(volume=30), False, True),
        ([part(1, Unit.TBSP), part(100, Unit.ML)], seg(volume=115), False, False),
        ([part(0.2, Unit.L, OIL)], seg(volume=200), False, False),
        # Mixed kinds: converted to the base unit where possible.
        ([part(500, Unit.G, ONION), part(2, Unit.PIECE, ONION)], seg(mass=800), False, False),
        ([part(500, Unit.G), part(2, Unit.PIECE)], seg(mass=500, count=2), False, False),
        ([part(100, Unit.G), part(2, Unit.TBSP)], seg(mass=100, volume=30), False, True),
        (
            [part(92, Unit.G, OIL), part(1, Unit.TBSP, OIL)],
            seg(volume=115),
            False,
            False,
        ),
        (
            [part(1, Unit.L, MILK), part(1, Unit.PIECE, MILK), part(103, Unit.G, MILK)],
            seg(volume=2100),
            False,
            False,
        ),
        (
            [part(1, Unit.PIECE, OIL), part(1, Unit.TBSP, OIL)],
            seg(volume=15, count=1),
            False,
            True,
        ),
        # A piece ingredient: its pieces add up; other kinds sit beside them, even with a
        # piece weight (AGG-03).
        ([part(2, Unit.PIECE, EGGS), part(1.5, Unit.PIECE, EGGS)], seg(count=3.5), False, False),
        (
            [part(2, Unit.PIECE, EGGS), part(120, Unit.G, EGGS)],
            seg(mass=120, count=2),
            False,
            False,
        ),
        (
            [part(2, Unit.PIECE, EGGS), part(1, Unit.TBSP, EGGS)],
            seg(volume=15, count=2),
            False,
            True,
        ),
        # Frozen as a g ingredient with a piece weight, live as a piece ingredient: the frozen
        # parts keep converting, the live pieces stay pieces.
        (
            [
                part(100, Unit.G, APPLES),
                part(2, Unit.PIECE, APPLES),
                part(1, Unit.PIECE, APPLE_PIECES),
            ],
            seg(mass=460, count=1),
            False,
            False,
        ),
        # Free text (no attributes) and parts without an amount.
        ([part(2, Unit.PIECE, None), part(10, Unit.G, None)], seg(mass=10, count=2), False, False),
        ([part(500, Unit.G), part(None, None), part(1, None)], seg(mass=500), True, False),
    ],
)
def test_totals(
    parts: list[Part], segments: dict[UnitKind, float], unspecified: bool, spoons_only: bool
) -> None:
    result = totals(parts)
    assert result.segments == pytest.approx(segments)
    assert list(result.segments) == [kind for kind in (MASS, VOLUME, COUNT) if kind in segments]
    assert result.has_unspecified is unspecified
    assert result.spoons_only is spoons_only


@pytest.mark.parametrize(
    ("parts", "base_total", "base_unit"),
    [
        # Every part with an amount converts strictly: the total in the base unit.
        ([part(2, Unit.PIECE, ONION)], 300, BaseUnit.G),
        ([part(500, Unit.G, ONION), part(2, Unit.PIECE, ONION)], 800, BaseUnit.G),
        ([part(500, Unit.G), part(None, None), part(1, None)], 500, BaseUnit.G),
        ([part(92, Unit.G, OIL), part(1, Unit.TBSP, OIL)], 115, BaseUnit.ML),
        ([part(1, Unit.L, MILK), part(1, Unit.PIECE, MILK)], 2000, BaseUnit.ML),
        ([part(2, Unit.PIECE, EGGS), part(1.5, Unit.PIECE, EGGS)], 3.5, BaseUnit.PIECE),
        ([part(2, Unit.PIECE, EGGS), part(None, None, EGGS)], 2, BaseUnit.PIECE),
        # Otherwise none: nothing measured, a part that does not convert, free text, or
        # parts with different base units.
        ([], None, None),
        ([part(None, None)], None, None),
        ([part(2, Unit.PIECE)], None, None),
        ([part(500, Unit.G, ONION), part(1, Unit.TBSP, ONION)], None, None),
        ([part(1, Unit.TBSP)], None, None),  # no 1 g/ml estimate
        ([part(2, Unit.PIECE, None)], None, None),
        ([part(100, Unit.G), part(100, Unit.ML, OIL)], None, None),
        ([part(2, Unit.PIECE, EGGS), part(120, Unit.G, EGGS)], None, None),
        ([part(2, Unit.PIECE, APPLES), part(1, Unit.PIECE, APPLE_PIECES)], None, None),
    ],
)
def test_base_total(
    parts: list[Part], base_total: float | None, base_unit: BaseUnit | None
) -> None:
    result = totals(parts)
    assert result.base_total == pytest.approx(base_total)
    assert result.base_unit is base_unit


# --- display rounding (AGG-04) -----------------------------------------------------------------


def shown(segments: dict[UnitKind, float], *, spoons_only: bool = False) -> list[tuple[float, str]]:
    result = display(LineTotals(segments, has_unspecified=False, spoons_only=spoons_only))
    return [(item.value, item.unit.value) for item in result]


@pytest.mark.parametrize(
    ("segments", "expected"),
    [
        (seg(mass=499.5), [(500, "g")]),
        (seg(mass=499.4999), [(499, "g")]),
        (seg(mass=2.5), [(3, "g")]),
        (seg(mass=0.2), [(1, "g")]),
        (seg(mass=0), [(0, "g")]),
        (seg(mass=999.4), [(999, "g")]),
        (seg(mass=999.5), [(1, "kg")]),
        (seg(mass=1000), [(1, "kg")]),
        (seg(mass=1250), [(1.25, "kg")]),
        (seg(mass=1255), [(1.26, "kg")]),
        # The unit comes from the whole grams, the kilograms from the exact amount.
        (seg(mass=1254.6), [(1.25, "kg")]),
        (seg(mass=999.6), [(1, "kg")]),
        (seg(mass=2004.999), [(2, "kg")]),
        (seg(mass=1004), [(1, "kg")]),
        (seg(mass=1005), [(1.01, "kg")]),
        (seg(mass=12_345.6), [(12.35, "kg")]),
        (seg(volume=250.4), [(250, "ml")]),
        (seg(volume=0.01), [(1, "ml")]),
        (seg(volume=1500), [(1.5, "l")]),
        (seg(volume=1254.6), [(1.25, "l")]),
        (seg(volume=999.6), [(1, "l")]),
        (seg(volume=2004.999), [(2, "l")]),
        (seg(count=2), [(2, "piece")]),
        (seg(count=2.0000000001), [(2, "piece")]),
        (seg(count=2.01), [(3, "piece")]),
        (seg(count=0.1), [(1, "piece")]),
        (seg(count=0.0000001), [(1, "piece")]),
        (seg(count=0), [(0, "piece")]),
        (seg(mass=500, volume=30, count=2), [(500, "g"), (30, "ml"), (2, "piece")]),
    ],
)
def test_display(segments: dict[UnitKind, float], expected: list[tuple[float, str]]) -> None:
    assert shown(segments) == expected


@pytest.mark.parametrize(
    ("ml", "tbsp"),
    [
        (15, 1),
        (5, 0.5),  # 1 tsp: at least half a tablespoon
        (10, 0.5),  # 2 tsp = 0.67 tbsp
        (11.25, 1),  # 0.75 tbsp rounds half up
        (22.5, 1.5),
        (30, 2),
        (37.5, 2.5),
        (0.1, 0.5),
        (0, 0),
        (1500, 100),
    ],
)
def test_spoons_only_lines_are_shown_in_tablespoons(ml: float, tbsp: float) -> None:
    assert shown(seg(volume=ml), spoons_only=True) == [(tbsp, "tbsp")]


# --- aggregate (AGG-02, AGG-05) ----------------------------------------------------------------


def test_aggregate_groups_sorts_and_keeps_sources() -> None:
    extra = SourceRef("extra", "x1")
    other_meal = SourceRef("meal", "m2")
    parts = [
        part(200, Unit.G, key="i:onion", source=MEAL),
        part(1, Unit.PIECE, ONION, key="i:onion", source=other_meal),
        part(1, Unit.TBSP, OIL, key="i:oil", source=MEAL),
        part(300, Unit.G, ONION, key="i:onion", source=MEAL),
        part(None, None, None, key="x:salt", source=extra),
        part(2, Unit.TBSP, OIL, key="i:oil", source=extra),
    ]
    order = {"i:oil": (9, "olivenoel"), "i:onion": (0, "zwiebeln"), "x:salt": (9, "a")}

    lines = aggregate(parts, lambda key: order[key])

    assert [line.line_key for line in lines] == ["i:onion", "x:salt", "i:oil"]
    onion, salt, oil = lines
    assert onion == Line(
        "i:onion",
        LineTotals(
            {MASS: 650},
            has_unspecified=False,
            spoons_only=False,
            base_total=650,
            base_unit=BaseUnit.G,
        ),
        [DisplayAmount(650, Unit.G)],
        [MEAL, other_meal],
    )
    assert salt.display == []
    assert salt.totals.has_unspecified
    assert salt.sources == [extra]
    assert oil.display == [DisplayAmount(3, Unit.TBSP)]
    assert oil.sources == [MEAL, extra]


def test_a_piece_ingredient_is_shown_in_whole_pieces_rounded_up() -> None:
    """AGG-04: 1.5 + 1 eggs are 3 Stk."""
    parts = [part(1.5, Unit.PIECE, EGGS, key="i:eggs"), part(1, Unit.PIECE, EGGS, key="i:eggs")]
    [eggs] = aggregate(parts, lambda _key: (0, "eier"))
    assert eggs.display == [DisplayAmount(3, Unit.PIECE)]
    assert (eggs.totals.base_total, eggs.totals.base_unit) == (2.5, BaseUnit.PIECE)


def test_equal_sort_keys_fall_back_to_the_line_key() -> None:
    parts = [part(1, Unit.G, key=key) for key in ("i:b", "i:c", "i:a")]
    lines = aggregate(parts, lambda _key: (0, "same"))
    assert [line.line_key for line in lines] == ["i:a", "i:b", "i:c"]


# --- needs more (LIST-12) ----------------------------------------------------------------------


def line(unspecified: bool = False, **segments: float) -> LineTotals:
    return LineTotals(seg(**segments), has_unspecified=unspecified, spoons_only=False)


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        (line(mass=500), line(mass=500), NeedsMore(needed=False)),
        (line(mass=500), line(mass=300), NeedsMore(needed=False)),
        (line(mass=500, count=2), line(mass=500), NeedsMore(needed=False)),
        (line(True, mass=500), line(mass=500), NeedsMore(needed=False)),
        (line(mass=500), line(mass=500 * (1 + 1e-12)), NeedsMore(needed=False)),
        (line(mass=500), line(mass=800), NeedsMore(needed=True, grown={MASS: 300})),
        (
            line(mass=500, count=2),
            line(mass=500, count=4),
            NeedsMore(needed=True, grown={COUNT: 2}),
        ),
        (line(mass=500), line(mass=500, count=2), NeedsMore(needed=True, new_segments=[COUNT])),
        (line(mass=0), line(mass=1e-300), NeedsMore(needed=True, grown={MASS: 1e-300})),
        (line(), line(True), NeedsMore(needed=True, new_unspecified=True)),
        (
            line(mass=500),
            line(True, mass=600, volume=30),
            NeedsMore(needed=True, grown={MASS: 100}, new_segments=[VOLUME], new_unspecified=True),
        ),
    ],
)
def test_needs_more(before: LineTotals, after: LineTotals, expected: NeedsMore) -> None:
    result = needs_more(CheckSnapshot.of(before), after)
    assert result.needed is expected.needed
    assert result.grown == pytest.approx(expected.grown)
    assert result.new_segments == expected.new_segments
    assert result.new_unspecified is expected.new_unspecified


def apples(
    *amounts: tuple[float | None, Unit | None], attrs: IngredientAttrs = APPLES
) -> LineTotals:
    return totals([part(amount, unit, attrs) for amount, unit in amounts])


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        # A checked line that needs less stays checked: 2 pieces + 100 g (mass 460) was
        # bought, 2 pieces (count 2, 360 g) are needed now.
        (
            apples((2, Unit.PIECE), (100, Unit.G)),
            apples((2, Unit.PIECE)),
            NeedsMore(needed=False),
        ),
        (
            apples((2, Unit.PIECE), (100, Unit.G)),
            apples((3, Unit.PIECE), (100, Unit.G)),
            NeedsMore(needed=True, grown={MASS: 180}),
        ),
        # In the base unit a new kind of amount is no new segment.
        (
            apples((2, Unit.PIECE)),
            apples((3, Unit.PIECE)),
            NeedsMore(needed=True, grown={MASS: 180}),
        ),
        (
            apples((2, Unit.PIECE), (100, Unit.G)),
            apples((3, Unit.PIECE)),
            NeedsMore(needed=True, grown={MASS: 80}),
        ),
        (apples((500, Unit.G)), apples((2, Unit.PIECE)), NeedsMore(needed=False)),
        (
            apples((2, Unit.PIECE), (100, Unit.G)),
            apples((2, Unit.PIECE), (None, None)),
            NeedsMore(needed=True, new_unspecified=True),
        ),
        (
            totals([part(1, Unit.TBSP, OIL), part(92, Unit.G, OIL)]),
            totals([part(0.2, Unit.L, OIL)]),
            NeedsMore(needed=True, grown={VOLUME: 85}),
        ),
        # Another base unit since: segment by segment.
        (
            apples((2, Unit.PIECE)),
            apples((2, Unit.PIECE), attrs=APPLES_ML),
            NeedsMore(needed=False),
        ),
        (
            apples((2, Unit.PIECE), (100, Unit.G)),
            apples((2, Unit.PIECE), (100, Unit.G), attrs=APPLES_ML),
            NeedsMore(needed=True, new_segments=[VOLUME]),
        ),
        # A part that does not convert (the piece weight is gone): segment by segment.
        (
            apples((2, Unit.PIECE), (100, Unit.G)),
            apples((2, Unit.PIECE), attrs=PLAIN),
            NeedsMore(needed=True, new_segments=[COUNT]),
        ),
        (
            apples((2, Unit.PIECE)),
            apples((2, Unit.PIECE), (1, Unit.TBSP)),
            NeedsMore(needed=True, new_segments=[MASS, VOLUME]),
        ),
        # A piece ingredient compares in pieces; another kind beside them, segment by segment.
        (
            totals([part(2, Unit.PIECE, EGGS)]),
            totals([part(3, Unit.PIECE, EGGS)]),
            NeedsMore(needed=True, grown={COUNT: 1}),
        ),
        (
            totals([part(2, Unit.PIECE, EGGS), part(120, Unit.G, EGGS)]),
            totals([part(2, Unit.PIECE, EGGS)]),
            NeedsMore(needed=False),
        ),
        # Free text has no base total.
        (
            totals([part(2, Unit.PIECE, None)]),
            totals([part(3, Unit.PIECE, None)]),
            NeedsMore(needed=True, grown={COUNT: 1}),
        ),
    ],
)
def test_needs_more_in_the_base_unit(
    before: LineTotals, after: LineTotals, expected: NeedsMore
) -> None:
    """LIST-12: compared in the ingredient's base unit whenever both totals convert."""
    result = needs_more(CheckSnapshot.of(before), after)
    assert result.needed is expected.needed
    assert result.grown == pytest.approx(expected.grown)
    assert result.new_segments == expected.new_segments
    assert result.new_unspecified is expected.new_unspecified


def test_a_snapshot_without_a_base_total_compares_segments() -> None:
    """Snapshots stored before base totals existed load without one."""
    old = CheckSnapshot.from_json({"mass_g": 460, "has_unspecified": False})
    assert (old.base_total, old.base_unit) == (None, None)
    assert needs_more(old, apples((2, Unit.PIECE))) == NeedsMore(needed=True, new_segments=[COUNT])


def test_snapshot_json() -> None:
    snapshot = CheckSnapshot.of(line(True, mass=500, count=2))
    data = snapshot.to_json()
    assert data == {"mass_g": 500, "count": 2, "has_unspecified": True}
    assert CheckSnapshot.from_json(data) == snapshot
    assert CheckSnapshot.from_json({"volume_ml": "15"}) == CheckSnapshot({VOLUME: 15}, False)

    with_base = CheckSnapshot.of(apples((2, Unit.PIECE), (100, Unit.G), (None, None)))
    data = with_base.to_json()
    assert data == {"mass_g": 460, "has_unspecified": True, "base_total": 460, "base_unit": "g"}
    assert CheckSnapshot.from_json(data) == with_base
    assert CheckSnapshot.from_json(data).base_unit is BaseUnit.G
    assert CheckSnapshot.from_json({"count": 2, "base_total": "360", "base_unit": "g"}) == (
        CheckSnapshot({COUNT: 2}, False, 360, BaseUnit.G)
    )
    assert CheckSnapshot.from_json({"count": 2, "base_total": None, "base_unit": "g"}) == (
        CheckSnapshot({COUNT: 2}, False)
    )

    in_pieces = CheckSnapshot.of(totals([part(2.5, Unit.PIECE, EGGS)]))
    data = in_pieces.to_json()
    assert data == {"count": 2.5, "has_unspecified": False, "base_total": 2.5, "base_unit": "piece"}
    assert CheckSnapshot.from_json(data).base_unit is BaseUnit.PIECE


@pytest.mark.parametrize(
    ("before", "after", "shown"),
    [
        # "+300 g", "+2 Stk.": the differences, rounded like any amount (AGG-04).
        (totals([part(300, Unit.G)]), totals([part(0.6, Unit.KG)]), [(300, Unit.G)]),
        (
            totals([part(1, Unit.PIECE)]),
            totals([part(2.2, Unit.PIECE)]),
            [(2, Unit.PIECE)],
        ),
        (
            totals([part(500, Unit.G), part(2, Unit.PIECE)]),
            totals([part(1.5, Unit.KG), part(3, Unit.PIECE)]),
            [(1, Unit.KG), (1, Unit.PIECE)],
        ),
        # Spoons stay spoons, pieces stay pieces, also when compared in the base unit.
        (totals([part(1, Unit.TBSP, OIL)]), totals([part(2, Unit.TBSP, OIL)]), [(1, Unit.TBSP)]),
        (apples((2, Unit.PIECE)), apples((3, Unit.PIECE)), [(1, Unit.PIECE)]),
        (
            totals([part(2, Unit.PIECE, ONION)]),
            totals([part(3, Unit.PIECE, ONION)]),
            [(1, Unit.PIECE)],
        ),
        (
            totals([part(2, Unit.TBSP, HONEY)]),
            totals([part(2, Unit.TBSP, HONEY), part(1, Unit.TSP, HONEY)]),
            [(0.5, Unit.TBSP)],
        ),
        (
            totals([part(1, Unit.TBSP, OIL), part(92, Unit.G, OIL)]),
            totals([part(0.2, Unit.L, OIL)]),
            [(85, Unit.ML)],
        ),
        (
            totals([part(2, Unit.PIECE, EGGS)]),
            totals([part(2.5, Unit.PIECE, EGGS)]),
            [(1, Unit.PIECE)],
        ),
        # Of different kinds, the difference is in the base unit.
        (apples((2, Unit.PIECE)), apples((2, Unit.PIECE), (100, Unit.G)), [(100, Unit.G)]),
        (
            apples((2, Unit.PIECE), (100, Unit.G)),
            apples((3, Unit.PIECE)),
            [(80, Unit.G)],
        ),
        # The same number of pieces, but heavier ones (frozen at another time): in grams.
        (
            apples((2, Unit.PIECE)),
            totals([part(1, Unit.PIECE, APPLES), part(1, Unit.PIECE, HEAVY_APPLES)]),
            [(20, Unit.G)],
        ),
        # Nothing grew.
        (totals([part(300, Unit.G)]), totals([part(300, Unit.G), part(None, None)]), []),
    ],
)
def test_grown_display(
    before: LineTotals, after: LineTotals, shown: list[tuple[float, Unit]]
) -> None:
    snapshot = CheckSnapshot.of(before)
    result = needs_more(snapshot, after)
    assert grown_display(result, snapshot, after) == [
        DisplayAmount(value, unit) for value, unit in shown
    ]


@pytest.mark.parametrize(
    ("old", "new", "changed"),
    [
        (("Klopapier", None), ("Klopapier", None), False),
        (("Klopapier", "2 Pakete"), ("Klopapier", "2 Pakete"), False),
        (("Klopapier", None), ("Klopapier", "2 Pakete"), True),
        (("Klopapier", "1"), ("Klopapier", None), True),
        (("Klopapier", None), ("Küchenrolle", None), True),
    ],
)
def test_text_changed(
    old: tuple[str, str | None], new: tuple[str, str | None], changed: bool
) -> None:
    assert text_changed(*old, *new) is changed


# --- properties (plan § 5.6) -------------------------------------------------------------------

attrs_strategy = st.none() | st.builds(
    IngredientAttrs,
    base_unit=st.sampled_from(BaseUnit),
    piece_weight_g=st.none() | st.floats(1, 1000),
    density_g_per_ml=st.none() | st.floats(0.1, 5),
)


@st.composite
def line_parts(draw: Any) -> list[Part]:
    """Parts of one line: one ingredient's attributes, amounts in any unit, some without."""
    attrs = draw(attrs_strategy)
    measured = st.tuples(st.floats(0.001, 10_000), st.sampled_from(Unit))
    amounts = draw(st.lists(st.none() | measured, min_size=1, max_size=8))
    return [
        part(None, None, attrs) if item is None else part(item[0], item[1], attrs)
        for item in amounts
    ]


@given(data=st.data(), parts=line_parts())
def test_merge_order_does_not_matter(data: st.DataObject, parts: list[Part]) -> None:
    shuffled = data.draw(st.permutations(parts))
    assert totals(shuffled) == totals(parts)


@given(parts=line_parts(), factor=st.floats(0.01, 100))
def test_scaling_amounts_scales_totals(parts: list[Part], factor: float) -> None:
    scaled = [part(None if p.amount is None else p.amount * factor, p.unit, p.attrs) for p in parts]
    before, after = totals(parts), totals(scaled)
    assert list(after.segments) == list(before.segments)
    for kind, value in before.segments.items():
        assert after.segments[kind] == pytest.approx(value * factor, rel=1e-9)
    assert (after.has_unspecified, after.spoons_only, after.base_unit) == (
        before.has_unspecified,
        before.spoons_only,
        before.base_unit,
    )
    if before.base_total is None:
        assert after.base_total is None
    else:
        assert after.base_total == pytest.approx(before.base_total * factor, rel=1e-9)


@given(parts=line_parts())
def test_positive_amounts_never_show_zero_and_pieces_never_round_down(parts: list[Part]) -> None:
    line_totals = totals(parts)
    amounts = display(line_totals)
    assert len(amounts) == len(line_totals.segments)
    assert all(amount.value > 0 for amount in amounts)
    if (count := line_totals.segments.get(COUNT)) is not None:
        pieces = amounts[-1]
        assert pieces.unit is Unit.PIECE
        assert pieces.value >= count - 1e-6
        assert pieces.value == int(pieces.value)


@given(value=st.floats(1e-9, 1e9), unit=st.sampled_from(UnitKind), spoons=st.booleans())
def test_display_of_a_single_segment(value: float, unit: UnitKind, spoons: bool) -> None:
    [amount] = display(LineTotals({unit: value}, has_unspecified=False, spoons_only=spoons))
    assert amount.value > 0
    if unit is MASS:
        assert amount.unit in {Unit.G, Unit.KG}
        grams = amount.value * (1000 if amount.unit is Unit.KG else 1)
        assert grams == pytest.approx(value, abs=max(5, value * 0.006))
    if unit is VOLUME and spoons:
        assert amount.unit is Unit.TBSP
        assert amount.value * 2 == int(amount.value * 2)


def scale(parts: list[Part], factor: float) -> list[Part]:
    return [part(None if p.amount is None else p.amount * factor, p.unit, p.attrs) for p in parts]


@given(parts=line_parts())
def test_identical_totals_need_nothing(parts: list[Part]) -> None:
    line_totals = totals(parts)
    assert not needs_more(CheckSnapshot.of(line_totals), line_totals).needed
    snapshot = CheckSnapshot.from_json(CheckSnapshot.of(line_totals).to_json())
    assert not needs_more(snapshot, line_totals).needed


@given(parts=line_parts(), factor=st.floats(1.01, 100))
def test_more_of_everything_needs_more(parts: list[Part], factor: float) -> None:
    before = totals(parts)
    result = needs_more(CheckSnapshot.of(before), totals(scale(parts, factor)))
    assert result.needed is bool(before.segments)
    assert not result.new_segments
    assert not result.new_unspecified


@given(parts=line_parts(), factor=st.floats(0.01, 0.99))
def test_less_of_everything_needs_nothing(parts: list[Part], factor: float) -> None:
    before = totals(parts)
    assert not needs_more(CheckSnapshot.of(before), totals(scale(parts, factor))).needed


@given(parts=line_parts(), extra=line_parts())
def test_needs_more_exactly_when_something_grows(parts: list[Part], extra: list[Part]) -> None:
    before = totals(parts)
    snapshot = CheckSnapshot.of(before)
    after = totals(parts + extra)
    result = needs_more(snapshot, after)
    new_unspecified = after.has_unspecified and not before.has_unspecified
    assert result.new_unspecified is new_unspecified
    if (
        before.base_total is not None
        and after.base_total is not None
        and before.base_unit is after.base_unit
    ):
        # Compared in the base unit (LIST-12).
        assert result.new_segments == []
        assert list(result.grown) in ([], [BASE_KIND[after.base_unit]])
        if after.base_total > before.base_total * (1 + 1e-6) or new_unspecified:
            assert result.needed
        if result.needed:
            assert after.base_total > before.base_total or new_unspecified
        return
    new_segments = [kind for kind in after.segments if kind not in before.segments]
    grew_clearly = any(
        after.segments[kind] > before.segments[kind] * (1 + 1e-6)
        for kind in after.segments
        if kind in before.segments
    )
    grew_at_all = any(
        after.segments[kind] > before.segments[kind]
        for kind in after.segments
        if kind in before.segments
    )
    assert result.new_segments == new_segments
    if grew_clearly or new_segments or new_unspecified:
        assert result.needed
    if result.needed:
        assert grew_at_all or new_segments or new_unspecified
