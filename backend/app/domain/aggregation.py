"""Aggregating shopping-list parts into lines, display rounding and "needs more" (AGG-02..05,
LIST-12, plan §§ 5.6 and 5.7).

The list service (M5a) turns meals and extra items into `Part`s and lets `aggregate()` group,
total, round and sort them. Calculations keep full precision; only `display()` rounds.

Merging rules (AGG-03), deliberately simple:
1. parts without an amount only set `has_unspecified` ("+ some");
2. if all parts with an amount are of one kind, they add up in that kind's segment: pieces stay
   pieces and spoons stay a volume, nothing is converted;
3. otherwise every part is converted strictly (no 1 g/ml estimate) to the ingredient's base
   unit where its attributes allow it; the others stay in their own kind's segment. Only parts
   frozen before D-32 cross kinds (a piece weight or density with g or ml); live ingredients
   have neither (`IngredientAttrs.live`), so their spoons of a g ingredient and amounts that
   don't fit sit beside the rest: "500 g + 2 Stk." (`units.convert`).

Sums use `math.fsum`, so they do not depend on the order of the parts (AGG-05).

"Needs more" (LIST-12) compares in the ingredient's base unit whenever every part with an
amount converts to it strictly, so rule 2 cannot make a line look different in kind: a checked
"2 Stk. + 100 g" (460 g of apples frozen before D-32) stays checked when only "2 Stk." (360 g)
remain. Otherwise it compares segment by segment.
"""

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal

from app.domain.units import (
    BASE_KIND,
    SPOONS,
    UNIT_KIND,
    BaseUnit,
    IngredientAttrs,
    Unit,
    UnitKind,
    convert,
    in_kind_base,
)

SourceKind = Literal["meal", "extra"]

# How segments are named in stored check snapshots (plan § 5.7).
SEGMENT_NAMES: Mapping[UnitKind, str] = {
    UnitKind.MASS: "mass_g",
    UnitKind.VOLUME: "volume_ml",
    UnitKind.COUNT: "count",
}
_KIND_ORDER = (UnitKind.MASS, UnitKind.VOLUME, UnitKind.COUNT)
# Growth smaller than this, relative to the larger total, is float noise, not "needs more".
GROWTH_REL_TOL = 1e-9
# Piece totals are rounded to this many decimals before rounding up, so 2.0000000001 → 2.
COUNT_DECIMALS = 6
KILO = Decimal(1000)
SPOON_ML = Decimal(15)


@dataclass(frozen=True)
class SourceRef:
    """Where a part comes from: a meal on the list or an extra item (LIST-08)."""

    kind: SourceKind
    id: str


@dataclass(frozen=True)
class Part:
    """One contribution to a line: `amount` is already scaled by the servings factor. `attrs`
    is None for free-text items, which have nothing to convert."""

    line_key: str
    amount: float | None
    unit: Unit | None
    attrs: IngredientAttrs | None
    source: SourceRef


@dataclass(frozen=True)
class LineTotals:
    """Exact totals per unit kind (g, ml, pieces). `spoons_only`: the volume segment is made
    of tablespoons and teaspoons only, so it is shown in tbsp (AGG-04).

    `base_total` is the sum of all parts with an amount, each converted strictly into the
    ingredient's `base_unit`; both are None unless there is such a part and every one converts
    (not for free text, missing piece weights or densities, or differing base units). Only
    `needs_more` uses it.
    """

    segments: dict[UnitKind, float]
    has_unspecified: bool
    spoons_only: bool
    base_total: float | None = None
    base_unit: BaseUnit | None = None


@dataclass(frozen=True)
class DisplayAmount:
    value: float
    unit: Unit


@dataclass(frozen=True)
class Line:
    line_key: str
    totals: LineTotals
    display: list[DisplayAmount]
    sources: list[SourceRef]


@dataclass(frozen=True)
class CheckSnapshot:
    """What a line looked like when it was checked off (`list_line_states.checked_snapshot`)."""

    segments: dict[UnitKind, float]
    has_unspecified: bool
    base_total: float | None = None
    base_unit: BaseUnit | None = None

    @classmethod
    def of(cls, totals: LineTotals) -> CheckSnapshot:
        return cls(
            dict(totals.segments), totals.has_unspecified, totals.base_total, totals.base_unit
        )

    def to_json(self) -> dict[str, Any]:
        """`{"mass_g": …, "volume_ml": …, "count": …, "has_unspecified": …, "base_total": …,
        "base_unit": "g"|"ml"|"piece"}`; absent segments and a missing base total are left
        out."""
        data: dict[str, Any] = {SEGMENT_NAMES[kind]: value for kind, value in self.segments.items()}
        data["has_unspecified"] = self.has_unspecified
        if self.base_total is not None and self.base_unit is not None:
            data["base_total"] = self.base_total
            data["base_unit"] = self.base_unit.value
        return data

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> CheckSnapshot:
        """Reads `to_json()`; snapshots stored before base totals existed have none."""
        segments = {kind: float(data[name]) for kind, name in SEGMENT_NAMES.items() if name in data}
        has_unspecified = bool(data.get("has_unspecified", False))
        if data.get("base_total") is None or data.get("base_unit") is None:
            return cls(segments, has_unspecified)
        return cls(
            segments, has_unspecified, float(data["base_total"]), BaseUnit(data["base_unit"])
        )


@dataclass(frozen=True)
class NeedsMore:
    """Whether a checked line must be unchecked again (LIST-12): per grown segment the
    difference ("+300 g"), segments that are new, and a new part without an amount. Compared
    in the base unit, `grown` holds the difference under the base unit's kind and there are no
    new segments."""

    needed: bool
    grown: dict[UnitKind, float] = field(default_factory=dict)
    new_segments: list[UnitKind] = field(default_factory=list)
    new_unspecified: bool = False


@dataclass
class _Segment:
    values: list[float] = field(default_factory=list)
    spoons_only: bool = True

    def add(self, value: float, *, spoon: bool) -> None:
        self.values.append(value)
        self.spoons_only = self.spoons_only and spoon


def _base_total(
    measured: Sequence[tuple[Part, float, Unit]],
) -> tuple[float, BaseUnit] | tuple[None, None]:
    """All measured parts converted strictly into their common base unit, if every one
    converts."""
    values: list[float] = []
    base_units: set[BaseUnit] = set()
    for part, amount, unit in measured:
        if part.attrs is None:
            return None, None
        converted = convert(amount, unit, part.attrs, allow_estimate=False)
        if converted is None:
            return None, None
        values.append(converted.value)
        base_units.add(part.attrs.base_unit)
    if len(base_units) != 1:
        return None, None
    return math.fsum(values), base_units.pop()


def totals(parts: Iterable[Part]) -> LineTotals:
    """The exact totals of one line's parts (AGG-03, see the module docstring)."""
    parts = list(parts)
    measured: list[tuple[Part, float, Unit]] = []
    for part in parts:
        if part.amount is not None and part.unit is not None:
            measured.append((part, part.amount, part.unit))
    has_unspecified = len(measured) < len(parts)
    single_kind = len({UNIT_KIND[unit] for _part, _amount, unit in measured}) <= 1
    segments: dict[UnitKind, _Segment] = {}
    for part, amount, unit in measured:
        kind, value = UNIT_KIND[unit], in_kind_base(amount, unit)
        if not single_kind and part.attrs is not None:
            converted = convert(amount, unit, part.attrs, allow_estimate=False)
            if converted is not None:
                kind, value = BASE_KIND[part.attrs.base_unit], converted.value
        segments.setdefault(kind, _Segment()).add(value, spoon=unit in SPOONS)
    volume = segments.get(UnitKind.VOLUME)
    base_total, base_unit = _base_total(measured)
    return LineTotals(
        segments={
            kind: math.fsum(segments[kind].values) for kind in _KIND_ORDER if kind in segments
        },
        has_unspecified=has_unspecified,
        spoons_only=volume is not None and volume.spoons_only,
        base_total=base_total,
        base_unit=base_unit,
    )


def _round_half_up(value: Decimal, step: Decimal = Decimal(1)) -> Decimal:
    return (value / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step


def _metric(value: float, small: Unit, large: Unit) -> DisplayAmount:
    """Whole g (ml), at least 1 for a positive amount; from 1000 (after rounding to whole g)
    in kg (l) with up to two decimals, rounded once from the exact amount: 1254.6 g is
    1.25 kg, not 1255 g → 1.26 kg."""
    exact = Decimal(repr(value))
    rounded = _round_half_up(exact)
    if value > 0 and rounded < 1:
        rounded = Decimal(1)
    if rounded >= KILO:
        return DisplayAmount(float(_round_half_up(exact / KILO, Decimal("0.01"))), large)
    return DisplayAmount(float(rounded), small)


def _spoons(value_ml: float) -> DisplayAmount:
    """Tablespoons, to the nearest half, at least half a tablespoon for a positive amount."""
    tbsp = _round_half_up(Decimal(repr(value_ml)) / SPOON_ML, Decimal("0.5"))
    if value_ml > 0 and tbsp < Decimal("0.5"):
        tbsp = Decimal("0.5")
    return DisplayAmount(float(tbsp), Unit.TBSP)


def _pieces(count: float) -> DisplayAmount:
    """Whole pieces, rounded up (after dropping float noise), at least 1 for a positive
    amount."""
    pieces = math.ceil(round(count, COUNT_DECIMALS))
    if count > 0:
        pieces = max(pieces, 1)
    return DisplayAmount(float(pieces), Unit.PIECE)


def display(line_totals: LineTotals) -> list[DisplayAmount]:
    """The rounded amounts to show (AGG-04), in the order mass, volume, pieces."""
    shown: list[DisplayAmount] = []
    segments = line_totals.segments
    if (mass := segments.get(UnitKind.MASS)) is not None:
        shown.append(_metric(mass, Unit.G, Unit.KG))
    if (volume := segments.get(UnitKind.VOLUME)) is not None:
        shown.append(
            _spoons(volume) if line_totals.spoons_only else _metric(volume, Unit.ML, Unit.L)
        )
    if (count := segments.get(UnitKind.COUNT)) is not None:
        shown.append(_pieces(count))
    return shown


def aggregate(parts: Sequence[Part], order: Callable[[str], tuple[Any, ...]]) -> list[Line]:
    """Group parts by line key into lines with totals, display amounts and their sources
    (deduplicated, in input order), sorted by `order(line_key)` and then the key itself, so
    the result is deterministic (AGG-05). The caller's order is typically (category
    sort_order, normalised name)."""
    groups: dict[str, list[Part]] = {}
    for part in parts:
        groups.setdefault(part.line_key, []).append(part)
    lines = []
    for line_key, group in groups.items():
        line_totals = totals(group)
        lines.append(
            Line(
                line_key=line_key,
                totals=line_totals,
                display=display(line_totals),
                sources=list(dict.fromkeys(part.source for part in group)),
            )
        )
    return sorted(lines, key=lambda line: (order(line.line_key), line.line_key))


def _grew(before: float, after: float) -> bool:
    return after > before and not math.isclose(after, before, rel_tol=GROWTH_REL_TOL)


def needs_more(snapshot: CheckSnapshot, current: LineTotals) -> NeedsMore:
    """Compare a checked line with its snapshot (LIST-12, plan § 5.7): it needs more if a
    part without an amount was added, or if more is needed: when both have a base total in
    the same base unit, the base total grew (beyond float noise); otherwise a segment grew or
    a new segment appeared. Needing less keeps it checked."""
    new_unspecified = current.has_unspecified and not snapshot.has_unspecified
    if (
        snapshot.base_total is not None
        and current.base_total is not None
        and snapshot.base_unit is not None
        and snapshot.base_unit == current.base_unit
    ):
        grown_base: dict[UnitKind, float] = {}
        if _grew(snapshot.base_total, current.base_total):
            grown_base[BASE_KIND[snapshot.base_unit]] = current.base_total - snapshot.base_total
        return NeedsMore(
            needed=bool(grown_base or new_unspecified),
            grown=grown_base,
            new_unspecified=new_unspecified,
        )
    grown: dict[UnitKind, float] = {}
    new_segments: list[UnitKind] = []
    for kind in _KIND_ORDER:
        if kind not in current.segments:
            continue
        after = current.segments[kind]
        if kind not in snapshot.segments:
            new_segments.append(kind)
        elif _grew(before := snapshot.segments[kind], after):
            grown[kind] = after - before
    return NeedsMore(
        needed=bool(grown or new_segments or new_unspecified),
        grown=grown,
        new_segments=new_segments,
        new_unspecified=new_unspecified,
    )


def grown_display(
    result: NeedsMore, snapshot: CheckSnapshot, current: LineTotals
) -> list[DisplayAmount]:
    """The differences of a line that needs more, rounded like any amount (AGG-04): "+300 g",
    "+2 Stk.". Compared in the base unit, the difference is shown in the line's own unit when
    the snapshot and the line have amounts of one and the same kind only ("3 Stk." checked at
    "2 Stk." is "+1 Stk." even with a piece weight); otherwise in the base unit. A grown volume
    of a line made of spoons only is shown in tbsp."""
    grown = result.grown
    if (
        grown
        and len(snapshot.segments) == 1
        and snapshot.segments.keys() == current.segments.keys()
    ):
        [(kind, before)] = snapshot.segments.items()
        if _grew(before, after := current.segments[kind]):
            grown = {kind: after - before}
    return display(
        LineTotals(
            segments={kind: grown[kind] for kind in _KIND_ORDER if kind in grown},
            has_unspecified=False,
            spoons_only=current.spoons_only,
        )
    )


def text_changed(
    old_text: str, old_amount_text: str | None, new_text: str, new_amount_text: str | None
) -> bool:
    """Whether a checked free-text item was edited since (shown as "changed", LIST-12)."""
    return old_text != new_text or old_amount_text != new_amount_text
