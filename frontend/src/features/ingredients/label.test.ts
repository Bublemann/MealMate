import { describe, expect, it } from 'vitest';
import { ingredientLabel } from './label';

describe('ingredientLabel', () => {
  it('is the name alone without a brand', () => {
    expect(ingredientLabel('Zwiebeln')).toBe('Zwiebeln');
    expect(ingredientLabel('Zwiebeln', null)).toBe('Zwiebeln');
    expect(ingredientLabel('Zwiebeln', '')).toBe('Zwiebeln');
    expect(ingredientLabel('Zwiebeln', '   ')).toBe('Zwiebeln');
  });

  it('adds the brand in brackets', () => {
    expect(ingredientLabel('Milch', 'Weidehof')).toBe('Milch (Weidehof)');
    expect(ingredientLabel('Ei', ' REWE ')).toBe('Ei (REWE)');
  });
});
