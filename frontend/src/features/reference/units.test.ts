import { describe, expect, it } from 'vitest';
import { UNITS } from '@/test/ingredients';
import { fittingUnits, keptUnit, unitFits } from './units';

describe('fittingUnits', () => {
  it.each([
    ['g', ['g', 'kg', 'tbsp', 'tsp']],
    ['ml', ['ml', 'l', 'tbsp', 'tsp']],
    ['piece', ['piece']],
  ] as const)('offers what fits %s, in display order (REF-02)', (baseUnit, expected) => {
    expect(fittingUnits(UNITS, baseUnit)).toEqual(expected);
  });
});

describe('unitFits', () => {
  it.each([
    ['g', 'kg', true],
    ['g', 'tsp', true],
    ['g', 'ml', false],
    ['g', 'piece', false],
    ['ml', 'l', true],
    ['ml', 'g', false],
    ['piece', 'piece', true],
    ['piece', 'g', false],
    ['piece', 'tbsp', false],
  ] as const)('%s takes %s: %s', (baseUnit, unit, expected) => {
    expect(unitFits(UNITS, baseUnit, unit, true)).toBe(expected);
  });

  it('counts an amount without a unit as pieces', () => {
    expect(unitFits(UNITS, 'piece', '', true)).toBe(true);
    expect(unitFits(UNITS, 'g', '', true)).toBe(false);
  });

  it('lets a row without an amount fit every base unit', () => {
    expect(unitFits(UNITS, 'piece', 'g', false)).toBe(true);
    expect(unitFits(UNITS, 'g', '', false)).toBe(true);
  });
});

describe('keptUnit', () => {
  it('keeps a unit that fits the newly chosen ingredient and clears one that no longer does', () => {
    expect(keptUnit(UNITS, 'ml', 'tbsp')).toBe('tbsp');
    expect(keptUnit(UNITS, 'piece', 'tbsp')).toBe('');
    expect(keptUnit(UNITS, 'g', 'l')).toBe('');
    expect(keptUnit(UNITS, 'g', '')).toBe('');
  });
});
