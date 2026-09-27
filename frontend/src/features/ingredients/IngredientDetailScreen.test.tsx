import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import i18n from '@/i18n';
import { errorResponse, mockApi, requestsTo, TEST_ADMIN } from '@/test/api';
import { APPLES, product, REFERENCE_ROUTES, summary } from '@/test/ingredients';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const PRODUCTS = [
  product(),
  product({
    id: 'prod-2',
    barcode: '4000000000013',
    name: null,
    brand: null,
    quantity_text: null,
    nutrients: { kcal: 49, protein: 0.3, carbs: null, sugar: null, fat: null },
  }),
];

function renderDetail(routes: Record<string, unknown> = {}, admin = false) {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    ...(admin ? { 'GET /api/me': TEST_ADMIN } : {}),
    'GET /api/ingredients/ing-aepfel': APPLES,
    'GET /api/ingredients/ing-aepfel/products': PRODUCTS,
    'GET /api/ingredients/similar': [],
    ...routes,
  });
  return {
    fetchMock,
    ...renderApp('/ingredients/ing-aepfel', admin ? { user: TEST_ADMIN } : {}),
  };
}

function nutrientRow(name: string): HTMLElement {
  const table = screen.getByTestId(testIds.ingredientNutrition);
  return within(table).getByRole('rowheader', { name }).closest('tr') as HTMLElement;
}

describe('IngredientDetailScreen', () => {
  it('shows the properties, who created and changed it, and a deleted creator (ING-06)', async () => {
    renderDetail();

    expect(await screen.findByRole('heading', { level: 1, name: 'Äpfel' })).toBeVisible();
    const screenEl = screen.getByTestId(testIds.screenIngredient);
    expect(await within(screenEl).findByText('Fruit & vegetables')).toBeVisible();
    expect(screenEl).toHaveTextContent('Base unitGrams (g)');
    expect(screenEl).toHaveTextContent('Weight of one piece180 g');
    expect(screenEl).toHaveTextContent('Densitynot set');
    expect(screenEl).toHaveTextContent('Created by Deleted user on 20/09/2026');
    expect(screenEl).toHaveTextContent('Last changed by Anna on 26/09/2026');
    expect(screen.getByRole('link', { name: 'All ingredients' })).toHaveAttribute(
      'href',
      '/ingredients',
    );
  });

  it('shows each nutrient with its source and the product average next to a manual value', async () => {
    renderDetail();

    await screen.findByTestId(testIds.ingredientNutrition);
    expect(screen.getByRole('heading', { name: 'Nutrition per 100 g' })).toBeVisible();
    expect(nutrientRow('Calories')).toHaveTextContent('52 kcal');
    expect(nutrientRow('Calories')).toHaveTextContent('Entered by hand');
    expect(nutrientRow('Calories')).toHaveTextContent('Products: Ø 49.5 kcal');
    expect(nutrientRow('Protein')).toHaveTextContent('0.3 g');
    expect(nutrientRow('Protein')).toHaveTextContent('Average of 2 products');
    expect(nutrientRow('Protein')).not.toHaveTextContent('Ø');
    expect(nutrientRow('Carbohydrates')).toHaveTextContent('–Unknown');
  });

  it('formats numbers in German', async () => {
    await i18n.changeLanguage('de');
    renderDetail();

    await waitFor(() => expect(nutrientRow('Kalorien')).toHaveTextContent('Produkte: Ø 49,5 kcal'));
    expect(nutrientRow('Eiweiß')).toHaveTextContent('0,3 g');
  });

  it('lists the products with their values', async () => {
    renderDetail();

    const list = await screen.findByTestId(testIds.productList);
    const rows = within(list).getAllByTestId(testIds.productRow);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Elstar · Hofgut');
    expect(rows[0]).toHaveTextContent('Barcode 4000000000006 · 1 kg');
    expect(rows[0]).toHaveTextContent('Per 100 g: Calories 50 kcal · Protein 0.3 g');
    expect(rows[1]).toHaveTextContent('Product without a name');
  });

  it('adds a product entered by hand', async () => {
    const { fetchMock, user } = renderDetail({
      'POST /api/products': Response.json(product({ id: 'prod-3' }), { status: 201 }),
    });

    await user.click(await screen.findByTestId(testIds.addProduct));
    const dialog = await screen.findByRole('dialog', { name: 'Add product' });
    expect(dialog).toHaveTextContent('Nutrition per 100 g');
    const barcode = within(dialog).getByLabelText('Barcode');
    expect(barcode).toHaveAttribute('inputmode', 'numeric');
    await user.type(barcode, '4000000000020');
    await user.type(within(dialog).getByLabelText('Brand'), 'Bio');
    await user.type(within(dialog).getByLabelText('Package contents'), '1,5');
    await user.selectOptions(within(dialog).getByLabelText('Unit of the contents'), 'kg');
    await user.type(within(dialog).getByLabelText('Calories'), '47,5');
    await user.click(within(dialog).getByRole('button', { name: 'Add product' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await expect(requestsTo(fetchMock, 'POST /api/products')[0]?.json()).resolves.toEqual({
      barcode: '4000000000020',
      ingredient_id: 'ing-aepfel',
      brand: 'Bio',
      pack_quantity: 1.5,
      pack_unit: 'kg',
      nutrients: { kcal: 47.5 },
    });
    // The nutrition average changes: the ingredient and its products are loaded again.
    await waitFor(() =>
      expect(requestsTo(fetchMock, 'GET /api/ingredients/ing-aepfel')).toHaveLength(2),
    );
  });

  it('sends only the changed fields of a product (BAR-04) and shows a taken barcode', async () => {
    const { fetchMock, user } = renderDetail({
      'PATCH /api/products/prod-1': errorResponse(422, 'common.validation', [
        { loc: ['body', 'barcode'], code: 'taken' },
      ]),
    });

    await user.click(await screen.findByRole('button', { name: 'Edit product Elstar' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit product' });
    expect(within(dialog).getByLabelText('Calories')).toHaveValue('50');
    const barcode = within(dialog).getByLabelText('Barcode');
    await user.clear(barcode);
    await user.type(barcode, '4000000000013');
    await user.clear(within(dialog).getByLabelText('Protein'));
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(within(dialog).getByLabelText('Barcode')).toHaveAccessibleDescription(
        /^Already taken/,
      ),
    );
    await expect(requestsTo(fetchMock, 'PATCH /api/products/prod-1')[0]?.json()).resolves.toEqual({
      barcode: '4000000000013',
      nutrients: { protein: null },
    });
  });

  it('shows a server error for a field the product form has no input for', async () => {
    const { user } = renderDetail({
      'POST /api/products': errorResponse(422, 'common.validation', [
        { loc: ['body', 'ingredient_id'], code: 'invalid' },
      ]),
    });

    await user.click(await screen.findByTestId(testIds.addProduct));
    const dialog = await screen.findByRole('dialog', { name: 'Add product' });
    await user.type(within(dialog).getByLabelText('Barcode'), '4000000000020');
    await user.click(within(dialog).getByRole('button', { name: 'Add product' }));

    expect(await within(dialog).findByText('Please check your input.')).toBeVisible();
  });

  it('does not send stored numbers with more decimals than shown unless they were edited (BAR-04)', async () => {
    const precise = product({
      pack_quantity: 0.33333333,
      nutrients: { kcal: 4.66666667, protein: 0.12345678, carbs: null, sugar: null, fat: null },
    });
    const { fetchMock, user } = renderDetail({
      'GET /api/ingredients/ing-aepfel/products': [precise],
      'PATCH /api/products/prod-1': { ...precise, name: 'Elstar rot' },
    });

    await user.click(await screen.findByRole('button', { name: 'Edit product Elstar' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit product' });
    expect(within(dialog).getByLabelText('Calories')).toHaveValue('4.666667');
    await user.type(within(dialog).getByLabelText('Product name'), ' rot');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await expect(requestsTo(fetchMock, 'PATCH /api/products/prod-1')[0]?.json()).resolves.toEqual({
      name: 'Elstar rot',
    });
  });

  it('edits only what changed and locks the base unit while products exist (ING-02)', async () => {
    const { fetchMock, user } = renderDetail({
      'PATCH /api/ingredients/ing-aepfel': {
        ...APPLES,
        manual: { ...APPLES.manual, kcal: 55 },
        nutrition: { ...APPLES.nutrition, kcal: { ...APPLES.nutrition.kcal, value: 55 } },
      },
    });

    await user.click(await screen.findByTestId(testIds.editIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Äpfel' });
    const grams = within(dialog).getByLabelText('Grams (g)');
    expect(grams).toBeChecked();
    expect(grams).toBeDisabled();
    expect(within(dialog).getByLabelText('Millilitres (ml)')).toBeDisabled();
    expect(dialog).toHaveTextContent("Can't be changed while products are linked.");
    expect(within(dialog).queryByTestId(testIds.ingredientSimilar)).not.toBeInTheDocument();
    const kcal = within(dialog).getByLabelText('Calories');
    expect(kcal).toHaveValue('52');
    await user.clear(kcal);
    await user.type(kcal, '55');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await expect(
      requestsTo(fetchMock, 'PATCH /api/ingredients/ing-aepfel')[0]?.json(),
    ).resolves.toEqual({ manual: { kcal: 55 } });
    expect(nutrientRow('Calories')).toHaveTextContent('55 kcal');
  });

  it('does not send stored numbers with more decimals than shown unless they were edited', async () => {
    const precise = {
      ...APPLES,
      piece_weight_g: 180.55555555,
      density_g_per_ml: 1.03333333,
      manual: { ...APPLES.manual, kcal: 52.66666667, protein: 0.33333333 },
    };
    const { fetchMock, user } = renderDetail({
      'GET /api/ingredients/ing-aepfel': precise,
      'PATCH /api/ingredients/ing-aepfel': { ...precise, name: 'Äpfel rot' },
    });

    await user.click(await screen.findByTestId(testIds.editIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Äpfel' });
    expect(within(dialog).getByLabelText('Protein')).toHaveValue('0.333333');
    await user.type(within(dialog).getByLabelText('Name'), ' rot');
    await user.clear(within(dialog).getByLabelText('Fat'));
    await user.type(within(dialog).getByLabelText('Fat'), '0,2');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await expect(
      requestsTo(fetchMock, 'PATCH /api/ingredients/ing-aepfel')[0]?.json(),
    ).resolves.toEqual({ name: 'Äpfel rot', manual: { fat: 0.2 } });
  });

  it('shows the base unit error of the server next to the base unit', async () => {
    const { user } = renderDetail({
      'GET /api/ingredients/ing-aepfel': { ...APPLES, product_count: 0 },
      'PATCH /api/ingredients/ing-aepfel': errorResponse(409, 'ingredient.base_unit_locked'),
    });

    await user.click(await screen.findByTestId(testIds.editIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Äpfel' });
    await user.click(within(dialog).getByLabelText('Millilitres (ml)'));
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(
      await within(dialog).findByText("The base unit can't be changed while products are linked."),
    ).toBeVisible();
  });

  it('shows "not found" for an ingredient that is gone', async () => {
    renderDetail({ 'GET /api/ingredients/ing-aepfel': errorResponse(404, 'common.not_found') });

    expect(await screen.findByText("This doesn't exist (any more).")).toBeVisible();
  });
});

describe('IngredientAdminActions', () => {
  it('are only shown to admins', async () => {
    renderDetail();

    await screen.findByTestId(testIds.ingredientNutrition);
    expect(screen.queryByTestId(testIds.mergeIngredient)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.deleteIngredient)).not.toBeInTheDocument();
  });

  it('merge into an ingredient picked from the others, after confirming both names', async () => {
    const apfel = summary('Apfel', 'fruit_vegetables');
    const { fetchMock, user, router } = renderDetail(
      {
        'GET /api/ingredients': (request: Request) =>
          new URL(request.url).searchParams.get('q') === 'Apf'
            ? [summary('Äpfel', 'fruit_vegetables', { id: 'ing-aepfel' }), apfel]
            : [],
        'POST /api/admin/ingredients/ing-aepfel/merge': {
          ...APPLES,
          id: apfel.id,
          name: 'Apfel',
          product_count: 3,
        },
        [`GET /api/ingredients/${apfel.id}/products`]: PRODUCTS,
      },
      true,
    );

    await user.click(await screen.findByTestId(testIds.mergeIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'Merge Äpfel into…' });
    const picker = within(dialog).getByTestId(testIds.ingredientPicker);
    await user.type(within(picker).getByLabelText('Ingredient that stays'), 'Apf');
    const option = await within(picker).findByRole('button', { name: /^Apfel/ });
    // The ingredient itself can't be picked, and nothing is created here.
    expect(within(picker).queryByRole('button', { name: /^Äpfel/ })).not.toBeInTheDocument();
    expect(within(picker).queryByTestId(testIds.ingredientPickerCreate)).not.toBeInTheDocument();
    await user.click(option);

    const confirm = await screen.findByRole('alertdialog', { name: 'Merge Äpfel into Apfel?' });
    expect(confirm).toHaveTextContent('All products of Äpfel and its uses in meals move to Apfel');
    await user.click(within(confirm).getByRole('button', { name: 'Merge' }));

    await waitFor(() => expect(router.state.location.pathname).toBe(`/ingredients/${apfel.id}`));
    await expect(
      requestsTo(fetchMock, 'POST /api/admin/ingredients/ing-aepfel/merge')[0]?.json(),
    ).resolves.toEqual({ into_id: apfel.id });
    expect(await screen.findByRole('heading', { level: 1, name: 'Apfel' })).toBeVisible();
  });

  it('explains why an ingredient in use cannot be deleted', async () => {
    const { user } = renderDetail(
      {
        'DELETE /api/admin/ingredients/ing-aepfel': Response.json(
          { code: 'ingredient.in_use', params: { products: 2, meals: 1 }, fields: [] },
          { status: 409 },
        ),
      },
      true,
    );

    await user.click(await screen.findByRole('button', { name: 'Delete Äpfel' }));
    const confirm = await screen.findByRole('alertdialog', { name: 'Delete Äpfel?' });
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));

    expect(
      await screen.findByText(
        'This ingredient is still in use (products: 2, meals: 1). Merge it into another ingredient instead.',
      ),
    ).toBeVisible();
  });

  it('deletes an unused ingredient and returns to the list', async () => {
    const { user, router } = renderDetail(
      { 'DELETE /api/admin/ingredients/ing-aepfel': null, 'GET /api/ingredients': [] },
      true,
    );

    await user.click(await screen.findByTestId(testIds.deleteIngredient));
    await user.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: 'Delete' }),
    );

    await waitFor(() => expect(router.state.location.pathname).toBe('/ingredients'));
  });
});
