import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { createQueryClient } from '@/app/queryClient';
import i18n from '@/i18n';
import { mockApi, requestsTo } from '@/test/api';
import {
  APPLES,
  expectInPageOrder,
  itemDetail,
  lookupResult,
  proposal,
  REFERENCE_ROUTES,
  scanInForm,
  summary,
} from '@/test/items';
import { chooseFromMenu } from '@/test/menu';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import { ItemPicker } from './ItemPicker';

// jsdom has no camera: the scanner of the form's scan icon shows its manual input.
vi.mock('@/features/scanner/decoder', () => ({
  loadDecoder: () => Promise.resolve(),
  decodeVideoFrame: () => Promise.resolve(null),
}));

const PAPER = itemDetail({
  id: 'ing-klopapier',
  name: 'Klopapier',
  kind: 'supply',
  base_unit: 'piece',
  usage: { meals: 0, lists: 2 },
});

function renderItems(routes: Record<string, unknown> = {}, path = '/items') {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    'GET /api/items': [],
    'GET /api/items/similar': [],
    'GET /api/items/ing-aepfel': APPLES,
    'GET /api/items/ing-klopapier': PAPER,
    ...routes,
  });
  return { fetchMock, ...renderApp(path) };
}

async function openNewItem(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByTestId(testIds.newItem));
  const dialog = await screen.findByRole('dialog', { name: 'New item' });
  return within(dialog).getByTestId(testIds.itemForm);
}

describe('Food or supplies (D-56)', () => {
  it('starts “New item” with “Food” chosen, at the very top', async () => {
    const { user } = renderItems();

    const form = await openNewItem(user);

    const kind = within(form).getByRole('radiogroup', { name: 'Kind' });
    expect(
      within(kind)
        .getAllByRole('radio')
        .map((radio) => radio.closest('label')?.textContent),
    ).toEqual(['Food', 'Supplies']);
    expect(within(kind).getByLabelText('Food')).toBeChecked();
    expectInPageOrder([kind, within(form).getByLabelText('Name')]);
    expect(
      within(form).getByRole('group', { name: 'Nutrition per 100 g (optional)' }),
    ).toBeVisible();
  });

  it('hides the nutrition and the piece weight for supplies, and sends neither', async () => {
    const { fetchMock, user } = renderItems({
      'POST /api/items': Response.json(PAPER, { status: 201 }),
    });

    const form = await openNewItem(user);
    await user.type(within(form).getByLabelText('Name'), 'Klopapier');
    await user.click(within(form).getByLabelText('Pieces (pcs)'));
    await user.type(within(form).getByLabelText('Weight per piece (g)'), '100');
    await user.type(within(form).getByLabelText('Calories'), '5');
    await user.click(within(form).getByLabelText('Supplies'));

    expect(within(form).queryByLabelText('Weight per piece (g)')).not.toBeInTheDocument();
    expect(within(form).queryByRole('group', { name: /^Nutrition/ })).not.toBeInTheDocument();
    expect(within(form).getByRole('group', { name: 'Base unit' })).toBeVisible();
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(requestsTo(fetchMock, 'POST /api/items')).toHaveLength(1));
    await expect(requestsTo(fetchMock, 'POST /api/items')[0]?.json()).resolves.toEqual({
      name: 'Klopapier',
      kind: 'supply',
      base_unit: 'piece',
      category_id: 'cat-other',
    });
  });

  it('keeps “Food” when Open Food Facts has no nutrition for a scanned product (BAR-03)', async () => {
    const { fetchMock, user } = renderItems({
      'GET /api/items/lookup': lookupResult({
        found_in: 'off',
        proposal: proposal({
          name: 'Kerzen',
          nutrition_basis: null,
          nutrients: { kcal: null, protein: null, carbs: null, sugar: null, fat: null },
        }),
      }),
      'POST /api/items': Response.json(itemDetail(), { status: 201 }),
    });

    const form = await openNewItem(user);
    await scanInForm(user, form, '4006381333931');
    await waitFor(() => expect(within(form).getByLabelText('Name')).toHaveValue('Kerzen'));

    expect(within(form).getByLabelText('Food')).toBeChecked();
    await user.click(within(form).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(requestsTo(fetchMock, 'POST /api/items')).toHaveLength(1));
    const body = (await requestsTo(fetchMock, 'POST /api/items')[0]?.json()) as object;
    expect(body).not.toHaveProperty('kind');
  });

  it('shows a supply as one, without nutrition or piece weight', async () => {
    renderItems({}, '/items/ing-klopapier');

    const page = await screen.findByTestId(testIds.screenItem);
    await waitFor(() => expect(page).toHaveTextContent('KindSupplies'));
    expect(page).toHaveTextContent('Base unitPieces (pcs)');
    expect(page).not.toHaveTextContent('Weight of one piece');
    expect(screen.queryByTestId(testIds.itemNutrition)).not.toBeInTheDocument();
  });

  it('switches an item to supplies in the edit pop-up, sending only the kind', async () => {
    const { fetchMock, user } = renderItems(
      {
        'PATCH /api/items/ing-aepfel': {
          ...APPLES,
          kind: 'supply',
          nutrients: { ...APPLES.nutrients, kcal: null, protein: null },
        },
      },
      '/items/ing-aepfel',
    );

    await chooseFromMenu(user, testIds.editItem);
    const dialog = await screen.findByRole('dialog', { name: 'Edit Äpfel' });
    const kind = within(dialog).getByRole('radiogroup', { name: 'Kind' });
    expectInPageOrder([kind, within(dialog).getByLabelText('Name')]);
    expect(within(kind).getByLabelText('Food')).toBeChecked();
    await user.click(within(kind).getByLabelText('Supplies'));
    expect(within(dialog).queryByLabelText('Calories')).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await expect(requestsTo(fetchMock, 'PATCH /api/items/ing-aepfel')[0]?.json()).resolves.toEqual({
      kind: 'supply',
    });
    expect(screen.queryByTestId(testIds.itemNutrition)).not.toBeInTheDocument();
  });

  it('opens a supply’s edit pop-up with “Supplies” chosen, and makes it food again', async () => {
    const { fetchMock, user } = renderItems(
      { 'PATCH /api/items/ing-klopapier': { ...PAPER, kind: 'food' } },
      '/items/ing-klopapier',
    );

    await chooseFromMenu(user, testIds.editItem);
    const dialog = await screen.findByRole('dialog', { name: 'Edit Klopapier' });
    expect(within(dialog).getByLabelText('Supplies')).toBeChecked();
    expect(within(dialog).queryByLabelText('Calories')).not.toBeInTheDocument();
    await user.click(within(dialog).getByLabelText('Food'));
    expect(within(dialog).getByLabelText('Calories')).toHaveValue('');
    expect(within(dialog).getByLabelText('Weight per piece (g)')).toBeVisible();
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await expect(
      requestsTo(fetchMock, 'PATCH /api/items/ing-klopapier')[0]?.json(),
    ).resolves.toEqual({ kind: 'food' });
  });

  it('saves a scanned product as a supply without its nutrition or marks on it (BAR-04)', async () => {
    const { fetchMock, user } = renderItems({
      'GET /api/items/lookup': lookupResult({
        found_in: 'off',
        proposal: proposal({ name: 'Taschentücher', nutrition_basis: 'g' }),
      }),
      'POST /api/items': Response.json(PAPER, { status: 201 }),
    });

    const form = await openNewItem(user);
    await scanInForm(user, form, '4006381333931');
    await waitFor(() => expect(within(form).getByLabelText('Name')).toHaveValue('Taschentücher'));
    await user.clear(within(form).getByLabelText('Calories'));
    await user.click(within(form).getByLabelText('Supplies'));
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(requestsTo(fetchMock, 'POST /api/items')).toHaveLength(1));
    const body = (await requestsTo(fetchMock, 'POST /api/items')[0]?.json()) as Record<
      string,
      unknown
    >;
    expect(body.kind).toBe('supply');
    expect(body).not.toHaveProperty('nutrients');
    expect(body.off).toEqual({ off_last_modified_at: '2026-09-01T10:00:00Z', edited_fields: [] });
  });

  it('names the meals that keep an item from becoming a supply, in German', async () => {
    await i18n.changeLanguage('de');
    const { user } = renderItems(
      {
        'PATCH /api/items/ing-aepfel': Response.json(
          {
            code: 'item.used_in_meals',
            params: { meals: 3, names: ['Apfelkuchen', 'Müsli'] },
            fields: [],
          },
          { status: 409 },
        ),
      },
      '/items/ing-aepfel',
    );

    await chooseFromMenu(user, testIds.editItem);
    const dialog = await screen.findByRole('dialog', { name: 'Äpfel bearbeiten' });
    await user.click(within(dialog).getByLabelText('Gebrauchsartikel'));
    await user.click(within(dialog).getByRole('button', { name: 'Speichern' }));

    expect(await within(dialog).findByTestId(testIds.itemUsedInMeals)).toHaveTextContent(
      'Äpfel wird in 3 Gerichten verwendet (Apfelkuchen, Müsli und 1 weiteres) und kann deshalb kein Gebrauchsartikel sein. Nimm den Artikel dort zuerst heraus.',
    );
    expect(dialog).toBeInTheDocument();
  });

  it('names the meals as a count only when the user may see none of them', async () => {
    const { user } = renderItems(
      {
        'PATCH /api/items/ing-aepfel': Response.json(
          { code: 'item.used_in_meals', params: { meals: 1, names: [] }, fields: [] },
          { status: 409 },
        ),
      },
      '/items/ing-aepfel',
    );

    await chooseFromMenu(user, testIds.editItem);
    const dialog = await screen.findByRole('dialog', { name: 'Edit Äpfel' });
    await user.click(within(dialog).getByLabelText('Supplies'));
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(await within(dialog).findByTestId(testIds.itemUsedInMeals)).toHaveTextContent(
      "Äpfel is used in 1 meal, so it can't be a supply. Take it out there first.",
    );
  });
});

describe('The meal form’s item search (MEAL-02, D-56)', () => {
  function renderPicker(routes: Record<string, unknown> = {}) {
    const fetchMock = mockApi({
      ...REFERENCE_ROUTES,
      'GET /api/items': [summary('Kekse', 'other')],
      'GET /api/items/similar': [],
      ...routes,
    });
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter>
          <ItemPicker onSelect={vi.fn()} kind="food" />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    return { fetchMock, user: userEvent.setup() };
  }

  it('asks for food only', async () => {
    const { fetchMock, user } = renderPicker();

    await user.type(screen.getByLabelText('Search item'), 'Ke');

    expect(await screen.findByText('Kekse')).toBeVisible();
    const asked = requestsTo(fetchMock, 'GET /api/items').map((request) =>
      new URL(request.url).searchParams.get('kind'),
    );
    expect(asked).toEqual(['food']);
  });

  it('creates food, without offering supplies', async () => {
    const { fetchMock, user } = renderPicker({
      'POST /api/items': Response.json(itemDetail({ name: 'Kerzen' }), { status: 201 }),
    });

    await user.type(screen.getByLabelText('Search item'), 'Kerzen');
    await user.click(await screen.findByTestId(testIds.itemPickerCreate));
    const form = within(await screen.findByRole('dialog')).getByTestId(testIds.itemForm);

    expect(within(form).queryByRole('radiogroup', { name: 'Kind' })).not.toBeInTheDocument();
    await user.click(within(form).getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(requestsTo(fetchMock, 'POST /api/items')).toHaveLength(1));
    const body = (await requestsTo(fetchMock, 'POST /api/items')[0]?.json()) as object;
    expect(body).not.toHaveProperty('kind');
  });

  it('shows a supply the Open Food Facts search finds, but doesn’t take it', async () => {
    const candles = summary('Kerzen', 'other', { kind: 'supply', id: 'ing-kerzen' });
    const { user } = renderPicker({
      'GET /api/items/off-search': {
        q: 'Kerzen',
        page: 1,
        has_more: false,
        results: [
          {
            proposal: proposal({ barcode: candles.barcode ?? '4006381333931', name: 'Kerzen' }),
            in_mealmate: true,
            item: candles,
          },
        ],
      },
    });

    await user.type(screen.getByLabelText('Search item'), 'Kerzen');
    await user.click(await screen.findByTestId(testIds.itemPickerCreate));
    const form = within(await screen.findByRole('dialog')).getByTestId(testIds.itemForm);
    await user.click(within(form).getByRole('button', { name: 'Search Open Food Facts' }));

    const search = await screen.findByTestId(testIds.offSearchDialog);
    const [result] = await within(search).findAllByTestId(testIds.offSearchResult);
    expect(result).toBeDisabled();
    expect(result).toHaveTextContent("“Kerzen” is a supply and can't be an ingredient.");
  });

  it('offers no supply a similar name or a scan finds', async () => {
    const candles = summary('Kerzen', 'other', { kind: 'supply', id: 'ing-kerzen' });
    const { user } = renderPicker({
      'GET /api/items/similar': [candles, summary('Kerzenwachs-Kekse', 'other')],
      'GET /api/items/lookup': lookupResult({
        found_in: 'db',
        item: itemDetail({ id: 'ing-kerzen', name: 'Kerzen', kind: 'supply' }),
      }),
    });

    await user.type(screen.getByLabelText('Search item'), 'Kerzen');
    await user.click(await screen.findByTestId(testIds.itemPickerCreate));
    const form = within(await screen.findByRole('dialog')).getByTestId(testIds.itemForm);

    const similar = await within(form).findByTestId(testIds.itemSimilar);
    expect(
      within(similar)
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['Use Kerzenwachs-Kekse']);
    await scanInForm(user, form, '4006381333931');
    const notice = await within(form).findByTestId(testIds.itemScanNotice);
    expect(notice).toHaveTextContent("“Kerzen” is a supply and can't be an ingredient.");
    expect(within(notice).queryByRole('button')).not.toBeInTheDocument();
  });
});
