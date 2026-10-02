import { act, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BEN, errorResponse, heldRoute, mockApi, requestsTo, TEST_USER } from '@/test/api';
import { emptyList, FEED_LISTS, feedPage, LIST_ID, LIST_ROUTES, listSummary } from '@/test/lists';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const IN_COUPLE = { partner: BEN, since: '2026-09-01T10:00:00Z', outgoing: null, incoming: [] };

function renderLists(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({ ...LIST_ROUTES, 'GET /api/couple': IN_COUPLE, ...routes });
  return { fetchMock, ...renderApp('/lists', { user: TEST_USER }) };
}

/** What a row says: whose it is (its marker), its text after the marker, and its icons. */
function rowOf(row: HTMLElement) {
  const [marker, ...icons] = within(row).getAllByRole('img');
  return {
    owner: marker?.getAttribute('aria-label'),
    text: row.textContent?.slice(marker?.textContent?.length ?? 0),
    icons: icons.map((icon) => icon.getAttribute('aria-label')),
  };
}

/** Stands in for the browser's IntersectionObserver: `reveal()` scrolls the observed into view. */
function stubIntersectionObserver() {
  const observers = new Set<{ callback: IntersectionObserverCallback; targets: Element[] }>();
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      private readonly entry: { callback: IntersectionObserverCallback; targets: Element[] };
      constructor(callback: IntersectionObserverCallback) {
        this.entry = { callback, targets: [] };
        observers.add(this.entry);
      }
      observe(target: Element) {
        this.entry.targets.push(target);
      }
      unobserve() {}
      disconnect() {
        observers.delete(this.entry);
      }
    },
  );
  return {
    reveal() {
      act(() => {
        for (const { callback, targets } of [...observers]) {
          const entries = targets.map((target) => ({ target, isIntersecting: true }));
          callback(entries as IntersectionObserverEntry[], {} as IntersectionObserver);
        }
      });
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('ListsScreen', () => {
  it('shows the pinned block at once and only a quiet placeholder below it (UI-03)', async () => {
    const feed = heldRoute();
    renderLists({ 'GET /api/lists': feed.route });

    const tile = await screen.findByTestId(testIds.newList);
    expect(tile).toHaveTextContent('New list');
    expect(tile).toBeEnabled();
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument();
    expect(await screen.findByText('Loading…')).toBeVisible();
    expect(screen.queryByTestId(testIds.listFeed)).not.toBeInTheDocument();

    await feed.answer(feedPage(FEED_LISTS));
    expect(await screen.findByTestId(testIds.listFeed)).toBeVisible();
    expect(screen.getByTestId(testIds.newList)).toBe(tile);
    expect(screen.queryByTestId(testIds.loadingState)).not.toBeInTheDocument();
  });

  it('shows one line below the same pinned block when there are no lists (UI-03)', async () => {
    renderLists({ 'GET /api/lists': feedPage([]) });

    expect(await screen.findByText('No lists yet')).toBeVisible();
    const tile = screen.getByTestId(testIds.newList);
    expect(tile).toHaveTextContent('New list');
    // The first-login tips come below the pinned block and scroll away with the feed.
    const tip = screen.getByTestId(testIds.hintTailscale);
    expect(tile.compareDocumentPosition(tip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByRole('heading', { level: 2 })).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.listFeed)).not.toBeInTheDocument();
  });

  it('shows every kind of list with its owner, icons and texts, newest first (UI-02)', async () => {
    renderLists();

    const feed = await screen.findByTestId(testIds.listFeed);
    const rows = within(feed).getAllByTestId(testIds.listCard);
    // The partner's name comes with the couple.
    await waitFor(() => expect(rows[0]).toHaveTextContent('Shared with Ben'));
    expect(rows.map(rowOf)).toEqual([
      {
        owner: 'Anna',
        text: 'Wochenende (26/09/2026)3 meals · 5 items · Shared with Ben',
        icons: ['Shared', 'Shopping now'],
      },
      { owner: 'Anna', text: 'Vorrat (25/09/2026)1 meal · 2 items', icons: [] },
      {
        owner: 'Ben',
        text: 'Shopping list (24/09/2026)1 meal · 1 item · by Ben, shared with you',
        icons: ['Shared'],
      },
      {
        owner: 'Ben',
        text: 'Party (23/09/2026)4 meals · 12 items · by Ben',
        icons: ['Read-only'],
      },
      {
        owner: 'Carl',
        text: 'Grillabend (22/09/2026)2 meals · 7 items · by Carl',
        icons: ['Read-only'],
      },
      {
        owner: 'Anna',
        text: 'Salatabend (19/09/2026)1 meal · 4 items · bought on 20/09',
        icons: ['Done'],
      },
      {
        owner: 'Carl',
        text: 'Vorrat (12/09/2026)1 meal · 3 items · by Carl · bought on 13/09',
        icons: ['Read-only', 'Done'],
      },
    ]);
    expect(within(rows[0]!).getByRole('img', { name: 'Anna' })).toHaveTextContent('A');
    expect(rows[0]).toHaveAttribute('href', `/lists/${LIST_ID}`);
    expect(rows[6]).toHaveAttribute('href', '/lists/list-carl-done');
  });

  it('does not say "shared" without a partner', async () => {
    renderLists({
      'GET /api/couple': { ...IN_COUPLE, partner: null, since: null },
      'GET /api/lists': feedPage([listSummary({ shared_with_partner: true })]),
    });

    const [row] = within(await screen.findByTestId(testIds.listFeed)).getAllByTestId(
      testIds.listCard,
    );
    expect(rowOf(row!)).toEqual({
      owner: 'Anna',
      text: 'Wochenende (26/09/2026)3 meals · 5 items',
      icons: [],
    });
  });

  it('loads the next 30 lists when the end of the feed comes into view (UI-02)', async () => {
    const observer = stubIntersectionObserver();
    const first = Array.from({ length: 30 }, (_, index) =>
      listSummary({ id: `list-${index}`, name: `Liste ${index + 1}` }),
    );
    const { fetchMock } = renderLists({
      'GET /api/lists': feedPage(first, 'cursor-2'),
      'GET /api/lists?cursor=cursor-2': feedPage([listSummary({ id: 'list-30', name: 'Alt' })]),
    });
    const feed = await screen.findByTestId(testIds.listFeed);
    expect(within(feed).getAllByTestId(testIds.listCard)).toHaveLength(30);
    expect(screen.queryByText('Alt (26/09/2026)')).not.toBeInTheDocument();

    observer.reveal();

    expect(await within(feed).findByText('Alt (26/09/2026)')).toBeVisible();
    expect(within(feed).getAllByTestId(testIds.listCard)).toHaveLength(31);
    const cursors = requestsTo(fetchMock, 'GET /api/lists').map((request) =>
      new URL(request.url).searchParams.get('cursor'),
    );
    expect(cursors).toEqual([null, 'cursor-2']);
    // The last page has been loaded: nothing more is asked for.
    observer.reveal();
    expect(requestsTo(fetchMock, 'GET /api/lists')).toHaveLength(2);
  });

  it('says why the next lists did not load, without asking again and again', async () => {
    const observer = stubIntersectionObserver();
    const { fetchMock } = renderLists({
      'GET /api/lists': feedPage(FEED_LISTS, 'cursor-2'),
      'GET /api/lists?cursor=cursor-2': errorResponse(503, 'common.service_unavailable'),
    });
    await screen.findByTestId(testIds.listFeed);

    observer.reveal();

    expect(
      await screen.findByText('MealMate is unavailable right now. Please try again later.'),
    ).toBeVisible();
    const pages = () =>
      requestsTo(fetchMock, 'GET /api/lists').filter((request) =>
        new URL(request.url).searchParams.has('cursor'),
      );
    const asked = pages().length;
    observer.reveal();
    expect(pages()).toHaveLength(asked);
    expect(screen.getAllByTestId(testIds.listCard)).toHaveLength(FEED_LISTS.length);
  });

  it('creates a draft with the "New list" tile and opens it with the meal picker (LIST-01)', async () => {
    const created = emptyList();
    const { fetchMock, user, router } = renderLists({
      'POST /api/lists': Response.json(created, { status: 201 }),
      'GET /api/lists/list-new': created,
      'GET /api/meals': [],
    });

    await user.click(await screen.findByTestId(testIds.newList));

    await waitFor(() => expect(router.state.location.pathname).toBe('/lists/list-new'));
    expect(await screen.findByRole('dialog', { name: 'Add meals' })).toBeVisible();
    await expect(requestsTo(fetchMock, 'POST /api/lists')[0]?.json()).resolves.toEqual({});
    // Behind the (modal) picker.
    expect(screen.getByRole('heading', { level: 1, hidden: true })).toHaveTextContent(
      'Shopping list (26/09/2026)',
    );
  });

  it('creates a list from an empty tab too', async () => {
    const created = emptyList();
    const { user, router } = renderLists({
      'GET /api/lists': feedPage([]),
      'POST /api/lists': Response.json(created, { status: 201 }),
      'GET /api/lists/list-new': created,
      'GET /api/meals': [],
    });
    await screen.findByText('No lists yet');

    await user.click(screen.getByRole('button', { name: 'New list' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/lists/list-new'));
  });

  it('shows why a new list could not be created', async () => {
    const { user } = renderLists({
      'POST /api/lists': errorResponse(503, 'common.service_unavailable'),
    });

    await user.click(await screen.findByTestId(testIds.newList));

    expect(
      await screen.findByText('MealMate is unavailable right now. Please try again later.'),
    ).toBeVisible();
  });

  it('leads an old link to the history to the Lists tab (UI-02)', async () => {
    mockApi(LIST_ROUTES);
    const { router } = renderApp('/lists/history');

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    expect(router.state.location.pathname).toBe('/lists');
  });
});
