import type { ListDetail, Op, OpResult, OutboxEntry } from './types';

/** The most ops `POST /lists/{id}/ops` takes at once. */
export const MAX_BATCH = 100;

/** What became of one request with a batch of ops. */
export type SendOutcome =
  /** 2xx: every op was applied, a duplicate or rejected; the list as it is now. */
  | { kind: 'sent'; results: OpResult[]; list: ListDetail }
  /**
   * 403/404 with the app's `common.forbidden` / `common.not_found`, confirmed by loading the list:
   * the list is gone, or no longer the user's to change.
   */
  | { kind: 'gone' }
  /** 401: the session ended (expired or revoked); the ops stay for the same user (SYNC-05). */
  | { kind: 'ended' }
  /**
   * The session is no longer the ops' user's (another user signed in meanwhile, e.g. in another
   * tab): nothing was sent, or the server refused it (409 `auth.user_mismatch`). The ops stay
   * (SYNC-10).
   */
  | { kind: 'stopped' }
  /**
   * No answer from the app: timeout, network failure, 5xx, 429, and any other 4xx that is not
   * one of the app's answers above (a proxy's 403, a 408, 413, …). Try again later.
   */
  | { kind: 'unreachable' }
  /** 400/422 with the app's error envelope: the batch can never succeed as it is. */
  | { kind: 'invalid'; status: number };

export type FlushResult = 'done' | 'unreachable' | 'ended' | 'stopped';

export interface FlushSteps {
  /** Checked before each request: ops are only sent with their own user's session (SYNC-10). */
  isCurrentUser(): boolean;
  send(listId: string, ops: Op[]): Promise<SendOutcome>;
  /** The server answered the batch: it is done with, whatever each op's result was. */
  sent(listId: string, batch: OutboxEntry[], results: OpResult[], list: ListDetail): Promise<void>;
  /** The list is gone: drop all of its ops. */
  gone(listId: string): Promise<void>;
  /** The batch was refused as a whole: drop it. */
  invalid(listId: string, batch: OutboxEntry[], status: number): Promise<void>;
}

/** Splits the entries into runs of one list, in order, of at most MAX_BATCH ops each. */
export function batches(entries: readonly OutboxEntry[]): OutboxEntry[][] {
  const result: OutboxEntry[][] = [];
  let current: OutboxEntry[] = [];
  for (const entry of entries) {
    const first = current[0];
    if (first && (first.listId !== entry.listId || current.length === MAX_BATCH)) {
      result.push(current);
      current = [];
    }
    current.push(entry);
  }
  if (current.length > 0) result.push(current);
  return result;
}

/**
 * Sends the user's waiting ops in the order they were made (plan § 5.8): consecutive ops of one
 * list go together, up to MAX_BATCH per request. It stops at the first request that doesn't reach
 * the server (the ops stay queued, SYNC-04) and when the session ends (SYNC-05). An op is only
 * dropped once the server has answered for it, or when its list is gone.
 */
export async function flushEntries(
  entries: readonly OutboxEntry[],
  steps: FlushSteps,
): Promise<FlushResult> {
  const goneLists = new Set<string>();
  for (const batch of batches(entries)) {
    const listId = batch[0]?.listId ?? '';
    if (goneLists.has(listId)) continue;
    if (!steps.isCurrentUser()) return 'stopped';
    const outcome = await steps.send(
      listId,
      batch.map((entry) => entry.op),
    );
    switch (outcome.kind) {
      case 'sent':
        await steps.sent(listId, batch, outcome.results, outcome.list);
        break;
      case 'gone':
        goneLists.add(listId);
        await steps.gone(listId);
        break;
      case 'invalid':
        await steps.invalid(listId, batch, outcome.status);
        break;
      case 'ended':
        return 'ended';
      case 'stopped':
        return 'stopped';
      case 'unreachable':
        return 'unreachable';
    }
  }
  return 'done';
}
