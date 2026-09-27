import type { components } from '@/api/generated/schema';

export type ListDetail = components['schemas']['ListDetail'];
export type ListLine = components['schemas']['ListLine'];
export type ExtraItem = components['schemas']['ExtraItem'];
export type UserRef = components['schemas']['UserRef'];
export type Category = components['schemas']['Category'];
/** One action of shopping mode (plan § 5.8), as `POST /lists/{id}/ops` takes it. */
export type Op = components['schemas']['Op'];
export type OpResult = components['schemas']['OpResult'];

/** A list of the local copy (SYNC-02): text only, as `GET /lists/sync` returned it. */
export interface StoredList {
  id: string;
  /** Whose copy it is; another user never gets to see it (SYNC-10). */
  userId: string;
  detail: ListDetail;
  /** When it was stored (ms since the epoch). */
  storedAt: number;
}

/** An op waiting to be sent (SYNC-03/04), tagged with the user who made it (SYNC-10). */
export interface OutboxEntry {
  /** Order of the outbox: ops are sent in this order. */
  seq: number;
  userId: string;
  listId: string;
  op: Op;
  /** When it was queued (ms since the epoch), for the "waiting too long" banner (SYNC-07). */
  queuedAt: number;
}

/** An entry about to be stored; the outbox gives it its `seq`. */
export type NewOutboxEntry = Omit<OutboxEntry, 'seq'>;
