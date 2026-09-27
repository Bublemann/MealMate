import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { errorResponse, mockApi, requestsTo } from '@/test/api';
import { ingredient, REFERENCE_ROUTES, summary } from '@/test/ingredients';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const ALL = [
  // The server's order; the screen groups by the categories' walking order.
  summary('Butter', 'dairy_eggs', { product_count: 1 }),
  summary('Salz', 'other'),
  summary('Äpfel', 'fruit_vegetables', { product_count: 2 }),
  summary('Milch', 'dairy_eggs', { base_unit: 'ml' }),
];

function listIngredients(request: Request) {
  const q = new URL(request.url).searchParams.get('q');
  if (!q) return ALL;
  return q === 'aepfel' ? [ALL[2]] : [];
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
  it('groups the ingredients under their categories in walking order', async () => {
    renderIngredients();

    const list = await screen.findByTestId(testIds.ingredientList);
    const headings = within(list).getAllByRole('heading', { level: 2 });
    expect(headings.map((heading) => heading.textContent)).toEqual([
      'Fruit & vegetables',
      'Dairy & eggs',
      'Other',
    ]);
    const dairy = within(list).getByRole('region', { name: 'Dairy & eggs' });
    const rows = within(dairy).getAllByTestId(testIds.ingredientRow);
    expect(rows.map((row) => row.textContent)).toEqual([
      'Butterg · 1 product',
      'Milchml · 0 products',
    ]);
    expect(within(list).getByRole('link', { name: /^Äpfel/ })).toHaveAttribute(
      'href',
      '/ingredients/ing-äpfel',
    );
    expect(within(list).getByRole('link', { name: /^Äpfel/ })).toHaveTextContent('2 products');
  });

  it('searches on the server once typing pauses', async () => {
    const { fetchMock, user } = renderIngredients();
    await screen.findByTestId(testIds.ingredientList);

    await user.type(screen.getByLabelText('Search ingredients'), 'aepfel');

    await waitFor(() => expect(searchTerms(fetchMock)).toEqual([null, 'aepfel']));
    const list = screen.getByTestId(testIds.ingredientList);
    await waitFor(() => expect(within(list).getAllByTestId(testIds.ingredientRow)).toHaveLength(1));
    expect(within(list).getByRole('heading', { level: 2 })).toHaveTextContent('Fruit & vegetables');
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
  it('creates an ingredient with decimal commas and opens it', async () => {
    const created = ingredient({ id: 'ing-birnen', name: 'Birnen' });
    const { fetchMock, user, router } = renderIngredients({
      'POST /api/ingredients': Response.json(created, { status: 201 }),
      'GET /api/ingredients/ing-birnen/products': [],
    });

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    const form = within(dialog).getByTestId(testIds.ingredientForm);
    await user.type(within(form).getByLabelText('Name'), '  Birnen ');
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
    await user.click(within(form).getByRole('button', { name: 'Create ingredient' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients/ing-birnen'));
    await expect(requestsTo(fetchMock, 'POST /api/ingredients')[0]?.json()).resolves.toEqual({
      name: 'Birnen',
      base_unit: 'g',
      category_id: 'cat-fruit_vegetables',
      piece_weight_g: 180.5,
      manual: { kcal: 57, fat: 0.4 },
    });
    expect(await screen.findByRole('heading', { level: 1, name: 'Birnen' })).toBeVisible();
  });

  it('shows the server field errors next to their fields', async () => {
    const { user } = renderIngredients({
      'POST /api/ingredients': errorResponse(422, 'common.validation', [
        { loc: ['body', 'name'], code: 'taken' },
        { loc: ['body', 'manual', 'kcal'], code: 'out_of_range' },
      ]),
    });

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    await user.type(within(dialog).getByLabelText('Name'), 'Äpfel');
    await user.type(within(dialog).getByLabelText('Calories'), '1000');
    await user.click(within(dialog).getByRole('button', { name: 'Create ingredient' }));

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
        { loc: ['body', 'manual'], code: 'invalid' },
      ]),
    });

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    await user.type(within(dialog).getByLabelText('Name'), 'Äpfel');
    await user.click(within(dialog).getByRole('button', { name: 'Create ingredient' }));

    expect(await within(dialog).findByText('Please check your input.')).toBeVisible();
    expect(within(dialog).getByLabelText('Name')).toHaveAccessibleDescription('Already taken');
  });

  it('refuses numbers it cannot read without asking the server', async () => {
    const { fetchMock, user } = renderIngredients();

    await user.click(await screen.findByTestId(testIds.newIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'New ingredient' });
    await user.type(within(dialog).getByLabelText('Name'), 'Birnen');
    await user.type(within(dialog).getByLabelText('Density (g/ml)'), '1,2,3');
    await user.click(within(dialog).getByRole('button', { name: 'Create ingredient' }));

    expect(within(dialog).getByLabelText('Density (g/ml)')).toHaveAccessibleDescription(
      /^Invalid format/,
    );
    expect(requestsTo(fetchMock, 'POST /api/ingredients')).toHaveLength(0);
  });

  it('points to similar ingredients while typing the name (ING-03)', async () => {
    const { fetchMock, user } = renderIngredients({
      'GET /api/ingredients/similar': (request: Request) =>
        new URL(request.url).searchParams.get('name') === 'Apfel' ? [ALL[2]] : [],
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
