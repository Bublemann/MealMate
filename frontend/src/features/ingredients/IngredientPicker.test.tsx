import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import type { components } from '@/api/generated/schema';
import { createQueryClient } from '@/app/queryClient';
import { mockApi, requestsTo } from '@/test/api';
import {
  ingredient,
  lookupResult,
  proposal,
  REFERENCE_ROUTES,
  scanInForm,
  summary,
} from '@/test/ingredients';
import { testIds } from '@/testIds';
import { toSummary, type IngredientSummary } from './api';
import { IngredientPicker } from './IngredientPicker';

type Schemas = components['schemas'];

// jsdom has no camera: the scanner of the form's scan icon shows its manual input.
vi.mock('@/features/scanner/decoder', () => ({
  loadDecoder: () => Promise.resolve(),
  decodeVideoFrame: () => Promise.resolve(null),
}));

const APPLES = summary('Äpfel', 'fruit_vegetables');
const APPLE_JUICE = summary('Apfelsaft', 'other', {
  base_unit: 'ml',
  brand: 'Hofgut',
  barcode: '4000000000006',
  source: 'off',
});

function renderPicker(
  props: Partial<Parameters<typeof IngredientPicker>[0]> = {},
  routes: Record<string, unknown> = {},
) {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    'GET /api/ingredients': (request: Request) =>
      new URL(request.url).searchParams.get('q') === 'apf' ? [APPLES, APPLE_JUICE] : [],
    'GET /api/ingredients/similar': [],
    ...routes,
  });
  const onSelect = vi.fn<(ingredient: IngredientSummary) => void>();
  const queryClient = createQueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <IngredientPicker onSelect={onSelect} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { fetchMock, onSelect, user: userEvent.setup() };
}

describe('IngredientPicker', () => {
  it('searches and picks an ingredient, showing brand and barcode', async () => {
    const { fetchMock, onSelect, user } = renderPicker();

    expect(screen.getByText('Type a name to search.')).toBeVisible();
    await user.type(screen.getByLabelText('Search ingredient'), 'apf');

    const results = await screen.findByRole('list', { name: 'Matching ingredients' });
    const juice = await within(results).findByRole('button', {
      name: /^Apfelsaft \(Hofgut\) with barcode/,
    });
    expect(juice).toHaveTextContent('Apfelsaft (Hofgut) with barcodeOther · ml');
    expect(within(results).getByRole('button', { name: /^Äpfel/ })).toHaveTextContent(
      'ÄpfelFruit & vegetables · g',
    );
    await user.click(juice);

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(APPLE_JUICE);
    // Only the finished word went to the server.
    expect(requestsTo(fetchMock, 'GET /api/ingredients')).toHaveLength(1);
  });

  it('leaves out excluded ingredients', async () => {
    const { user } = renderPicker({ excludeIds: [APPLES.id] });

    await user.type(screen.getByLabelText('Search ingredient'), 'apf');

    const results = await screen.findByRole('list', { name: 'Matching ingredients' });
    await within(results).findByRole('button', { name: /^Apfelsaft/ });
    expect(within(results).queryByRole('button', { name: /^Äpfel/ })).not.toBeInTheDocument();
  });

  it('moves through the results with the arrow keys', async () => {
    const { onSelect, user } = renderPicker();

    const input = screen.getByLabelText('Search ingredient');
    await user.type(input, 'apf');
    await screen.findByRole('button', { name: /^Apfelsaft/ });
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: /^Äpfel/ })).toHaveFocus();
    await user.keyboard('{ArrowDown}{ArrowDown}');
    expect(screen.getByTestId(testIds.ingredientPickerCreate)).toHaveFocus();
    await user.keyboard('{ArrowUp}{ArrowUp}{ArrowUp}');
    expect(input).toHaveFocus();
    await user.keyboard('{ArrowDown}{Enter}');

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(APPLES);
  });

  it('says when nothing matches and offers to create it', async () => {
    const { user } = renderPicker();

    await user.type(screen.getByLabelText('Search ingredient'), 'Quitten');

    expect(await screen.findByText('Nothing found.')).toBeVisible();
    expect(screen.getByTestId(testIds.ingredientPickerCreate)).toHaveTextContent(
      'Create “Quitten”',
    );
  });

  it('creates the typed ingredient inline and picks it', async () => {
    const created = ingredient({ id: 'ing-quitten', name: 'Quitten', category_id: 'cat-other' });
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      { 'POST /api/ingredients': Response.json(created, { status: 201 }) },
    );

    await user.type(screen.getByLabelText('Search ingredient'), 'Quitten');
    await user.click(await screen.findByTestId(testIds.ingredientPickerCreate));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    expect(within(dialog).getByLabelText('Name')).toHaveValue('Quitten');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(onSelect).toHaveBeenCalledExactlyOnceWith({
        id: 'ing-quitten',
        name: 'Quitten',
        brand: null,
        barcode: null,
        source: 'manual',
        category_id: 'cat-other',
        base_unit: 'g',
      }),
    );
    expect(dialog).not.toBeInTheDocument();
    await expect(requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()).resolves.toMatchObject({
      name: 'Quitten',
    });
  });

  it('picks a similar existing ingredient instead of creating a duplicate', async () => {
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      { 'GET /api/ingredients/similar': [APPLES] },
    );

    await user.type(screen.getByLabelText('Search ingredient'), 'Apfl');
    await user.click(await screen.findByTestId(testIds.ingredientPickerCreate));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    const hint = await within(dialog).findByTestId(testIds.ingredientSimilar);
    await user.click(within(hint).getByRole('button', { name: 'Use Äpfel' }));

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(APPLES);
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(0);
  });
});

describe('IngredientPicker, created from Open Food Facts', () => {
  const MILK = proposal();

  function offPage(results: Schemas['OffSearchResult'][]): Schemas['OffSearchPage'] {
    return { q: 'Milch', page: 1, results, has_more: false };
  }

  it('fills the new ingredient from a search result and picks it once saved', async () => {
    const created = ingredient({ id: 'ing-vollmilch', name: MILK.name ?? '', brand: 'Weidehof' });
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      {
        'GET /api/ingredients/off-search': offPage([
          { proposal: MILK, in_mealmate: false, ingredient: null },
        ]),
        'POST /api/ingredients': Response.json(created, { status: 201 }),
      },
    );

    await user.type(screen.getByLabelText('Search ingredient'), 'Milch');
    await user.click(await screen.findByTestId(testIds.ingredientPickerCreate));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    await user.click(within(dialog).getByTestId(testIds.offSearchButton));
    const search = await screen.findByTestId(testIds.offSearchDialog);
    await user.click(await within(search).findByTestId(testIds.offSearchResult));

    await waitFor(() => expect(within(dialog).getByLabelText('Brand')).toHaveValue('Weidehof'));
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onSelect).toHaveBeenCalledOnce());
    expect(onSelect.mock.calls[0]?.[0]).toMatchObject({ id: 'ing-vollmilch', brand: 'Weidehof' });
    await expect(requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()).resolves.toMatchObject({
      barcode: MILK.barcode,
      off: { edited_fields: [] },
    });
  });

  it('picks a product that is already in MealMate instead of creating it again', async () => {
    const known = summary('Vollmilch', 'dairy_eggs', {
      id: 'ing-known',
      brand: 'Weidehof',
      barcode: MILK.barcode,
      source: 'off',
    });
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      {
        'GET /api/ingredients/off-search': offPage([
          { proposal: MILK, in_mealmate: true, ingredient: known },
        ]),
      },
    );

    await user.type(screen.getByLabelText('Search ingredient'), 'Milch');
    await user.click(await screen.findByTestId(testIds.ingredientPickerCreate));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    await user.click(within(dialog).getByTestId(testIds.offSearchButton));
    const search = await screen.findByTestId(testIds.offSearchDialog);
    const result = await within(search).findByRole('button', { name: /Already in MealMate/ });
    await user.click(result);

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(known);
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(0);
  });
});

describe('IngredientPicker, scanning in "New ingredient" (BAR-02, BAR-03)', () => {
  const BARCODE = '4006381333931';
  const LOOKUP = 'GET /api/ingredients/lookup';
  const HONEY = summary('Honig', 'other');
  const HONEY_JAR = summary('Honig', 'other', {
    id: 'ing-honig-imkerei',
    brand: 'Imkerei',
    barcode: '4000000000013',
  });

  /** Types `name` into the picker and opens "New ingredient" for it. */
  async function openNew(user: ReturnType<typeof userEvent.setup>, name: string) {
    await user.type(screen.getByLabelText('Search ingredient'), name);
    await user.click(await screen.findByTestId(testIds.ingredientPickerCreate));
    return screen.findByRole('dialog', { name: 'New ingredient' });
  }

  it('takes the ingredient a scanned barcode belongs to', async () => {
    const known = ingredient({ id: 'ing-honig', name: 'Honig', barcode: BARCODE });
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      { [LOOKUP]: lookupResult({ found_in: 'db', ingredient: known }) },
    );

    const dialog = await openNew(user, 'Honi');
    await scanInForm(user, dialog, BARCODE);

    const notice = await within(dialog).findByTestId(testIds.ingredientScanNotice);
    expect(notice).toHaveTextContent(/^Already belongs to Honiguse$/);
    expect(within(dialog).getByLabelText('Barcode')).toHaveValue('');
    expect(within(notice).queryByRole('link')).not.toBeInTheDocument();
    const take = within(notice).getByRole('button', { name: 'use' });
    expect(take).toHaveAttribute('data-testid', testIds.ingredientScanTake);
    await user.click(take);

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(toSummary(known));
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(0);
  });

  it('gives a similar ingredient without a barcode the scanned one, then takes it', async () => {
    const linked = ingredient({ ...HONEY, barcode: BARCODE });
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      {
        [LOOKUP]: lookupResult(),
        'GET /api/ingredients/similar': [HONEY, HONEY_JAR],
        'POST /api/ingredients/ing-honig/barcode': linked,
      },
    );

    const dialog = await openNew(user, 'Honig');
    await scanInForm(user, dialog, BARCODE);
    const hint = await within(dialog).findByTestId(testIds.ingredientSimilar);
    await user.click(within(hint).getByRole('button', { name: 'Use Honig' }));

    await waitFor(() => expect(onSelect).toHaveBeenCalledExactlyOnceWith(toSummary(linked)));
    expect(dialog).not.toBeInTheDocument();
    await expect(
      requestsTo(fetchMock, 'POST /api/ingredients/ing-honig/barcode')[0]?.json(),
    ).resolves.toEqual({ barcode: BARCODE });
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(0);
  });

  it('takes a similar ingredient that has a barcode as it is (D-21)', async () => {
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      { [LOOKUP]: lookupResult(), 'GET /api/ingredients/similar': [HONEY, HONEY_JAR] },
    );

    const dialog = await openNew(user, 'Honig');
    await scanInForm(user, dialog, BARCODE);
    const hint = await within(dialog).findByTestId(testIds.ingredientSimilar);
    await user.click(within(hint).getByRole('button', { name: 'Use Honig (Imkerei)' }));

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(HONEY_JAR);
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(requestsTo(fetchMock, 'POST /api/ingredients/ing-honig-imkerei/barcode')).toHaveLength(
      0,
    );
  });
});
