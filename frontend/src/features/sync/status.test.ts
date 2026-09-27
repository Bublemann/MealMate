import { describe, expect, it } from 'vitest';
import {
  indicatorFor,
  INITIAL_STATUS,
  isConnected,
  Store,
  untilWaitingTooLong,
  WAITING_TOO_LONG_MS,
  type SyncStatus,
} from './status';

function status(change: Partial<SyncStatus>): SyncStatus {
  return { ...INITIAL_STATUS, ...change };
}

describe('indicatorFor (SYNC-07)', () => {
  it.each([
    { name: 'saved', given: {}, expected: { kind: 'saved' } },
    { name: 'saving', given: { pending: 2 }, expected: { kind: 'saving', waiting: 2 } },
    {
      name: 'offline with changes waiting',
      given: { online: false, pending: 3 },
      expected: { kind: 'offline', waiting: 3 },
    },
    { name: 'offline', given: { online: false }, expected: { kind: 'offline', waiting: 0 } },
    {
      name: 'offline wins over unreachable',
      given: { online: false, reachable: false },
      expected: { kind: 'offline', waiting: 0 },
    },
    {
      name: 'unreachable',
      given: { reachable: false, pending: 1 },
      expected: { kind: 'unreachable', waiting: 1 },
    },
  ])('$name', ({ given, expected }) => {
    expect(indicatorFor(status(given))).toEqual(expected);
  });

  it('counts as connected only when online and reachable', () => {
    expect(isConnected(status({}))).toBe(true);
    expect(isConnected(status({ online: false }))).toBe(false);
    expect(isConnected(status({ reachable: false }))).toBe(false);
  });
});

describe('untilWaitingTooLong', () => {
  it('is null when nothing waits', () => {
    expect(untilWaitingTooLong(status({ oldestQueuedAt: 1 }), 5)).toBeNull();
  });

  it('counts down to an hour after the oldest change', () => {
    const waiting = status({ pending: 1, oldestQueuedAt: 1_000 });
    expect(untilWaitingTooLong(waiting, 1_000)).toBe(WAITING_TOO_LONG_MS);
    expect(untilWaitingTooLong(waiting, 1_000 + WAITING_TOO_LONG_MS)).toBe(0);
  });
});

describe('Store', () => {
  it('notifies only on changes', () => {
    const store = new Store({ a: 1, b: 2 });
    let calls = 0;
    const stop = store.subscribe(() => (calls += 1));
    store.update({ a: 1 });
    expect(calls).toBe(0);
    store.update({ a: 3 });
    expect(store.get()).toEqual({ a: 3, b: 2 });
    expect(calls).toBe(1);
    stop();
    store.update({ b: 5 });
    expect(calls).toBe(1);
  });
});
