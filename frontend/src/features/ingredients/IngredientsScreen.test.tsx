import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { errorResponse, heldRoute, mockApi, requestsTo } from '@/test/api';
import {
  CATEGORIES,
  CATEGORIES_WITH_ADDED,
  ingredient,
  REFERENCE_ROUTES,
  summary,
} from '@/test/ingredients';
import i18n from '@/i18n';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const ALL = [
  // The server's dictionary order (ING-03), which the screen keeps, although "Other" comes last
  // in the categories' walking order.
  summary('Alufolie', 'other'),
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

/** The server's answer: any of the categories asked for (ING-03), then the search. */
function listIngredients(request: Request) {
  const params = new URL(request.url).searchParams;
  const categories = params.getAll('category_id');
  const inCategories = categories.length
    ? ALL.filter((ingredient) => categories.includes(ingredient.category_id))
    : ALL;
  const q = params.get('q');
  if (!q) return inCategories;
  return q === 'aepfel' ? inCategories.filter((ingredient) => ingredient === ALL[1]) : [];
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

function categoriesAskedFor(fetchMock: ReturnType<typeof mockApi>) {
  return requestsTo(fetchMock, 'GET /api/ingredients').map((request) =>
    new URL(request.url).searchParams.getAll('category_id'),
  );
}

/** The rows, also while the filter panel hides the list from screen readers. */
function rowTexts() {
  return within(screen.getByTestId(testIds.ingredientList))
    .getAllByTestId(testIds.ingredientRow)
    .map((row) => row.textContent);
}

function searchTerms(fetchMock: ReturnType<typeof mockApi>) {
  return requestsTo(fetchMock, 'GET /api/ingredients').map((request) =>
    new URL(request.url).searchParams.get('q'),
  );
}

describe('IngredientsScreen', () => {
  it('shows the pinned block at once and the placeholder only below it (UI-01, UI-03)', async () => {
    const ingredients = heldRoute();
    renderIngredients({ 'GET /api/ingredients': ingredients.route });

    expect(await screen.findByText('Loading…')).toBeVisible();
    expect(screen.getByLabelText('Search ingredients')).toBeVisible();
    expect(screen.getByTestId(testIds.newIngredient)).toHaveAccessibleName('New ingredient');

    await ingredients.answer([]);
    expect(await screen.findByText('No ingredients yet')).toBeVisible();
    expect(screen.queryByTestId(testIds.loadingState)).toBeNull();
    expect(screen.getByLabelText('Search ingredients')).toBeVisible();
    expect(screen.getByTestId(testIds.newIngredient)).toHaveAccessibleName('New ingredient');
  });

  it('shows one A–Z list with category and base unit in the grey line, brand and barcode (ING-03)', async () => {
    renderIngredients();

    const list = await screen.findByTestId(testIds.ingredientList);
    expect(list).toHaveAccessibleName('Ingredients');
    expect(screen.queryAllByRole('heading', { level: 2 })).toEqual([]);
    const rows = within(list).getAllByTestId(testIds.ingredientRow);
    expect(rows.map((row) => row.textContent)).toEqual([
      'AlufolieOther · g',
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

  it('shows “Stk.” in the grey line of an ingredient counted in pieces (ING-03)', async () => {
    await i18n.changeLanguage('de');
    renderIngredients({
      'GET /api/ingredients': [summary('Eier', 'dairy_eggs', { base_unit: 'piece' })],
    });

    const list = await screen.findByTestId(testIds.ingredientList);
    expect(within(list).getByTestId(testIds.ingredientRow)).toHaveTextContent(
      'EierMilchprodukte & Eier · Stk.',
    );
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

  it('turns the tile into “Create …” while searching, filled in as the new name (ING-03)', async () => {
    const { user } = renderIngredients();
    await screen.findByTestId(testIds.ingredientList);
    const search = screen.getByLabelText('Search ingredients');
    const tile = screen.getByTestId(testIds.newIngredient);

    await user.type(search, ' Quitten ');
    expect(tile).toHaveAccessibleName('Create “Quitten”');
    await user.click(tile);
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    expect(within(dialog).getByLabelText('Name')).toHaveValue('Quitten');

    await user.keyboard('{Escape}');
    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await user.clear(search);
    expect(tile).toHaveAccessibleName('New ingredient');
  });

  it('keeps the search and the categories until the app closes, but not in the address or browser storage (UI-01)', async () => {
    const { router, unmount, user } = renderIngredients({
      'GET /api/ingredients/ing-%C3%A4pfel': ingredient({ id: 'ing-äpfel', name: 'Äpfel' }),
    });
    await screen.findByTestId(testIds.ingredientList);
    await user.type(screen.getByLabelText('Search ingredients'), 'aepfel');
    await user.click(screen.getByTestId(testIds.filterButton));
    const panel = await screen.findByTestId(testIds.filterPanel);
    await user.click(within(panel).getByRole('checkbox', { name: 'Fruit & vegetables' }));
    await user.click(within(panel).getByRole('button', { name: 'Done' }));
    const rows = () =>
      within(screen.getByTestId(testIds.ingredientList)).getAllByTestId(testIds.ingredientRow);
    await waitFor(() => expect(rows()).toHaveLength(1));

    // Open the ingredient and come back through the tab bar.
    await user.click(rows()[0]!);
    expect(await screen.findByRole('heading', { level: 1, name: 'Äpfel' })).toBeVisible();
    await user.click(screen.getByTestId(testIds.tabIngredients));

    expect(await screen.findByLabelText('Search ingredients')).toHaveValue('aepfel');
    expect(screen.getByTestId(testIds.newIngredient)).toHaveAccessibleName('Create “aepfel”');
    expect(screen.getByTestId(testIds.filterButton)).toHaveAccessibleName('Filters, 1 active');
    await waitFor(() => expect(rows()).toHaveLength(1));
    await user.click(screen.getByTestId(testIds.filterButton));
    expect(
      within(await screen.findByTestId(testIds.filterPanel)).getByRole('checkbox', {
        name: 'Fruit & vegetables',
      }),
    ).toBeChecked();
    expect(router.state.location.search).toBe('');
    const stored = [localStorage, sessionStorage].flatMap((storage) =>
      Object.keys(storage).map((key) => `${key}=${storage.getItem(key)}`),
    );
    expect(stored.join('\n')).not.toContain('aepfel');
    expect(stored.join('\n')).not.toContain('cat-fruit_vegetables');

    // Started again, the app has forgotten them.
    unmount();
    renderIngredients();
    expect(await screen.findByLabelText('Search ingredients')).toHaveValue('');
    expect(screen.getByTestId(testIds.filterButton)).toHaveAccessibleName('Filters');
  });

  it('opens the filter panel from next to the search, with every category (UI-01)', async () => {
    const { user } = renderIngredients();
    await screen.findByTestId(testIds.ingredientList);
    const button = screen.getByTestId(testIds.filterButton);
    expect(button).toHaveAccessibleName('Filters');

    await user.click(button);

    const panel = await screen.findByRole('dialog', { name: 'Filters' });
    expect(panel).toBe(screen.getByTestId(testIds.filterPanel));
    const group = within(panel).getByRole('group', { name: 'Categories' });
    expect(group).toBe(within(panel).getByTestId(testIds.filterGroup));
    // In the categories' walking order, none ticked: every ingredient shows.
    const boxes = within(group).getAllByRole('checkbox');
    ['Fruit & vegetables', 'Dairy & eggs', 'Cheese', 'Other'].forEach((name, index) => {
      expect(boxes[index]).toHaveAccessibleName(name);
      expect(boxes[index]).not.toBeChecked();
    });
    expect(boxes).toHaveLength(4);
  });

  it('names the categories in the rows and the filter panel as the server does (I18N-04)', async () => {
    const { authSession, user } = renderIngredients({
      'GET /api/categories': CATEGORIES.map((category) =>
        category.key === 'dairy_eggs'
          ? { ...category, names: { de: 'Kühlregal', en: 'Chilled goods' } }
          : category,
      ),
    });
    authSession.setUser({ ...authSession.getState().user!, language: 'de' });
    const { changeLanguage } = await import('@/i18n');
    await changeLanguage('de');

    await waitFor(() => expect(rowTexts()).toContain('MilchKühlregal · ml'));
    expect(rowTexts()).toContain('ÄpfelObst & Gemüse · g');
    await user.click(screen.getByTestId(testIds.filterButton));
    const group = within(await screen.findByTestId(testIds.filterPanel)).getByTestId(
      testIds.filterGroup,
    );
    const boxes = within(group).getAllByRole('checkbox');
    ['Obst & Gemüse', 'Kühlregal', 'Käse', 'Sonstiges'].forEach((name, index) => {
      expect(boxes[index]).toHaveAccessibleName(name);
    });
  });

  it('shows the placeholder in the panel until the categories have loaded (UI-03)', async () => {
    const categories = heldRoute();
    const { user } = renderIngredients({ 'GET /api/categories': categories.route });

    await user.click(await screen.findByTestId(testIds.filterButton));

    const group = within(await screen.findByTestId(testIds.filterPanel)).getByRole('group', {
      name: 'Categories',
    });
    expect(await within(group).findByText('Loading…')).toBeVisible();
    expect(within(group).queryAllByRole('checkbox')).toEqual([]);
    await categories.answer(CATEGORIES);
    await waitFor(() => expect(within(group).getAllByRole('checkbox')).toHaveLength(4));
    expect(within(group).queryByText('Loading…')).toBeNull();
  });

  it('applies each ticked category at once and counts the group on the button (UI-01, ING-03)', async () => {
    const { fetchMock, user } = renderIngredients();
    await screen.findByTestId(testIds.ingredientList);
    const button = screen.getByTestId(testIds.filterButton);
    await user.click(button);
    const group = within(await screen.findByTestId(testIds.filterPanel)).getByRole('group', {
      name: 'Categories',
    });

    await user.click(within(group).getByRole('checkbox', { name: 'Dairy & eggs' }));

    // The list behind the open panel follows at once.
    await waitFor(() =>
      expect(rowTexts()).toEqual([
        'Butter (Kerrygold) with barcodeDairy & eggs · g',
        'MilchDairy & eggs · ml',
      ]),
    );
    expect(button).toHaveAccessibleName('Filters, 1 active');
    expect(button).toHaveTextContent('1');

    // Several categories show the ingredients of any of them; it is still one group.
    await user.click(within(group).getByRole('checkbox', { name: 'Fruit & vegetables' }));
    await waitFor(() =>
      expect(rowTexts()).toEqual([
        'ÄpfelFruit & vegetables · g',
        'Butter (Kerrygold) with barcodeDairy & eggs · g',
        'MilchDairy & eggs · ml',
      ]),
    );
    expect(categoriesAskedFor(fetchMock)).toEqual([
      [],
      ['cat-dairy_eggs'],
      ['cat-fruit_vegetables', 'cat-dairy_eggs'],
    ]);
    expect(button).toHaveAccessibleName('Filters, 1 active');
    expect(within(group).getByRole('checkbox', { name: 'Dairy & eggs' })).toBeChecked();
    expect(within(group).getByRole('checkbox', { name: 'Cheese' })).not.toBeChecked();
  });

  it('resets every group but keeps the search, and closes with “Done” (UI-01)', async () => {
    const { user } = renderIngredients();
    await screen.findByTestId(testIds.ingredientList);
    const search = screen.getByLabelText('Search ingredients');
    await user.type(search, 'aepfel');
    await waitFor(() => expect(rowTexts()).toEqual(['ÄpfelFruit & vegetables · g']));
    const button = screen.getByTestId(testIds.filterButton);
    await user.click(button);
    const panel = await screen.findByRole('dialog', { name: 'Filters' });
    await user.click(within(panel).getByRole('checkbox', { name: 'Dairy & eggs' }));
    await user.click(within(panel).getByRole('checkbox', { name: 'Cheese' }));
    await waitFor(() => expect(screen.queryByTestId(testIds.ingredientList)).toBeNull());
    expect(button).toHaveAccessibleName('Filters, 1 active');

    await user.click(within(panel).getByRole('button', { name: 'Reset' }));

    within(panel)
      .getAllByRole('checkbox')
      .forEach((box) => expect(box).not.toBeChecked());
    expect(button).toHaveAccessibleName('Filters');
    expect(button).not.toHaveTextContent('1');
    expect(search).toHaveValue('aepfel');
    await screen.findByTestId(testIds.ingredientList);
    expect(rowTexts()).toEqual(['ÄpfelFruit & vegetables · g']);
    // The panel stays open until "Done", which gives the focus back to the button.
    expect(panel).toBeVisible();

    await user.click(within(panel).getByRole('button', { name: 'Done' }));

    await waitFor(() => expect(panel).not.toBeInTheDocument());
    expect(button).toHaveFocus();
  });

  it('says “No matches” when the categories hide everything; “Reset filters” clears search and categories (UI-03)', async () => {
    const { user } = renderIngredients();
    await screen.findByTestId(testIds.ingredientList);
    const search = screen.getByLabelText('Search ingredients');
    const button = screen.getByTestId(testIds.filterButton);
    await user.click(button);
    const panel = await screen.findByRole('dialog', { name: 'Filters' });
    // No ingredient is in "Cheese": that is no match, not an empty tab.
    await user.click(within(panel).getByRole('checkbox', { name: 'Cheese' }));
    await user.click(within(panel).getByRole('button', { name: 'Done' }));
    expect(await screen.findByText('No matches')).toBeVisible();
    expect(screen.queryByText('No ingredients yet')).toBeNull();
    await user.type(search, 'Quitten');

    await user.click(screen.getByRole('button', { name: 'Reset filters' }));

    expect(search).toHaveValue('');
    expect(button).toHaveAccessibleName('Filters');
    const list = await screen.findByTestId(testIds.ingredientList);
    expect(within(list).getAllByTestId(testIds.ingredientRow)).toHaveLength(ALL.length);
    await user.click(button);
    within(await screen.findByRole('dialog', { name: 'Filters' }))
      .getAllByRole('checkbox')
      .forEach((box) => expect(box).not.toBeChecked());
  });

  it('shows “No matches” with “Reset filters”, which clears the search (UI-03)', async () => {
    const { user } = renderIngredients();
    await screen.findByTestId(testIds.ingredientList);
    const search = screen.getByLabelText('Search ingredients');

    await user.type(search, 'Quitten');
    expect(await screen.findByText('No matches')).toBeVisible();
    expect(screen.queryByTestId(testIds.ingredientList)).toBeNull();
    // The tile offers to create it; there is no other "Create" button any more.
    expect(screen.getAllByRole('button', { name: 'Create “Quitten”' })).toEqual([
      screen.getByTestId(testIds.newIngredient),
    ]);
    await user.click(screen.getByRole('button', { name: 'Reset filters' }));

    expect(search).toHaveValue('');
    const list = await screen.findByTestId(testIds.ingredientList);
    expect(within(list).getAllByTestId(testIds.ingredientRow)).toHaveLength(ALL.length);
    expect(screen.queryByText('No matches')).toBeNull();
  });

  it('does not call a filled tab empty while the full list loads again (UI-03)', async () => {
    const again = heldRoute();
    let fullLoads = 0;
    const { queryClient, user } = renderIngredients({
      'GET /api/ingredients': (request: Request) => {
        if (new URL(request.url).searchParams.get('q')) return [];
        fullLoads += 1;
        return fullLoads === 1 ? ALL : again.route();
      },
    });
    await screen.findByTestId(testIds.ingredientList);
    await user.type(screen.getByLabelText('Search ingredients'), 'Quitten');
    expect(await screen.findByText('No matches')).toBeVisible();

    // The cache has dropped the unused full list (after its gcTime), so it is loaded again.
    queryClient.removeQueries({ queryKey: ['ingredients', 'list', '', []], exact: true });
    await user.click(screen.getByRole('button', { name: 'Reset filters' }));
    await waitFor(() => expect(fullLoads).toBe(2));

    expect(screen.queryByText('No ingredients yet')).toBeNull();
    expect(screen.queryByText('No matches')).toBeNull();
    await again.answer(ALL);
    const list = await screen.findByTestId(testIds.ingredientList);
    expect(within(list).getAllByTestId(testIds.ingredientRow)).toHaveLength(ALL.length);
  });

  it('shows one line under the pinned block when there are no ingredients yet (UI-03)', async () => {
    const { user } = renderIngredients({ 'GET /api/ingredients': [] });

    expect(await screen.findByText('No ingredients yet')).toBeVisible();
    const tab = screen.getByTestId(testIds.screenIngredients);
    expect(within(tab).queryAllByRole('heading', { level: 2 })).toEqual([]);
    // Only the pinned block's filter button and tile; the scanner is no longer linked from the
    // tab (BAR-01).
    expect(within(tab).getAllByRole('button')).toEqual([
      screen.getByTestId(testIds.filterButton),
      screen.getByTestId(testIds.newIngredient),
    ]);
    expect(within(tab).queryByRole('link')).toBeNull();
    await user.click(screen.getByTestId(testIds.newIngredient));

    expect(await screen.findByRole('dialog', { name: 'New ingredient' })).toBeVisible();
  });

  it('no longer links the barcode scanner from the tab (BAR-01)', async () => {
    renderIngredients();

    await screen.findByTestId(testIds.ingredientList);
    expect(screen.queryByRole('link', { name: 'Scan barcode' })).toBeNull();
    expect(screen.queryByTestId(testIds.scanBarcode)).toBeNull();
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
    await user.type(within(form).getByLabelText('Calories'), '57,5');
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
      nutrients: { kcal: 57.5, fat: 0.4 },
    });
    expect(await screen.findByRole('heading', { level: 1, name: 'Birnen (Hofgut)' })).toBeVisible();
  });

  it('counts an ingredient in pieces: “Pieces” shows the weight per piece, nutrition per 100 g (ING-02)', async () => {
    const created = ingredient({ id: 'ing-eier', name: 'Eier', base_unit: 'piece' });
    const { fetchMock, user } = renderIngredients({
      'POST /api/ingredients': Response.json(created, { status: 201 }),
    });

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    const form = within(dialog).getByTestId(testIds.ingredientForm);
    await user.type(within(form).getByLabelText('Name'), 'Eier');
    const baseUnit = within(form).getByRole('group', { name: 'Base unit' });
    expect(
      within(baseUnit)
        .getAllByRole('radio')
        .map((radio) => radio.closest('label')?.textContent),
    ).toEqual(['Grams (g)', 'Millilitres (ml)', 'Pieces (pcs)']);
    // Grams and millilitres have neither a piece weight nor a density (D-32).
    expect(within(form).queryByLabelText('Weight per piece (g)')).not.toBeInTheDocument();
    expect(within(form).queryByLabelText(/density/i)).not.toBeInTheDocument();
    await user.click(within(baseUnit).getByLabelText('Millilitres (ml)'));
    expect(within(form).queryByLabelText('Weight per piece (g)')).not.toBeInTheDocument();

    await user.click(within(baseUnit).getByLabelText('Pieces (pcs)'));

    const pieceWeight = within(form).getByLabelText('Weight per piece (g)');
    expect(pieceWeight).toHaveAttribute('inputmode', 'decimal');
    expect(
      within(form).getByRole('group', { name: 'Nutrition per 100 g (optional)' }),
    ).toBeVisible();
    await user.type(pieceWeight, '60');
    await user.type(within(form).getByLabelText('Calories'), '155');
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await expect(requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()).resolves.toEqual({
      name: 'Eier',
      base_unit: 'piece',
      category_id: 'cat-other',
      piece_weight_g: 60,
      nutrients: { kcal: 155 },
    });
  });

  it('sends the weight per piece only for “Pieces” (ING-02)', async () => {
    const created = ingredient({ id: 'ing-mehl', name: 'Mehl' });
    const { fetchMock, user } = renderIngredients({
      'POST /api/ingredients': Response.json(created, { status: 201 }),
    });

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    const form = within(dialog).getByTestId(testIds.ingredientForm);
    await user.type(within(form).getByLabelText('Name'), 'Mehl');
    await user.click(within(form).getByLabelText('Pieces (pcs)'));
    await user.type(within(form).getByLabelText('Weight per piece (g)'), '60');
    await user.click(within(form).getByLabelText('Grams (g)'));
    expect(within(form).queryByLabelText('Weight per piece (g)')).not.toBeInTheDocument();
    // Coming back, it is still there.
    await user.click(within(form).getByLabelText('Pieces (pcs)'));
    expect(within(form).getByLabelText('Weight per piece (g)')).toHaveValue('60');
    await user.click(within(form).getByLabelText('Grams (g)'));
    expect(
      within(form).getByRole('group', { name: 'Nutrition per 100 g (optional)' }),
    ).toBeVisible();
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await expect(requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()).resolves.toEqual({
      name: 'Mehl',
      base_unit: 'g',
      category_id: 'cat-other',
    });
  });

  it('offers a category an admin added in walking order, and still starts with Other (REF-01)', async () => {
    const created = ingredient({ id: 'ing-feta', name: 'Feta' });
    const { fetchMock, user } = renderIngredients({
      'GET /api/categories': CATEGORIES_WITH_ADDED,
      'POST /api/ingredients': Response.json(created, { status: 201 }),
    });

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    const category = within(dialog).getByLabelText('Category');
    await waitFor(() => expect(category).toHaveDisplayValue('Other'));
    expect(
      within(category)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['Fruit & vegetables', 'Dairy & eggs', 'Cheese', 'Cheese counter', 'Other']);
    await user.type(within(dialog).getByLabelText('Name'), 'Feta');
    await user.selectOptions(category, 'Cheese counter');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(1));
    await expect(requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()).resolves.toMatchObject({
      name: 'Feta',
      category_id: 'cat-cheese-counter',
    });
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
    await user.click(within(dialog).getByLabelText('Pieces (pcs)'));
    await user.type(within(dialog).getByLabelText('Weight per piece (g)'), '1,2,3');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(within(dialog).getByLabelText('Weight per piece (g)')).toHaveAccessibleDescription(
      /^Invalid format/,
    );
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(0);
  });

  it('points to similar ingredients while typing the name (ING-03)', async () => {
    const { fetchMock, user } = renderIngredients({
      'GET /api/ingredients/similar': (request: Request) =>
        new URL(request.url).searchParams.get('name') === 'Apfel' ? [ALL[1]] : [],
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
