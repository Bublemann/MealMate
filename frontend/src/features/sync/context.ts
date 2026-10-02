import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
} from 'react';
import { useCurrentUser } from '@/features/auth/context';
import { useCategories } from '@/features/reference/api';
import { applyPending, type PendingList } from './applyPending';
import type { SyncEngine } from './engine';
import { isConnected, untilWaitingTooLong, type SyncStatus } from './status';
import type { Category, ListDetail, Op } from './types';

export const SyncContext = createContext<SyncEngine | null>(null);

/** Stable while the categories load, so the pending list isn't built again on every render. */
const NO_CATEGORIES: readonly Category[] = [];

export function useSyncEngine(): SyncEngine {
  const engine = useContext(SyncContext);
  if (!engine) throw new Error('useSyncEngine needs a <SyncProvider>');
  return engine;
}

/** The sync status (SYNC-07): waiting changes, connection, sending. */
export function useSyncStatus(): SyncStatus {
  const engine = useSyncEngine();
  return useSyncExternalStore(engine.status.subscribe, engine.status.get);
}

/** False while offline or MealMate can't be reached: online-only controls are disabled (SYNC-03). */
export function useConnected(): boolean {
  return isConnected(useSyncStatus());
}

/** Whether changes have been waiting for more than an hour (SYNC-07); updates on its own. */
export function useWaitingTooLong(): boolean {
  const status = useSyncStatus();
  const [now, setNow] = useState(() => Date.now());
  const left = untilWaitingTooLong(status, now);

  useEffect(() => {
    if (left === null || left <= 0) return;
    const timer = setTimeout(() => setNow(Date.now()), left);
    return () => clearTimeout(timer);
  }, [left]);

  return left !== null && left <= 0;
}

/** The waiting ops of the signed-in user for one list, in order. */
export function usePendingOps(listId: string): Op[] {
  const engine = useSyncEngine();
  const entries = useSyncExternalStore(engine.outbox.subscribe, engine.outbox.get);
  return useMemo(
    () => entries.filter((entry) => entry.listId === listId).map((entry) => entry.op),
    [entries, listId],
  );
}

/** Lists finished here whose *Finish* hasn't been sent yet: they are done already on screen. */
export function usePendingFinishes(): ReadonlySet<string> {
  const engine = useSyncEngine();
  const entries = useSyncExternalStore(engine.outbox.subscribe, engine.outbox.get);
  return useMemo(
    () => new Set(entries.filter((entry) => entry.op.type === 'list.finish').map((e) => e.listId)),
    [entries],
  );
}

/**
 * The list as the view shows it (plan § 8): the server's list or the local copy with this user's
 * waiting ops applied, so actions show at once and stay while they wait (SYNC-03/07).
 */
export function usePendingList(list: ListDetail | undefined): PendingList | undefined {
  const me = useCurrentUser();
  const ops = usePendingOps(list?.id ?? '');
  const categories = useCategories().data ?? NO_CATEGORIES;
  const user = useMemo(
    () => ({ id: me.id, display_name: me.display_name, deactivated: false }),
    [me.id, me.display_name],
  );
  return useMemo(
    () => list && applyPending(list, ops, { me: user, categories }),
    [list, ops, user, categories],
  );
}

/**
 * Queues shopping actions of one list (SYNC-03): resolves to true once the action is stored, to
 * false (with a message) if it couldn't be queued because nobody is signed in any more.
 */
export function useQueueOp(listId: string): (op: Op) => Promise<boolean> {
  const engine = useSyncEngine();
  return useMemo(() => (op: Op) => engine.enqueue(listId, op), [engine, listId]);
}
