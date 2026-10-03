import type { Unit, UnitInfo } from './api';

/** What an ingredient is counted in (ING-02): `g`, `ml` or `piece`. */
type BaseUnit = UnitInfo['base_units'][number];

/**
 * The units an ingredient counted in `baseUnit` takes (REF-02), in display order. Which units fit
 * which base unit comes from the server (`/api/units`), which also refuses the others.
 */
export function fittingUnits(units: readonly UnitInfo[], baseUnit: BaseUnit): Unit[] {
  return units.filter((info) => info.base_units.includes(baseUnit)).map((info) => info.unit);
}

/**
 * Whether an amount fits its ingredient (REF-02): an amount without a unit counts as pieces, and
 * a row without an amount fits every base unit.
 */
export function unitFits(
  units: readonly UnitInfo[],
  baseUnit: BaseUnit,
  unit: Unit | '' | null,
  hasAmount: boolean,
): boolean {
  return !hasAmount || fittingUnits(units, baseUnit).includes(unit || 'piece');
}

/**
 * The unit an amount keeps when another ingredient is chosen for it: the same one while it fits
 * the new ingredient, none once it no longer does (MEAL-02).
 */
export function keptUnit(
  units: readonly UnitInfo[],
  baseUnit: BaseUnit,
  unit: Unit | '',
): Unit | '' {
  return unit !== '' && fittingUnits(units, baseUnit).includes(unit) ? unit : '';
}
