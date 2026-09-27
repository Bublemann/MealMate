import { describe, expect, it } from 'vitest';
import { formatDate, formatNumber, parseAmount } from './format';

describe('formatNumber', () => {
  it('uses the decimal separator of the UI language', () => {
    expect(formatNumber(1.5, 'de')).toBe('1,5');
    expect(formatNumber(1.5, 'en')).toBe('1.5');
  });

  it('groups thousands and passes options through', () => {
    expect(formatNumber(1234.5, 'de')).toBe('1.234,5');
    expect(formatNumber(1234.5, 'en')).toBe('1,234.5');
    expect(formatNumber(0.333, 'de', { maximumFractionDigits: 1 })).toBe('0,3');
  });
});

describe('formatDate', () => {
  // Built from local components, so the result does not depend on the machine's time zone.
  const date = new Date(2026, 8, 26, 12, 0);

  it('formats day first in both languages', () => {
    expect(formatDate(date, 'de')).toBe('26.09.2026');
    expect(formatDate(date, 'en')).toBe('26/09/2026');
  });

  it('accepts timestamps and ISO strings', () => {
    expect(formatDate(date.getTime(), 'de')).toBe('26.09.2026');
    expect(formatDate(date.toISOString(), 'en')).toBe('26/09/2026');
  });
});

describe('parseAmount', () => {
  it.each([
    ['1,5', 1.5],
    ['1.5', 1.5],
    [' 2 ', 2],
    ['0', 0],
    ['250', 250],
    ['0,25', 0.25],
    [',5', 0.5],
    ['3.', 3],
  ])('parses %j as %d', (input, expected) => {
    expect(parseAmount(input)).toBe(expected);
  });

  it.each([
    '',
    '   ',
    'abc',
    '1,5 kg',
    '-1',
    '-0,5',
    '+2',
    '1,5,0',
    '1.000,5',
    '1.2.3',
    '1 000',
    '1e3',
    '.',
    ',',
  ])('rejects %j', (input) => {
    expect(parseAmount(input)).toBeNull();
  });
});
