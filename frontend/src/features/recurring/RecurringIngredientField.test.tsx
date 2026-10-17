import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { goOffline, heldRoute, mockApi, requestsTo } from '@/test/api';
import { ingredient, REFERENCE_ROUTES, summary } from '@/test/ingredients';
import { recurringItem, recurringList, stubResizeObserver } from '@/test/recurring';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const KLOPAPIER = summary('Klopapier', 'other', { base_unit: 'piece' });
const KLOPAPIER_HALTER = summary('Klopapierhalter', 'other', { base_unit: 'piece' });
const ZAHNPASTA = summary('Zahnpasta', 'other', { base_unit: 'piece' });
const ZAHNPASTA_DM = summary('Zahnpasta', 'other', { id: 'ing-zahnpasta-dm', brand: 'dm' });

/** The ingredient search: what each typed text finds. */
function search(results: Record<string, unknown[]>) {
  return (request: Request) => results[new URL(request.url).searchParams.get('q') ?? ''] ?? [];
}

function renderPage(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    'GET /api/ingredients': search({
      klo: [KLOPAPIER, KLOPAPIER_HALTER],
      klopapier: [KLOPAPIER, KLOPAPIER_HALTER],
      zahnpasta: [ZAHNPASTA, ZAHNPASTA_DM],
    }),
    'GET /api/ingredients/similar': [],
    'POST /api/recurring-items': Response.json(recurringItem(), { status: 201 }),
    ...routes,
  });
  return { fetchMock, ...renderApp('/me/recurring') };
}

function field() {
  return screen.getByTestId(testIds.recurringInput);
}

async function postBodies(fetchMock: ReturnType<typeof mockApi>, route: string) {
  return Promise.all(requestsTo(fetchMock, route).map((request) => request.json()));
}

beforeEach(() => {
  stubResizeObserver();
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date('2026-10-25T10:00:00'));
});

afterEach(() => {
  vi.useRealTimers();
});

describe('the ingredient field on "Regelmäßige Artikel" (LIST-16, D-41, ING-04)', () => {
  it('offers “as a new ingredient” right under the field, then the ingredients, no free text', async () => {
    const { user } = renderPage();

    await user.type(await screen.findByRole('searchbox', { name: 'Search ingredient' }), 'klo');

    const results = await screen.findByRole('list', { name: 'Matching ingredients' });
    await waitFor(() =>
      expect(
        within(results)
          .getAllByRole('button')
          .map((option) => option.textContent),
      ).toEqual([
        '“klo” as a new ingredient',
        'KlopapierOther · pcs',
        'KlopapierhalterOther · pcs',
      ]),
    );
    expect(screen.getByTestId(testIds.recurringNewIngredient)).toBe(
      within(results).getAllByRole('button')[0],
    );
    expect(screen.getByRole('button', { name: 'Add “klo”' })).toBeEnabled();
  });

  it('adds a picked ingredient with four weeks, adapting, bought today', async () => {
    let items: ReturnType<typeof recurringItem>[] = [];
    const { fetchMock, user } = renderPage({
      'GET /api/recurring-items': () => recurringList(items),
      'POST /api/recurring-items': () => {
        items = [recurringItem()];
        return Response.json(items[0], { status: 201 });
      },
    });

    await user.type(await screen.findByRole('searchbox', { name: 'Search ingredient' }), 'klo');
    await user.click(await screen.findByRole('button', { name: /^Klopapier ?Other/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Klopapier' });
    expect(within(dialog).getByRole('spinbutton', { name: 'Every weeks' })).toHaveValue(4);
    expect(within(dialog).getByRole('switch', { name: 'Adjust automatically' })).toBeChecked();
    expect(within(dialog).getByLabelText('Last bought')).toHaveValue('2026-10-25');
    expect(within(dialog).queryByTestId(testIds.recurringRemove)).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    // Untouched, the date is left to the server's today.
    expect(await postBodies(fetchMock, 'POST /api/recurring-items')).toEqual([
      { ingredient_id: KLOPAPIER.id, interval_weeks: 4 },
    ]);
    expect(field()).toHaveValue('');
    expect(await screen.findByTestId(testIds.recurringItem)).toHaveTextContent(/^Klopapier/);
  });

  it('sends the weeks and the date as typed, and switches adapting off with a second request', async () => {
    const created = recurringItem();
    const { fetchMock, user } = renderPage({
      [`PATCH /api/recurring-items/${created.id}`]: created,
    });

    await user.type(await screen.findByRole('searchbox', { name: 'Search ingredient' }), 'klo');
    await user.click(await screen.findByRole('button', { name: /^Klopapier ?Other/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Klopapier' });
    const weeks = within(dialog).getByRole('spinbutton', { name: 'Every weeks' });
    await user.clear(weeks);
    await user.type(weeks, '6');
    // A new item's weeks are a first guess: it keeps adapting…
    const automatic = within(dialog).getByRole('switch', { name: 'Adjust automatically' });
    expect(automatic).toBeChecked();
    // …unless switched off.
    await user.click(automatic);
    fireEvent.change(within(dialog).getByLabelText('Last bought'), {
      target: { value: '2026-10-01' },
    });
    await user.click(within(dialog).getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(await postBodies(fetchMock, 'POST /api/recurring-items')).toEqual([
      { ingredient_id: KLOPAPIER.id, interval_weeks: 6, last_purchased_on: '2026-10-01' },
    ]);
    expect(await postBodies(fetchMock, `PATCH /api/recurring-items/${created.id}`)).toEqual([
      { automatic: false },
    ]);
  });

  it('opens the pop-up with ＋ or Enter when one ingredient has exactly that name', async () => {
    const { user } = renderPage();

    await user.type(
      await screen.findByRole('searchbox', { name: 'Search ingredient' }),
      'klopapier',
    );
    await user.click(screen.getByRole('button', { name: 'Add “klopapier”' }));
    expect(await screen.findByRole('dialog', { name: 'Klopapier' })).toBeVisible();
    await user.keyboard('{Escape}');

    await user.click(field());
    await user.keyboard('{Enter}');
    expect(await screen.findByRole('dialog', { name: 'Klopapier' })).toBeVisible();
  });

  it('waits with ＋ for the results of the typed text', async () => {
    const search = heldRoute();
    const { user } = renderPage({ 'GET /api/ingredients': search.route });

    await user.type(
      await screen.findByRole('searchbox', { name: 'Search ingredient' }),
      'klopapier',
    );
    await user.click(screen.getByRole('button', { name: 'Add “klopapier”' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await search.answer([KLOPAPIER, KLOPAPIER_HALTER]);
    expect(await screen.findByRole('dialog', { name: 'Klopapier' })).toBeVisible();
  });

  it('leaves the choice to the results when several brands have that name', async () => {
    const { user } = renderPage();

    await user.type(
      await screen.findByRole('searchbox', { name: 'Search ingredient' }),
      'zahnpasta',
    );
    await screen.findByRole('button', { name: /^Zahnpasta \(dm\)/ });
    await user.click(screen.getByRole('button', { name: 'Add “zahnpasta”' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('list', { name: 'Matching ingredients' })).toBeVisible();
  });

  it('opens an ingredient that is recurring already for editing', async () => {
    const { user } = renderPage({
      'GET /api/recurring-items': recurringList([recurringItem({ interval_weeks: 3 })]),
    });

    await user.type(await screen.findByRole('searchbox', { name: 'Search ingredient' }), 'klo');
    const results = await screen.findByRole('list', { name: 'Matching ingredients' });
    await user.click(await within(results).findByRole('button', { name: /^Klopapier ?Other/ }));

    const dialog = await screen.findByRole('dialog', { name: 'Klopapier' });
    expect(within(dialog).getByRole('spinbutton', { name: 'Every weeks' })).toHaveValue(3);
    expect(within(dialog).getByRole('button', { name: 'Save' })).toBeVisible();
    expect(within(dialog).getByTestId(testIds.recurringRemove)).toBeVisible();
  });

  it('creates “as a new ingredient” in “New ingredient”, then opens the pop-up for it', async () => {
    const created = ingredient({ id: 'ing-duschgel', name: 'Duschgel', category_id: 'cat-other' });
    const { fetchMock, user } = renderPage({
      'POST /api/ingredients': Response.json(created, { status: 201 }),
    });

    await user.type(
      await screen.findByRole('searchbox', { name: 'Search ingredient' }),
      'Duschgel',
    );
    await user.click(await screen.findByTestId(testIds.recurringNewIngredient));
    const form = await screen.findByRole('dialog', { name: 'New ingredient' });
    expect(within(form).getByLabelText('Name')).toHaveValue('Duschgel');
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    const dialog = await screen.findByRole('dialog', { name: 'Duschgel' });
    expect(form).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Add' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(await postBodies(fetchMock, 'POST /api/recurring-items')).toEqual([
      { ingredient_id: 'ing-duschgel', interval_weeks: 4 },
    ]);
  });

  it('opens “New ingredient” with ＋ when no ingredient has that name', async () => {
    const { user } = renderPage();

    await user.type(
      await screen.findByRole('searchbox', { name: 'Search ingredient' }),
      'Duschgel',
    );
    await user.click(screen.getByRole('button', { name: 'Add “Duschgel”' }));

    const form = await screen.findByRole('dialog', { name: 'New ingredient' });
    expect(within(form).getByLabelText('Name')).toHaveValue('Duschgel');
  });
});

describe('"Regelmäßige Artikel" offline (SYNC-09)', () => {
  it('shows the friendly offline message', async () => {
    const fetchMock = mockApi(REFERENCE_ROUTES);
    goOffline(fetchMock);
    renderApp('/me/recurring');

    expect(await screen.findByTestId(testIds.offlineNotice)).toHaveTextContent(
      "You're offline. This page needs a connection.",
    );
    expect(screen.getByRole('searchbox', { name: 'Search ingredient' })).toBeDisabled();
  });
});
