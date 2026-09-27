import { describe, expect, it } from 'vitest';
import { meal, MILK, SALT } from '@/test/meals';
import { newRow, rowsOf, withAmountText, withoutRowProblems } from './form';

describe('withAmountText', () => {
  it('picks the base unit for a typed amount and takes it back when the amount is cleared', () => {
    const typed = withAmountText(newRow(MILK), '300');
    expect(typed).toMatchObject({ amountText: '300', unit: 'ml', unitChosen: false });

    const changed = withAmountText(typed, '250');
    expect(changed.unit).toBe('ml');

    const cleared = withAmountText(changed, ' ');
    expect(cleared).toMatchObject({ amountText: ' ', unit: '', unitChosen: false });
  });

  it('keeps a unit the user chose, also "no unit"', () => {
    const chosen = { ...newRow(MILK), unit: 'l' as const, unitChosen: true };
    expect(withAmountText(chosen, '0,5').unit).toBe('l');
    expect(withAmountText(withAmountText(chosen, '0,5'), '').unit).toBe('l');

    const none = { ...newRow(MILK), unit: '' as const, unitChosen: true };
    expect(withAmountText(none, '2').unit).toBe('');
  });
});

describe('rowsOf', () => {
  it('treats a loaded "to taste" row like a new one, and a loaded unit as chosen', () => {
    const rows = rowsOf(meal(), 'en');

    expect(rows.map((row) => [row.ingredient.name, row.unit, row.unitChosen])).toEqual([
      ['Mehl', 'g', true],
      ['Milch', 'ml', true],
      ['Eier', 'piece', true],
      ['Salz', '', false],
    ]);
    const salt = rows[3];
    if (!salt) throw new Error('no salt row');
    expect(salt.ingredient).toEqual(SALT);
    expect(withAmountText(salt, '5').unit).toBe('g');
    expect(withAmountText(rows[2] ?? salt, '').unit).toBe('piece');
  });
});

describe('withoutRowProblems', () => {
  it('drops the problems of ingredient rows only', () => {
    const problems = new Set(['servings', 'ingredients.0.amount', 'ingredients.3.amount']);
    expect(withoutRowProblems(problems)).toEqual(new Set(['servings']));
  });
});
