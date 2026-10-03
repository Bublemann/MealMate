import type { BaseUnit } from '@/features/ingredients/api';
import { useUnits, type Unit, type UnitInfo } from './api';

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

export interface UnitOption {
  unit: Unit;
  /** An older unit that doesn't fit: shown while it is chosen, but it can't be chosen again. */
  disabled: boolean;
}

/**
 * The unit choices of an amount of an ingredient counted in `baseUnit` (REF-02): the units that
 * fit, then an older unit that doesn't (D-33), disabled, so it stays shown until the user picks one
 * that fits. `fits` follows the amount and unit as entered, so the mark of a unit that doesn't fit
 * comes and goes with the user's edits; the server judges what is stored the same way (`unit_fits`)
 * and refuses a new amount that doesn't fit. `noUnitFits` tells whether "no unit" would fit: an
 * amount without a unit counts as pieces, a row without an amount fits anything. Until the units
 * have loaded, the chosen unit is the only choice and counts as fitting; without a known base
 * unit, every unit is offered.
 */
export function useUnitChoice(
  baseUnit: BaseUnit | null,
  unit: Unit | '',
  hasAmount: boolean,
): { options: UnitOption[]; fits: boolean; noUnitFits: boolean } {
  const units = useUnits();
  if (!units.data) {
    return { options: unit ? [{ unit, disabled: false }] : [], fits: true, noUnitFits: true };
  }
  const fitting = baseUnit
    ? fittingUnits(units.data, baseUnit)
    : units.data.map((info) => info.unit);
  const options = fitting.map((option) => ({ unit: option, disabled: false }));
  if (unit && !fitting.includes(unit)) options.push({ unit, disabled: true });
  return {
    options,
    fits: !baseUnit || unitFits(units.data, baseUnit, unit, hasAmount),
    noUnitFits: !baseUnit || unitFits(units.data, baseUnit, '', hasAmount),
  };
}
