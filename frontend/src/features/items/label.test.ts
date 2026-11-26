import { describe, expect, it } from 'vitest';
import { itemLabel } from './label';

describe('itemLabel', () => {
  it('is the name alone without a brand', () => {
    expect(itemLabel('Zwiebeln')).toBe('Zwiebeln');
    expect(itemLabel('Zwiebeln', null)).toBe('Zwiebeln');
    expect(itemLabel('Zwiebeln', '')).toBe('Zwiebeln');
    expect(itemLabel('Zwiebeln', '   ')).toBe('Zwiebeln');
  });

  it('adds the brand in brackets', () => {
    expect(itemLabel('Milch', 'Weidehof')).toBe('Milch (Weidehof)');
    expect(itemLabel('Ei', ' REWE ')).toBe('Ei (REWE)');
  });
});
