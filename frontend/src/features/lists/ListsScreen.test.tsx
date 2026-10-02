import { act, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  BEN,
  CARL,
  errorResponse,
  heldRoute,
  mockApi,
  requestsTo,
  slowFilterSaves,
  TEST_USER,
} from '@/test/api';
import { emptyList, FEED_LISTS, feedPage, LIST_ID, LIST_ROUTES, listSummary } from '@/test/lists';
import { ME } from '@/test/meals';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const IN_COUPLE = { partner: BEN, since: '2026-09-01T10:00:00Z', outgoing: null, incoming: [] };

type SavedFilters = typeof TEST_USER.filter_hidden;

/** The server's feed: the lists of every kind, as far as the saved filters show them (UI-02). */
function filteredFeed(saved: () => SavedFilters) {
  return () =>
    feedPage(
      FEED_LISTS.filter(
        (list) =>
          !saved().lists.includes(list.owner.id) && !saved().list_states.includes(list.status),
      ),
    );
}

function renderLists(routes: Record<string, unknown> = {}, me = TEST_USER) {
  let saved = me.filter_hidden;
  const fetchMock = mockApi({
    ...LIST_ROUTES,
    'GET /api/couple': IN_COUPLE,
    'GET /api/lists': filteredFeed(() => saved),
    // Saves the filters, as the server does.
    'PATCH /api/me': async (request: Request) => {
      const body = (await request.json()) as Pick<typeof TEST_USER, 'filter_hidden'>;
      saved = body.filter_hidden;
      return { ...me, filter_hidden: saved };
    },
    ...routes,
  });
  return { fetchMock, ...renderApp('/lists', { user: me }) };
}

/** I am Anna, with saved filters that hide these users' lists and the lists in these states. */
function hiding(lists: string[], listStates: SavedFilters['list_states'] = []) {
  return { ...TEST_USER, filter_hidden: { meals: [], lists, list_states: listStates } };
}

/** The ids of the lists shown, also while the filter panel hides them from screen readers. */
function shownIds() {
  return screen
    .queryAllByTestId(testIds.listCard)
    .map((row) => row.getAttribute('href')?.replace('/lists/', ''));
}

const ALL_IDS = FEED_LISTS.map((list) => list.id);

/** The bodies of the profile saves, read from copies so a waitFor can read them again. */
async function savedFilters(fetchMock: ReturnType<typeof mockApi>) {
  return Promise.all(
    requestsTo(fetchMock, 'PATCH /api/me').map((request) => request.clone().json()),
  );
}

type User = ReturnType<typeof renderApp>['user'];

async function openPanel(user: User) {
  await user.click(screen.getByTestId(testIds.filterButton));
  return screen.findByRole('dialog', { name: 'Filters' });
}

function group(panel: HTMLElement, name: string) {
  return within(panel).getByRole('group', { name });
}

/** The checkboxes' names: the text of the label each one sits in. */
function checkboxNames(element: HTMLElement) {
  return within(element)
    .getAllByRole('checkbox')
    .map((box) => (box as HTMLInputElement).labels?.[0]?.textContent);
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
    // Nor is there a local copy yet, which would stand in for the feed (SYNC-09).
    renderLists({ 'GET /api/lists': feed.route, 'GET /api/lists/sync': heldRoute().route });

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

  it('marks my shared list at once and names the partner once the couple is known', async () => {
    const couple = heldRoute();
    renderLists({
      'GET /api/couple': couple.route,
      'GET /api/lists': feedPage([listSummary({ shared_with_partner: true })]),
    });

    const [row] = within(await screen.findByTestId(testIds.listFeed)).getAllByTestId(
      testIds.listCard,
    );
    expect(rowOf(row!)).toEqual({
      owner: 'Anna',
      text: 'Wochenende (26/09/2026)3 meals · 5 items',
      icons: ['Shared'],
    });
    await couple.answer(IN_COUPLE);
    await waitFor(() =>
      expect(rowOf(row!).text).toBe('Wochenende (26/09/2026)3 meals · 5 items · Shared with Ben'),
    );
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

  it('offers the user filter and the state filter in the panel, everything ticked (UI-02)', async () => {
    const { user } = renderLists();
    await screen.findByTestId(testIds.listFeed);
    const button = screen.getByTestId(testIds.filterButton);
    expect(button).toHaveAccessibleName('Filters');

    const panel = await openPanel(user);

    expect(panel).toBe(screen.getByTestId(testIds.filterPanel));
    expect(within(panel).getAllByTestId(testIds.filterGroup)).toEqual([
      group(panel, 'Lists by'),
      group(panel, 'State'),
    ]);
    // Me first, my partner and everyone else whose lists I can see.
    await waitFor(() =>
      expect(checkboxNames(group(panel, 'Lists by'))).toEqual(['Me', 'Ben', 'Carl']),
    );
    expect(checkboxNames(group(panel, 'State'))).toEqual(['Draft', 'Shopping', 'Done']);
    within(panel)
      .getAllByRole('checkbox')
      .forEach((box) => expect(box).toBeChecked());
  });

  it('unticks a user at once, hiding all of their lists, shared ones too, and saves it (UI-02)', async () => {
    const { fetchMock, user } = renderLists();
    await screen.findByTestId(testIds.listFeed);
    const button = screen.getByTestId(testIds.filterButton);
    const users = group(await openPanel(user), 'Lists by');

    await user.click(await within(users).findByRole('checkbox', { name: 'Ben' }));

    // Ben's lists go right away: the one he shares with me and his read-only one.
    expect(shownIds()).toEqual([
      LIST_ID,
      'list-vorrat',
      'list-carl',
      'list-done',
      'list-carl-done',
    ]);
    expect(button).toHaveAccessibleName('Filters, 1 active');
    await waitFor(async () =>
      expect(await savedFilters(fetchMock)).toEqual([
        { filter_hidden: { meals: [], lists: [BEN.id], list_states: [] } },
      ]),
    );
    // The feed loads again with the saved filter.
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/lists')).toHaveLength(2));
    expect(shownIds()).toEqual([
      LIST_ID,
      'list-vorrat',
      'list-carl',
      'list-done',
      'list-carl-done',
    ]);

    // Unticking myself hides my own lists, the one I share included.
    await user.click(within(users).getByRole('checkbox', { name: 'Me' }));
    expect(shownIds()).toEqual(['list-carl', 'list-carl-done']);
    await waitFor(async () =>
      expect((await savedFilters(fetchMock)).at(-1)).toEqual({
        filter_hidden: { meals: [], lists: [ME.id, BEN.id], list_states: [] },
      }),
    );
  });

  it('unticks a state at once, hiding its lists, and saves it (UI-02)', async () => {
    const { fetchMock, user } = renderLists();
    await screen.findByTestId(testIds.listFeed);
    const button = screen.getByTestId(testIds.filterButton);
    const states = group(await openPanel(user), 'State');

    await user.click(within(states).getByRole('checkbox', { name: 'Done' }));

    expect(shownIds()).toEqual([
      LIST_ID,
      'list-vorrat',
      'list-ben',
      'list-ben-private',
      'list-carl',
    ]);
    expect(button).toHaveAccessibleName('Filters, 1 active');
    await user.click(within(states).getByRole('checkbox', { name: 'Draft' }));
    expect(shownIds()).toEqual([LIST_ID]);
    expect(button).toHaveAccessibleName('Filters, 1 active');
    await waitFor(async () =>
      expect((await savedFilters(fetchMock)).at(-1)).toEqual({
        filter_hidden: { meals: [], lists: [], list_states: ['draft', 'done'] },
      }),
    );
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/lists').length).toBeGreaterThan(1));
    expect(shownIds()).toEqual([LIST_ID]);
  });

  it('keeps a quick change of users while a change of states is still being saved', async () => {
    const saves = slowFilterSaves();
    const { fetchMock, user } = renderLists({ 'PATCH /api/me': saves.route });
    await screen.findByTestId(testIds.listFeed);
    const panel = await openPanel(user);
    await within(group(panel, 'Lists by')).findByRole('checkbox', { name: 'Carl' });

    await user.click(within(group(panel, 'State')).getByRole('checkbox', { name: 'Done' }));
    await user.click(within(group(panel, 'Lists by')).getByRole('checkbox', { name: 'Carl' }));
    await saves.answer(1);
    await saves.answer(2);

    expect((await savedFilters(fetchMock)).at(-1)).toEqual({
      filter_hidden: { meals: [], lists: [CARL.id], list_states: ['done'] },
    });
    expect(within(group(panel, 'State')).getByRole('checkbox', { name: 'Done' })).not.toBeChecked();
    expect(
      within(group(panel, 'Lists by')).getByRole('checkbox', { name: 'Carl' }),
    ).not.toBeChecked();
  });

  it('shows the saved filters ticked and counts both groups (UI-02)', async () => {
    const { user } = renderLists({}, hiding([CARL.id], ['done']));

    await screen.findByTestId(testIds.listFeed);
    expect(shownIds()).toEqual([LIST_ID, 'list-vorrat', 'list-ben', 'list-ben-private']);
    const button = screen.getByTestId(testIds.filterButton);
    await waitFor(() => expect(button).toHaveAccessibleName('Filters, 2 active'));
    const panel = await openPanel(user);
    const ticked = (name: string) =>
      within(group(panel, name))
        .getAllByRole('checkbox')
        .map((box) => (box as HTMLInputElement).checked);
    expect(ticked('Lists by')).toEqual([true, true, false]);
    expect(ticked('State')).toEqual([true, true, false]);
  });

  it('ticks every user and state again with “Reset” (UI-01)', async () => {
    const { fetchMock, user } = renderLists({}, hiding([CARL.id], ['draft', 'done']));
    await screen.findByTestId(testIds.listFeed);
    const button = screen.getByTestId(testIds.filterButton);
    const panel = await openPanel(user);
    await within(group(panel, 'Lists by')).findByRole('checkbox', { name: 'Carl' });
    expect(button).toHaveAccessibleName('Filters, 2 active');

    await user.click(within(panel).getByRole('button', { name: 'Reset' }));

    within(panel)
      .getAllByRole('checkbox')
      .forEach((box) => expect(box).toBeChecked());
    expect(button).toHaveAccessibleName('Filters');
    await waitFor(async () =>
      expect((await savedFilters(fetchMock)).at(-1)).toEqual({
        filter_hidden: { meals: [], lists: [], list_states: [] },
      }),
    );
    await waitFor(() => expect(shownIds()).toEqual(ALL_IDS));
  });

  it('says “No matches”; “Reset filters” resets users and states (UI-03)', async () => {
    const { fetchMock, user } = renderLists({}, hiding([ME.id, BEN.id], ['draft', 'done']));

    expect(await screen.findByText('No matches')).toBeVisible();
    expect(screen.queryByText('No lists yet')).toBeNull();
    const button = screen.getByTestId(testIds.filterButton);
    await waitFor(() => expect(button).toHaveAccessibleName('Filters, 2 active'));

    await user.click(screen.getByRole('button', { name: 'Reset filters' }));

    expect(button).toHaveAccessibleName('Filters');
    await waitFor(() => expect(shownIds()).toEqual(ALL_IDS));
    expect((await savedFilters(fetchMock)).at(-1)).toEqual({
      filter_hidden: { meals: [], lists: [], list_states: [] },
    });
  });

  it('does not call the tab empty while the feed loads again after a reset (UI-03)', async () => {
    const again = heldRoute();
    let loads = 0;
    const { user } = renderLists(
      { 'GET /api/lists': () => (++loads === 1 ? feedPage([]) : again.route()) },
      hiding([], ['draft', 'shopping', 'done']),
    );
    expect(await screen.findByText('No matches')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Reset filters' }));

    // The answer from before says nothing about the lists in every state.
    expect(screen.queryByText('No lists yet')).toBeNull();
    await waitFor(() => expect(loads).toBe(2));
    expect(screen.queryByText('No lists yet')).toBeNull();
    expect(screen.getByTestId(testIds.loadingState)).toBeVisible();
    await again.answer(feedPage(FEED_LISTS));
    await waitFor(() => expect(shownIds()).toEqual(ALL_IDS));
  });

  it('leads an old link to the history to the Lists tab (UI-02)', async () => {
    mockApi(LIST_ROUTES);
    const { router } = renderApp('/lists/history');

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    expect(router.state.location.pathname).toBe('/lists');
  });
});
