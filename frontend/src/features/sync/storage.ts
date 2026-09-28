import { openDB, type DBSchema, type IDBPDatabase, type IDBPObjectStore } from 'idb';
import type { ListDetail, NewOutboxEntry, OutboxEntry, StoredList } from './types';

/** The IndexedDB database of the sync module (plan § 8). */
export const DB_NAME = 'mealmate';
export const DB_VERSION = 1;
/**
 * How long opening the database may take. An upgrade blocked by an old tab, or iOS's IndexedDB
 * hanging after the app returns from the background, must not keep the app waiting: after this
 * it goes on in memory (SYNC-09).
 */
export const OPEN_DEADLINE_MS = 3_000;
/** How long one read or write may take before it counts as failed (and is tried once more). */
export const OPERATION_DEADLINE_MS = 5_000;

interface SyncDbSchema extends DBSchema {
  /** The local copy (SYNC-02), by list id. Only one user's lists are ever stored at a time. */
  lists: { key: string; value: StoredList };
  /** Ops waiting to be sent (SYNC-03/04), in `seq` order, tagged with their user. */
  outbox: { key: number; value: OutboxEntry; indexes: { byUser: string } };
  /** Small values, e.g. `etag:<userId>`; keys ending in `:<userId>` belong to that user. */
  meta: { key: string; value: unknown };
}

/**
 * Where the sync module keeps the local copy, the outbox and a few values. `persistent` is false
 * when IndexedDB can't be used (private browsing, blocked site data, or it failed for good during
 * this visit): everything then lasts for this visit only, and the app works online as before
 * (SYNC-09).
 */
export interface SyncStorage {
  readonly persistent: boolean;
  readLists(userId: string): Promise<StoredList[]>;
  /**
   * Replaces the user's copy with `lists`: lists that are not among them are deleted, and so are
   * other users' lists together with their copy's values (see `deleteListsOf`).
   */
  replaceLists(userId: string, lists: readonly ListDetail[], storedAt: number): Promise<void>;
  putList(entry: StoredList): Promise<void>;
  deleteList(listId: string): Promise<void>;
  /**
   * Deletes the user's copy together with the values that describe it (`etag:`, `lastSync:`):
   * a stored ETag of a deleted copy would make the next sync answer 304 and leave it empty.
   */
  deleteListsOf(userId: string): Promise<void>;
  /** The same for every other user. */
  deleteListsExcept(userId: string): Promise<void>;
  addOp(entry: NewOutboxEntry): Promise<OutboxEntry>;
  /** The user's ops in the order they were queued. */
  readOps(userId: string): Promise<OutboxEntry[]>;
  deleteOps(seqs: readonly number[]): Promise<void>;
  deleteOpsOf(userId: string): Promise<void>;
  deleteOpsExcept(userId: string): Promise<void>;
  getMeta(key: string): Promise<unknown>;
  setMeta(key: string, value: unknown): Promise<void>;
  deleteMetaOf(userId: string): Promise<void>;
}

/** What the app holds of the stored data: carried into memory when IndexedDB is given up. */
export interface KnownData {
  ops: readonly OutboxEntry[];
  lists: readonly StoredList[];
}

/** How the storage tells the app that IndexedDB failed for good during this visit. */
export interface StorageHooks {
  /** The ops and lists the app knows of right now; memory starts with them. */
  known(): KnownData;
  /** IndexedDB was given up: from now on everything lasts for this visit only. */
  degraded(): void;
}

const NO_HOOKS: StorageHooks = {
  known: () => ({ ops: [], lists: [] }),
  degraded: () => undefined,
};

/** The meta key of a value that belongs to `userId`. */
export function userMetaKey(name: string, userId: string): string {
  return `${name}:${userId}`;
}

function belongsTo(key: string, userId: string): boolean {
  return key.endsWith(`:${userId}`);
}

/** The values that describe a user's copy; they go whenever the copy goes. */
const COPY_META = ['etag', 'lastSync'];

/** The user a value of the copy belongs to, or null for any other value. */
function copyMetaUser(key: string): string | null {
  const separator = key.indexOf(':');
  if (separator < 0 || !COPY_META.includes(key.slice(0, separator))) return null;
  return key.slice(separator + 1);
}

class StorageTimeoutError extends Error {
  constructor(ms: number) {
    super(`IndexedDB did not answer within ${ms} ms`);
    this.name = 'StorageTimeoutError';
  }
}

/** Rejects when `promise` hasn't settled after `ms`; the work itself may still finish later. */
function withDeadline<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new StorageTimeoutError(ms)), ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error: unknown) => {
        clearTimeout(timer);
        reject(error instanceof Error ? error : new Error(String(error)));
      },
    );
  });
}

type SyncDb = IDBPDatabase<SyncDbSchema>;

/**
 * Opens the database within OPEN_DEADLINE_MS. `lost` is called when the connection can no longer
 * be used: the browser closed it (`terminated`: iOS after the app was in the background, site
 * data cleared), or a newer version of the app wants to upgrade it (`blocking`: this connection
 * steps aside instead of blocking the other tab). The next access then opens it again.
 */
async function openDatabase(lost: (db: SyncDb) => void): Promise<SyncDb> {
  let db: SyncDb | undefined;
  const opening = openDB<SyncDbSchema>(DB_NAME, DB_VERSION, {
    upgrade(database) {
      database.createObjectStore('lists', { keyPath: 'id' });
      const outbox = database.createObjectStore('outbox', {
        keyPath: 'seq',
        autoIncrement: true,
      });
      outbox.createIndex('byUser', 'userId');
      database.createObjectStore('meta');
    },
    blocking() {
      if (!db) return;
      db.close();
      lost(db);
    },
    terminated() {
      if (db) lost(db);
    },
  });
  try {
    db = await withDeadline(opening, OPEN_DEADLINE_MS);
    return db;
  } catch (error) {
    // Should it open after all, it must not stay open unused and block a later upgrade.
    opening.then(
      (late) => late.close(),
      () => undefined,
    );
    throw error;
  }
}

/**
 * IndexedDB. A failed read or write (a closed connection, no answer in time) closes the
 * connection, opens it again and is tried once more; only if that fails too does the error reach
 * the caller (FallbackStorage), so a connection iOS dropped in the background costs nothing.
 */
class IdbStorage implements SyncStorage {
  readonly persistent = true;
  private db: SyncDb | null = null;
  private opening: Promise<SyncDb> | null = null;

  static async open(): Promise<IdbStorage> {
    const storage = new IdbStorage();
    await storage.connection();
    return storage;
  }

  private connection(): Promise<SyncDb> {
    if (this.db) return Promise.resolve(this.db);
    this.opening ??= openDatabase((db) => this.lost(db))
      .then((db) => {
        this.db = db;
        return db;
      })
      .finally(() => {
        this.opening = null;
      });
    return this.opening;
  }

  private lost(db: SyncDb): void {
    if (this.db === db) this.db = null;
  }

  private async run<T>(action: (db: SyncDb) => Promise<T>): Promise<T> {
    const db = await this.connection();
    try {
      return await withDeadline(action(db), OPERATION_DEADLINE_MS);
    } catch (error) {
      console.warn('MealMate: local storage failed, opening it again', error);
      try {
        db.close();
      } catch {
        // Already closed.
      }
      this.lost(db);
      // Throws when it can't be opened again or fails again: the caller then uses memory. A write
      // that only timed out may still land later; an op stored twice is harmless, since the
      // server applies each op_id once.
      return withDeadline(action(await this.connection()), OPERATION_DEADLINE_MS);
    }
  }

  readLists(userId: string) {
    return this.run(async (db) => {
      const all = await db.getAll('lists');
      return all.filter((entry) => entry.userId === userId);
    });
  }

  replaceLists(userId: string, lists: readonly ListDetail[], storedAt: number) {
    return this.run(async (db) => {
      const tx = db.transaction(['lists', 'meta'], 'readwrite');
      const keep = new Set(lists.map((list) => list.id));
      const store = tx.objectStore('lists');
      let cursor = await store.openCursor();
      while (cursor) {
        if (cursor.value.userId !== userId || !keep.has(cursor.value.id)) await cursor.delete();
        cursor = await cursor.continue();
      }
      for (const detail of lists) await store.put({ id: detail.id, userId, detail, storedAt });
      await deleteCopyMeta(tx.objectStore('meta'), (owner) => owner !== userId);
      await tx.done;
    });
  }

  putList(entry: StoredList) {
    return this.run(async (db) => {
      await db.put('lists', entry);
    });
  }

  deleteList(listId: string) {
    return this.run((db) => db.delete('lists', listId));
  }

  deleteListsOf(userId: string) {
    return this.deleteCopiesWhere((owner) => owner === userId);
  }

  deleteListsExcept(userId: string) {
    return this.deleteCopiesWhere((owner) => owner !== userId);
  }

  private deleteCopiesWhere(test: (userId: string) => boolean) {
    return this.run(async (db) => {
      const tx = db.transaction(['lists', 'meta'], 'readwrite');
      let cursor = await tx.objectStore('lists').openCursor();
      while (cursor) {
        if (test(cursor.value.userId)) await cursor.delete();
        cursor = await cursor.continue();
      }
      await deleteCopyMeta(tx.objectStore('meta'), test);
      await tx.done;
    });
  }

  addOp(entry: NewOutboxEntry) {
    return this.run(async (db) => {
      const tx = db.transaction('outbox', 'readwrite');
      // The key path fills in `seq`; the value is stored with it.
      const seq = await tx.store.add(entry as OutboxEntry);
      await tx.done;
      return { ...entry, seq };
    });
  }

  readOps(userId: string) {
    return this.run(async (db) => {
      const ops = await db.getAllFromIndex('outbox', 'byUser', userId);
      return ops.sort((a, b) => a.seq - b.seq);
    });
  }

  deleteOps(seqs: readonly number[]) {
    return this.run(async (db) => {
      const tx = db.transaction('outbox', 'readwrite');
      for (const seq of seqs) await tx.store.delete(seq);
      await tx.done;
    });
  }

  deleteOpsOf(userId: string) {
    return this.deleteOpsWhere((entry) => entry.userId === userId);
  }

  deleteOpsExcept(userId: string) {
    return this.deleteOpsWhere((entry) => entry.userId !== userId);
  }

  private deleteOpsWhere(test: (entry: OutboxEntry) => boolean) {
    return this.run(async (db) => {
      const tx = db.transaction('outbox', 'readwrite');
      let cursor = await tx.store.openCursor();
      while (cursor) {
        if (test(cursor.value)) await cursor.delete();
        cursor = await cursor.continue();
      }
      await tx.done;
    });
  }

  getMeta(key: string) {
    return this.run((db) => db.get('meta', key));
  }

  setMeta(key: string, value: unknown) {
    return this.run(async (db) => {
      await db.put('meta', value, key);
    });
  }

  deleteMetaOf(userId: string) {
    return this.run(async (db) => {
      const tx = db.transaction('meta', 'readwrite');
      let cursor = await tx.store.openCursor();
      while (cursor) {
        if (belongsTo(cursor.key, userId)) await cursor.delete();
        cursor = await cursor.continue();
      }
      await tx.done;
    });
  }
}

/** The meta store within a transaction over the copy and its values. */
type MetaStore = IDBPObjectStore<SyncDbSchema, ('lists' | 'meta')[], 'meta', 'readwrite'>;

async function deleteCopyMeta(store: MetaStore, test: (userId: string) => boolean) {
  let cursor = await store.openCursor();
  while (cursor) {
    const owner = copyMetaUser(cursor.key);
    if (owner !== null && test(owner)) await cursor.delete();
    cursor = await cursor.continue();
  }
}

/**
 * The same in memory, when IndexedDB can't be used: lasts for this visit only. It can start with
 * what the app already knew (`KnownData`), with new ops numbered after the known ones, so taking
 * over from IndexedDB mid-visit loses nothing and mixes nothing up.
 */
export class MemoryStorage implements SyncStorage {
  readonly persistent = false;
  private readonly lists = new Map<string, StoredList>();
  private readonly ops = new Map<number, OutboxEntry>();
  private readonly meta = new Map<string, unknown>();
  private nextSeq = 1;

  constructor(known: KnownData = { ops: [], lists: [] }) {
    for (const entry of known.lists) this.lists.set(entry.id, entry);
    for (const entry of known.ops) {
      this.ops.set(entry.seq, entry);
      this.nextSeq = Math.max(this.nextSeq, entry.seq + 1);
    }
  }

  readLists(userId: string) {
    return Promise.resolve([...this.lists.values()].filter((entry) => entry.userId === userId));
  }

  replaceLists(userId: string, lists: readonly ListDetail[], storedAt: number) {
    const keep = new Set(lists.map((list) => list.id));
    for (const [id, entry] of this.lists) {
      if (entry.userId !== userId || !keep.has(id)) this.lists.delete(id);
    }
    for (const detail of lists)
      this.lists.set(detail.id, { id: detail.id, userId, detail, storedAt });
    this.deleteCopyMeta((owner) => owner !== userId);
    return Promise.resolve();
  }

  putList(entry: StoredList) {
    this.lists.set(entry.id, entry);
    return Promise.resolve();
  }

  deleteList(listId: string) {
    this.lists.delete(listId);
    return Promise.resolve();
  }

  deleteListsOf(userId: string) {
    for (const [id, entry] of this.lists) if (entry.userId === userId) this.lists.delete(id);
    this.deleteCopyMeta((owner) => owner === userId);
    return Promise.resolve();
  }

  deleteListsExcept(userId: string) {
    for (const [id, entry] of this.lists) if (entry.userId !== userId) this.lists.delete(id);
    this.deleteCopyMeta((owner) => owner !== userId);
    return Promise.resolve();
  }

  private deleteCopyMeta(test: (userId: string) => boolean) {
    for (const key of this.meta.keys()) {
      const owner = copyMetaUser(key);
      if (owner !== null && test(owner)) this.meta.delete(key);
    }
  }

  addOp(entry: NewOutboxEntry) {
    const stored = { ...entry, seq: this.nextSeq++ };
    this.ops.set(stored.seq, stored);
    return Promise.resolve(stored);
  }

  readOps(userId: string) {
    const ops = [...this.ops.values()].filter((entry) => entry.userId === userId);
    return Promise.resolve(ops.sort((a, b) => a.seq - b.seq));
  }

  deleteOps(seqs: readonly number[]) {
    for (const seq of seqs) this.ops.delete(seq);
    return Promise.resolve();
  }

  deleteOpsOf(userId: string) {
    for (const [seq, entry] of this.ops) if (entry.userId === userId) this.ops.delete(seq);
    return Promise.resolve();
  }

  deleteOpsExcept(userId: string) {
    for (const [seq, entry] of this.ops) if (entry.userId !== userId) this.ops.delete(seq);
    return Promise.resolve();
  }

  getMeta(key: string) {
    return Promise.resolve(this.meta.get(key));
  }

  setMeta(key: string, value: unknown) {
    this.meta.set(key, value);
    return Promise.resolve();
  }

  deleteMetaOf(userId: string) {
    for (const key of this.meta.keys()) if (belongsTo(key, userId)) this.meta.delete(key);
    return Promise.resolve();
  }
}

/**
 * IndexedDB that switches to memory when it keeps failing although it was opened again (e.g. the
 * quota is full, or it can't be opened any more), so an action is never lost for this visit and
 * never crashes the app. Memory then starts with what the app knows (the waiting ops with their
 * `seq`, the copy), and `hooks.degraded()` lets the status say that nothing is kept any more.
 */
class FallbackStorage implements SyncStorage {
  private readonly primary: SyncStorage;
  private readonly hooks: StorageHooks;
  private current: SyncStorage;

  constructor(primary: SyncStorage, hooks: StorageHooks) {
    this.primary = primary;
    this.hooks = hooks;
    this.current = primary;
  }

  get persistent() {
    return this.current.persistent;
  }

  private async run<T>(action: (storage: SyncStorage) => Promise<T>): Promise<T> {
    const storage = this.current;
    try {
      return await action(storage);
    } catch (error) {
      if (storage !== this.primary) throw error;
      if (this.current === this.primary) {
        console.warn('MealMate: local storage failed, keeping changes in memory only', error);
        this.current = new MemoryStorage(this.hooks.known());
        this.hooks.degraded();
      }
      return action(this.current);
    }
  }

  readLists(userId: string) {
    return this.run((storage) => storage.readLists(userId));
  }
  replaceLists(userId: string, lists: readonly ListDetail[], storedAt: number) {
    return this.run((storage) => storage.replaceLists(userId, lists, storedAt));
  }
  putList(entry: StoredList) {
    return this.run((storage) => storage.putList(entry));
  }
  deleteList(listId: string) {
    return this.run((storage) => storage.deleteList(listId));
  }
  deleteListsOf(userId: string) {
    return this.run((storage) => storage.deleteListsOf(userId));
  }
  deleteListsExcept(userId: string) {
    return this.run((storage) => storage.deleteListsExcept(userId));
  }
  addOp(entry: NewOutboxEntry) {
    return this.run((storage) => storage.addOp(entry));
  }
  readOps(userId: string) {
    return this.run((storage) => storage.readOps(userId));
  }
  deleteOps(seqs: readonly number[]) {
    return this.run((storage) => storage.deleteOps(seqs));
  }
  deleteOpsOf(userId: string) {
    return this.run((storage) => storage.deleteOpsOf(userId));
  }
  deleteOpsExcept(userId: string) {
    return this.run((storage) => storage.deleteOpsExcept(userId));
  }
  getMeta(key: string) {
    return this.run((storage) => storage.getMeta(key));
  }
  setMeta(key: string, value: unknown) {
    return this.run((storage) => storage.setMeta(key, value));
  }
  deleteMetaOf(userId: string) {
    return this.run((storage) => storage.deleteMetaOf(userId));
  }
}

/**
 * Opens the database, or falls back to memory when IndexedDB is missing, refuses (private
 * browsing, blocked site data) or doesn't answer within OPEN_DEADLINE_MS (an upgrade blocked by an
 * old tab): never throws, never hangs.
 */
export async function openSyncStorage(hooks: StorageHooks = NO_HOOKS): Promise<SyncStorage> {
  try {
    if (typeof indexedDB === 'undefined') return new MemoryStorage();
    return new FallbackStorage(await IdbStorage.open(), hooks);
  } catch (error) {
    console.warn('MealMate: no local storage, offline use is not available', error);
    return new MemoryStorage();
  }
}

// --- device-level markers (localStorage) --------------------------------------------------------

/**
 * What a session's end deletes on this device (SYNC-05, SYNC-10): `logged_out` everything of the
 * user; `revoked` the copy and its values, and every *other* user's ops (this user's stay for when
 * they are allowed back in); `replaced` (someone else signed in) only the copy.
 */
export type WipeReason = 'logged_out' | 'revoked' | 'replaced';

/**
 * `mm.sync.wipe.<userId>`: a wipe that hasn't reached IndexedDB yet. Device-level (not `mm.user.`,
 * which the session's end clears itself).
 */
const WIPE_KEY_PREFIX = 'mm.sync.wipe.';
/** `mm.sync.persisted.<userId>`: persistent storage was asked for once for this user. */
const PERSISTED_KEY_PREFIX = 'mm.sync.persisted.';
const WIPE_REASONS: readonly string[] = ['logged_out', 'revoked', 'replaced'];

// localStorage can be unavailable (private browsing, blocked site data); every access is guarded.
function localKeys(): string[] {
  try {
    return Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i) ?? '');
  } catch {
    return [];
  }
}

function readLocal(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeLocal(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Then it lasts for this visit only.
  }
}

/**
 * Deletes what a session's end takes away (see WipeReason). It is noted in localStorage first and
 * the note is removed only once the wipe reached IndexedDB: when IndexedDB failed and memory
 * stands in for it, the next start does it (`applyPendingWipes`), so another user never finds the
 * data of the previous one.
 */
export async function wipeUser(
  storage: SyncStorage,
  userId: string,
  reason: WipeReason,
): Promise<void> {
  const key = `${WIPE_KEY_PREFIX}${userId}`;
  writeLocal(key, reason);
  await storage.deleteListsOf(userId);
  if (reason !== 'replaced') await storage.deleteMetaOf(userId);
  if (reason === 'logged_out') await storage.deleteOpsOf(userId);
  if (reason === 'revoked') await storage.deleteOpsExcept(userId);
  if (storage.persistent) writeLocal(key, null);
}

/** Does the wipes an earlier visit couldn't do in IndexedDB; never throws. */
export async function applyPendingWipes(storage: SyncStorage): Promise<void> {
  if (!storage.persistent) return;
  for (const key of localKeys()) {
    if (!key.startsWith(WIPE_KEY_PREFIX)) continue;
    const reason = readLocal(key);
    const userId = key.slice(WIPE_KEY_PREFIX.length);
    try {
      if (reason && WIPE_REASONS.includes(reason)) {
        await wipeUser(storage, userId, reason as WipeReason);
      } else {
        writeLocal(key, null);
      }
    } catch (error) {
      console.error('MealMate sync:', error);
    }
  }
}

/**
 * Asks the browser to keep the local data under storage pressure (plan § 8). The answer doesn't
 * matter: iOS decides on its own, and the app works either way.
 */
export function requestPersistence(): void {
  try {
    void navigator.storage?.persist?.().catch(() => undefined);
  } catch {
    // Not supported.
  }
}

/**
 * Asks for persistent storage once per user on this device, after the server confirmed them
 * (plan § 8), rather than on every start.
 */
export function requestPersistenceFor(userId: string): void {
  const key = `${PERSISTED_KEY_PREFIX}${userId}`;
  if (readLocal(key) !== null) return;
  writeLocal(key, '1');
  requestPersistence();
}
