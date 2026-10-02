import 'fake-indexeddb/auto';
import { QueryClient } from '@tanstack/react-query';
import { IDBFactory } from 'fake-indexeddb';
import { openDB } from 'idb';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, connectAuth } from '@/api/client';
import type { components } from '@/api/generated/schema';
import { createAuthSession, type AuthSession } from '@/features/auth/session';
import { detailKey, FEED_KEY } from '@/features/lists/keys';
import i18n from '@/i18n';
import { BEN, errorResponse, loginResponse, mockApi, requestsTo, TEST_USER } from '@/test/api';
import { doneList, LIST_ID, shoppingList } from '@/test/lists';
import { SyncEngine } from './engine';
import {
  DB_NAME,
  MemoryStorage,
  OPEN_DEADLINE_MS,
  openSyncStorage,
  userMetaKey,
  type SyncStorage,
} from './storage';

type Schemas = components['schemas'];
type Op = Schemas['Op'];

const OTHER_LIST = 'list-other';
const BEN_USER: Schemas['Me'] = { ...TEST_USER, id: BEN.id, username: 'ben', display_name: 'Ben' };

let seq = 0;
function check(key = 'i:ing-zwiebeln', checked = true): Op {
  seq += 1;
  return {
    type: 'line.check',
    payload: { line_key: key, checked },
    op_id: `0190c0de-0000-7000-8000-${String(seq).padStart(12, '0')}`,
    at: new Date().toISOString(),
  };
}

function opsAnswer(
  list: Schemas['ListDetail'],
  statuses: Schemas['OpResult']['status'][] = ['applied'],
  code: Schemas['ErrorCode'] | null = null,
): Schemas['OpsResponse'] {
  return {
    list,
    results: statuses.map((status, i) => ({
      op_id: `op-${i}`,
      status,
      code: status === 'rejected' ? code : null,
    })),
  };
}

function syncAnswer(...lists: Schemas['ListDetail'][]): Schemas['ListsSync'] {
  return { lists, generated_at: '2026-09-26T14:00:00Z' };
}

interface Harness {
  engine: SyncEngine;
  session: AuthSession;
  queryClient: QueryClient;
  storage: SyncStorage;
  stop: () => void;
}

const running: (() => void)[] = [];

async function startEngine({
  user = TEST_USER,
  session,
}: { user?: Schemas['Me']; session?: AuthSession } = {}): Promise<Harness> {
  const authSession = session ?? createAuthSession({ initial: { user, accessToken: 'token' } });
  connectAuth(authSession);
  const queryClient = new QueryClient();
  // Like AuthProvider: a session's end drops the cached server data.
  running.push(authSession.onEnd(() => queryClient.clear()));
  const engine = new SyncEngine({ session: authSession, queryClient });
  const stop = engine.start();
  running.push(stop);
  const storage = await openSyncStorage();
  return { engine, session: authSession, queryClient, storage, stop };
}

/** Lets the engine's storage work, flushes and refreshes run to the end. */
async function settle(engine: SyncEngine) {
  for (let i = 0; i < 5; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
    await engine.flush();
    await engine.refreshCopy();
  }
}

function goOffline() {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
  window.dispatchEvent(new Event('offline'));
}

function goOnline() {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
  window.dispatchEvent(new Event('online'));
}

async function sentBodies(fetchMock: ReturnType<typeof mockApi>, listId = LIST_ID) {
  const requests = requestsTo(fetchMock, `POST /api/lists/${listId}/ops`);
  return Promise.all(
    requests.map((request) => request.clone().json() as Promise<Schemas['OpsRequest']>),
  );
}

beforeEach(() => {
  // A fresh, empty database for every test.
  globalThis.indexedDB = new IDBFactory();
});

afterEach(() => {
  for (const stop of running.splice(0)) stop();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe('outbox (SYNC-03/04)', () => {
  it('stores ops first, in order, and they survive a restart', async () => {
    mockApi();
    goOffline();
    const first = await startEngine();
    await settle(first.engine);
    const ops = [check('i:a'), check('i:b')];

    await first.engine.enqueue(LIST_ID, ops[0]!);
    await first.engine.enqueue(OTHER_LIST, ops[1]!);

    expect(first.engine.outbox.get().map((entry) => entry.op)).toEqual(ops);
    expect(first.engine.status.get()).toMatchObject({ pending: 2, online: false });
    first.stop();

    // The app was closed: a new start reads them back.
    const again = await startEngine();
    await vi.waitFor(() => expect(again.engine.outbox.get()).toHaveLength(2));
    expect(again.engine.outbox.get().map((entry) => entry.op)).toEqual(ops);
    const stored = await again.storage.readOps(TEST_USER.id);
    expect(stored.map((entry) => [entry.listId, entry.userId])).toEqual([
      [LIST_ID, TEST_USER.id],
      [OTHER_LIST, TEST_USER.id],
    ]);
  });

  it('sends consecutive ops of a list together, in order, and forgets them after 2xx', async () => {
    const fetchMock = mockApi({
      [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(shoppingList({ version: 6 }), [
        'applied',
        'applied',
      ]),
      [`POST /api/lists/${OTHER_LIST}/ops`]: opsAnswer(shoppingList({ id: OTHER_LIST })),
      'GET /api/lists/sync': syncAnswer(shoppingList({ version: 6 })),
    });
    goOffline();
    const { engine, storage, queryClient } = await startEngine();
    await settle(engine);
    const ops = [check('i:a'), check('i:b'), check('i:c')];
    await engine.enqueue(LIST_ID, ops[0]!);
    await engine.enqueue(LIST_ID, ops[1]!);
    await engine.enqueue(OTHER_LIST, ops[2]!);

    goOnline();
    await settle(engine);

    expect((await sentBodies(fetchMock)).map((body) => body.ops)).toEqual([[ops[0], ops[1]]]);
    expect((await sentBodies(fetchMock, OTHER_LIST)).map((body) => body.ops)).toEqual([[ops[2]]]);
    const posts = fetchMock.mock.calls.filter(([request]) => request.method === 'POST');
    expect(posts.map(([request]) => new URL(request.url).pathname)).toEqual([
      `/api/lists/${LIST_ID}/ops`,
      `/api/lists/${OTHER_LIST}/ops`,
    ]);
    expect(engine.outbox.get()).toEqual([]);
    expect(await storage.readOps(TEST_USER.id)).toEqual([]);
    expect(engine.status.get()).toMatchObject({ pending: 0, sending: false, reachable: true });
    // The answer is the list as it is now: into the cache and the copy.
    expect(queryClient.getQueryData(detailKey(LIST_ID))).toMatchObject({ version: 6 });
    expect(engine.copied(LIST_ID)).toMatchObject({ version: 6 });
  });

  it('is done with applied, duplicate and rejected ops, and says once what was refused', async () => {
    mockApi({
      [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(
        doneList(),
        ['applied', 'duplicate', 'rejected', 'rejected'],
        'list.done',
      ),
    });
    goOffline();
    const { engine, storage } = await startEngine();
    await settle(engine);
    for (const op of [check('i:a'), check('i:b'), check('i:c'), check('i:d')]) {
      await engine.enqueue(LIST_ID, op);
    }

    goOnline();
    await settle(engine);

    expect(await storage.readOps(TEST_USER.id)).toEqual([]);
    const toasts = engine.toasts.get();
    expect(toasts).toHaveLength(1);
    expect(toasts[0]?.text(i18n.t, 'en')).toBe(
      "2 changes to “Wochenende (26/09/2026)” could not be saved: This list is finished, so it can't be changed any more. Reopen it first.",
    );
    // A done list no longer belongs in the copy (SYNC-02).
    expect(engine.copied(LIST_ID)).toBeUndefined();
    engine.dismissToast(toasts[0]!.id);
    expect(engine.toasts.get()).toEqual([]);
  });

  it.each([404, 403])(
    'drops the ops of a list that answers %i, with one message',
    async (status) => {
      const fetchMock = mockApi({
        [`POST /api/lists/${LIST_ID}/ops`]: errorResponse(
          status,
          status === 404 ? 'common.not_found' : 'common.forbidden',
        ),
        [`POST /api/lists/${OTHER_LIST}/ops`]: opsAnswer(shoppingList({ id: OTHER_LIST })),
        'GET /api/lists/sync': syncAnswer(shoppingList()),
      });
      const { engine, storage } = await startEngine();
      await settle(engine);
      expect(engine.copied(LIST_ID)).toBeDefined();
      goOffline();
      await engine.enqueue(LIST_ID, check('i:a'));
      await engine.enqueue(OTHER_LIST, check('i:b'));
      await engine.enqueue(LIST_ID, check('i:c'));
      const code = status === 404 ? 'common.not_found' : 'common.forbidden';
      const secondMock = mockApi({
        [`POST /api/lists/${LIST_ID}/ops`]: errorResponse(status, code),
        // Loading the list confirms it before anything is dropped.
        [`GET /api/lists/${LIST_ID}`]: errorResponse(status, code),
        [`POST /api/lists/${OTHER_LIST}/ops`]: opsAnswer(shoppingList({ id: OTHER_LIST })),
        'GET /api/lists/sync': syncAnswer(),
      });

      goOnline();
      await settle(engine);

      expect(await storage.readOps(TEST_USER.id)).toEqual([]);
      expect(engine.toasts.get().map((toast) => toast.text(i18n.t, 'en'))).toEqual([
        '2 changes to a list you no longer have access to were discarded.',
      ]);
      expect(engine.copied(LIST_ID)).toBeUndefined();
      expect(fetchMock).toBeDefined();
      expect(requestsTo(secondMock, `GET /api/lists/${LIST_ID}`)).toHaveLength(1);
    },
  );

  it('keeps everything when the network is gone, and says the server can’t be reached', async () => {
    const fetchMock = mockApi();
    const { engine, storage } = await startEngine();
    await settle(engine);
    fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')));

    await engine.enqueue(LIST_ID, check('i:a'));
    await engine.enqueue(LIST_ID, check('i:b'));
    await settle(engine);

    expect(await storage.readOps(TEST_USER.id)).toHaveLength(2);
    expect(engine.status.get()).toMatchObject({ pending: 2, reachable: false, sending: false });
  });

  it.each([500, 503, 429])('keeps everything on %i and tries again later', async (status) => {
    mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: errorResponse(status, 'common.internal') });
    const { engine, storage } = await startEngine();
    await settle(engine);
    await engine.enqueue(LIST_ID, check());
    await settle(engine);
    expect(await storage.readOps(TEST_USER.id)).toHaveLength(1);
  });

  it('drops a batch the server refuses as invalid (422), saying so', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: errorResponse(422, 'common.validation') });
    const { engine, storage } = await startEngine();
    await settle(engine);
    await engine.enqueue(LIST_ID, check());
    await settle(engine);
    expect(await storage.readOps(TEST_USER.id)).toEqual([]);
    expect(engine.toasts.get().map((toast) => toast.text(i18n.t, 'en'))).toEqual([
      '1 change could not be saved and was discarded.',
    ]);
    expect(error).toHaveBeenCalled();
  });

  it('keeps the ops when the session expired while sending (SYNC-05)', async () => {
    mockApi({
      [`POST /api/lists/${LIST_ID}/ops`]: errorResponse(401, 'auth.session_expired'),
    });
    const { engine, storage, session } = await startEngine();
    await settle(engine);
    await engine.enqueue(LIST_ID, check());
    await settle(engine);

    expect(session.getState()).toMatchObject({ status: 'anonymous', reason: 'expired' });
    expect(await storage.readOps(TEST_USER.id)).toHaveLength(1);
  });

  it('refreshes an expired access token mid-flush and sends the batch again', async () => {
    let expired = true;
    const fetchMock = mockApi({
      'POST /api/auth/refresh': loginResponse(TEST_USER),
      [`POST /api/lists/${LIST_ID}/ops`]: () => {
        if (!expired) return opsAnswer(shoppingList({ version: 6 }));
        expired = false;
        return errorResponse(401, 'auth.token_expired');
      },
    });
    const { engine, storage } = await startEngine();
    await settle(engine);
    const op = check();

    await engine.enqueue(LIST_ID, op);
    await settle(engine);

    expect((await sentBodies(fetchMock)).map((body) => body.ops)).toEqual([[op], [op]]);
    expect(requestsTo(fetchMock, 'POST /api/auth/refresh')).toHaveLength(1);
    expect(await storage.readOps(TEST_USER.id)).toEqual([]);
  });

  it('never sends another user’s ops (SYNC-10)', async () => {
    const fetchMock = mockApi();
    const storage = await openSyncStorage();
    await storage.addOp({ userId: BEN.id, listId: LIST_ID, op: check(), queuedAt: 1 });

    const { engine } = await startEngine();
    await settle(engine);
    await engine.flush();

    expect(requestsTo(fetchMock, `POST /api/lists/${LIST_ID}/ops`)).toHaveLength(0);
    expect(engine.status.get().pending).toBe(0);
    expect(await storage.readOps(BEN.id)).toHaveLength(1);
  });

  it('waits for the server to confirm the user before sending (start without connection)', async () => {
    localStorage.setItem('mm.user.profile', JSON.stringify(TEST_USER));
    let reachable = false;
    const fetchMock = mockApi({
      'POST /api/auth/refresh': () => {
        if (!reachable) throw new TypeError('Failed to fetch');
        return loginResponse(TEST_USER);
      },
      [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(shoppingList()),
    });
    const session = createAuthSession();
    const { engine } = await startEngine({ session });
    await session.start();
    expect(session.getState()).toMatchObject({ status: 'authenticated', offline: true });
    await engine.enqueue(LIST_ID, check());
    await settle(engine);
    expect(requestsTo(fetchMock, `POST /api/lists/${LIST_ID}/ops`)).toHaveLength(0);

    reachable = true;
    goOnline();
    await settle(engine);
    expect(requestsTo(fetchMock, `POST /api/lists/${LIST_ID}/ops`)).toHaveLength(1);
    expect(engine.status.get().pending).toBe(0);
  });
});

describe('local copy (SYNC-02, SYNC-10)', () => {
  it('replaces the copy: a list no longer returned disappears', async () => {
    const other = shoppingList({ id: OTHER_LIST, name: 'Grillen' });
    mockApi({ 'GET /api/lists/sync': syncAnswer(shoppingList(), other) });
    const { engine, storage } = await startEngine();
    await settle(engine);
    expect((await storage.readLists(TEST_USER.id)).map((entry) => entry.id).sort()).toEqual(
      [LIST_ID, OTHER_LIST].sort(),
    );

    // Access to "Grillen" was lost.
    mockApi({ 'GET /api/lists/sync': syncAnswer(shoppingList({ version: 6 })) });
    await engine.refreshCopy();

    expect((await storage.readLists(TEST_USER.id)).map((entry) => entry.id)).toEqual([LIST_ID]);
    expect(engine.copied(OTHER_LIST)).toBeUndefined();
    expect(engine.copied(LIST_ID)).toMatchObject({ version: 6 });
  });

  it('sends the stored ETag and keeps the copy on 304', async () => {
    const answers: Response[] = [
      Response.json(syncAnswer(shoppingList()), { headers: { ETag: 'W/"a"' } }),
      new Response(null, { status: 304, headers: { ETag: 'W/"a"' } }),
    ];
    const fetchMock = mockApi({ 'GET /api/lists/sync': () => answers.shift() });
    const { engine, storage } = await startEngine();
    await settle(engine);
    await engine.refreshCopy();

    const gets = requestsTo(fetchMock, 'GET /api/lists/sync');
    expect(gets.at(0)?.headers.get('If-None-Match')).toBeNull();
    expect(gets.at(-1)?.headers.get('If-None-Match')).toBe('W/"a"');
    expect(await storage.readLists(TEST_USER.id)).toHaveLength(1);
  });

  it('seeds the query cache from the copy at start (SYNC-09)', async () => {
    const storage = await openSyncStorage();
    await storage.putList({
      id: LIST_ID,
      userId: TEST_USER.id,
      detail: shoppingList(),
      storedAt: 5,
    });
    await storage.setMeta(userMetaKey('lastSync', TEST_USER.id), 5);
    let answer: (() => void) | undefined;
    mockApi({
      'GET /api/lists/sync': () =>
        new Promise((resolve) => {
          answer = () => resolve(syncAnswer(shoppingList()));
        }),
    });

    const { engine, queryClient } = await startEngine();
    await vi.waitFor(() =>
      expect(queryClient.getQueryData(detailKey(LIST_ID))).toMatchObject({ id: LIST_ID }),
    );
    expect(queryClient.getQueryData(FEED_KEY)).toEqual({
      pages: [
        {
          lists: [expect.objectContaining({ id: LIST_ID, status: 'shopping', meal_count: 3 })],
          next_cursor: null,
        },
      ],
      pageParams: [null],
    });
    expect(engine.copiedSummaries()).toHaveLength(1);
    answer?.();
  });

  it('keeps a list opened on screen in the copy', async () => {
    mockApi({ 'GET /api/lists/sync': syncAnswer(shoppingList()) });
    const { engine, queryClient, storage } = await startEngine();
    await settle(engine);
    await queryClient.fetchQuery({
      queryKey: detailKey(LIST_ID),
      queryFn: () => Promise.resolve(shoppingList({ version: 8 })),
    });
    expect(engine.copied(LIST_ID)).toMatchObject({ version: 8 });
    await vi.waitFor(async () =>
      expect((await storage.readLists(TEST_USER.id))[0]?.detail.version).toBe(8),
    );
    // Finished: no longer part of the copy (SYNC-02).
    queryClient.setQueryData(detailKey(LIST_ID), doneList());
    await queryClient.fetchQuery({
      queryKey: detailKey(LIST_ID),
      queryFn: () => Promise.resolve(doneList({ version: 10 })),
      staleTime: 0,
    });
    expect(engine.copied(LIST_ID)).toBeUndefined();
  });
});

describe('lifecycle (SYNC-05, SYNC-10)', () => {
  async function withData(harness: Harness) {
    const { engine, storage } = harness;
    await settle(engine);
    goOffline();
    await engine.enqueue(LIST_ID, check());
    await storage.addOp({ userId: BEN.id, listId: LIST_ID, op: check(), queuedAt: 1 });
    await storage.putList({
      id: LIST_ID,
      userId: TEST_USER.id,
      detail: shoppingList(),
      storedAt: 1,
    });
    await storage.setMeta(userMetaKey('etag', TEST_USER.id), 'W/"x"');
    await storage.setMeta(userMetaKey('lastSync', TEST_USER.id), 1);
  }

  async function contents(storage: SyncStorage) {
    return {
      mine: (await storage.readOps(TEST_USER.id)).length,
      ben: (await storage.readOps(BEN.id)).length,
      lists: (await storage.readLists(TEST_USER.id)).length,
      etag: await storage.getMeta(userMetaKey('etag', TEST_USER.id)),
      lastSync: await storage.getMeta(userMetaKey('lastSync', TEST_USER.id)),
    };
  }

  it('logging out deletes the copy, the values and the outbox of the user', async () => {
    mockApi({ 'POST /api/auth/logout': null });
    const harness = await startEngine();
    await withData(harness);

    await harness.session.logout();
    await settle(harness.engine);

    expect(await contents(harness.storage)).toEqual({
      mine: 0,
      ben: 1,
      lists: 0,
      etag: undefined,
      lastSync: undefined,
    });
    expect(harness.engine.status.get().pending).toBe(0);
  });

  it('a revoked session deletes the copy and keeps only this user’s outbox', async () => {
    mockApi();
    const harness = await startEngine();
    await withData(harness);

    harness.session.sessionEnded('auth.session_revoked');
    await settle(harness.engine);

    expect(await contents(harness.storage)).toEqual({
      mine: 1,
      ben: 0,
      lists: 0,
      etag: undefined,
      lastSync: undefined,
    });
  });

  it('an expired session keeps the copy and the outbox; the same user sends it later', async () => {
    const fetchMock = mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(shoppingList()) });
    const harness = await startEngine();
    await withData(harness);

    harness.session.sessionEnded('auth.session_expired');
    await settle(harness.engine);
    expect(await contents(harness.storage)).toEqual({
      mine: 1,
      ben: 1,
      lists: 1,
      etag: 'W/"x"',
      lastSync: 1,
    });

    goOnline();
    harness.session.signIn(loginResponse(TEST_USER));
    await settle(harness.engine);
    expect(requestsTo(fetchMock, `POST /api/lists/${LIST_ID}/ops`)).toHaveLength(1);
    expect((await contents(harness.storage)).mine).toBe(0);
  });

  it('someone else signing in removes the previous copy; their ops stay unsent', async () => {
    const fetchMock = mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(shoppingList()) });
    const harness = await startEngine();
    await withData(harness);
    goOnline();

    harness.session.signIn(loginResponse(BEN_USER));
    await settle(harness.engine);

    const after = await contents(harness.storage);
    expect(after.lists).toBe(0);
    expect(after.mine).toBe(1);
    // The values that describe the deleted copy go with it: a stale ETag would make Anna's next
    // sync answer 304 and leave her copy empty.
    expect(after.etag).toBeUndefined();
    expect(after.lastSync).toBeUndefined();
    // Ben's own waiting op is sent with his session; Anna's never is.
    const sent = (await sentBodies(fetchMock)).flatMap((body) => body.ops);
    expect(sent).toHaveLength(1);
    expect(after.ben).toBe(0);
    expect(harness.engine.status.get().pending).toBe(0);
  });

  it('gives the previous user a full copy again when they come back', async () => {
    // The server's copy is unchanged: with the old ETag it would answer 304.
    const fetchMock = mockApi({
      'GET /api/lists/sync': (request: Request) =>
        request.headers.get('If-None-Match') === 'W/"a"'
          ? new Response(null, { status: 304, headers: { ETag: 'W/"a"' } })
          : Response.json(syncAnswer(shoppingList()), { headers: { ETag: 'W/"a"' } }),
    });
    const harness = await startEngine();
    await settle(harness.engine);
    expect(await harness.storage.getMeta(userMetaKey('etag', TEST_USER.id))).toBe('W/"a"');

    harness.session.signIn(loginResponse(BEN_USER));
    await settle(harness.engine);
    const before = requestsTo(fetchMock, 'GET /api/lists/sync').length;
    harness.session.signIn(loginResponse(TEST_USER));
    await settle(harness.engine);

    expect(harness.engine.copied(LIST_ID)).toMatchObject({ id: LIST_ID });
    expect(await harness.storage.readLists(TEST_USER.id)).toHaveLength(1);
    const back = requestsTo(fetchMock, 'GET /api/lists/sync')[before];
    expect(back?.headers.get('If-None-Match')).toBeNull();
  });

  it('a cached profile that turns out to be someone else never sends or shows the old data', async () => {
    const storage = await openSyncStorage();
    await storage.putList({
      id: LIST_ID,
      userId: TEST_USER.id,
      detail: shoppingList(),
      storedAt: 1,
    });
    await storage.setMeta(userMetaKey('lastSync', TEST_USER.id), 1);
    await storage.addOp({ userId: TEST_USER.id, listId: LIST_ID, op: check(), queuedAt: 1 });
    localStorage.setItem('mm.user.profile', JSON.stringify(TEST_USER));
    let answer: (() => void) | undefined;
    const fetchMock = mockApi({
      // The refresh cookie is Ben's now (he signed in in another tab).
      'POST /api/auth/refresh': () =>
        new Promise((resolve) => {
          answer = () => resolve(loginResponse(BEN_USER));
        }),
      'GET /api/lists/sync': syncAnswer(),
      [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(shoppingList()),
    });
    const session = createAuthSession();
    const { engine, queryClient } = await startEngine({ session });
    const started = session.start();
    // Anna's copy shows at once while the refresh runs: it is her profile on screen (SYNC-09).
    await vi.waitFor(() => expect(engine.copied(LIST_ID)).toBeDefined());
    await engine.enqueue(LIST_ID, check('i:b'));

    answer?.();
    await started;
    await settle(engine);

    expect(session.getState().user?.id).toBe(BEN.id);
    expect(requestsTo(fetchMock, `POST /api/lists/${LIST_ID}/ops`)).toHaveLength(0);
    expect(engine.copied(LIST_ID)).toBeUndefined();
    expect(queryClient.getQueryData(detailKey(LIST_ID))).toBeUndefined();
    expect(engine.copiedSummaries()).toEqual([]);
    expect(await storage.readLists(TEST_USER.id)).toEqual([]);
    expect(await storage.readOps(TEST_USER.id)).toHaveLength(2);
    expect(engine.outbox.get()).toEqual([]);
  });
});

describe('without IndexedDB', () => {
  it('falls back to memory: works online as before and says it can’t keep anything', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.stubGlobal('indexedDB', undefined);
    const storage = await openSyncStorage();
    expect(storage).toBeInstanceOf(MemoryStorage);
    vi.unstubAllGlobals();

    const fetchMock = mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(shoppingList()) });
    const session = createAuthSession({ initial: { user: TEST_USER, accessToken: 'token' } });
    connectAuth(session);
    const engine = new SyncEngine({
      session,
      queryClient: new QueryClient(),
      openStorage: () => Promise.resolve(storage),
    });
    running.push(engine.start());
    await engine.enqueue(LIST_ID, check());
    await settle(engine);

    expect(requestsTo(fetchMock, `POST /api/lists/${LIST_ID}/ops`)).toHaveLength(1);
    expect(engine.status.get()).toMatchObject({ persistent: false, pending: 0 });
    expect(warn).not.toHaveBeenCalled();
  });

  it('falls back to memory when opening the database fails', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.spyOn(indexedDB, 'open').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    await expect(openSyncStorage()).resolves.toBeInstanceOf(MemoryStorage);
    expect(warn).toHaveBeenCalled();
  });
});

describe('only with the ops’ own user (SYNC-10)', () => {
  it('names the user in every request with ops', async () => {
    const fetchMock = mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(shoppingList()) });
    const { engine } = await startEngine();
    await settle(engine);
    await engine.enqueue(LIST_ID, check());
    await settle(engine);

    const [request] = requestsTo(fetchMock, `POST /api/lists/${LIST_ID}/ops`);
    expect(request?.headers.get('X-MealMate-User')).toBe(TEST_USER.id);
  });

  it('never sends the batch again with the token of someone a refresh signed in', async () => {
    let calls = 0;
    const fetchMock = mockApi({
      // Ben signed in in another tab: the shared refresh cookie is his now.
      'POST /api/auth/refresh': loginResponse(BEN_USER),
      [`POST /api/lists/${LIST_ID}/ops`]: () => {
        calls += 1;
        return calls === 1
          ? errorResponse(401, 'auth.token_expired')
          : opsAnswer(shoppingList({ version: 6 }));
      },
    });
    const { engine, storage, session } = await startEngine();
    await settle(engine);
    const op = check();

    await engine.enqueue(LIST_ID, op);
    await settle(engine);

    expect(session.getState().user?.id).toBe(BEN.id);
    const sent = requestsTo(fetchMock, `POST /api/lists/${LIST_ID}/ops`);
    expect(sent).toHaveLength(1);
    expect(sent[0]?.headers.get('Authorization')).toBe('Bearer token');
    // Anna's check-off waits for Anna.
    expect((await storage.readOps(TEST_USER.id)).map((entry) => entry.op)).toEqual([op]);
  });

  it('keeps the ops when the server says they belong to someone else', async () => {
    mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: errorResponse(409, 'auth.user_mismatch') });
    const { engine, storage } = await startEngine();
    await settle(engine);
    await engine.enqueue(LIST_ID, check());
    await settle(engine);

    expect(await storage.readOps(TEST_USER.id)).toHaveLength(1);
    expect(engine.toasts.get()).toEqual([]);
  });

  it('does not put an answer for the previous user on the new user’s screen', async () => {
    let answer: (() => void) | undefined;
    mockApi({
      [`POST /api/lists/${LIST_ID}/ops`]: () =>
        new Promise((resolve) => {
          answer = () => resolve(opsAnswer(shoppingList({ version: 9 })));
        }),
    });
    const { engine, storage, session, queryClient } = await startEngine();
    await settle(engine);
    await engine.enqueue(LIST_ID, check());
    await vi.waitFor(() => expect(answer).toBeDefined());

    session.signIn(loginResponse(BEN_USER));
    answer?.();
    await settle(engine);

    // Sent with Anna's session, so it is done with; but it is not Ben's list.
    expect(await storage.readOps(TEST_USER.id)).toEqual([]);
    expect(queryClient.getQueryData(detailKey(LIST_ID))).toBeUndefined();
    expect(engine.copied(LIST_ID)).toBeUndefined();
    expect(await storage.readLists(BEN.id)).toEqual([]);
  });
});

describe('what drops ops', () => {
  it.each([
    ['a 408', () => new Response(null, { status: 408 })],
    ['a 409 of a proxy', () => new Response('Conflict', { status: 409 })],
    ['a 413 of a proxy', () => new Response('Request Entity Too Large', { status: 413 })],
    ['a 425', () => new Response(null, { status: 425 })],
    ['a 400 without the app’s envelope', () => new Response('Bad Request', { status: 400 })],
    ['a 404 of a proxy', () => new Response('Not Found', { status: 404 })],
    ['a 403 of a proxy', () => Response.json({ message: 'Forbidden' }, { status: 403 })],
  ])('keeps them on %s', async (_name, answer) => {
    mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: answer });
    const { engine, storage } = await startEngine();
    await settle(engine);
    await engine.enqueue(LIST_ID, check());
    await settle(engine);

    expect(await storage.readOps(TEST_USER.id)).toHaveLength(1);
    expect(engine.toasts.get()).toEqual([]);
  });

  it('drops a batch on the app’s 400', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
    mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: errorResponse(400, 'common.validation') });
    const { engine, storage } = await startEngine();
    await settle(engine);
    await engine.enqueue(LIST_ID, check());
    await settle(engine);

    expect(await storage.readOps(TEST_USER.id)).toEqual([]);
  });

  it('keeps them when the list is there after all (a 403 while sharing was toggled)', async () => {
    let forbidden = true;
    const fetchMock = mockApi({
      [`POST /api/lists/${LIST_ID}/ops`]: () =>
        forbidden ? errorResponse(403, 'common.forbidden') : opsAnswer(shoppingList()),
      [`GET /api/lists/${LIST_ID}`]: () => {
        forbidden = false;
        return shoppingList();
      },
    });
    const { engine, storage } = await startEngine();
    await settle(engine);
    await engine.enqueue(LIST_ID, check());
    await engine.flush();

    expect(requestsTo(fetchMock, `GET /api/lists/${LIST_ID}`)).toHaveLength(1);
    expect(await storage.readOps(TEST_USER.id)).toHaveLength(1);
    expect(engine.toasts.get()).toEqual([]);

    await settle(engine);
    expect(requestsTo(fetchMock, `POST /api/lists/${LIST_ID}/ops`)).toHaveLength(2);
    expect(await storage.readOps(TEST_USER.id)).toEqual([]);
  });

  it('drops them when the list is still there but no longer mine to change', async () => {
    mockApi({
      [`POST /api/lists/${LIST_ID}/ops`]: errorResponse(403, 'common.forbidden'),
      [`GET /api/lists/${LIST_ID}`]: shoppingList({ can_edit: false }),
    });
    const { engine, storage } = await startEngine();
    await settle(engine);
    await engine.enqueue(LIST_ID, check());
    await settle(engine);

    expect(await storage.readOps(TEST_USER.id)).toEqual([]);
    expect(engine.toasts.get()).toHaveLength(1);
  });
});

describe('when IndexedDB fails mid-visit', () => {
  const lost = () =>
    new DOMException(
      'Connection to Indexed Database server lost. Refresh the page to try again',
      'UnknownError',
    );

  async function withTwoWaiting() {
    mockApi();
    goOffline();
    const harness = await startEngine();
    await settle(harness.engine);
    const ops = [check('i:a'), check('i:b')];
    for (const op of ops) await harness.engine.enqueue(LIST_ID, op);
    return { ...harness, ops };
  }

  it('opens it again and loses nothing when the connection was lost', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const { engine, ops } = await withTwoWaiting();
    vi.spyOn(IDBDatabase.prototype, 'transaction').mockImplementationOnce(() => {
      throw lost();
    });

    const third = check('i:c');
    await expect(engine.enqueue(LIST_ID, third)).resolves.toBe(true);

    expect(warn).toHaveBeenCalledOnce();
    expect(engine.status.get()).toMatchObject({ persistent: true, pending: 3 });
    const stored = await (await openSyncStorage()).readOps(TEST_USER.id);
    expect(stored.map((entry) => entry.op)).toEqual([...ops, third]);
  });

  it('keeps what it knows in memory when it can’t be opened again, and says so', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const { engine, ops } = await withTwoWaiting();
    const known = engine.outbox.get().map((entry) => entry.seq);
    vi.spyOn(IDBDatabase.prototype, 'transaction').mockImplementation(() => {
      throw lost();
    });
    vi.spyOn(IDBFactory.prototype, 'open').mockImplementation(() => {
      throw lost();
    });

    // Back in the foreground: the outbox is read again, which fails for good.
    document.dispatchEvent(new Event('visibilitychange'));
    await vi.waitFor(() => expect(engine.status.get().persistent).toBe(false));
    await settle(engine);
    expect(engine.outbox.get().map((entry) => entry.op)).toEqual(ops);

    // A new op is numbered after the known ones: nothing is overwritten.
    const third = check('i:c');
    await engine.enqueue(LIST_ID, third);
    const seqs = engine.outbox.get().map((entry) => entry.seq);
    expect(new Set(seqs).size).toBe(3);
    expect(Math.min(...seqs.slice(2))).toBeGreaterThan(Math.max(...known));
    expect(await engine.waitingCount()).toBe(3);

    // Everything is sent once the connection is back, and leaves the outbox.
    const fetchMock = mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(shoppingList()) });
    goOnline();
    await settle(engine);
    expect((await sentBodies(fetchMock)).flatMap((body) => body.ops)).toEqual([...ops, third]);
    expect(engine.outbox.get()).toEqual([]);
  });

  it('logging out then wipes IndexedDB at the next start', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const { engine, session } = await withTwoWaiting();
    const transaction = vi.spyOn(IDBDatabase.prototype, 'transaction').mockImplementation(() => {
      throw lost();
    });
    const open = vi.spyOn(IDBFactory.prototype, 'open').mockImplementation(() => {
      throw lost();
    });
    mockApi({ 'POST /api/auth/logout': null });

    await session.logout();
    await settle(engine);
    expect(engine.status.get().persistent).toBe(false);
    transaction.mockRestore();
    open.mockRestore();
    const storage = await openSyncStorage();
    expect(await storage.readOps(TEST_USER.id)).toHaveLength(2);

    // The next start (someone else signs in on this phone).
    await startEngine({ user: BEN_USER });
    await vi.waitFor(async () => expect(await storage.readOps(TEST_USER.id)).toEqual([]));
    expect(localStorage.getItem(`mm.sync.wipe.${TEST_USER.id}`)).toBeNull();
  });

  it('goes on in memory when opening the database hangs (an upgrade blocked by an old tab)', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      // An older connection that doesn't step aside blocks this upgrade for ever.
      const old = await openDB('blocker', 1);
      const factory = indexedDB;
      const blocked = factory.open('blocker', 2);
      vi.spyOn(factory, 'open').mockReturnValue(blocked);

      const opening = openSyncStorage();
      await vi.advanceTimersByTimeAsync(OPEN_DEADLINE_MS);

      await expect(opening).resolves.toBeInstanceOf(MemoryStorage);
      old.close();
    } finally {
      vi.useRealTimers();
    }
  });

  it('steps aside when a newer version of the app upgrades the database', async () => {
    const storage = await openSyncStorage();
    await storage.setMeta('x', 1);

    const upgraded = openDB(DB_NAME, 2);
    const blocked = new Promise((resolve) => setTimeout(() => resolve('blocked'), 1_000));

    await expect(Promise.race([upgraded.then(() => 'upgraded'), blocked])).resolves.toBe(
      'upgraded',
    );
    (await upgraded).close();
  });
});

describe('queueing', () => {
  it('refuses an action when nobody is signed in, and says so', async () => {
    mockApi({ 'POST /api/auth/logout': null });
    const { engine, session, storage } = await startEngine();
    await settle(engine);
    await session.logout();

    await expect(engine.enqueue(LIST_ID, check())).resolves.toBe(false);

    expect(engine.toasts.get().map((toast) => toast.text(i18n.t, 'en'))).toEqual([
      "Your change could not be saved because you're not signed in any more.",
    ]);
    expect(await storage.readOps(TEST_USER.id)).toEqual([]);
  });
});

describe('several tabs', () => {
  it('another tab’s flush leaves nothing stale in this one', async () => {
    // Without BroadcastChannel (older browsers): the flush itself must set things right.
    vi.stubGlobal('BroadcastChannel', undefined);
    // Web Locks: one tab sends at a time, the other waits for the lock.
    let tail: Promise<unknown> = Promise.resolve();
    const locks = {
      request: (_name: string, callback: () => Promise<unknown>) => {
        const run = tail.then(callback);
        tail = run.catch(() => undefined);
        return run;
      },
    };
    Object.defineProperty(navigator, 'locks', { value: locks, configurable: true });
    try {
      const fetchMock = mockApi({
        [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(shoppingList()),
      });
      goOffline();
      const first = await startEngine();
      await settle(first.engine);
      await first.engine.enqueue(LIST_ID, check());
      const second = await startEngine();
      await vi.waitFor(() => expect(second.engine.outbox.get()).toHaveLength(1));

      // Both tabs try; one sends, the other finds nothing left under the lock.
      goOnline();
      await settle(first.engine);
      await settle(second.engine);

      expect(requestsTo(fetchMock, `POST /api/lists/${LIST_ID}/ops`)).toHaveLength(1);
      for (const tab of [first, second]) {
        expect(tab.engine.outbox.get()).toEqual([]);
        expect(tab.engine.status.get().pending).toBe(0);
      }
    } finally {
      Reflect.deleteProperty(navigator, 'locks');
    }
  });

  it('tells the other tabs when the outbox changed', async () => {
    mockApi();
    goOffline();
    const first = await startEngine();
    const second = await startEngine();
    await settle(first.engine);
    await settle(second.engine);

    await first.engine.enqueue(LIST_ID, check());

    await vi.waitFor(() => expect(second.engine.outbox.get()).toHaveLength(1));
  });
});

describe('reachability', () => {
  it('sends what waits as soon as the server answers again, without an online event', async () => {
    const fetchMock = mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(shoppingList()) });
    const { engine, storage } = await startEngine();
    await settle(engine);
    fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')));
    await engine.enqueue(LIST_ID, check());
    await settle(engine);
    expect(engine.status.get().reachable).toBe(false);

    // Tailscale is back (iOS fires no `online`): some other request gets an answer.
    const again = mockApi({ [`POST /api/lists/${LIST_ID}/ops`]: opsAnswer(shoppingList()) });
    await api.GET('/api/version');

    await vi.waitFor(async () => expect(await storage.readOps(TEST_USER.id)).toEqual([]));
    expect(requestsTo(again, `POST /api/lists/${LIST_ID}/ops`)).toHaveLength(1);
  });
});

describe('persistent storage', () => {
  it('is asked for once per user on this device', async () => {
    const persist = vi.fn(() => Promise.resolve(true));
    Object.defineProperty(navigator, 'storage', { value: { persist }, configurable: true });
    try {
      mockApi();

      const first = await startEngine();
      await settle(first.engine);
      first.stop();
      const again = await startEngine();
      await settle(again.engine);
      expect(persist).toHaveBeenCalledOnce();

      await startEngine({ user: BEN_USER });
      await vi.waitFor(() => expect(persist).toHaveBeenCalledTimes(2));
    } finally {
      Reflect.deleteProperty(navigator, 'storage');
    }
  });
});
