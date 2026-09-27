/** What the sync status indicator (SYNC-07, SHOP-03) and the offline banners are made of. */
export interface SyncStatus {
  /** Ops of the signed-in user waiting to be sent. */
  pending: number;
  /** When the oldest of them was queued (ms since the epoch), or null. */
  oldestQueuedAt: number | null;
  /** Whether the last request reached the server (not a timeout, network failure or 5xx). */
  reachable: boolean;
  /** `navigator.onLine`: false means the phone knows it has no connection. */
  online: boolean;
  /** Ops are being sent right now. */
  sending: boolean;
  /** False when IndexedDB can't be used: changes then last for this visit only. */
  persistent: boolean;
}

export const INITIAL_STATUS: SyncStatus = {
  pending: 0,
  oldestQueuedAt: null,
  reachable: true,
  online: true,
  sending: false,
  persistent: true,
};

/** SYNC-07: changes waiting longer than this get a banner. */
export const WAITING_TOO_LONG_MS = 60 * 60 * 1000;

export type Indicator =
  | { kind: 'offline'; waiting: number }
  | { kind: 'unreachable'; waiting: number }
  | { kind: 'saving'; waiting: number }
  | { kind: 'saved' };

/**
 * The indicator's state (SYNC-07): offline as the phone says, then "can't reach" after a failed
 * request, then "saving" while changes wait, otherwise "saved".
 */
export function indicatorFor(status: SyncStatus): Indicator {
  if (!status.online) return { kind: 'offline', waiting: status.pending };
  if (!status.reachable) return { kind: 'unreachable', waiting: status.pending };
  if (status.pending > 0) return { kind: 'saving', waiting: status.pending };
  return { kind: 'saved' };
}

/** Online-only actions are disabled while this is false (SYNC-03). */
export function isConnected(status: SyncStatus): boolean {
  return status.online && status.reachable;
}

/** How long until the oldest waiting change is "waiting too long" (≤ 0: it is), or null. */
export function untilWaitingTooLong(status: SyncStatus, now: number): number | null {
  if (status.pending === 0 || status.oldestQueuedAt === null) return null;
  return status.oldestQueuedAt + WAITING_TOO_LONG_MS - now;
}

/** A tiny external store for useSyncExternalStore. */
export class Store<T> {
  private listeners = new Set<() => void>();
  private value: T;

  constructor(value: T) {
    this.value = value;
  }

  get = (): T => this.value;

  set(next: T): void {
    if (Object.is(next, this.value)) return;
    this.value = next;
    for (const listener of this.listeners) listener();
  }

  update(change: Partial<T>): void {
    const entries = Object.entries(change) as [keyof T, T[keyof T]][];
    if (entries.every(([key, value]) => Object.is(this.value[key], value))) return;
    this.set({ ...this.value, ...change });
  }

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };
}
