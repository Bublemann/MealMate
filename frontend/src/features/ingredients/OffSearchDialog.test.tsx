import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { components } from '@/api/generated/schema';
import { errorResponse, mockApi, requestsTo } from '@/test/api';
import {
  CATEGORIES_AFTER_DELETE,
  ingredient,
  proposal,
  REFERENCE_ROUTES,
  summary,
} from '@/test/ingredients';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

type Schemas = components['schemas'];

const MILK = proposal();
const OATS = proposal({
  barcode: '2000000000015',
  name: 'Haferflocken zart',
  brand: 'Kornmühle',
  quantity_text: '500 g',
  pack_quantity: 500,
  pack_unit: 'g',
  nutrition_basis: 'g',
  nutrients: { kcal: 372, protein: 13.5, carbs: 58.7, sugar: 0.7, fat: 7 },
  category_key: 'other',
});
const KNOWN = summary('Vollmilch', 'dairy_eggs', {
  id: 'ing-known',
  brand: 'Alpenhof',
  barcode: '2000000000022',
  source: 'off',
  base_unit: 'ml',
});

function page(
  results: Schemas['OffSearchResult'][],
  overrides: Partial<Schemas['OffSearchPage']> = {},
): Schemas['OffSearchPage'] {
  return { q: 'milch', page: 1, results, has_more: false, ...overrides };
}

function found(product: Schemas['ProductProposal']): Schemas['OffSearchResult'] {
  return { proposal: product, in_mealmate: false, ingredient: null };
}

const KNOWN_RESULT: Schemas['OffSearchResult'] = {
  proposal: proposal({ barcode: '2000000000022', name: 'Vollmilch', brand: 'Alpenhof' }),
  in_mealmate: true,
  ingredient: KNOWN,
};

function renderSearch(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    'GET /api/ingredients': [summary('Salz', 'other')],
    'GET /api/ingredients/similar': [],
    'GET /api/ingredients/off-search': page([found(MILK), KNOWN_RESULT]),
    ...routes,
  });
  return { fetchMock, ...renderApp('/ingredients') };
}

type User = ReturnType<typeof renderApp>['user'];

/** Opens "New ingredient" with `name` typed, then the search dialog from the magnifier. */
async function openSearch(user: User, name = 'Milch') {
  await user.click(await screen.findByTestId(testIds.newIngredient));
  const form = await screen.findByTestId(testIds.ingredientForm);
  if (name) await user.type(within(form).getByLabelText('Name'), name);
  await user.click(within(form).getByRole('button', { name: 'Search Open Food Facts' }));
  return screen.findByTestId(testIds.offSearchDialog);
}

function searches(fetchMock: ReturnType<typeof mockApi>) {
  return requestsTo(fetchMock, 'GET /api/ingredients/off-search').map((request) => {
    const params = new URL(request.url).searchParams;
    return { q: params.get('q'), page: params.get('page') };
  });
}

describe('OffSearchDialog', () => {
  it('searches the typed name at once, then only when asked to, never while typing (BAR-08, BAR-11)', async () => {
    const { fetchMock, user } = renderSearch();
    const dialog = await openSearch(user);

    // Tapping the magnifier is the explicit action: the name typed so far is searched at once.
    const field = within(dialog).getByLabelText('Product name or brand');
    expect(field).toHaveValue('Milch');
    await within(dialog).findAllByTestId(testIds.offSearchResult);
    expect(searches(fetchMock)).toEqual([{ q: 'Milch', page: '1' }]);
    await user.type(field, ' Weidehof');
    // A pause in typing sends nothing.
    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(searches(fetchMock)).toHaveLength(1);

    await user.type(field, '{Enter}');
    await waitFor(() =>
      expect(searches(fetchMock)).toEqual([
        { q: 'Milch', page: '1' },
        { q: 'Milch Weidehof', page: '1' },
      ]),
    );
    await within(dialog).findAllByTestId(testIds.offSearchResult);
    // Enter in the search field must not save the ingredient form behind the dialog.
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(0);

    await user.click(within(dialog).getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(searches(fetchMock)).toHaveLength(3));
  });

  it('opens with an empty search field when no name is typed (BAR-11)', async () => {
    const { fetchMock, user } = renderSearch();
    const dialog = await openSearch(user, '');

    expect(within(dialog).getByLabelText('Product name or brand')).toHaveValue('');
    expect(within(dialog).getByRole('button', { name: 'Search' })).toBeDisabled();
    expect(searches(fetchMock)).toEqual([]);
  });

  it('needs at least two characters', async () => {
    const { fetchMock, user } = renderSearch();
    const dialog = await openSearch(user, 'M');

    expect(within(dialog).getByRole('button', { name: 'Search' })).toBeDisabled();
    await user.type(within(dialog).getByLabelText('Product name or brand'), '{Enter}');
    expect(searches(fetchMock)).toEqual([]);
  });

  it('shows name, brand, package size, calories and the attribution (BAR-09, BAR-10)', async () => {
    const { user } = renderSearch({
      'GET /api/ingredients/off-search': page([found({ ...MILK, name: '<b>Milch</b>' })]),
    });
    const dialog = await openSearch(user);

    const [result] = await within(dialog).findAllByTestId(testIds.offSearchResult);
    expect(result).toHaveTextContent('<b>Milch</b> (Weidehof)1 l · 64 kcal per 100 ml');
    expect(within(dialog).getByTestId(testIds.offAttribution)).toHaveTextContent(
      /^Nutrition data: Open Food Facts.*\(ODbL\)$/,
    );
  });

  it('fills the form with the chosen product, saved in one request with its pack size (BAR-04, D-38)', async () => {
    const created = ingredient({ id: 'ing-vollmilch', name: 'Frische Vollmilch 3,5 %' });
    const { fetchMock, user, router } = renderSearch({
      'POST /api/ingredients': Response.json(created, { status: 201 }),
    });
    const dialog = await openSearch(user);
    const [first] = await within(dialog).findAllByTestId(testIds.offSearchResult);
    await user.click(first!);

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    const form = screen.getByTestId(testIds.ingredientForm);
    expect(within(form).getByLabelText('Name')).toHaveValue('Frische Vollmilch 3,5 %');
    expect(within(form).getByLabelText('Brand')).toHaveValue('Weidehof');
    await waitFor(() =>
      expect(within(form).getByLabelText('Category')).toHaveValue('cat-dairy_eggs'),
    );
    expect(within(form).getByRole('radio', { name: 'Millilitres (ml)' })).toBeChecked();
    expect(within(form).getByLabelText('Calories')).toHaveValue('64');
    expect(within(form).getByLabelText('Barcode')).toHaveValue('4006381333931');
    expect(within(form).getByLabelText('Barcode')).toHaveAttribute('readonly');
    // The barcode belongs to the values: the scan icon can't replace it.
    expect(within(form).getByRole('button', { name: 'Scan barcode' })).toBeDisabled();
    expect(within(form).getByTestId(testIds.offAttribution)).toBeVisible();
    // Another product can still be chosen instead.
    expect(within(form).getByTestId(testIds.offSearchButton)).toBeVisible();

    await user.clear(within(form).getByLabelText('Fat'));
    await user.type(within(form).getByLabelText('Fat'), '3,6');
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-vollmilch'));
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(1);
    await expect(requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()).resolves.toEqual({
      name: 'Frische Vollmilch 3,5 %',
      base_unit: 'ml',
      category_id: 'cat-dairy_eggs',
      brand: 'Weidehof',
      barcode: '4006381333931',
      quantity_text: '1 l',
      pack_quantity: 1,
      pack_unit: 'l',
      nutrients: { kcal: 64, protein: 3.4, carbs: 4.8, sugar: 4.8, fat: 3.6 },
      off: { off_last_modified_at: '2026-09-01T10:00:00Z', edited_fields: ['nutrients.fat'] },
    });
  });

  it('keeps the values per 100 g when a chosen product is counted in pieces instead (ING-02)', async () => {
    const { fetchMock, user } = renderSearch({
      'GET /api/ingredients/off-search': page([found(OATS)]),
      'POST /api/ingredients': Response.json(ingredient({ id: 'ing-oats' }), { status: 201 }),
    });
    const dialog = await openSearch(user, 'Haferflocken');
    const [first] = await within(dialog).findAllByTestId(testIds.offSearchResult);
    await user.click(first!);

    const form = screen.getByTestId(testIds.ingredientForm);
    // Open Food Facts proposes grams or millilitres, never pieces.
    expect(within(form).getByRole('radio', { name: 'Grams (g)' })).toBeChecked();
    await user.click(within(form).getByRole('radio', { name: 'Pieces (pcs)' }));
    expect(
      within(form).getByRole('group', { name: 'Nutrition per 100 g (optional)' }),
    ).toBeVisible();
    expect(within(form).getByLabelText('Calories')).toHaveValue('372');
    await user.type(within(form).getByLabelText('Weight per piece (g)'), '40');
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(1));
    const body = (await requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()) as {
      base_unit: string;
      piece_weight_g: number;
      nutrients: Record<string, number>;
      off: { edited_fields: string[] };
    };
    expect([body.base_unit, body.piece_weight_g]).toEqual(['piece', 40]);
    expect(body.nutrients).toEqual(OATS.nutrients);
    // The values are still Open Food Facts': later updates may change them.
    expect(body.off.edited_fields).toEqual([]);
  });

  it('counts a name typed before choosing a product without one as edited (BAR-04)', async () => {
    const { fetchMock, user } = renderSearch({
      'GET /api/ingredients/off-search': page([
        found(proposal({ name: null, brand: null, category_key: null })),
      ]),
      'POST /api/ingredients': Response.json(ingredient({ id: 'ing-new' }), { status: 201 }),
    });
    const dialog = await openSearch(user, 'Hafermilch');
    const [first] = await within(dialog).findAllByTestId(testIds.offSearchResult);
    await user.click(first!);

    const form = screen.getByTestId(testIds.ingredientForm);
    expect(within(form).getByLabelText('Name')).toHaveValue('Hafermilch');
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(1));
    const body = (await requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()) as {
      name: string;
      off: { edited_fields: string[] };
    };
    // The name is the user's, not Open Food Facts': a refresh must not replace it.
    expect(body.name).toBe('Hafermilch');
    expect(body.off.edited_fields).toEqual(['name']);
  });

  it('keeps what was typed where a product has no value, but nothing of a product chosen before (BAR-03, BAR-04)', async () => {
    const OAT_DRINK = proposal({
      barcode: '2000000000015',
      name: 'Haferdrink',
      brand: null,
      nutrients: { kcal: 46, protein: null, carbs: 6.7, sugar: 3.3, fat: null },
      category_key: null,
    });
    const { fetchMock, user } = renderSearch({
      'GET /api/ingredients/off-search': page([found(MILK), found(OAT_DRINK)]),
      'POST /api/ingredients': Response.json(ingredient({ id: 'ing-new' }), { status: 201 }),
    });
    await user.click(await screen.findByTestId(testIds.newIngredient));
    const form = await screen.findByTestId(testIds.ingredientForm);
    await user.type(within(form).getByLabelText('Name'), 'Milch');
    await user.type(within(form).getByLabelText('Protein'), '1');

    // Typed first, then a product without a protein value: the typed value stays.
    await user.click(within(form).getByRole('button', { name: 'Search Open Food Facts' }));
    let dialog = await screen.findByTestId(testIds.offSearchDialog);
    await user.click((await within(dialog).findAllByTestId(testIds.offSearchResult))[1]!);
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(within(form).getByLabelText('Protein')).toHaveValue('1');

    // Milch has a brand and every value; the oat drink chosen after it has neither brand nor fat,
    // and those were Milch's, not typed.
    await user.click(within(form).getByRole('button', { name: 'Search Open Food Facts' }));
    dialog = await screen.findByTestId(testIds.offSearchDialog);
    await user.click((await within(dialog).findAllByTestId(testIds.offSearchResult))[0]!);
    await waitFor(() => expect(within(form).getByLabelText('Brand')).toHaveValue('Weidehof'));
    await user.click(within(form).getByRole('button', { name: 'Search Open Food Facts' }));
    dialog = await screen.findByTestId(testIds.offSearchDialog);
    await user.click((await within(dialog).findAllByTestId(testIds.offSearchResult))[1]!);
    await waitFor(() => expect(within(form).getByLabelText('Name')).toHaveValue('Haferdrink'));
    expect(within(form).getByLabelText('Brand')).toHaveValue('');
    expect(within(form).getByLabelText('Fat')).toHaveValue('');
    expect(within(form).getByLabelText('Protein')).toHaveValue('');
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(1));
    await expect(requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()).resolves.toMatchObject({
      name: 'Haferdrink',
      nutrients: { kcal: 46, carbs: 6.7, sugar: 3.3 },
      off: { edited_fields: [] },
    });
  });

  it("keeps the chosen category when the product doesn't suggest one", async () => {
    const { user } = renderSearch({
      'GET /api/ingredients/off-search': page([
        found(MILK),
        found(proposal({ barcode: '2000000000015', name: 'Hafermilch', category_key: null })),
      ]),
    });
    await user.click(await screen.findByTestId(testIds.newIngredient));
    const form = await screen.findByTestId(testIds.ingredientForm);
    const category = within(form).getByLabelText('Category');
    await waitFor(() => expect(category).toHaveValue('cat-other'));
    await user.selectOptions(category, 'cat-cheese');
    await user.type(within(form).getByLabelText('Name'), 'Milch');
    await user.click(within(form).getByRole('button', { name: 'Search Open Food Facts' }));
    let dialog = await screen.findByTestId(testIds.offSearchDialog);

    // Without a guess, the user's category stays …
    await user.click((await within(dialog).findAllByTestId(testIds.offSearchResult))[1]!);
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    expect(category).toHaveValue('cat-cheese');

    // … while a product's guess replaces it.
    await user.click(within(form).getByRole('button', { name: 'Search Open Food Facts' }));
    dialog = await screen.findByTestId(testIds.offSearchDialog);
    await user.click((await within(dialog).findAllByTestId(testIds.offSearchResult))[0]!);
    await waitFor(() => expect(category).toHaveValue('cat-dairy_eggs'));
  });

  it('links to a product that is already in MealMate', async () => {
    const { user, router } = renderSearch({
      'GET /api/ingredients/ing-known': ingredient({ ...KNOWN, id: 'ing-known' }),
    });
    const dialog = await openSearch(user);

    const known = await within(dialog).findByRole('link', { name: /^Vollmilch \(Alpenhof\)/ });
    expect(known).toHaveTextContent('Already in MealMate');
    await user.click(known);

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-known'));
    expect(screen.queryByTestId(testIds.ingredientForm)).not.toBeInTheDocument();
  });

  it('says when nothing is found; the values can still be typed', async () => {
    const { user } = renderSearch({ 'GET /api/ingredients/off-search': page([]) });
    const dialog = await openSearch(user, 'Quittenbrot');

    expect(await within(dialog).findByTestId(testIds.offSearchEmpty)).toHaveTextContent(
      'Nothing found – try brand and product name, or enter the values yourself.',
    );
    await user.keyboard('{Escape}');
    const form = screen.getByTestId(testIds.ingredientForm);
    expect(within(form).getByLabelText('Name')).toHaveValue('Quittenbrot');
  });

  it.each([
    ['busy', errorResponse(503, 'off.busy')],
    ['unavailable', errorResponse(503, 'off.unavailable')],
  ])('says Open Food Facts is slow (%s) and tries again on request', async (_case, answer) => {
    let calls = 0;
    const { fetchMock, user } = renderSearch({
      'GET /api/ingredients/off-search': () => {
        calls += 1;
        return calls === 1 ? answer : page([found(MILK)]);
      },
    });
    const dialog = await openSearch(user);

    expect(await within(dialog).findByText('Open Food Facts is slow – try again.')).toBeVisible();
    await user.click(within(dialog).getByRole('button', { name: 'Try again' }));
    expect(await within(dialog).findAllByTestId(testIds.offSearchResult)).toHaveLength(1);
    expect(searches(fetchMock)).toEqual([
      { q: 'Milch', page: '1' },
      { q: 'Milch', page: '1' },
    ]);
  });

  it('loads more results', async () => {
    const { fetchMock, user } = renderSearch({
      'GET /api/ingredients/off-search': (request: Request) =>
        new URL(request.url).searchParams.get('page') === '1'
          ? page([found(MILK)], { has_more: true })
          : page([found(OATS)], { page: 2 }),
    });
    const dialog = await openSearch(user);
    await within(dialog).findAllByTestId(testIds.offSearchResult);

    await user.click(within(dialog).getByRole('button', { name: 'More results' }));

    await waitFor(() =>
      expect(within(dialog).getAllByTestId(testIds.offSearchResult)).toHaveLength(2),
    );
    expect(within(dialog).getAllByTestId(testIds.offSearchResult)[1]).toHaveTextContent(
      'Haferflocken zart (Kornmühle)500 g · 372 kcal per 100 g',
    );
    expect(within(dialog).queryByTestId(testIds.offSearchMore)).not.toBeInTheDocument();
    expect(searches(fetchMock)).toEqual([
      { q: 'Milch', page: '1' },
      { q: 'Milch', page: '2' },
    ]);
  });

  it('shows a product only once when it moved to the next page', async () => {
    const { user } = renderSearch({
      'GET /api/ingredients/off-search': (request: Request) =>
        new URL(request.url).searchParams.get('page') === '1'
          ? page([found(MILK)], { has_more: true })
          : page([found(MILK), found(OATS)], { page: 2 }),
    });
    const dialog = await openSearch(user);
    await within(dialog).findAllByTestId(testIds.offSearchResult);

    await user.click(within(dialog).getByRole('button', { name: 'More results' }));

    await waitFor(() =>
      expect(within(dialog).getAllByTestId(testIds.offSearchResult)[1]).toHaveTextContent(
        'Haferflocken zart',
      ),
    );
    expect(
      within(dialog)
        .getAllByTestId(testIds.offSearchResult)
        .map((result) => result.textContent),
    ).toEqual([
      'Frische Vollmilch 3,5 % (Weidehof)1 l · 64 kcal per 100 ml',
      'Haferflocken zart (Kornmühle)500 g · 372 kcal per 100 g',
    ]);
  });

  it('falls back to Other when the guessed category was deleted (REF-01)', async () => {
    const { user } = renderSearch({
      'GET /api/categories': CATEGORIES_AFTER_DELETE,
      'GET /api/ingredients/off-search': page([found(proposal({ category_key: 'cheese' }))]),
    });
    const dialog = await openSearch(user);
    const [first] = await within(dialog).findAllByTestId(testIds.offSearchResult);
    await user.click(first!);

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    const form = screen.getByTestId(testIds.ingredientForm);
    await waitFor(() => expect(within(form).getByLabelText('Category')).toHaveValue('cat-other'));
  });
});
