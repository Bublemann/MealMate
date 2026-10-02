import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { errorResponse, heldRoute, mockApi, requestsTo } from '@/test/api';
import { ingredient, REFERENCE_ROUTES, summary } from '@/test/ingredients';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const ALL = [
  // The server's dictionary order (ING-03), which the screen keeps.
  summary('Äpfel', 'fruit_vegetables'),
  summary('Butter', 'dairy_eggs', { brand: 'Kerrygold', barcode: '5011038133535', source: 'off' }),
  summary('Milch', 'dairy_eggs', { base_unit: 'ml' }),
  summary('Salz', 'other'),
];

// jsdom has no camera: the barcode field's scanner shows its manual input.
vi.mock('@/features/scanner/decoder', () => ({
  loadDecoder: () => Promise.resolve(),
  decodeVideoFrame: () => Promise.resolve(null),
}));

function listIngredients(request: Request) {
  const q = new URL(request.url).searchParams.get('q');
  if (!q) return ALL;
  return q === 'aepfel' ? [ALL[0]] : [];
}

function renderIngredients(routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    'GET /api/ingredients': listIngredients,
    'GET /api/ingredients/similar': [],
    ...routes,
  });
  return { fetchMock, ...renderApp('/ingredients') };
}

function searchTerms(fetchMock: ReturnType<typeof mockApi>) {
  return requestsTo(fetchMock, 'GET /api/ingredients').map((request) =>
    new URL(request.url).searchParams.get('q'),
  );
}

describe('IngredientsScreen', () => {
  it('shows only a quiet placeholder until it knows whether there are ingredients (UI-03)', async () => {
    const ingredients = heldRoute();
    renderIngredients({ 'GET /api/ingredients': ingredients.route });

    expect(await screen.findByText('Loading…')).toBeVisible();
    expect(screen.queryByLabelText('Search ingredients')).toBeNull();
    expect(screen.queryByTestId(testIds.newIngredient)).toBeNull();

    await ingredients.answer([]);
    expect(await screen.findByText('No ingredients yet')).toBeVisible();
    expect(screen.queryByTestId(testIds.loadingState)).toBeNull();
    expect(screen.queryByLabelText('Search ingredients')).toBeNull();
  });

  it('shows one A–Z list with category and base unit in the grey line, brand and barcode (ING-03)', async () => {
    renderIngredients();

    const list = await screen.findByTestId(testIds.ingredientList);
    expect(list).toHaveAccessibleName('Ingredients');
    expect(screen.queryAllByRole('heading', { level: 2 })).toEqual([]);
    const rows = within(list).getAllByTestId(testIds.ingredientRow);
    expect(rows.map((row) => row.textContent)).toEqual([
      'ÄpfelFruit & vegetables · g',
      'Butter (Kerrygold) with barcodeDairy & eggs · g',
      'MilchDairy & eggs · ml',
      'SalzOther · g',
    ]);
    expect(within(list).getByRole('link', { name: /^Äpfel/ })).toHaveAttribute(
      'href',
      '/ingredients/ing-äpfel',
    );
    expect(
      within(list).getByRole('link', { name: /^Butter \(Kerrygold\) with barcode/ }),
    ).toHaveAttribute('href', '/ingredients/ing-butter');
  });

  it('searches on the server once typing pauses', async () => {
    const { fetchMock, user } = renderIngredients();
    await screen.findByTestId(testIds.ingredientList);

    await user.type(screen.getByLabelText('Search ingredients'), 'aepfel');

    await waitFor(() => expect(searchTerms(fetchMock)).toEqual([null, 'aepfel']));
    const list = screen.getByTestId(testIds.ingredientList);
    await waitFor(() => expect(within(list).getAllByTestId(testIds.ingredientRow)).toHaveLength(1));
    expect(within(list).getByTestId(testIds.ingredientRow)).toHaveTextContent(
      'ÄpfelFruit & vegetables · g',
    );
  });

  it('offers to create what was searched for when nothing matches', async () => {
    const { user } = renderIngredients();
    await screen.findByTestId(testIds.ingredientList);

    await user.type(screen.getByTestId(testIds.ingredientSearch), 'Quitten');

    expect(await screen.findByText('No ingredient matches “Quitten”.')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Create “Quitten”' }));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    expect(within(dialog).getByLabelText('Name')).toHaveValue('Quitten');
  });

  it('shows one sentence and one action when there are no ingredients yet (UI-03)', async () => {
    const { user } = renderIngredients({ 'GET /api/ingredients': [] });

    expect(await screen.findByText('No ingredients yet')).toBeVisible();
    expect(screen.queryByTestId(testIds.ingredientSearch)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Add ingredient' }));

    expect(await screen.findByRole('dialog', { name: 'New ingredient' })).toBeVisible();
  });

  it.each([
    ['with ingredients', listIngredients],
    ['without ingredients', []],
  ])('offers the barcode scanner %s (BAR-01)', async (_case, answer) => {
    renderIngredients({ 'GET /api/ingredients': answer });

    const link = await screen.findByRole('link', { name: 'Scan barcode' });
    expect(link).toHaveAttribute('href', '/scan');
    expect(link).toHaveAttribute('data-testid', testIds.scanBarcode);
  });

  it('shows a translated error when the list cannot be loaded', async () => {
    renderIngredients({ 'GET /api/ingredients': errorResponse(503, 'common.service_unavailable') });

    expect(
      await screen.findByText('MealMate is unavailable right now. Please try again later.'),
    ).toBeVisible();
  });
});

describe('IngredientFormDialog (create)', () => {
  it('creates an ingredient with brand, barcode, package and decimal commas, and opens it', async () => {
    const created = ingredient({ id: 'ing-birnen', name: 'Birnen', brand: 'Hofgut' });
    const { fetchMock, user, router } = renderIngredients({
      'POST /api/ingredients': Response.json(created, { status: 201 }),
    });

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    const form = within(dialog).getByTestId(testIds.ingredientForm);
    await user.type(within(form).getByLabelText('Name'), '  Birnen ');
    await user.type(within(form).getByLabelText('Brand'), 'Hofgut ');
    // The category defaults to Other.
    await waitFor(() =>
      expect(within(form).getByLabelText('Category')).toHaveDisplayValue('Other'),
    );
    await user.selectOptions(within(form).getByLabelText('Category'), 'cat-fruit_vegetables');
    expect(within(form).getByLabelText('Grams (g)')).toBeChecked();
    await user.type(within(form).getByLabelText('Weight of one piece (g)'), '180,5');
    expect(within(form).getByLabelText('Weight of one piece (g)')).toHaveAttribute(
      'inputmode',
      'decimal',
    );
    await user.type(within(form).getByLabelText('Calories'), '57');
    await user.type(within(form).getByLabelText('Fat'), '0.4');
    await user.type(within(form).getByLabelText('Barcode'), '4006381 333931');
    // The package is optional and folded away under "More".
    const more = within(form).getByText('More: package');
    expect(within(form).getByLabelText('Package contents')).not.toBeVisible();
    await user.click(more);
    await user.type(within(form).getByLabelText('Package contents'), '1,5');
    await user.selectOptions(within(form).getByLabelText('Unit of the contents'), 'kg');
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-birnen'));
    await expect(requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()).resolves.toEqual({
      name: 'Birnen',
      base_unit: 'g',
      category_id: 'cat-fruit_vegetables',
      brand: 'Hofgut',
      barcode: '4006381333931',
      pack_quantity: 1.5,
      pack_unit: 'kg',
      piece_weight_g: 180.5,
      nutrients: { kcal: 57, fat: 0.4 },
    });
    expect(await screen.findByRole('heading', { level: 1, name: 'Birnen (Hofgut)' })).toBeVisible();
  });

  it('scans a barcode into the barcode field', async () => {
    const { user } = renderIngredients();

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    await user.click(within(dialog).getByTestId(testIds.barcodeFieldScan));
    const scanner = await screen.findByTestId(testIds.barcodeScanDialog);
    await user.type(within(scanner).getByTestId(testIds.barcodeInput), '4006381333931{Enter}');

    await waitFor(() => expect(scanner).not.toBeInTheDocument());
    // Only filled in: nothing is looked up, and the form is still open.
    const form = screen.getByTestId(testIds.ingredientForm);
    expect(within(form).getByLabelText('Barcode')).toHaveValue('4006381333931');
    expect(screen.getByRole('dialog', { name: 'New ingredient' })).toBeVisible();
  });

  it('shows a barcode another ingredient has next to the field', async () => {
    const { user } = renderIngredients({
      'POST /api/ingredients': errorResponse(409, 'ingredient.barcode_taken'),
    });

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    await user.type(within(dialog).getByLabelText('Name'), 'Milch');
    await user.type(within(dialog).getByLabelText('Barcode'), '4006381333931');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(within(dialog).getByLabelText('Barcode')).toHaveAccessibleDescription(
        /^Another ingredient already has this barcode/,
      ),
    );
    expect(within(dialog).queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows the server field errors next to their fields', async () => {
    const { user } = renderIngredients({
      'POST /api/ingredients': errorResponse(422, 'common.validation', [
        { loc: ['body', 'name'], code: 'taken' },
        { loc: ['body', 'nutrients', 'kcal'], code: 'out_of_range' },
      ]),
    });

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    await user.type(within(dialog).getByLabelText('Name'), 'Äpfel');
    await user.type(within(dialog).getByLabelText('Calories'), '1000');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(within(dialog).getByLabelText('Name')).toHaveAccessibleDescription('Already taken'),
    );
    expect(within(dialog).getByLabelText('Name')).toBeInvalid();
    expect(within(dialog).getByLabelText('Calories')).toHaveAccessibleDescription('Out of range');
    expect(within(dialog).queryByText('Please check your input.')).not.toBeInTheDocument();
  });

  it('shows a server error for a field the form has no input for', async () => {
    const { user } = renderIngredients({
      'POST /api/ingredients': errorResponse(422, 'common.validation', [
        { loc: ['body', 'name'], code: 'taken' },
        { loc: ['body', 'off'], code: 'invalid' },
      ]),
    });

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    await user.type(within(dialog).getByLabelText('Name'), 'Äpfel');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(await within(dialog).findByText('Please check your input.')).toBeVisible();
    expect(within(dialog).getByLabelText('Name')).toHaveAccessibleDescription('Already taken');
  });

  it('refuses numbers it cannot read without asking the server', async () => {
    const { fetchMock, user } = renderIngredients();

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    await user.type(within(dialog).getByLabelText('Name'), 'Birnen');
    await user.type(within(dialog).getByLabelText('Density (g/ml)'), '1,2,3');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(within(dialog).getByLabelText('Density (g/ml)')).toHaveAccessibleDescription(
      /^Invalid format/,
    );
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(0);
  });

  it('points to similar ingredients while typing the name (ING-03)', async () => {
    const { fetchMock, user } = renderIngredients({
      'GET /api/ingredients/similar': (request: Request) =>
        new URL(request.url).searchParams.get('name') === 'Apfel' ? [ALL[0]] : [],
    });

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    await user.type(within(dialog).getByLabelText('Name'), 'Apfel');

    const hint = await within(dialog).findByTestId(testIds.ingredientSimilar);
    expect(hint).toHaveTextContent('Similar ingredients already exist:');
    expect(within(hint).getByRole('link', { name: 'Äpfel' })).toHaveAttribute(
      'href',
      '/ingredients/ing-äpfel',
    );
    // Debounced: one request for the whole name.
    const names = requestsTo(fetchMock, 'GET /api/ingredients/similar').map((request) =>
      new URL(request.url).searchParams.get('name'),
    );
    expect(names).toEqual(['Apfel']);
  });
});
