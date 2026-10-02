"""Units and conversion into an ingredient's base unit (REF-02, NUT-05, plan § 5.6).

Every unit has a kind (mass, volume, count) and a factor to the base unit of its kind (g, ml,
piece). An ingredient counted in pieces (base unit `piece`, D-32) takes only pieces: grams or
millilitres don't say how many pieces they are. For a g or ml ingredient, crossing kinds needs
its attributes: piece weight for pieces, density for g↔ml. Spoons of a g-based ingredient
without a density may be counted as 1 g/ml, flagged as an estimate; nutrition allows that
(NUT-05), aggregation does not (AGG-03).

Adding a unit: add it to `Unit` (the order is the display order), `UNIT_KIND` and `UNIT_FACTOR`,
add its translation `unit.<unit>`, and extend the tests (MNT-06).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class Unit(StrEnum):
    """The fixed units; the order is the display order."""

    G = "g"
    KG = "kg"
    ML = "ml"
    L = "l"
    PIECE = "piece"
    TBSP = "tbsp"
    TSP = "tsp"


class UnitKind(StrEnum):
    MASS = "mass"
    VOLUME = "volume"
    COUNT = "count"


class BaseUnit(StrEnum):
    """What an ingredient is counted in (ING-02). Its nutrition values are per 100 g, or per
    100 ml for `ml`; a `piece` ingredient's pieces count through its piece weight (NUT-05)."""

    G = "g"
    ML = "ml"
    PIECE = "piece"


UNIT_KIND: Mapping[Unit, UnitKind] = MappingProxyType(
    {
        Unit.G: UnitKind.MASS,
        Unit.KG: UnitKind.MASS,
        Unit.ML: UnitKind.VOLUME,
        Unit.L: UnitKind.VOLUME,
        Unit.PIECE: UnitKind.COUNT,
        Unit.TBSP: UnitKind.VOLUME,
        Unit.TSP: UnitKind.VOLUME,
    }
)
# Factor to the base unit of the unit's kind: g, ml or piece.
UNIT_FACTOR: Mapping[Unit, float] = MappingProxyType(
    {
        Unit.G: 1.0,
        Unit.KG: 1000.0,
        Unit.ML: 1.0,
        Unit.L: 1000.0,
        Unit.PIECE: 1.0,
        Unit.TBSP: 15.0,
        Unit.TSP: 5.0,
    }
)
SPOONS = frozenset({Unit.TBSP, Unit.TSP})
# The kind an ingredient's base unit belongs to.
BASE_KIND: Mapping[BaseUnit, UnitKind] = MappingProxyType(
    {BaseUnit.G: UnitKind.MASS, BaseUnit.ML: UnitKind.VOLUME, BaseUnit.PIECE: UnitKind.COUNT}
)
# What an ingredient's nutrition values are per 100 of: g, or ml for an ml ingredient (ING-02).
NUTRITION_BASIS: Mapping[BaseUnit, BaseUnit] = MappingProxyType(
    {BaseUnit.G: BaseUnit.G, BaseUnit.ML: BaseUnit.ML, BaseUnit.PIECE: BaseUnit.G}
)


@dataclass(frozen=True)
class IngredientAttrs:
    """What conversions need to know about an ingredient, live or from a frozen snapshot.

    `base_unit` may be given as a plain string ("g", "ml", "piece"), as rows and JSON snapshots
    store it;
    it is turned into a `BaseUnit` (anything else raises ValueError).
    """

    base_unit: BaseUnit
    piece_weight_g: float | None
    density_g_per_ml: float | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "base_unit", BaseUnit(self.base_unit))


@dataclass(frozen=True)
class Converted:
    """An amount in the ingredient's base unit; `estimate` if 1 g/ml was assumed (NUT-05)."""

    value: float
    estimate: bool


def in_kind_base(amount: float, unit: Unit) -> float:
    """The amount in the base unit of its own kind (g, ml or pieces)."""
    return amount * UNIT_FACTOR[unit]


def _grams_to_base(grams: float, attrs: IngredientAttrs) -> Converted | None:
    if attrs.base_unit == BaseUnit.G:
        return Converted(grams, estimate=False)
    if attrs.density_g_per_ml:
        return Converted(grams / attrs.density_g_per_ml, estimate=False)
    return None


def convert(
    amount: float, unit: Unit, attrs: IngredientAttrs, *, allow_estimate: bool
) -> Converted | None:
    """`amount` `unit` of the ingredient in its base unit, or None if it can't be converted.

    A `piece` ingredient takes pieces only. For a g or ml ingredient:

    - mass: to g by factor; to ml by dividing by the density;
    - volume: to ml by factor; to g by multiplying with the density. Without one, spoons count
      as 1 g/ml if `allow_estimate` (the result is flagged), ml and l stay unconvertible;
    - pieces: need the piece weight (to g), and for an ml ingredient also the density.
    """
    value = in_kind_base(amount, unit)
    if attrs.base_unit == BaseUnit.PIECE:
        return Converted(value, estimate=False) if UNIT_KIND[unit] == UnitKind.COUNT else None
    match UNIT_KIND[unit]:
        case UnitKind.MASS:
            return _grams_to_base(value, attrs)
        case UnitKind.VOLUME:
            if attrs.base_unit == BaseUnit.ML:
                return Converted(value, estimate=False)
            if attrs.density_g_per_ml:
                return Converted(value * attrs.density_g_per_ml, estimate=False)
            if allow_estimate and unit in SPOONS:
                return Converted(value, estimate=True)
            return None
        case UnitKind.COUNT:
            if not attrs.piece_weight_g:
                return None
            return _grams_to_base(value * attrs.piece_weight_g, attrs)
