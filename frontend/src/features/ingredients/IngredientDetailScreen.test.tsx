import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import i18n from '@/i18n';
import { errorResponse, mockApi, requestsTo, TEST_ADMIN } from '@/test/api';
import { APPLES, REFERENCE_ROUTES, summary, WEIDEHOF_MILK } from '@/test/ingredients';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const MILK_PATH = `/api/ingredients/${WEIDEHOF_MILK.id}`;

function renderDetail(routes: Record<string, unknown> = {}, admin = false, id = 'ing-aepfel') {
  const fetchMock = mockApi({
    ...REFERENCE_ROUTES,
    ...(admin ? { 'GET /api/me': TEST_ADMIN } : {}),
    'GET /api/ingredients/ing-aepfel': APPLES,
    [`GET ${MILK_PATH}`]: WEIDEHOF_MILK,
    'GET /api/ingredients/similar': [],
    ...routes,
  });
  return {
    fetchMock,
    ...renderApp(`/ingredients/${id}`, admin ? { user: TEST_ADMIN } : {}),
  };
}

function nutrientRow(name: RegExp | string): HTMLElement {
  const table = screen.getByTestId(testIds.ingredientNutrition);
  return within(table).getByRole('rowheader', { name }).closest('tr') as HTMLElement;
}

describe('IngredientDetailScreen', () => {
  it('shows the details, who created and changed it, and a deleted creator (ING-06)', async () => {
    renderDetail();

    expect(await screen.findByRole('heading', { level: 1, name: 'Äpfel' })).toBeVisible();
    const screenEl = screen.getByTestId(testIds.screenIngredient);
    expect(await within(screenEl).findByText('Fruit & vegetables')).toBeVisible();
    expect(screenEl).toHaveTextContent('Brandnot set');
    expect(screenEl).toHaveTextContent('Base unitGrams (g)');
    expect(screenEl).toHaveTextContent('Weight of one piece180 g');
    expect(screenEl).toHaveTextContent('Densitynot set');
    expect(screenEl).toHaveTextContent('Barcodenot set');
    expect(screenEl).toHaveTextContent('Packagenot set');
    expect(screenEl).toHaveTextContent('SourceEntered by hand');
    expect(screenEl).toHaveTextContent('Used in3 meals');
    expect(screenEl).toHaveTextContent('Created by Deleted user on 20/09/2026');
    expect(screenEl).toHaveTextContent('Last changed by Anna on 26/09/2026');
    expect(within(screenEl).queryByTestId(testIds.offAttribution)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'All ingredients' })).toHaveAttribute(
      'href',
      '/ingredients',
    );
  });

  it('shows brand, barcode, package and Open Food Facts as the source (BAR-09)', async () => {
    renderDetail({}, false, WEIDEHOF_MILK.id);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Vollmilch (Weidehof)' }),
    ).toBeVisible();
    const screenEl = screen.getByTestId(testIds.screenIngredient);
    expect(screenEl).toHaveTextContent('BrandWeidehof');
    expect(screenEl).toHaveTextContent('Barcode4006381333931');
    expect(screenEl).toHaveTextContent('Package1 l');
    expect(screenEl).toHaveTextContent('SourceOpen Food Facts');
    expect(screenEl).toHaveTextContent('Used in1 meal');
    const link = within(screenEl).getByRole('link', { name: /^Open Food Facts/ });
    expect(link).toHaveAttribute('href', 'https://world.openfoodfacts.org');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('shows the package from its contents when there is no printed size', async () => {
    renderDetail(
      { [`GET ${MILK_PATH}`]: { ...WEIDEHOF_MILK, quantity_text: null, pack_quantity: 1.5 } },
      false,
      WEIDEHOF_MILK.id,
    );

    const screenEl = await screen.findByTestId(testIds.screenIngredient);
    await waitFor(() => expect(screenEl).toHaveTextContent('Package1.5 l'));
  });

  it('shows its own value per nutrient, unknown ones as "–" (NUT-02)', async () => {
    renderDetail();

    await screen.findByTestId(testIds.ingredientNutrition);
    expect(screen.getByRole('heading', { name: 'Nutrition per 100 g' })).toBeVisible();
    expect(nutrientRow('Calories')).toHaveTextContent('52 kcal');
    expect(nutrientRow('Protein')).toHaveTextContent('0.3 g');
    expect(nutrientRow('Carbohydrates')).toHaveTextContent('–');
  });

  it('marks the values a user changed on an Open Food Facts ingredient (BAR-04)', async () => {
    renderDetail({}, false, WEIDEHOF_MILK.id);

    await screen.findByTestId(testIds.ingredientNutrition);
    expect(nutrientRow(/^Fat/)).toHaveTextContent(
      'Changed in MealMate: updates from Open Food Facts keep it.3.6 g',
    );
    expect(nutrientRow('Calories')).toHaveTextContent('64 kcal');
  });

  it('shows an ingredient counted in pieces with its piece weight, nutrition per 100 g (ING-02)', async () => {
    const eggs = {
      ...APPLES,
      id: 'ing-eier',
      name: 'Eier',
      base_unit: 'piece' as const,
      piece_weight_g: 60,
      density_g_per_ml: 1.03,
    };
    renderDetail({ 'GET /api/ingredients/ing-eier': eggs }, false, 'ing-eier');

    expect(await screen.findByRole('heading', { level: 1, name: 'Eier' })).toBeVisible();
    const screenEl = screen.getByTestId(testIds.screenIngredient);
    expect(screenEl).toHaveTextContent('Base unitPieces (pcs)');
    expect(screenEl).toHaveTextContent('Weight of one piece60 g');
    // A density means nothing for pieces.
    expect(screenEl).not.toHaveTextContent('Density');
    expect(screen.getByRole('heading', { name: 'Nutrition per 100 g' })).toBeVisible();
  });

  it('formats numbers in German', async () => {
    await i18n.changeLanguage('de');
    renderDetail();

    await waitFor(() => expect(nutrientRow('Eiweiß')).toHaveTextContent('0,3 g'));
    expect(screen.getByTestId(testIds.screenIngredient)).toHaveTextContent(
      'Verwendet in3 Gerichten',
    );
  });

  describe('newer values from Open Food Facts (BAR-06)', () => {
    const PENDING = {
      ...WEIDEHOF_MILK,
      user_edited_fields: ['nutrients.kcal', 'name', 'brand', 'pack_unit'],
      pending_update: {
        fields: [
          { field: 'nutrients.kcal', current: 65, proposed: 64 },
          { field: 'name', current: 'Vollmilch', proposed: 'Frische Vollmilch' },
          { field: 'brand', current: 'Weidehof', proposed: null },
          { field: 'pack_unit', current: 'l', proposed: 'ml' },
        ],
        off_last_modified_at: '2026-09-25T10:00:00Z',
      },
    } satisfies typeof WEIDEHOF_MILK;

    it('shows them with units and applies them', async () => {
      const applied = { ...WEIDEHOF_MILK, name: 'Frische Vollmilch', pending_update: null };
      const { fetchMock, user } = renderDetail(
        {
          [`GET ${MILK_PATH}`]: PENDING,
          [`POST ${MILK_PATH}/pending-update/apply`]: applied,
        },
        false,
        WEIDEHOF_MILK.id,
      );

      const hint = await screen.findByTestId(testIds.pendingUpdate);
      expect(hint).toHaveTextContent('Open Food Facts has newer values:');
      const changes = within(hint)
        .getAllByRole('listitem')
        .map((item) => item.textContent);
      expect(changes).toEqual([
        'Calories: 65 kcal → 64 kcal',
        'Name: Vollmilch → Frische Vollmilch',
        'Brand: Weidehof → empty',
        'Unit of the contents: l → ml',
      ]);

      await user.click(
        within(hint).getByRole('button', {
          name: 'Apply the newer values for Vollmilch (Weidehof)',
        }),
      );

      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${MILK_PATH}/pending-update/apply`)).toHaveLength(1),
      );
      // The answer is the updated ingredient: shown at once, without loading it again.
      expect(
        await screen.findByRole('heading', { level: 1, name: 'Frische Vollmilch (Weidehof)' }),
      ).toBeVisible();
      expect(screen.queryByTestId(testIds.pendingUpdate)).not.toBeInTheDocument();
    });

    it('ignores them and says when there is nothing left to ignore', async () => {
      const { fetchMock, user } = renderDetail(
        {
          [`GET ${MILK_PATH}`]: PENDING,
          [`POST ${MILK_PATH}/pending-update/ignore`]: errorResponse(
            409,
            'ingredient.no_pending_update',
          ),
        },
        false,
        WEIDEHOF_MILK.id,
      );

      const hint = await screen.findByTestId(testIds.pendingUpdate);
      await user.click(
        within(hint).getByRole('button', {
          name: 'Ignore the newer values for Vollmilch (Weidehof)',
        }),
      );

      expect(await within(hint).findByRole('alert')).toHaveTextContent(
        'There are no newer values for this ingredient (any more).',
      );
      expect(requestsTo(fetchMock, `POST ${MILK_PATH}/pending-update/ignore`)).toHaveLength(1);
    });

    it('formats them in German', async () => {
      await i18n.changeLanguage('de');
      renderDetail({ [`GET ${MILK_PATH}`]: PENDING }, false, WEIDEHOF_MILK.id);

      const hint = await screen.findByTestId(testIds.pendingUpdate);
      expect(hint).toHaveTextContent('Open Food Facts hat neuere Werte:');
      expect(hint).toHaveTextContent('Kalorien: 65 kcal → 64 kcal');
      expect(hint).toHaveTextContent('Marke: Weidehof → leer');
    });
  });

  it('edits only what changed, including the base unit (ING-02)', async () => {
    const { fetchMock, user } = renderDetail({
      'PATCH /api/ingredients/ing-aepfel': {
        ...APPLES,
        brand: 'Hofgut',
        base_unit: 'ml',
        nutrients: { ...APPLES.nutrients, kcal: 55 },
      },
    });

    await user.click(await screen.findByTestId(testIds.editIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Äpfel' });
    expect(within(dialog).queryByTestId(testIds.ingredientSimilar)).not.toBeInTheDocument();
    // Editing is not creating: no search at Open Food Facts here.
    expect(within(dialog).queryByTestId(testIds.offSearchButton)).not.toBeInTheDocument();
    expect(dialog).toHaveTextContent('Changing it converts nothing: check the values.');
    await user.click(within(dialog).getByLabelText('Millilitres (ml)'));
    await user.type(within(dialog).getByLabelText('Brand'), 'Hofgut');
    const kcal = within(dialog).getByLabelText('Calories');
    expect(kcal).toHaveValue('52');
    await user.clear(kcal);
    await user.type(kcal, '55');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await expect(
      requestsTo(fetchMock, 'PATCH /api/ingredients/ing-aepfel')[0]?.json(),
    ).resolves.toEqual({ brand: 'Hofgut', base_unit: 'ml', nutrients: { kcal: 55 } });
    expect(nutrientRow('Calories')).toHaveTextContent('55 kcal');
    expect(screen.getByRole('heading', { level: 1, name: 'Äpfel (Hofgut)' })).toBeVisible();
  });

  it('edits an ingredient counted in pieces; leaving “Pieces” clears its piece weight (ING-02)', async () => {
    const eggs = { ...APPLES, id: 'ing-eier', name: 'Eier', base_unit: 'piece' as const };
    const { fetchMock, user } = renderDetail(
      {
        'GET /api/ingredients/ing-eier': { ...eggs, piece_weight_g: 60 },
        'PATCH /api/ingredients/ing-eier': { ...eggs, base_unit: 'g', piece_weight_g: null },
      },
      false,
      'ing-eier',
    );

    await user.click(await screen.findByTestId(testIds.editIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Eier' });
    expect(within(dialog).getByLabelText('Pieces (pcs)')).toBeChecked();
    expect(within(dialog).getByLabelText('Weight per piece (g)')).toHaveValue('60');
    await user.click(within(dialog).getByLabelText('Grams (g)'));
    expect(within(dialog).getByLabelText('Weight of one piece (g)')).toHaveValue('');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await expect(
      requestsTo(fetchMock, 'PATCH /api/ingredients/ing-eier')[0]?.json(),
    ).resolves.toEqual({ base_unit: 'g', piece_weight_g: null });
  });

  it('clears a barcode and marks the fields a user changed on an Open Food Facts ingredient', async () => {
    const { fetchMock, user } = renderDetail(
      { [`PATCH ${MILK_PATH}`]: { ...WEIDEHOF_MILK, barcode: null, source: 'manual' } },
      false,
      WEIDEHOF_MILK.id,
    );

    await user.click(await screen.findByTestId(testIds.editIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Vollmilch (Weidehof)' });
    expect(within(dialog).getByTestId(testIds.offAttribution)).toBeVisible();
    expect(within(dialog).getByLabelText('Fat')).toHaveAccessibleDescription(
      'Changed in MealMate: updates from Open Food Facts keep it.',
    );
    expect(within(dialog).getByLabelText('Calories')).not.toHaveAccessibleDescription();
    // Packed away under "More", opened because there is a package.
    expect(within(dialog).getByLabelText('Package size as printed')).toBeVisible();
    await user.clear(within(dialog).getByLabelText('Barcode'));
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(dialog).not.toBeInTheDocument());
    await expect(requestsTo(fetchMock, `PATCH ${MILK_PATH}`)[0]?.json()).resolves.toEqual({
      barcode: null,
    });
  });

  it('does not send stored numbers with more decimals than shown unless they were edited', async () => {
    const precise = {
      ...APPLES,
      piece_weight_g: 180.55555555,
      density_g_per_ml: 1.03333333,
      pack_quantity: 0.33333333,
      nutrients: { ...APPLES.nutrients, kcal: 52.66666667, protein: 0.33333333 },
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
    ).resolves.toEqual({ name: 'Äpfel rot', nutrients: { fat: 0.2 } });
  });

  it('shows a barcode another ingredient has next to the field', async () => {
    const { user } = renderDetail({
      'PATCH /api/ingredients/ing-aepfel': errorResponse(409, 'ingredient.barcode_taken'),
    });

    await user.click(await screen.findByTestId(testIds.editIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Äpfel' });
    await user.type(within(dialog).getByLabelText('Barcode'), '4006381333931');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(within(dialog).getByLabelText('Barcode')).toHaveAccessibleDescription(
        /^Another ingredient already has this barcode/,
      ),
    );
  });

  it('warns that changing the barcode of a product from Open Food Facts ends its updates', async () => {
    const { user } = renderDetail({}, false, WEIDEHOF_MILK.id);

    await user.click(await screen.findByTestId(testIds.editIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Vollmilch (Weidehof)' });
    const barcode = within(dialog).getByLabelText('Barcode');
    expect(barcode).not.toHaveAttribute('readonly');
    expect(barcode).toHaveAccessibleDescription(
      /^Changing it turns off the updates from Open Food Facts for this ingredient/,
    );
  });

  it('shows the plain barcode hint for an ingredient typed by hand', async () => {
    const { user } = renderDetail();

    await user.click(await screen.findByTestId(testIds.editIngredient));
    const dialog = await screen.findByRole('dialog', { name: 'Edit Äpfel' });
    expect(within(dialog).getByLabelText('Barcode')).toHaveAccessibleDescription(
      'Optional: the 8, 12 or 13 digits under the bars.',
    );
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
        'POST /api/admin/ingredients/ing-aepfel/merge': { ...APPLES, id: apfel.id, name: 'Apfel' },
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
    expect(confirm).toHaveTextContent('All uses of Äpfel in meals and lists move to Apfel');
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
          { code: 'ingredient.in_use', params: { meals: 1, lists: 3 }, fields: [] },
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
        'This ingredient is still in use (meals: 1, lists: 3). Merge it into another ingredient instead.',
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
