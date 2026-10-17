import { screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import { mockApi, requestsTo, TEST_USER } from '@/test/api';
import { REFERENCE_ROUTES, summary } from '@/test/ingredients';
import { deletedNotice, noticeList, recurringItem, recurringList } from '@/test/recurring';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const GERMAN = { ...TEST_USER, language: 'de' as const };

function renderPage(routes: Record<string, unknown> = {}, { german = false } = {}) {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    ...(german ? { 'GET /api/me': GERMAN } : {}),
    ...routes,
  });
  return { fetchMock, ...renderApp('/me/recurring', german ? { user: GERMAN } : {}) };
}

/** The rows of the set, each as its text, in their order on the page. */
async function rowTexts(): Promise<string[]> {
  const list = await screen.findByTestId(testIds.recurringList);
  return within(list)
    .getAllByTestId(testIds.recurringItem)
    .map((row) => row.textContent ?? '');
}

beforeEach(() => {
  // Today is Sunday, 25 October 2026: a purchase in 2025 shows its year.
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-25T10:00:00'));
});

afterEach(() => {
  vi.useRealTimers();
});

describe('RecurringScreen: the set (LIST-16, MNT-02, I18N-05)', () => {
  it('lists the items in the server order, formatted from its display values', async () => {
    await i18n.changeLanguage('de');
    renderPage(
      {
        'GET /api/recurring-items': recurringList([
          recurringItem({
            id: 'rec-duschgel',
            ingredient: summary('Duschgel', 'other', { brand: 'Duschdas' }),
            interval: { value: 5, unit: 'day', automatic: true },
            last_purchased_on: '2026-10-17',
            days_until_due: -3,
            due: true,
          }),
          recurringItem({
            id: 'rec-zahnpasta',
            ingredient: summary('Zahnpasta', 'other'),
            interval: { value: 2, unit: 'week', automatic: false },
            last_purchased_on: '2025-12-20',
            days_until_due: 0,
            due: true,
          }),
          recurringItem({
            id: 'rec-spuelmittel',
            ingredient: summary('Spülmittel', 'other'),
            interval: { value: 1, unit: 'week', automatic: false },
            last_purchased_on: '2026-10-19',
            days_until_due: 1,
          }),
          recurringItem(),
        ]),
      },
      { german: true },
    );

    expect(await rowTexts()).toEqual([
      'Duschgel (Duschdas)alle ~5 Tage · zuletzt 17.10. · fällig seit 3 Tagen',
      'Zahnpastaalle 2 Wochen · zuletzt 20.12.2025 · fällig heute',
      'Spülmitteljede Woche · zuletzt 19.10. · fällig morgen',
      'Klopapieralle ~4 Wochen · zuletzt 02.10. · fällig in 5 Tagen',
    ]);
  });
});

describe('RecurringScreen: empty (LIST-16)', () => {
  it('shows the hint with examples when there are no items and no notices, and seeds nothing', async () => {
    await i18n.changeLanguage('de');
    const { fetchMock } = renderPage({}, { german: true });

    expect(await screen.findByText(/Klopapier, Zahnpasta, Duschgel, …/)).toBeVisible();
    expect(screen.queryByTestId(testIds.recurringList)).not.toBeInTheDocument();
    const writes = fetchMock.mock.calls.filter(([request]) => request.method !== 'GET');
    expect(writes).toEqual([]);
  });
});

describe('RecurringScreen: notices (D-51)', () => {
  it('shows the unread notices first, named with the brand, and no empty hint', async () => {
    await i18n.changeLanguage('de');
    renderPage(
      {
        'GET /api/me/notices': noticeList([
          deletedNotice('Klopapier', 'Hakle'),
          deletedNotice('Zahnpasta'),
        ]),
      },
      { german: true },
    );

    const page = await screen.findByTestId(testIds.screenRecurring);
    const notices = await within(page).findByTestId(testIds.recurringNotices);
    expect(
      within(notices)
        .getAllByRole('listitem')
        .map((notice) => notice.textContent),
    ).toEqual([
      '„Klopapier (Hakle)“ wurde von einem Admin gelöscht und ist nicht mehr regelmäßig.',
      '„Zahnpasta“ wurde von einem Admin gelöscht und ist nicht mehr regelmäßig.',
    ]);
    // At the top of the page: right after its title.
    const title = within(page).getByRole('heading', { level: 1, name: 'Regelmäßige Artikel' });
    expect(title.nextElementSibling).toBe(notices);
    expect(within(page).queryByText(/Klopapier, Zahnpasta, Duschgel/)).not.toBeInTheDocument();
  });

  it('dismisses one with ✕ for this user, and the row and the gear count drop at once', async () => {
    let notices = [deletedNotice('Klopapier', 'Hakle'), deletedNotice('Zahnpasta')];
    const { fetchMock, user } = renderPage({
      'GET /api/me/notices': () => noticeList(notices),
      'POST /api/me/notices/notice-klopapier/dismiss': () => {
        notices = notices.slice(1);
        return null;
      },
    });
    const gear = screen.getByTestId(testIds.tabMe);
    await waitFor(() => expect(gear).toHaveAccessibleName('Settings, 2 new'));

    await user.click(
      await screen.findByRole('button', { name: 'Dismiss the notice about Klopapier (Hakle)' }),
    );

    await waitFor(() => expect(gear).toHaveAccessibleName('Settings, 1 new'));
    const list = screen.getByTestId(testIds.recurringNotices);
    expect(within(list).getAllByRole('listitem')).toHaveLength(1);
    expect(list).toHaveTextContent('“Zahnpasta” was deleted by an admin');
    expect(requestsTo(fetchMock, 'POST /api/me/notices/notice-klopapier/dismiss')).toHaveLength(1);

    await user.click(screen.getByTestId(testIds.backLink));
    expect(await screen.findByRole('link', { name: 'Recurring items 1 notice' })).toBeVisible();
  });
});

describe('the row "Regelmäßige Artikel" on the Settings tab (UI-07, D-45, D-51)', () => {
  const DUE = recurringItem({ id: 'rec-due', days_until_due: -1, due: true });
  const NOT_DUE = recurringItem({ id: 'rec-later' });

  it.each([
    ['nothing without notices or due items', [], [NOT_DUE], 'Regelmäßige Artikel'],
    [
      'the due items',
      [],
      [DUE, { ...DUE, id: 'rec-due-2' }, NOT_DUE],
      'Regelmäßige Artikel 2 fällig',
    ],
    ['one notice', [deletedNotice('Klopapier')], [], 'Regelmäßige Artikel 1 Hinweis'],
    [
      'notices and due items',
      [deletedNotice('Klopapier'), deletedNotice('Zahnpasta')],
      [DUE],
      'Regelmäßige Artikel 2 Hinweise · 1 fällig',
    ],
  ])('shows %s, and opens the page', async (_, notices, items, name) => {
    await i18n.changeLanguage('de');
    const fetchMock = mockApi({
      'GET /api/me': GERMAN,
      'GET /api/me/notices': noticeList(notices),
      'GET /api/recurring-items': recurringList(items),
    });
    const { user, router } = renderApp('/me', { user: GERMAN });

    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/recurring-items')).toHaveLength(1));
    const row = await screen.findByRole('link', { name });
    await user.click(row);

    expect(router.state.location.pathname).toBe('/me/recurring');
    expect(await screen.findByTestId(testIds.screenRecurring)).toBeVisible();
  });
});
