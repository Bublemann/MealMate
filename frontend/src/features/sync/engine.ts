import { notifyManager, type QueryClient } from '@tanstack/react-query';
import type { TFunction } from 'i18next';
import {
  api,
  createTimeoutFetch,
  isErrorEnvelope,
  onReachability,
  type FetchFn,
} from '@/api/client';
import { ApiError, isApiError } from '@/api/errors';
import type { AuthSession, SessionEnd } from '@/features/auth/session';
import { detailKey, FEED_KEY, type FeedData } from '@/features/lists/keys';
import { listDisplayName } from '@/features/lists/format';
import { CATEGORIES_KEY, categoriesQuery } from '@/features/reference/api';
import type { Language } from '@/i18n';
import { errorMessage } from '@/i18n/errors';
import { flushEntries, type FlushResult, type SendOutcome } from './flush';
import {
  applyPendingWipes,
  MemoryStorage,
  openSyncStorage,
  requestPersistenceFor,
  userMetaKey,
  wipeUser,
  type KnownData,
  type StorageHooks,
  type SyncStorage,
  type WipeReason,
} from './storage';
import { INITIAL_STATUS, Store, type SyncStatus } from './status';
import type { Category, ListDetail, Op, OpResult, OutboxEntry, StoredList } from './types';

/** The cross-tab lock around sending the outbox (plan § 5.8). */
export const OUTBOX_LOCK = 'mm-outbox';
/** Tabs tell each other on this channel that the outbox changed, so they read it again. */
export const OUTBOX_CHANNEL = 'mm-outbox';
/** While something waits and the app is visible, sending is tried again this often. */
export const FLUSH_INTERVAL_MS = 30_000;
/** Changes made online are followed by a refresh of the local copy, this long after the last. */
export const REFRESH_DEBOUNCE_MS = 1_000;

/** A short message about something that happened in the background; rendered in the UI. */
export interface Toast {
  id: number;
  text: (t: TFunction, language: Language) => string;
}

interface StoredCategories {
  categories: Category[];
  storedAt: number;
}

/** Summaries of the copy for the Lists home: the copy holds exactly "my" lists (UI-02). */
function summaryOf(list: ListDetail) {
  return {
    id: list.id,
    name: list.name,
    created_at: list.created_at,
    updated_at: list.updated_at,
    finished_at: list.finished_at,
    status: list.status,
    owner: list.owner,
    is_owner: list.is_owner,
    can_edit: list.can_edit,
    shared_with_partner: list.shared_with_partner,
    meal_count: list.meals.length,
    line_count: list.lines.filter((line) => !line.hidden).length,
  };
}

/**
 * The order of the list feed (UI-02): newest created first, ties by id. The times are compared as
 * times: the server writes fractions of a second only when there are any.
 */
function newestCreatedFirst(a: ListDetail, b: ListDetail): number {
  const byTime = Date.parse(b.created_at) - Date.parse(a.created_at);
  if (byTime !== 0) return byTime;
  return a.id === b.id ? 0 : a.id < b.id ? 1 : -1;
}

/** Whether a list belongs in the local copy: editable, and a draft or being shopped (SYNC-02). */
function belongsInCopy(list: ListDetail): boolean {
  return list.can_edit && list.status !== 'done';
}

function isDetailKey(key: readonly unknown[]): key is ReturnType<typeof detailKey> {
  return key.length === 3 && key[0] === 'lists' && key[1] === 'detail';
}

function isCategoriesKey(key: readonly unknown[]): boolean {
  return key.length === CATEGORIES_KEY.length && key.every((part, i) => part === CATEGORIES_KEY[i]);
}

/** App versions before D-31 stored the categories without their names, which headings need. */
function hasNames(stored: StoredCategories): boolean {
  return stored.categories.every((category) => typeof category.names === 'object');
}

/** The request would go out with a session that isn't the ops' user's any more (SYNC-10). */
class UserChangedError extends Error {
  constructor() {
    super('The signed-in user changed; the ops stay queued');
    this.name = 'UserChangedError';
  }
}

/** The code of the app's error envelope, or null for any other body (a proxy's page, nothing). */
function appErrorCode(body: unknown): string | null {
  return isErrorEnvelope(body) ? (body as { code: string }).code : null;
}

/** The app's own answer that a list is gone or no longer the user's to change. */
function isGoneAnswer(status: number, code: string | null): boolean {
  return (
    (status === 404 && code === 'common.not_found') ||
    (status === 403 && code === 'common.forbidden')
  );
}

/** What a session's end deletes on this device (SYNC-10); null: nothing. */
function wipeFor(reason: SessionEnd['reason']): WipeReason | null {
  switch (reason) {
    case 'logged_out':
      // Confirmed first when changes were waiting (SYNC-05).
      return 'logged_out';
    case 'revoked':
      return 'revoked';
    case null:
      // Someone else signed in: the copy goes, the ops stay tagged with their user.
      return 'replaced';
    default:
      // Expired (or a refused fork): the same user logs in again and everything is sent.
      return null;
  }
}

export interface SyncEngineOptions {
  session: AuthSession;
  queryClient: QueryClient;
  /** Where the copy and the outbox live (default: IndexedDB, else memory). */
  openStorage?: (hooks: StorageHooks) => Promise<SyncStorage>;
}

/**
 * The sync module (plan § 8, SYNC-02..10): the local copy of the user's lists, the outbox of ops
 * with its flush loop, the status the indicator shows, and the local data lifecycle that follows
 * the session. One per app, created next to the query client.
 *
 * - The copy is refreshed from `GET /lists/sync` at start, when the app comes to the foreground,
 *   when the connection returns and shortly after changes; it seeds the query cache, so lists show
 *   at once, also without a connection.
 * - Shopping actions always go through the outbox, online or offline (one code path): stored
 *   first, shown at once (`applyPending`), then sent in order.
 * - Ops are only ever sent with a session of the user who made them (SYNC-10).
 */
export class SyncEngine {
  readonly status = new Store<SyncStatus>(INITIAL_STATUS);
  /** The signed-in user's waiting ops, in order. */
  readonly outbox = new Store<readonly OutboxEntry[]>([]);
  readonly toasts = new Store<readonly Toast[]>([]);

  private readonly session: AuthSession;
  private readonly queryClient: QueryClient;
  private readonly openStorage: (hooks: StorageHooks) => Promise<SyncStorage>;
  private storagePromise: Promise<SyncStorage> | null = null;
  private readonly copy = new Map<string, StoredList>();
  private userId: string | null = null;
  /** When the copy of this user was last complete (so it stands for "my lists"), or null. */
  private syncedAt: number | null = null;
  /** Storage work that must not overlap (loading a user, wiping one), in order. */
  private chain: Promise<void> = Promise.resolve();
  /** Counts local outbox changes, so a reload from storage never undoes a newer one. */
  private outboxRevision = 0;
  private flushing: Promise<void> | null = null;
  private flushAgain = false;
  private refreshing: Promise<void> | null = null;
  private refreshAgain = false;
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;
  private nextToastId = 1;
  private channel: BroadcastChannel | null = null;
  private stops: (() => void)[] = [];

  constructor({ session, queryClient, openStorage = openSyncStorage }: SyncEngineOptions) {
    this.session = session;
    this.queryClient = queryClient;
    this.openStorage = openStorage;
  }

  /**
   * The storage, opened once. Should IndexedDB fail for good later on, memory takes over with
   * what this engine knows (the waiting ops with their `seq`, the copy) and the status says that
   * nothing is kept any more, so the "no storage" banner shows. Wipes an earlier visit couldn't
   * do in IndexedDB are done first.
   */
  private storage(): Promise<SyncStorage> {
    this.storagePromise ??= (async () => {
      const hooks: StorageHooks = {
        known: () => this.known(),
        degraded: () => this.status.update({ persistent: false }),
      };
      let storage: SyncStorage;
      try {
        storage = await this.openStorage(hooks);
      } catch (error) {
        console.warn('MealMate: no local storage, offline use is not available', error);
        storage = new MemoryStorage();
      }
      this.status.update({ persistent: storage.persistent });
      await applyPendingWipes(storage);
      return storage;
    })();
    return this.storagePromise;
  }

  private known(): KnownData {
    return { ops: this.outbox.get(), lists: [...this.copy.values()] };
  }

  /** Starts following the session, the connection and the app's visibility; returns `stop`. */
  start(): () => void {
    this.stop();
    const onOnline = () => {
      this.status.update({ online: true });
      this.syncNow();
    };
    const onOffline = () => this.status.update({ online: false });
    const onVisibility = () => {
      if (document.visibilityState !== 'visible') return;
      void this.reloadOutbox();
      this.syncNow();
    };
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    document.addEventListener('visibilitychange', onVisibility);
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible' && this.outbox.get().length > 0) {
        void this.flush();
      }
    }, FLUSH_INTERVAL_MS);
    this.status.update({ online: navigator.onLine });
    // Another tab sent or queued ops of this user: read the outbox again (SYNC-04).
    const channel =
      typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel(OUTBOX_CHANNEL);
    if (channel) {
      channel.onmessage = (event: MessageEvent<{ userId?: unknown }>) => {
        if (this.userId !== null && event.data.userId === this.userId) void this.reloadOutbox();
      };
    }
    this.channel = channel;

    this.stops = [
      () => window.removeEventListener('online', onOnline),
      () => window.removeEventListener('offline', onOffline),
      () => document.removeEventListener('visibilitychange', onVisibility),
      () => clearInterval(interval),
      () => {
        channel?.close();
        if (this.channel === channel) this.channel = null;
      },
      onReachability((reachable) => {
        const was = this.status.get().reachable;
        this.status.update({ reachable });
        // iOS fires no `online` when Tailscale comes back: the first answer after a failure is
        // the sign to send what waits (SYNC-04). Only the flush: a refresh of the copy would be
        // an answer of its own and could keep this going while only some requests get through.
        if (reachable && !was) void this.flush();
      }),
      this.session.subscribe(() => {
        this.followUser();
        this.confirmedUser();
      }),
      this.session.onEnd((event) => this.afterSessionEnd(event)),
      this.queryClient.getQueryCache().subscribe((event) => {
        if (event.type !== 'updated' || event.action.type !== 'success' || event.action.manual) {
          return;
        }
        const key = event.query.queryKey as readonly unknown[];
        this.remember(key, event.query.state.data);
      }),
      this.queryClient.getMutationCache().subscribe((event) => {
        if (event.type === 'updated' && event.action.type === 'success') this.scheduleRefresh();
      }),
      () => {
        if (this.refreshTimer) clearTimeout(this.refreshTimer);
      },
    ];
    this.followUser();
    this.confirmedUser();
    return () => this.stop();
  }

  private stop(): void {
    for (const stop of this.stops) stop();
    this.stops = [];
  }

  /** Runs storage work after everything scheduled before it, never failing the chain. */
  private schedule(task: (storage: SyncStorage) => Promise<void>): Promise<void> {
    const next = this.chain.then(async () => task(await this.storage()));
    this.chain = next.catch((error: unknown) => console.error('MealMate sync:', error));
    return this.chain;
  }

  /** The signed-in user as the session says; null while signed out or starting. */
  private sessionUserId(): string | null {
    const state = this.session.getState();
    return state.status === 'authenticated' ? (state.user?.id ?? null) : null;
  }

  /** Whether ops of `userId` may be sent now: the server confirmed that user in this tab. */
  private mayActFor(userId: string): boolean {
    const state = this.session.getState();
    return this.userId === userId && !state.offline && this.sessionUserId() === userId;
  }

  /**
   * How many ops of the signed-in user wait, once they have been read from storage (the count in
   * `status` may still be loading right after the start).
   */
  async waitingCount(): Promise<number> {
    await this.chain;
    return this.outbox.get().length;
  }

  private followUser(): void {
    const id = this.sessionUserId();
    if (id === this.userId) return;
    this.userId = id;
    this.syncedAt = null;
    this.copy.clear();
    this.outboxRevision++;
    this.outbox.set([]);
    this.updatePending();
    if (id === null) return;
    void this.schedule(async (storage) => {
      // Someone else signed in on this device: their copy must never be shown (SYNC-10). Their
      // waiting ops stay, tagged with them, and are never sent with this session.
      await storage.deleteListsExcept(id);
      if (this.userId !== id) return;
      const [lists, ops, categories, lastSync] = await Promise.all([
        storage.readLists(id),
        storage.readOps(id),
        storage.getMeta(userMetaKey('categories', id)),
        storage.getMeta(userMetaKey('lastSync', id)),
      ]);
      if (this.userId !== id) return;
      for (const entry of lists) this.copy.set(entry.id, entry);
      this.syncedAt = typeof lastSync === 'number' ? lastSync : null;
      this.mergeOutbox(ops);
      this.seed(lists, categories as StoredCategories | undefined);
    }).then(() => {
      if (this.userId === id) this.syncNow();
    });
  }

  /**
   * Once the server has confirmed a user, persistent storage is asked for (plan § 8): once per
   * user on this device, not on every start.
   */
  private confirmedUser(): void {
    const id = this.sessionUserId();
    if (id === null || this.session.getState().offline) return;
    void this.storage().then((storage) => {
      if (storage.persistent) requestPersistenceFor(id);
    });
  }

  /**
   * SYNC-10: what a session's end means for the data on this device (`wipeUser`). A wipe that
   * can't reach IndexedDB is done at the next start.
   */
  private afterSessionEnd({ reason, userId }: SessionEnd): void {
    const wipe = wipeFor(reason);
    if (wipe) void this.schedule((storage) => wipeUser(storage, userId, wipe));
  }

  /** Puts the copy into the query cache where nothing newer is there yet (SYNC-09). */
  private seed(lists: StoredList[], categories: StoredCategories | undefined) {
    const cache = this.queryClient;
    for (const { detail, storedAt } of lists) {
      if (cache.getQueryData(detailKey(detail.id)) === undefined) {
        cache.setQueryData(detailKey(detail.id), detail, { updatedAt: storedAt });
      }
    }
    // Only a copy that was ever complete stands in for the feed (an empty one too).
    const feed = this.copiedFeed();
    if (feed && cache.getQueryData(FEED_KEY) === undefined) {
      // Stale at once: the copy lacks read-only and done lists, so the feed is asked for anyway.
      cache.setQueryData(FEED_KEY, feed, { updatedAt: 0 });
    }
    if (categories && hasNames(categories) && cache.getQueryData(CATEGORIES_KEY) === undefined) {
      cache.setQueryData(CATEGORIES_KEY, categories.categories, {
        updatedAt: categories.storedAt,
      });
    }
  }

  /** Keeps what the app loaded for offline use: categories, and lists opened on screen. */
  private remember(key: readonly unknown[], data: unknown): void {
    const userId = this.userId;
    if (!userId || data === undefined) return;
    if (isCategoriesKey(key)) {
      const value: StoredCategories = { categories: data as Category[], storedAt: Date.now() };
      void this.schedule((storage) => storage.setMeta(userMetaKey('categories', userId), value));
    } else if (isDetailKey(key)) {
      this.keepInCopy(userId, data as ListDetail);
    }
  }

  /** Stores a list the server just sent in the copy, or removes it if it no longer belongs. */
  private keepInCopy(userId: string, list: ListDetail): void {
    const stored = this.copy.get(list.id);
    if (belongsInCopy(list)) {
      // Unchanged (a poll answered 304) or older: nothing to store.
      if (stored && (stored.detail === list || stored.detail.version > list.version)) return;
      const entry = { id: list.id, userId, detail: list, storedAt: Date.now() };
      this.copy.set(list.id, entry);
      void this.schedule(async (storage) => {
        if (this.userId === userId) await storage.putList(entry);
      });
    } else if (stored) {
      this.copy.delete(list.id);
      void this.schedule((storage) => storage.deleteList(list.id));
    }
  }

  /** A list of the copy, shown until the server answers (SYNC-09). */
  copied(listId: string): ListDetail | undefined {
    return this.copy.get(listId)?.detail;
  }

  /** When the list was stored in the copy. */
  copiedAt(listId: string): number | undefined {
    return this.copy.get(listId)?.storedAt;
  }

  /** The lists of the copy as rows of the list feed, in its order, once complete (SYNC-09). */
  copiedSummaries() {
    if (this.syncedAt === null) return undefined;
    return [...this.copy.values()]
      .map((entry) => entry.detail)
      .sort(newestCreatedFirst)
      .map(summaryOf);
  }

  /** The first page of the list feed from the copy, shown until the server answers (SYNC-09). */
  copiedFeed(): FeedData | undefined {
    const lists = this.copiedSummaries();
    return lists && { pages: [{ lists, next_cursor: null }], pageParams: [null] };
  }

  private mergeOutbox(entries: readonly OutboxEntry[]): void {
    const bySeq = new Map(this.outbox.get().map((entry) => [entry.seq, entry]));
    for (const entry of entries) bySeq.set(entry.seq, entry);
    this.outbox.set([...bySeq.values()].sort((a, b) => a.seq - b.seq));
    this.updatePending();
  }

  private removeFromOutbox(seqs: ReadonlySet<number>): void {
    this.outboxRevision++;
    this.outbox.set(this.outbox.get().filter((entry) => !seqs.has(entry.seq)));
    this.updatePending();
  }

  /** Reads the outbox again (another tab may have sent or added ops). */
  private async reloadOutbox(): Promise<void> {
    const userId = this.userId;
    if (!userId) return;
    const revision = this.outboxRevision;
    const storage = await this.storage();
    this.takeRead(storage, userId, await storage.readOps(userId), revision);
  }

  /**
   * Takes the user's ops as just read from storage for the outbox, unless it changed here since
   * the read began (`revision`). IndexedDB is shared by the tabs, so what it holds is the truth;
   * memory (IndexedDB given up) only holds what this tab put there, so a read of it may add to
   * what is known but never replace it.
   */
  private takeRead(
    storage: SyncStorage,
    userId: string,
    entries: readonly OutboxEntry[],
    revision: number,
  ): void {
    if (this.userId !== userId || this.outboxRevision !== revision) return;
    if (!storage.persistent) {
      this.mergeOutbox(entries);
      return;
    }
    this.outbox.set(entries);
    this.updatePending();
  }

  /** Tells the other tabs that this user's outbox changed. */
  private announce(storage: SyncStorage, userId: string): void {
    // Memory is this tab's alone: there is nothing for other tabs to read.
    if (!storage.persistent) return;
    try {
      this.channel?.postMessage({ userId });
    } catch {
      // The channel was closed meanwhile.
    }
  }

  private updatePending(): void {
    const entries = this.outbox.get();
    const oldest = entries.reduce<number | null>(
      (min, entry) => (min === null || entry.queuedAt < min ? entry.queuedAt : min),
      null,
    );
    this.status.update({ pending: entries.length, oldestQueuedAt: oldest });
  }

  /**
   * Queues an action of the signed-in user (SYNC-03/04): stored first, then shown (the view
   * applies the waiting ops), then sent. Resolves to true once it is stored, which never takes
   * long: the storage gives up on IndexedDB after a few seconds and keeps it in memory. False
   * (with a message) when nobody is signed in any more, so the UI can keep what was typed.
   */
  async enqueue(listId: string, op: Op): Promise<boolean> {
    const userId = this.userId;
    if (!userId) {
      this.toast((t) => t('sync.notQueued'));
      return false;
    }
    const storage = await this.storage();
    const entry = await storage.addOp({ userId, listId, op, queuedAt: Date.now() });
    if (this.userId !== userId) return true;
    this.outboxRevision++;
    this.mergeOutbox([entry]);
    this.announce(storage, userId);
    void this.flush();
    return true;
  }

  /** Sends what waits and refreshes the copy (start, foreground, connection back). */
  syncNow(): void {
    void this.flush().then(() => this.refreshCopy());
  }

  /** Sends the waiting ops: one run at a time in this tab, and across tabs under a lock. */
  flush(): Promise<void> {
    if (this.flushing) {
      this.flushAgain = true;
      return this.flushing;
    }
    this.flushing = (async () => {
      try {
        let result: FlushResult;
        do {
          this.flushAgain = false;
          result = await this.flushOnce();
        } while (this.flushAgain && result === 'done');
      } catch (error) {
        console.error('MealMate sync:', error);
      } finally {
        this.flushing = null;
        this.status.update({ sending: false });
      }
    })();
    return this.flushing;
  }

  private async flushOnce(): Promise<FlushResult> {
    const userId = this.userId;
    if (!userId || this.outbox.get().length === 0) return 'done';
    // The phone knows it has no connection: the `online` event tries again.
    if (!this.status.get().online) return 'unreachable';
    const storage = await this.storage();
    const run = async (): Promise<FlushResult> => {
      // Started without a connection: the server confirms who is signed in first (SYNC-10).
      if (this.session.getState().offline && !(await this.session.refresh())) return 'unreachable';
      if (!this.mayActFor(userId)) return 'stopped';
      const revision = this.outboxRevision;
      const entries = await storage.readOps(userId);
      // Another tab may have sent ops meanwhile: what is stored now is what waits.
      this.takeRead(storage, userId, entries, revision);
      if (entries.length === 0) return 'done';
      this.status.update({ sending: true });
      try {
        return await flushEntries(entries, {
          isCurrentUser: () => this.mayActFor(userId),
          send: (listId, ops) => this.sendOps(userId, listId, ops),
          sent: (_listId, batch, results, list) =>
            this.onSent(storage, userId, batch, results, list),
          gone: (listId) => this.onGone(storage, userId, listId),
          invalid: (_listId, batch, status) => this.onInvalid(storage, userId, batch, status),
        });
      } finally {
        this.announce(storage, userId);
      }
    };
    const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined;
    const result = locks ? await locks.request(OUTBOX_LOCK, run) : await run();
    if (result === 'done') this.scheduleRefresh();
    return result;
  }

  /**
   * One request with a batch of ops of `userId`, sorted into what it means for the outbox. It is
   * only ever sent with that user's session (`fetchFor`), and names the user in
   * `X-MealMate-User` so the server refuses it otherwise (SYNC-10).
   */
  private async sendOps(userId: string, listId: string, ops: Op[]): Promise<SendOutcome> {
    const fetch = this.fetchFor(userId);
    try {
      const { data, error, response } = await api.POST('/api/lists/{list_id}/ops', {
        params: { path: { list_id: listId }, header: { 'X-MealMate-User': userId } },
        body: { ops },
        fetch,
      });
      if (response.ok && data) return { kind: 'sent', results: data.results, list: data.list };
      const status = response.status;
      const code = appErrorCode(error);
      if (status === 401) return { kind: 'ended' };
      if (status === 409 && code === 'auth.user_mismatch') return { kind: 'stopped' };
      // Only the app's own "this can never work" drops a batch; anything else (a proxy's 4xx,
      // 408, 413, 429, 5xx) may pass and keeps the ops.
      if ((status === 400 || status === 422) && code !== null) return { kind: 'invalid', status };
      if (isGoneAnswer(status, code)) return await this.confirmGone(listId, fetch);
      return { kind: 'unreachable' };
    } catch (error) {
      if (error instanceof UserChangedError) return { kind: 'stopped' };
      if (isApiError(error) && error.status === 0) return { kind: 'unreachable' };
      throw error;
    }
  }

  /**
   * A 403/404 for the ops is checked once by loading the list before anything is dropped: while
   * the partners toggle sharing, a 403 may be over a moment later. Only a list that is still
   * gone, or no longer the user's to change, drops the ops.
   */
  private async confirmGone(listId: string, fetch: FetchFn): Promise<SendOutcome> {
    const { data, error, response } = await api.GET('/api/lists/{list_id}', {
      params: { path: { list_id: listId } },
      fetch,
    });
    if (data) return data.can_edit ? { kind: 'unreachable' } : { kind: 'gone' };
    return isGoneAnswer(response.status, appErrorCode(error))
      ? { kind: 'gone' }
      : { kind: 'unreachable' };
  }

  /**
   * The fetch for requests on behalf of `userId`'s ops. Right before each attempt it checks that
   * the session is still that user's and that the request carries its current token, and
   * refuses otherwise (UserChangedError). openapi-fetch hands it to the middleware too, so the
   * retry after a token refresh is checked as well: that refresh may have signed in someone else
   * (another tab, a shared refresh cookie), and one user's ops must never go out with another
   * user's token (SYNC-10).
   */
  private fetchFor(userId: string): FetchFn {
    const send = createTimeoutFetch();
    return (request) => {
      const token = this.session.accessToken();
      const allowed =
        this.mayActFor(userId) &&
        token !== null &&
        request.headers.get('Authorization') === `Bearer ${token}`;
      return allowed ? send(request) : Promise.reject(new UserChangedError());
    };
  }

  private async onSent(
    storage: SyncStorage,
    userId: string,
    batch: OutboxEntry[],
    results: OpResult[],
    list: ListDetail,
  ): Promise<void> {
    const seqs = new Set(batch.map((entry) => entry.seq));
    await storage.deleteOps([...seqs]);
    // Someone else signed in while the batch was on its way: the answer is not for their screen,
    // copy or messages (SYNC-10).
    if (this.userId !== userId) return;
    // The answer and the ops leaving the outbox reach the screen together, so nothing flickers.
    notifyManager.batch(() => {
      this.queryClient.setQueryData<ListDetail>(detailKey(list.id), (current) =>
        current && current.version > list.version ? current : list,
      );
      notifyManager.schedule(() => this.removeFromOutbox(seqs));
    });
    this.keepInCopy(userId, list);
    void this.queryClient.invalidateQueries({ queryKey: FEED_KEY });
    const rejected = new Map<string, number>();
    for (const result of results) {
      if (result.status !== 'rejected') continue;
      const code = result.code ?? 'common.internal';
      rejected.set(code, (rejected.get(code) ?? 0) + 1);
    }
    for (const [code, count] of rejected) {
      const reason = new ApiError({ status: 409, code: code as ApiError['code'] });
      this.toast((t, language) =>
        t('sync.rejected', {
          count,
          name: listDisplayName(list, t, language),
          reason: errorMessage(t, reason),
        }),
      );
    }
  }

  private async onGone(storage: SyncStorage, userId: string, listId: string): Promise<void> {
    const dropped = (await storage.readOps(userId)).filter((entry) => entry.listId === listId);
    const seqs = new Set(dropped.map((entry) => entry.seq));
    await storage.deleteOps([...seqs]);
    if (this.userId !== userId) return;
    await storage.deleteList(listId);
    this.copy.delete(listId);
    this.removeFromOutbox(seqs);
    this.toast((t) => t('sync.discarded', { count: dropped.length }));
    void this.queryClient.invalidateQueries({ queryKey: detailKey(listId) });
    void this.queryClient.invalidateQueries({ queryKey: FEED_KEY });
  }

  private async onInvalid(
    storage: SyncStorage,
    userId: string,
    batch: OutboxEntry[],
    status: number,
  ) {
    // Should not happen: the app only makes valid ops. Kept, it would block the queue for good.
    console.error(`MealMate sync: ${status} for ops, dropping them`, batch);
    const seqs = new Set(batch.map((entry) => entry.seq));
    await storage.deleteOps([...seqs]);
    if (this.userId !== userId) return;
    this.removeFromOutbox(seqs);
    this.toast((t) => t('sync.invalid', { count: batch.length }));
  }

  private toast(text: Toast['text']): void {
    this.toasts.set([...this.toasts.get(), { id: this.nextToastId++, text }]);
  }

  dismissToast(id: number): void {
    this.toasts.set(this.toasts.get().filter((toast) => toast.id !== id));
  }

  private scheduleRefresh(): void {
    if (this.refreshTimer) clearTimeout(this.refreshTimer);
    this.refreshTimer = setTimeout(() => {
      this.refreshTimer = null;
      void this.refreshCopy();
    }, REFRESH_DEBOUNCE_MS);
  }

  /**
   * Replaces the copy with `GET /lists/sync` (SYNC-02): lists that are no longer returned (done,
   * deleted, access lost) disappear from it (SYNC-10). An unchanged answer (304) changes nothing.
   */
  refreshCopy(): Promise<void> {
    if (this.refreshing) {
      this.refreshAgain = true;
      return this.refreshing;
    }
    this.refreshing = (async () => {
      try {
        do {
          this.refreshAgain = false;
          await this.refreshOnce();
        } while (this.refreshAgain);
      } catch (error) {
        // Not reached: the status says so; the copy stays as it is.
        if (!isApiError(error)) console.error('MealMate sync:', error);
      } finally {
        this.refreshing = null;
      }
    })();
    return this.refreshing;
  }

  private async refreshOnce(): Promise<void> {
    const userId = this.userId;
    if (!userId) return;
    // They head the stored lists offline (LIST-11), so they are kept as current as the copy;
    // loaded only once they are stale, and kept for offline use by `remember`.
    void this.queryClient.prefetchQuery(categoriesQuery);
    const storage = await this.storage();
    const etagKey = userMetaKey('etag', userId);
    // An empty copy (e.g. deleted while someone else was signed in) is loaded in full: a stored
    // ETag might still match, and a 304 would leave it empty.
    const etag =
      this.copy.size > 0 ? ((await storage.getMeta(etagKey)) as string | undefined) : undefined;
    const { data, response } = await api.GET('/api/lists/sync', {
      params: { header: etag ? { 'if-none-match': etag } : {} },
    });
    if (this.sessionUserId() !== userId || this.userId !== userId) return;
    if (response.status === 304 || !response.ok || !data) return;
    const storedAt = Date.now();
    await this.schedule(async (current) => {
      if (this.userId !== userId) return;
      await current.replaceLists(userId, data.lists, storedAt);
      await current.setMeta(etagKey, response.headers.get('ETag') ?? undefined);
      await current.setMeta(userMetaKey('lastSync', userId), storedAt);
    });
    if (this.userId !== userId) return;
    this.copy.clear();
    this.syncedAt = storedAt;
    for (const detail of data.lists) {
      this.copy.set(detail.id, { id: detail.id, userId, detail, storedAt });
      this.queryClient.setQueryData<ListDetail>(detailKey(detail.id), (current) =>
        current && current.version >= detail.version ? current : detail,
      );
    }
  }
}
