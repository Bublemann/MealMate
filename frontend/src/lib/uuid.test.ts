import { describe, expect, it } from 'vitest';
import { isUuid, uuidv7 } from './uuid';

const UUID_V7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe('uuidv7', () => {
  it('makes version 7 UUIDs that start with the time', () => {
    const id = uuidv7(Date.UTC(2026, 8, 26, 12, 0, 0));

    expect(id).toMatch(UUID_V7);
    expect(Number.parseInt(id.slice(0, 8) + id.slice(9, 13), 16)).toBe(
      Date.UTC(2026, 8, 26, 12, 0, 0),
    );
  });

  it('makes a different id each time', () => {
    const ids = new Set(Array.from({ length: 100 }, () => uuidv7()));
    expect(ids.size).toBe(100);
  });
});

describe('isUuid', () => {
  it('takes UUIDs in either case and nothing else', () => {
    expect(isUuid(uuidv7())).toBe(true);
    expect(isUuid('0190C0DE-0000-7000-8000-0000000000B1')).toBe(true);
    expect(isUuid('../me/admin')).toBe(false);
    expect(isUuid(`${uuidv7()}/../me`)).toBe(false);
    expect(isUuid('')).toBe(false);
  });
});
