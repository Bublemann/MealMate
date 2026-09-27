import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  BEN,
  CARL,
  errorResponse,
  mockApi,
  requestsTo,
  slowFilterSaves,
  TEST_USER,
} from '@/test/api';
import { emptyList, LIST_ID, LIST_ROUTES } from '@/test/lists';
import { ME } from '@/test/meals';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const IN_COUPLE = { partner: BEN, since: '2026-09-01T10:00:00Z', outgoing: null, incoming: [] };

function renderLists(routes: Record<string, unknown> = {}, user = TEST_USER) {
  const fetchMock = mockApi({ ...LIST_ROUTES, 'GET /api/couple': IN_COUPLE, ...routes });
  return { fetchMock, ...renderApp('/lists', { user }) };
}

function othersRequests(fetchMock: ReturnType<typeof mockApi>) {
  return requestsTo(fetchMock, 'GET /api/lists').filter(
    (request) => new URL(request.url).searchParams.get('scope') === 'others',
  );
}

describe('ListsScreen', () => {
  it('shows my drafts with name, date, counts and who they are shared with (UI-02)', async () => {
    renderLists();

    const drafts = await screen.findByTestId(testIds.listDrafts);
    const cards = within(drafts).getAllByTestId(testIds.listCard);
    // The partner's name comes with the couple.
    await waitFor(() => expect(cards[0]).toHaveTextContent('Shared with Ben'));
    expect(cards.map((card) => card.textContent)).toEqual([
      'Wochenende (26/09/2026)3 meals · 5 items · Shared with Ben',
      'Shopping list (20/09/2026)1 meal · 1 item · by Ben',
    ]);
    expect(cards[0]).toHaveAttribute('href', `/lists/${LIST_ID}`);
    expect(screen.getByRole('heading', { level: 2, name: 'My lists' })).toBeVisible();
  });

  it('shows others’ lists read-only below, with their own user chips but none for me', async () => {
    renderLists();

    const others = await screen.findByTestId(testIds.othersLists);
    expect(within(others).getByRole('heading', { level: 2 })).toHaveTextContent("Others' lists");
    const cards = await within(others).findAllByTestId(testIds.listCard);
    expect(cards.map((card) => card.textContent)).toEqual([
      'Grillabend (26/09/2026)2 meals · 7 items · by Carl',
    ]);
    const chips = await within(others).findByTestId(testIds.listUserChips);
    expect(chips).toHaveAccessibleName('Show lists of');
    expect(
      within(chips)
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['Ben', 'Carl']);
  });

  it('asks the server for the users whose lists I can see', async () => {
    const { fetchMock } = renderLists();

    await screen.findByTestId(testIds.listUserChips);
    const [request] = requestsTo(fetchMock, 'GET /api/users/visible');
    expect(new URL(request?.url ?? '').searchParams.get('for')).toBe('lists');
  });

  it('switches a chip off at once, saves filter_hidden.lists and loads the lists again', async () => {
    const start = { ...TEST_USER, filter_hidden: { meals: ['someone'], lists: [] } };
    const saved = { ...TEST_USER, filter_hidden: { meals: ['someone'], lists: [CARL.id] } };
    const { fetchMock, user } = renderLists({ 'PATCH /api/me': saved }, start);
    const chips = await screen.findByTestId(testIds.listUserChips);
    await screen.findByText('Grillabend (26/09/2026)', { exact: false });

    await user.click(within(chips).getByRole('button', { name: 'Carl' }));

    expect(within(chips).getByRole('button', { name: 'Carl' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    expect(screen.queryByText(/Grillabend/)).not.toBeInTheDocument();
    expect(screen.getByText('No lists from the people selected above.')).toBeVisible();
    await waitFor(() => expect(requestsTo(fetchMock, 'PATCH /api/me')).toHaveLength(1));
    await expect(requestsTo(fetchMock, 'PATCH /api/me')[0]?.json()).resolves.toEqual({
      filter_hidden: { meals: ['someone'], lists: [CARL.id] },
    });
    await waitFor(() => expect(othersRequests(fetchMock)).toHaveLength(2));
  });

  it('keeps quick toggles while earlier ones are still being saved', async () => {
    const saves = slowFilterSaves();
    const { fetchMock, user } = renderLists({ 'PATCH /api/me': saves.route });
    const chips = await screen.findByTestId(testIds.listUserChips);
    const chip = (name: string) => within(chips).getByRole('button', { name });

    await user.click(chip('Ben'));
    await user.click(chip('Carl'));
    // The first save answers while the second waits: it doesn't know about Carl yet.
    await saves.answer(1);
    await user.click(chip('Ben'));
    await saves.answer(2);
    await saves.answer(3);

    await waitFor(() => expect(requestsTo(fetchMock, 'PATCH /api/me')).toHaveLength(3));
    await expect(requestsTo(fetchMock, 'PATCH /api/me')[2]?.json()).resolves.toEqual({
      filter_hidden: { meals: [], lists: [CARL.id] },
    });
    expect(chip('Ben')).toHaveAttribute('aria-pressed', 'true');
    expect(chip('Carl')).toHaveAttribute('aria-pressed', 'false');
  });

  it('loads the saved chips again when saving fails', async () => {
    const { fetchMock, user } = renderLists({
      'PATCH /api/me': errorResponse(503, 'common.service_unavailable'),
      'GET /api/me': { ...TEST_USER, filter_hidden: { meals: [], lists: [BEN.id] } },
    });
    const chips = await screen.findByTestId(testIds.listUserChips);

    await user.click(within(chips).getByRole('button', { name: 'Carl' }));

    expect(
      await screen.findByText('MealMate is unavailable right now. Please try again later.'),
    ).toBeVisible();
    await waitFor(() =>
      expect(within(chips).getByRole('button', { name: 'Ben' })).toHaveAttribute(
        'aria-pressed',
        'false',
      ),
    );
    expect(within(chips).getByRole('button', { name: 'Carl' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await waitFor(() => expect(othersRequests(fetchMock)).toHaveLength(2));
  });

  it('says so when nobody else shares a list, without chips when nobody else is visible', async () => {
    renderLists({ 'GET /api/lists?scope=others': [], 'GET /api/users/visible': [ME] });

    expect(await screen.findByText('Nobody else shares a list right now.')).toBeVisible();
    expect(screen.queryByTestId(testIds.listUserChips)).not.toBeInTheDocument();
  });

  it('creates a draft with "+ New list" and opens it with the meal picker (LIST-01)', async () => {
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

  it('shows one sentence and "New list" when I have no lists yet (UI-03)', async () => {
    const created = emptyList();
    const { user, router } = renderLists({
      'GET /api/lists?scope=mine': [],
      'POST /api/lists': Response.json(created, { status: 201 }),
      'GET /api/lists/list-new': created,
      'GET /api/meals': [],
    });

    expect(await screen.findByRole('heading', { name: 'No shopping lists yet' })).toBeVisible();
    expect(screen.queryByTestId(testIds.listDrafts)).not.toBeInTheDocument();
    // Others' lists are still offered.
    expect(await screen.findByText(/Grillabend/)).toBeVisible();
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

  it('does not say "shared" without a partner', async () => {
    renderLists({ 'GET /api/couple': { ...IN_COUPLE, partner: null, since: null } });

    const drafts = await screen.findByTestId(testIds.listDrafts);
    await waitFor(() =>
      expect(within(drafts).getAllByTestId(testIds.listCard)[0]).toHaveTextContent(
        /^Wochenende \(26\/09\/2026\)3 meals · 5 items$/,
      ),
    );
  });
});
