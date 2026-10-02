import { describe, expect, it } from 'vitest';
import { initialOf } from './initial';

describe('initialOf (SHOP-01, UI-02)', () => {
  it('is the first letter, upper case', () => {
    expect(initialOf('ben')).toBe('B');
    expect(initialOf(' Anna ')).toBe('A');
    expect(initialOf('Özlem')).toBe('Ö');
    expect(initialOf('')).toBe('?');
  });
});
