import { describe, expect, it } from 'vitest';
import { groupByWeek, mondayOf } from './history';

describe('mondayOf', () => {
  it('finds the Monday of the ISO week', () => {
    expect(mondayOf('2026-09-26T10:00:00Z', 'UTC')).toBe('2026-09-21'); // Saturday
    expect(mondayOf('2026-09-21T00:00:00Z', 'UTC')).toBe('2026-09-21'); // Monday
    expect(mondayOf('2026-09-27T23:59:00Z', 'UTC')).toBe('2026-09-21'); // Sunday
  });

  it('uses the calendar day in the viewer’s time zone', () => {
    // Sunday night in UTC is already Monday in Berlin, and still Sunday in New York.
    expect(mondayOf('2026-09-27T22:30:00Z', 'Europe/Berlin')).toBe('2026-09-28');
    expect(mondayOf('2026-09-27T22:30:00Z', 'UTC')).toBe('2026-09-21');
    // Monday early morning in UTC is still Sunday in New York.
    expect(mondayOf('2026-09-28T02:00:00Z', 'America/New_York')).toBe('2026-09-21');
  });

  it('crosses months and years', () => {
    expect(mondayOf('2026-10-02T12:00:00Z', 'UTC')).toBe('2026-09-28');
    expect(mondayOf('2027-01-01T12:00:00Z', 'UTC')).toBe('2026-12-28');
  });
});

describe('groupByWeek (SHOP-05)', () => {
  const list = (id: string, finished_at: string | null) => ({ id, finished_at });

  it('groups by the week of finishing, keeping the server’s order', () => {
    const lists = [
      list('a', '2026-09-26T18:00:00Z'),
      list('b', '2026-09-21T08:00:00Z'),
      list('c', '2026-09-19T12:00:00Z'),
      list('d', '2026-08-31T12:00:00Z'),
    ];

    expect(groupByWeek(lists, 'Europe/Berlin')).toEqual([
      { monday: '2026-09-21', lists: [lists[0], lists[1]] },
      { monday: '2026-09-14', lists: [lists[2]] },
      { monday: '2026-08-31', lists: [lists[3]] },
    ]);
  });

  it('puts a list finished late on Sunday (UTC) into the next week in Berlin', () => {
    const lists = [list('late', '2026-09-27T22:30:00Z'), list('early', '2026-09-27T10:00:00Z')];

    expect(groupByWeek(lists, 'Europe/Berlin').map((group) => group.monday)).toEqual([
      '2026-09-28',
      '2026-09-21',
    ]);
    expect(groupByWeek(lists, 'UTC').map((group) => group.monday)).toEqual(['2026-09-21']);
  });

  it('leaves out lists that are not finished', () => {
    expect(groupByWeek([list('x', null)], 'UTC')).toEqual([]);
  });
});
