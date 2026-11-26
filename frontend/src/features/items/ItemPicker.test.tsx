import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent, { type UserEvent } from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import type { components } from '@/api/generated/schema';
import { createQueryClient } from '@/app/queryClient';
import { heldRoute, mockApi, requestsTo } from '@/test/api';
import {
  itemDetail,
  lookupResult,
  proposal,
  REFERENCE_ROUTES,
  scanInForm,
  summary,
} from '@/test/items';
import { testIds } from '@/testIds';
import { toSummary, type ItemSummary } from './api';
import { ItemPicker } from './ItemPicker';

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
  props: Partial<Parameters<typeof ItemPicker>[0]> = {},
  routes: Record<string, unknown> = {},
) {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    'GET /api/items': (request: Request) =>
      new URL(request.url).searchParams.get('q') === 'apf' ? [APPLES, APPLE_JUICE] : [],
    'GET /api/items/similar': [],
    ...routes,
  });
  const onSelect = vi.fn<(ingredient: ItemSummary) => void>();
  const queryClient = createQueryClient();
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ItemPicker onSelect={onSelect} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { fetchMock, onSelect, user: userEvent.setup() };
}

describe('ItemPicker', () => {
  it('searches and picks an ingredient, showing brand and barcode', async () => {
    const { fetchMock, onSelect, user } = renderPicker();

    expect(screen.getByText('Type a name to search.')).toBeVisible();
    await user.type(screen.getByLabelText('Search item'), 'apf');

    const results = await screen.findByRole('list', { name: 'Matching items' });
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
    expect(requestsTo(fetchMock, 'GET /api/items')).toHaveLength(1);
  });

  it('leaves out excluded ingredients', async () => {
    const { user } = renderPicker({ excludeIds: [APPLES.id] });

    await user.type(screen.getByLabelText('Search item'), 'apf');

    const results = await screen.findByRole('list', { name: 'Matching items' });
    await within(results).findByRole('button', { name: /^Apfelsaft/ });
    expect(within(results).queryByRole('button', { name: /^Äpfel/ })).not.toBeInTheDocument();
  });

  it('moves through the results with the arrow keys', async () => {
    const { onSelect, user } = renderPicker();

    const input = screen.getByLabelText('Search item');
    await user.type(input, 'apf');
    await screen.findByRole('button', { name: /^Apfelsaft/ });
    await user.keyboard('{ArrowDown}');
    expect(screen.getByTestId(testIds.itemPickerCreate)).toHaveFocus();
    await user.keyboard('{ArrowDown}');
    expect(screen.getByRole('button', { name: /^Äpfel/ })).toHaveFocus();
    await user.keyboard('{ArrowDown}{ArrowDown}');
    expect(screen.getByRole('button', { name: /^Apfelsaft/ })).toHaveFocus();
    await user.keyboard('{ArrowUp}{ArrowUp}{ArrowUp}');
    expect(input).toHaveFocus();
    await user.keyboard('{ArrowDown}{ArrowDown}{Enter}');

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(APPLES);
  });

  it('keeps "Create" first while results arrive, change and go, hiding an earlier search’s results (MEAL-03)', async () => {
    const search = heldRoute();
    const { fetchMock, user } = renderPicker({}, { 'GET /api/items': search.route });
    const picker = screen.getByTestId(testIds.itemPicker);
    const input = screen.getByLabelText('Search item');
    // The picker's buttons in DOM order: what a tap under the field lands on.
    const options = () =>
      within(picker)
        .getAllByRole('button')
        .map((button) => button.textContent);

    await user.type(input, 'apf');
    expect(options()).toEqual(['Create “apf”']);
    await search.answer([APPLES, APPLE_JUICE]);
    await within(picker).findByRole('button', { name: /^Apfelsaft/ });
    expect(options()).toEqual([
      'Create “apf”',
      'ÄpfelFruit & vegetables · g',
      'Apfelsaft (Hofgut) with barcodeOther · ml',
    ]);

    // While the longer text waits for the debounce and then for its answer, the shorter one's
    // results are gone.
    await user.type(input, 'els');
    expect(options()).toEqual(['Create “apfels”']);
    await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/items')).toHaveLength(2));
    expect(options()).toEqual(['Create “apfels”']);
    await search.answer([APPLE_JUICE]);
    await within(picker).findByRole('button', { name: /^Apfelsaft/ });
    expect(options()).toEqual(['Create “apfels”', 'Apfelsaft (Hofgut) with barcodeOther · ml']);

    await user.type(input, 'x');
    expect(options()).toEqual(['Create “apfelsx”']);
    await search.answer([]);
    const nothing = await screen.findByText('Nothing found.');
    expect(options()).toEqual(['Create “apfelsx”']);
    // The notice comes after the option, so it doesn't push the option down either.
    expect(
      screen.getByTestId(testIds.itemPickerCreate).compareDocumentPosition(nothing) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('says when nothing matches and offers to create it', async () => {
    const { user } = renderPicker();

    await user.type(screen.getByLabelText('Search item'), 'Quitten');

    expect(await screen.findByText('Nothing found.')).toBeVisible();
    expect(screen.getByTestId(testIds.itemPickerCreate)).toHaveTextContent('Create “Quitten”');
  });

  it('creates the typed ingredient inline and picks it', async () => {
    const created = itemDetail({ id: 'ing-quitten', name: 'Quitten', category_id: 'cat-other' });
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      { 'POST /api/items': Response.json(created, { status: 201 }) },
    );

    await user.type(screen.getByLabelText('Search item'), 'Quitten');
    await user.click(await screen.findByTestId(testIds.itemPickerCreate));
    const dialog = await screen.findByRole('dialog', { name: 'New item' });
    expect(within(dialog).getByLabelText('Name')).toHaveValue('Quitten');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(onSelect).toHaveBeenCalledExactlyOnceWith({
        id: 'ing-quitten',
        name: 'Quitten',
        brand: null,
        barcode: null,
        source: 'manual',
        kind: 'food',
        category_id: 'cat-other',
        base_unit: 'g',
      }),
    );
    expect(dialog).not.toBeInTheDocument();
    await expect(requestsTo(fetchMock, 'POST /api/items')[0]?.json()).resolves.toMatchObject({
      name: 'Quitten',
    });
  });

  it('picks a similar existing ingredient instead of creating a duplicate', async () => {
    const { fetchMock, onSelect, user } = renderPicker({}, { 'GET /api/items/similar': [APPLES] });

    await user.type(screen.getByLabelText('Search item'), 'Apfl');
    await user.click(await screen.findByTestId(testIds.itemPickerCreate));
    const dialog = await screen.findByRole('dialog', { name: 'New item' });
    const hint = await within(dialog).findByTestId(testIds.itemSimilar);
    await user.click(within(hint).getByRole('button', { name: 'Use Äpfel' }));

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(APPLES);
    expect(requestsTo(fetchMock, 'POST /api/items')).toHaveLength(0);
  });
});

describe('ItemPicker, created from Open Food Facts', () => {
  const MILK = proposal();

  function offPage(results: Schemas['OffSearchResult'][]): Schemas['OffSearchPage'] {
    return { q: 'Milch', page: 1, results, has_more: false };
  }

  it('fills the new ingredient from a search result and picks it once saved', async () => {
    const created = itemDetail({ id: 'ing-vollmilch', name: MILK.name ?? '', brand: 'Weidehof' });
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      {
        'GET /api/items/off-search': offPage([{ proposal: MILK, in_mealmate: false, item: null }]),
        'POST /api/items': Response.json(created, { status: 201 }),
      },
    );

    await user.type(screen.getByLabelText('Search item'), 'Milch');
    await user.click(await screen.findByTestId(testIds.itemPickerCreate));
    const dialog = await screen.findByRole('dialog', { name: 'New item' });
    await user.click(within(dialog).getByTestId(testIds.offSearchButton));
    const search = await screen.findByTestId(testIds.offSearchDialog);
    await user.click(await within(search).findByTestId(testIds.offSearchResult));

    await waitFor(() => expect(within(dialog).getByLabelText('Brand')).toHaveValue('Weidehof'));
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(onSelect).toHaveBeenCalledOnce());
    expect(onSelect.mock.calls[0]?.[0]).toMatchObject({ id: 'ing-vollmilch', brand: 'Weidehof' });
    await expect(requestsTo(fetchMock, 'POST /api/items')[0]?.json()).resolves.toMatchObject({
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
        'GET /api/items/off-search': offPage([{ proposal: MILK, in_mealmate: true, item: known }]),
      },
    );

    await user.type(screen.getByLabelText('Search item'), 'Milch');
    await user.click(await screen.findByTestId(testIds.itemPickerCreate));
    const dialog = await screen.findByRole('dialog', { name: 'New item' });
    await user.click(within(dialog).getByTestId(testIds.offSearchButton));
    const search = await screen.findByTestId(testIds.offSearchDialog);
    const result = await within(search).findByRole('button', { name: /Already in MealMate/ });
    await user.click(result);

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(known);
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(requestsTo(fetchMock, 'POST /api/items')).toHaveLength(0);
  });
});

describe('ItemPicker, scanning in "New item" (BAR-02, BAR-03)', () => {
  const BARCODE = '4006381333931';
  const LOOKUP = 'GET /api/items/lookup';
  const HONEY = summary('Honig', 'other');
  const HONEY_JAR = summary('Honig', 'other', {
    id: 'ing-honig-imkerei',
    brand: 'Imkerei',
    barcode: '4000000000013',
  });

  /** Types `name` into the picker and opens "New item" for it. */
  async function openNew(user: UserEvent, name: string) {
    await user.type(screen.getByLabelText('Search item'), name);
    await user.click(await screen.findByTestId(testIds.itemPickerCreate));
    return screen.findByRole('dialog', { name: 'New item' });
  }

  it('takes the ingredient a scanned barcode belongs to', async () => {
    const known = itemDetail({ id: 'ing-honig', name: 'Honig', barcode: BARCODE });
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      { [LOOKUP]: lookupResult({ found_in: 'db', item: known }) },
    );

    const dialog = await openNew(user, 'Honi');
    await scanInForm(user, dialog, BARCODE);

    const notice = await within(dialog).findByTestId(testIds.itemScanNotice);
    expect(notice).toHaveTextContent(/^Already belongs to Honiguse$/);
    expect(within(dialog).getByLabelText('Barcode')).toHaveValue('');
    expect(within(notice).queryByRole('link')).not.toBeInTheDocument();
    const take = within(notice).getByRole('button', { name: 'use' });
    expect(take).toHaveAttribute('data-testid', testIds.itemScanTake);
    await user.click(take);

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(toSummary(known));
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(requestsTo(fetchMock, 'POST /api/items')).toHaveLength(0);
  });

  it('gives a similar ingredient without a barcode the scanned one, then takes it', async () => {
    const linked = itemDetail({ ...HONEY, barcode: BARCODE });
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      {
        [LOOKUP]: lookupResult(),
        'GET /api/items/similar': [HONEY, HONEY_JAR],
        'POST /api/items/ing-honig/barcode': linked,
      },
    );

    const dialog = await openNew(user, 'Honig');
    await scanInForm(user, dialog, BARCODE);
    const hint = await within(dialog).findByTestId(testIds.itemSimilar);
    await user.click(within(hint).getByRole('button', { name: 'Use Honig' }));

    await waitFor(() => expect(onSelect).toHaveBeenCalledExactlyOnceWith(toSummary(linked)));
    expect(dialog).not.toBeInTheDocument();
    await expect(
      requestsTo(fetchMock, 'POST /api/items/ing-honig/barcode')[0]?.json(),
    ).resolves.toEqual({ barcode: BARCODE });
    expect(requestsTo(fetchMock, 'POST /api/items')).toHaveLength(0);
  });

  it('takes a similar ingredient that has a barcode as it is (D-21)', async () => {
    const { fetchMock, onSelect, user } = renderPicker(
      {},
      { [LOOKUP]: lookupResult(), 'GET /api/items/similar': [HONEY, HONEY_JAR] },
    );

    const dialog = await openNew(user, 'Honig');
    await scanInForm(user, dialog, BARCODE);
    const hint = await within(dialog).findByTestId(testIds.itemSimilar);
    await user.click(within(hint).getByRole('button', { name: 'Use Honig (Imkerei)' }));

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(HONEY_JAR);
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(requestsTo(fetchMock, 'POST /api/items/ing-honig-imkerei/barcode')).toHaveLength(0);
  });
});
