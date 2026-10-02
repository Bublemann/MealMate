import 'fake-indexeddb/auto';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { IDBFactory } from 'fake-indexeddb';
import { openDB } from 'idb';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { components } from '@/api/generated/schema';
import { errorResponse, heldRoute, mockApi, requestsTo, TEST_USER } from '@/test/api';
import { CATEGORIES } from '@/test/ingredients';
import { FEED_LISTS, feedPage, LIST_ID, LIST_ROUTES, listDetail, shoppingList } from '@/test/lists';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import { DB_NAME, DB_VERSION, openSyncStorage, userMetaKey } from './storage';
import { WAITING_TOO_LONG_MS } from './status';

type Schemas = components['schemas'];

const NEVER = () => new Promise<never>(() => undefined);
const FAIL = () => Promise.reject(new TypeError('Failed to fetch'));

/** The local copy as a previous visit left it: the list, the categories, a complete sync. */
async function storeCopy(list: Schemas['ListDetail'], { synced = true } = {}) {
  const storage = await openSyncStorage();
  await storage.putList({ id: list.id, userId: TEST_USER.id, detail: list, storedAt: 1_000 });
  await storage.setMeta(userMetaKey('categories', TEST_USER.id), {
    categories: CATEGORIES,
    storedAt: 1_000,
  });
  if (synced) await storage.setMeta(userMetaKey('lastSync', TEST_USER.id), 1_000);
  return storage;
}

/** Every request of the list screens goes nowhere (lie-fi) or fails (no signal). */
function serverGone(answer: () => Promise<never>) {
  const fetchMock = mockApi({ ...LIST_ROUTES });
  fetchMock.mockImplementation(answer);
  return fetchMock;
}

function goOffline() {
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
  act(() => {
    window.dispatchEvent(new Event('offline'));
  });
}

beforeEach(() => {
  globalThis.indexedDB = new IDBFactory();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  Reflect.deleteProperty(navigator, 'share');
});

describe('lists from the local copy (SYNC-09)', () => {
  it('shows a stored list at once while the server doesn’t answer (lie-fi)', async () => {
    await storeCopy(shoppingList());
    serverGone(NEVER);

    renderApp(`/lists/${LIST_ID}`);

    expect(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' })).toBeVisible();
    expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
  });

  it('keeps the stored list when the server can’t be reached, and says so', async () => {
    await storeCopy(shoppingList());
    serverGone(FAIL);

    renderApp(`/lists/${LIST_ID}`);

    const status = await screen.findByTestId(testIds.syncStatus);
    await waitFor(() =>
      expect(status).toHaveTextContent("Can't reach MealMate – no signal or Tailscale off?"),
    );
    expect(screen.getByRole('checkbox', { name: 'Check off Zwiebeln' })).toBeVisible();
    expect(screen.getByTestId(testIds.offlineBanner)).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('checks off from the copy offline and keeps the change over a restart', async () => {
    await storeCopy(shoppingList());
    serverGone(FAIL);
    const first = renderApp(`/lists/${LIST_ID}`);
    goOffline();

    fireEvent.click(await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' }));
    await waitFor(() =>
      expect(screen.getByTestId(testIds.syncStatus)).toHaveTextContent(
        'Offline – 1 change waiting',
      ),
    );
    first.unmount();

    // The app is opened again, still without a connection.
    renderApp(`/lists/${LIST_ID}`);
    const box = await screen.findByRole('checkbox', { name: 'Uncheck Zwiebeln' });
    expect(within(box.closest('li')!).getByTestId(testIds.linePending)).toHaveTextContent(
      'not sent yet',
    );
  });

  it('says a list that isn’t stored needs a connection', async () => {
    await storeCopy(shoppingList({ id: 'another-list' }));
    serverGone(FAIL);

    renderApp(`/lists/${LIST_ID}`);

    expect(await screen.findByTestId(testIds.offlineNotice)).toHaveTextContent(
      "You're offline. This page needs a connection.",
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the copy on the Lists tab, newest created first, until the feed answers', async () => {
    const storage = await storeCopy(
      listDetail({ name: 'Vorrat', created_at: '2026-09-20T10:00:00Z' }),
    );
    for (const detail of [
      listDetail({ id: 'list-two', name: 'Grillen', updated_at: '2026-09-20T11:00:00Z' }),
      // A quarter of a second later than "Grillen": the server writes fractions only if any.
      listDetail({ id: 'list-three', name: 'Brunch', created_at: '2026-09-26T10:00:00.25Z' }),
      // Created together with "Brunch": the higher id comes first.
      listDetail({ id: 'list-tie', name: 'Mittag', created_at: '2026-09-26T10:00:00.250Z' }),
    ]) {
      await storage.putList({ id: detail.id, userId: TEST_USER.id, detail, storedAt: 1_000 });
    }
    // Online, but the server is slow: the copy shows first (SYNC-09, UI-02).
    const feed = heldRoute();
    mockApi({ ...LIST_ROUTES, 'GET /api/lists': feed.route, 'GET /api/lists/sync': NEVER });

    renderApp('/lists');

    const copied = within(await screen.findByTestId(testIds.listFeed)).getAllByTestId(
      testIds.listCard,
    );
    expect(copied).toHaveLength(4);
    expect(copied[0]).toHaveTextContent('Mittag (26/09/2026)');
    expect(copied[1]).toHaveTextContent('Brunch (26/09/2026)');
    expect(copied[2]).toHaveTextContent('Grillen (26/09/2026)');
    expect(copied[3]).toHaveTextContent('Vorrat (20/09/2026)');
    await feed.answer(feedPage(FEED_LISTS));
    await waitFor(() =>
      expect(screen.getAllByTestId(testIds.listCard)).toHaveLength(FEED_LISTS.length),
    );
  });

  it('says why the feed did not load while it shows the copy', async () => {
    await storeCopy(listDetail({ name: 'Vorrat' }));
    const feed = heldRoute();
    mockApi({ ...LIST_ROUTES, 'GET /api/lists': feed.route, 'GET /api/lists/sync': NEVER });
    renderApp('/lists');
    expect(await screen.findByTestId(testIds.listCard)).toHaveTextContent('Vorrat (26/09/2026)');

    await feed.answer(errorResponse(503, 'common.service_unavailable'));

    expect(
      await screen.findByText('MealMate is unavailable right now. Please try again later.'),
    ).toBeVisible();
    expect(screen.getByTestId(testIds.listCard)).toHaveTextContent('Vorrat (26/09/2026)');
  });

  it('says why the feed did not load instead of "No lists yet" when the copy is empty', async () => {
    const storage = await openSyncStorage();
    await storage.setMeta(userMetaKey('lastSync', TEST_USER.id), 1_000);
    const feed = heldRoute();
    mockApi({ ...LIST_ROUTES, 'GET /api/lists': feed.route, 'GET /api/lists/sync': NEVER });
    renderApp('/lists');
    expect(await screen.findByText('No lists yet')).toBeVisible();

    await feed.answer(errorResponse(503, 'common.service_unavailable'));

    expect(
      await screen.findByText('MealMate is unavailable right now. Please try again later.'),
    ).toBeVisible();
    expect(screen.queryByText('No lists yet')).not.toBeInTheDocument();
  });

  it('leaves out a list finished here whose *Finish* waits to be sent', async () => {
    const storage = await storeCopy(shoppingList());
    await storage.putList({
      id: 'list-two',
      userId: TEST_USER.id,
      detail: shoppingList({ id: 'list-two', name: 'Grillen' }),
      storedAt: 1_000,
    });
    await storage.addOp({
      userId: TEST_USER.id,
      listId: LIST_ID,
      queuedAt: Date.now(),
      op: {
        type: 'list.finish',
        payload: {},
        op_id: '0190c0de-0000-7000-8000-0000000000d3',
        at: new Date().toISOString(),
      },
    });
    serverGone(NEVER);

    renderApp('/lists');

    expect(await screen.findByText('Grillen (26/09/2026)')).toBeVisible();
    expect(screen.getAllByTestId(testIds.listCard)).toHaveLength(1);
    expect(screen.queryByText('Wochenende (26/09/2026)')).not.toBeInTheDocument();
  });

  it('shows no lists from a copy that was never complete', async () => {
    await storeCopy(listDetail({ name: 'Vorrat' }), { synced: false });
    serverGone(NEVER);

    renderApp('/lists');

    expect(await screen.findByText('Loading…')).toBeVisible();
    expect(screen.queryByText('Vorrat (26/09/2026)')).not.toBeInTheDocument();
  });

  it('exports a stored list offline (EXP-03)', async () => {
    await storeCopy(listDetail());
    serverGone(FAIL);
    const share = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'share', { value: share, configurable: true });

    renderApp(`/lists/${LIST_ID}`);
    await screen.findByTestId(testIds.listLines);
    goOffline();
    const button = screen.getByTestId(testIds.exportList);
    expect(button).toBeEnabled();
    fireEvent.click(button);

    const [[{ text }]] = share.mock.calls as unknown as [[{ text: string }]];
    expect(text.startsWith('Wochenende (26/09/2026)\n\n4× Pfannkuchen')).toBe(true);
  });
});

describe('a draft offline (SYNC-03)', () => {
  it('says changes need a connection and disables every edit control', async () => {
    await storeCopy(listDetail());
    serverGone(FAIL);

    renderApp(`/lists/${LIST_ID}`);
    await screen.findByTestId(testIds.listLines);
    goOffline();

    expect(screen.getByTestId(testIds.offlineBanner)).toHaveTextContent(
      "You're offline. Changes to this list need a connection.",
    );
    expect(screen.getByTestId(testIds.syncStatus)).toHaveTextContent('Offline');
    for (const testId of [
      testIds.startShopping,
      testIds.renameList,
      testIds.deleteList,
      testIds.addMeals,
      testIds.extraItemInput,
    ]) {
      expect(screen.getByTestId(testId)).toBeDisabled();
    }
    const meals = screen.getByTestId(testIds.listMeals);
    expect(within(meals).getByRole('button', { name: 'Remove Pfannkuchen' })).toBeDisabled();
    expect(
      within(meals).getByRole('button', { name: 'Fewer servings of Pfannkuchen' }),
    ).toBeDisabled();
    // Restoring a removed line needs the server too.
    fireEvent.click(screen.getByText('Removed (1)'));
    expect(screen.getByRole('button', { name: 'Restore Eier' })).toBeDisabled();
  });
});

describe('waiting too long (SYNC-07)', () => {
  it('shows a banner once the oldest change has waited for more than an hour', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ['Date', 'setTimeout', 'clearTimeout'] });
    const storage = await storeCopy(shoppingList());
    await storage.addOp({
      userId: TEST_USER.id,
      listId: LIST_ID,
      queuedAt: Date.now() - WAITING_TOO_LONG_MS + 60_000,
      op: {
        type: 'line.check',
        payload: { line_key: 'i:ing-zwiebeln', checked: true },
        op_id: '0190c0de-0000-7000-8000-0000000000d1',
        at: new Date().toISOString(),
      },
    });
    serverGone(FAIL);

    renderApp(`/lists/${LIST_ID}`);
    await screen.findByRole('checkbox', { name: 'Uncheck Zwiebeln' });
    expect(screen.queryByTestId(testIds.waitingBanner)).not.toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(61_000));

    expect(await screen.findByTestId(testIds.waitingBanner)).toHaveTextContent(
      'Some changes have been waiting for more than an hour. Open MealMate with a connection to send them.',
    );
  });
});

describe('logging out with waiting changes (SYNC-05, SYNC-10)', () => {
  async function withWaitingChange() {
    const storage = await storeCopy(shoppingList());
    await storage.addOp({
      userId: TEST_USER.id,
      listId: LIST_ID,
      queuedAt: Date.now(),
      op: {
        type: 'line.check',
        payload: { line_key: 'i:ing-zwiebeln', checked: true },
        op_id: '0190c0de-0000-7000-8000-0000000000d2',
        at: new Date().toISOString(),
      },
    });
    return storage;
  }

  it('asks first; Cancel keeps everything', async () => {
    await withWaitingChange();
    const fetchMock = mockApi({ 'POST /api/auth/logout': null });
    goOffline();
    const { user } = renderApp('/me');

    // Right after the start: the outbox is read before deciding.
    await user.click(await screen.findByTestId(testIds.logoutButton));

    const dialog = await screen.findByRole('alertdialog', {
      name: "1 change hasn't been sent yet",
    });
    expect(dialog).toHaveTextContent('If you log out now, they will be lost.');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(requestsTo(fetchMock, 'POST /api/auth/logout')).toHaveLength(0);
  });

  it('"Log out anyway" deletes the copy and the waiting changes', async () => {
    const storage = await withWaitingChange();
    mockApi({ 'POST /api/auth/logout': null });
    goOffline();
    const { user, router } = renderApp('/me');
    await user.click(await screen.findByTestId(testIds.logoutButton));
    expect(await screen.findByRole('alertdialog')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Log out anyway' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
    await waitFor(async () => expect(await storage.readOps(TEST_USER.id)).toEqual([]));
    expect(await storage.readLists(TEST_USER.id)).toEqual([]);
  });

  it('"Log out everywhere" asks too, also before the outbox has been read', async () => {
    await withWaitingChange();
    // Another tab writes to the outbox for a while: reading it has to wait.
    const other = await openDB(DB_NAME, DB_VERSION);
    const busy = other.transaction('outbox', 'readwrite');
    let held = true;
    const keepBusy = (): void => {
      if (held) void busy.store.count().then(keepBusy);
    };
    keepBusy();
    const fetchMock = mockApi({ 'POST /api/auth/logout-all': null });
    goOffline();
    const { user } = renderApp('/me');

    await user.click(await screen.findByTestId(testIds.logoutAllButton));
    // Nothing is asked before it is known what waits.
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    held = false;
    await busy.done;
    other.close();

    const dialog = await screen.findByRole('alertdialog', {
      name: "1 change hasn't been sent yet",
    });
    expect(dialog).toHaveTextContent('If you log out now, they will be lost.');
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(requestsTo(fetchMock, 'POST /api/auth/logout-all')).toHaveLength(0);
  });

  it('logs out without asking when nothing waits', async () => {
    const fetchMock = mockApi({ 'POST /api/auth/logout': null });
    const { user, router } = renderApp('/me');

    await user.click(await screen.findByTestId(testIds.logoutButton));

    await waitFor(() => expect(router.state.location.pathname).toBe('/login'));
    expect(requestsTo(fetchMock, 'POST /api/auth/logout')).toHaveLength(1);
  });
});

describe('the Lists tab offline (UI-02, SYNC-03)', () => {
  it('disables the "New list" tile: creating a list needs the server', async () => {
    await storeCopy(listDetail({ name: 'Vorrat' }));
    serverGone(FAIL);
    renderApp('/lists');

    const button = await screen.findByTestId(testIds.newList);
    goOffline();

    expect(button).toBeDisabled();
  });

  it('shows only the copy, without read-only and done lists, and says so below the tile', async () => {
    await storeCopy(shoppingList());
    mockApi({ ...LIST_ROUTES, 'GET /api/lists/sync': NEVER });
    renderApp('/lists');
    await waitFor(() =>
      expect(screen.getAllByTestId(testIds.listCard)).toHaveLength(FEED_LISTS.length),
    );

    goOffline();

    await waitFor(() => expect(screen.getAllByTestId(testIds.listCard)).toHaveLength(1));
    expect(screen.getByTestId(testIds.listCard)).toHaveTextContent('Wochenende (26/09/2026)');
    const tile = screen.getByTestId(testIds.newList);
    expect(tile).toBeDisabled();
    const notice = screen.getByTestId(testIds.syncStatus);
    expect(notice).toHaveTextContent('Offline');
    expect(tile.compareDocumentPosition(notice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('says the lists need a connection before the copy was ever complete', async () => {
    mockApi({ ...LIST_ROUTES, 'GET /api/lists/sync': NEVER });
    renderApp('/lists');
    await waitFor(() =>
      expect(screen.getAllByTestId(testIds.listCard)).toHaveLength(FEED_LISTS.length),
    );

    goOffline();

    expect(await screen.findByTestId(testIds.offlineNotice)).toHaveTextContent(
      "You're offline. This page needs a connection.",
    );
    expect(screen.queryByTestId(testIds.listCard)).not.toBeInTheDocument();
  });

  it('disables it on an empty tab too', async () => {
    mockApi();
    renderApp('/lists');
    await screen.findByText('No lists yet');
    const button = screen.getByTestId(testIds.newList);
    expect(button).toBeEnabled();

    goOffline();

    expect(button).toBeDisabled();
  });
});

describe('without local storage', () => {
  it('says that waiting changes only last while the app is open', async () => {
    vi.stubGlobal('indexedDB', undefined);
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    mockApi({ ...LIST_ROUTES, [`GET /api/lists/${LIST_ID}`]: shoppingList() });
    renderApp(`/lists/${LIST_ID}`);
    const box = await screen.findByRole('checkbox', { name: 'Check off Zwiebeln' });
    expect(screen.queryByTestId(testIds.noStorageBanner)).not.toBeInTheDocument();
    goOffline();

    fireEvent.click(box);

    expect(await screen.findByTestId(testIds.noStorageBanner)).toHaveTextContent(
      "MealMate can't store anything on this device right now: changes made without a connection are lost when the app is closed.",
    );
  });
});

describe('other screens offline (SYNC-09)', () => {
  it('say they need a connection instead of showing an error', async () => {
    serverGone(FAIL);
    renderApp('/meals');

    expect(await screen.findByTestId(testIds.offlineNotice)).toHaveTextContent(
      "You're offline. This page needs a connection.",
    );
  });
});
