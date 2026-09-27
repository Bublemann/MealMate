import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BEN, mockApi } from '@/test/api';
import { LIST_ROUTES, listSummary, MY_LISTS } from '@/test/lists';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

// Finished in the afternoon (UTC), so the day is the same in every time zone a test runs in.
const HISTORY = [
  listSummary({
    id: 'done-1',
    name: 'Grillabend',
    status: 'done',
    finished_at: '2026-09-26T14:00:00Z',
  }),
  listSummary({
    id: 'done-2',
    name: null,
    status: 'done',
    created_at: '2026-09-20T10:00:00Z',
    finished_at: '2026-09-21T15:00:00Z',
    owner: BEN,
    is_owner: false,
    shared_with_partner: true,
    meal_count: 1,
    line_count: 2,
  }),
  listSummary({
    id: 'done-3',
    status: 'done',
    created_at: '2026-09-15T10:00:00Z',
    finished_at: '2026-09-19T12:00:00Z',
  }),
];

describe('Lists home (UI-02)', () => {
  it('shows a list being shopped as a "Continue shopping" card at the top', async () => {
    mockApi({
      ...LIST_ROUTES,
      'GET /api/lists?scope=mine': [
        listSummary({ id: 'shopping-1', status: 'shopping', name: 'Wocheneinkauf' }),
        ...MY_LISTS,
      ],
    });
    renderApp('/lists');

    const card = await screen.findByTestId(testIds.continueShopping);
    expect(card).toHaveTextContent('Continue shoppingWocheneinkauf (26/09/2026)');
    expect(card).toHaveAttribute('href', '/lists/shopping-1');
    // It comes first, and not again among the drafts.
    const screenElement = screen.getByTestId(testIds.screenLists);
    expect(within(screenElement).getAllByRole('link')[0]).toBe(card);
    const drafts = screen.getByTestId(testIds.listDrafts);
    expect(within(drafts).getAllByTestId(testIds.listCard)).toHaveLength(2);
    expect(drafts).not.toHaveTextContent('Wocheneinkauf');
  });

  it('says so when all my lists are being shopped', async () => {
    mockApi({
      ...LIST_ROUTES,
      'GET /api/lists?scope=mine': [listSummary({ status: 'shopping' })],
    });
    renderApp('/lists');

    expect(await screen.findByTestId(testIds.continueShopping)).toBeVisible();
    expect(screen.getByText('No drafts right now.')).toBeVisible();
    expect(screen.getByTestId(testIds.newList)).toBeVisible();
  });

  it('has the entry to the history between my lists and others’ lists', async () => {
    mockApi(LIST_ROUTES);
    const { user, router } = renderApp('/lists');

    const entry = await screen.findByTestId(testIds.historyLink);
    expect(entry).toHaveTextContent('History');
    const others = screen.getByTestId(testIds.othersLists);
    expect(entry.compareDocumentPosition(others) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    await user.click(entry);
    expect(router.state.location.pathname).toBe('/lists/history');
  });
});

describe('HistoryScreen (SHOP-05)', () => {
  it('groups done lists by the week they were finished, newest first', async () => {
    mockApi({ ...LIST_ROUTES, 'GET /api/lists/history': HISTORY });
    renderApp('/lists/history');

    expect(await screen.findByRole('heading', { level: 1, name: 'History' })).toBeVisible();
    const weeks = await screen.findAllByTestId(testIds.historyWeek);
    expect(
      weeks.map((week) => within(week).getByRole('heading', { level: 2 }).textContent),
    ).toEqual(['Week of 21/09', 'Week of 14/09']);
    const cards = within(weeks[0]!).getAllByTestId(testIds.listCard);
    expect(cards.map((card) => card.textContent)).toEqual([
      'Grillabend (26/09/2026)bought on 26/09 · 3 meals · 5 items',
      'Shopping list (20/09/2026)bought on 21/09 · 1 meal · 2 items · by Ben',
    ]);
    expect(cards[0]).toHaveAttribute('href', '/lists/done-1');
    expect(within(weeks[1]!).getByTestId(testIds.listCard)).toHaveTextContent('bought on 19/09');
  });

  it('uses German headings and dates', async () => {
    mockApi({ ...LIST_ROUTES, 'GET /api/lists/history': HISTORY });
    const { authSession } = renderApp('/lists/history');
    authSession.setUser({ ...authSession.getState().user!, language: 'de' });
    const { changeLanguage } = await import('@/i18n');
    await changeLanguage('de');

    expect(
      await screen.findByRole('heading', { level: 2, name: 'Woche vom 21.09.' }),
    ).toBeVisible();
    expect(screen.getByText('gekauft am 26.09. · 3 Gerichte · 5 Artikel')).toBeVisible();
  });

  it('says what the history is for while it is empty', async () => {
    mockApi({ ...LIST_ROUTES, 'GET /api/lists/history': [] });
    const { user, router } = renderApp('/lists/history');

    expect(await screen.findByText('Nothing bought yet')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Go to lists' }));
    expect(router.state.location.pathname).toBe('/lists');
  });
});
