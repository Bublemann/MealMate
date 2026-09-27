import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import i18n from '@/i18n';
import { BEN, CARL, errorResponse, mockApi, requestsTo } from '@/test/api';
import { bareMeal, EGGS, FLOUR, meal, MEAL_ROUTES } from '@/test/meals';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

type Meal = ReturnType<typeof meal>;

function renderDetail(shown: Meal = meal(), routes: Record<string, unknown> = {}) {
  const fetchMock = mockApi({
    ...MEAL_ROUTES,
    [`GET /api/meals/${shown.id}`]: shown,
    'GET /api/meals': [],
    ...routes,
  });
  return { fetchMock, ...renderApp(`/meals/${shown.id}`) };
}

function nutrientRow(name: string): HTMLElement {
  const table = screen.getByTestId(testIds.mealNutrition);
  return within(table).getByRole('rowheader', { name }).closest('tr') as HTMLElement;
}

describe('MealDetailScreen', () => {
  it('shows the photo, facts, ingredients and instructions as plain text (MEAL-06)', async () => {
    const withMarkup = meal({ instructions: '<b>Nicht fett</b>\nZweite Zeile' });
    renderDetail(withMarkup);

    expect(await screen.findByRole('heading', { level: 1, name: 'Pfannkuchen' })).toBeVisible();
    const photo = screen.getByTestId(testIds.mealPhoto);
    expect(photo).toHaveAttribute('src', '/api/media/abc.webp?exp=1&sig=x');
    expect(photo).toHaveAccessibleName('Pfannkuchen');
    const detail = screen.getByTestId(testIds.screenMeal);
    expect(detail).toHaveTextContent('Servings2');
    expect(detail).toHaveTextContent('CuisineGerman');
    expect(within(detail).getByRole('list', { name: 'Tags' })).toHaveTextContent('schnell');

    const rows = within(screen.getByTestId(testIds.mealIngredients)).getAllByRole('listitem');
    expect(rows.map((row) => row.textContent)).toEqual([
      '200 gMehl',
      '300 mlMilch',
      '2 pcsEier · Größe M',
      'Salz · to taste',
    ]);
    expect(within(rows[0] as HTMLElement).getByRole('link', { name: 'Mehl' })).toHaveAttribute(
      'href',
      `/ingredients/${FLOUR.id}`,
    );

    const instructions = screen.getByTestId(testIds.mealInstructions);
    expect(instructions.textContent).toBe('<b>Nicht fett</b>\nZweite Zeile');
    expect(instructions.querySelector('b')).toBeNull();
    expect(instructions).toHaveClass('whitespace-pre-wrap');
  });

  it('opens the source in a new tab without access to the app (MEAL-05)', async () => {
    renderDetail();

    const source = await screen.findByTestId(testIds.mealSourceLink);
    expect(source).toHaveAttribute('href', 'https://example.org/pfannkuchen');
    expect(source).toHaveAttribute('target', '_blank');
    expect(source).toHaveAttribute('rel', 'noopener noreferrer');
    expect(source).toHaveAccessibleName(/^Open recipe ?\(opens in a new tab\)$/);
  });

  it('shows the nutrition per meal and per serving with the incomplete marker (NUT-03/04)', async () => {
    renderDetail();

    await screen.findByTestId(testIds.mealNutrition);
    expect(nutrientRow('Calories')).toHaveTextContent('1,106 kcal553 kcal');
    expect(nutrientRow('Fat')).toHaveTextContent('30.3 g15.1 g');
    const incomplete = screen.getByTestId(testIds.mealIncomplete);
    expect(incomplete).toHaveTextContent('Incomplete');
    expect(incomplete).toHaveTextContent('Salz: no amount');
    expect(screen.queryByTestId(testIds.mealEstimate)).not.toBeInTheDocument();
  });

  it('groups unknown values per ingredient and marks estimates (NUT-04/05)', async () => {
    await i18n.changeLanguage('de');
    const base = meal();
    renderDetail(
      meal({
        nutrition: {
          ...base.nutrition,
          per_meal: { ...base.nutrition.per_meal, sugar: null },
          estimate: true,
          missing: [
            {
              ingredient_id: EGGS.id,
              ingredient_name: 'Eier',
              reason: 'unknown_value',
              nutrient: 'sugar',
            },
            {
              ingredient_id: EGGS.id,
              ingredient_name: 'Eier',
              reason: 'unknown_value',
              nutrient: 'fat',
            },
            {
              ingredient_id: 'ing-x',
              ingredient_name: 'Rübe',
              reason: 'not_convertible',
              nutrient: null,
            },
            {
              ingredient_id: 'ing-y',
              ingredient_name: 'Zimt',
              reason: 'unknown_value',
              nutrient: null,
            },
          ],
        },
      }),
    );

    await screen.findByTestId(testIds.mealNutrition);
    expect(nutrientRow('Kalorien')).toHaveTextContent('1.106 kcal553 kcal');
    expect(nutrientRow('davon Zucker')).toHaveTextContent('–7,5 g');
    const lines = within(screen.getByTestId(testIds.mealIncomplete)).getAllByRole('listitem');
    expect(lines.map((line) => line.textContent)).toEqual([
      'Eier: davon Zucker und Fett unbekannt',
      'Rübe: Menge lässt sich nicht umrechnen (Stückgewicht oder Dichte fehlt)',
      'Zimt: Nährwerte unbekannt',
    ]);
    expect(screen.getByTestId(testIds.mealEstimate)).toHaveTextContent('Schätzung');
  });

  it('offers Edit and Delete to the owner and deletes after asking', async () => {
    const { fetchMock, user, router } = renderDetail(meal(), {
      'DELETE /api/meals/meal-pancakes': null,
    });

    expect(await screen.findByTestId(testIds.editMeal)).toHaveAttribute(
      'href',
      '/meals/meal-pancakes/edit',
    );
    await user.click(screen.getByTestId(testIds.deleteMeal));
    const confirm = await screen.findByRole('alertdialog', { name: 'Delete Pfannkuchen?' });
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals'));
    expect(requestsTo(fetchMock, 'DELETE /api/meals/meal-pancakes')).toHaveLength(1);
  });

  it("shows the owner and no Edit or Delete on someone else's meal (VIS-04)", async () => {
    renderDetail(meal({ owner: BEN, is_owner: false }));

    expect(await screen.findByText('by Ben')).toBeVisible();
    expect(screen.getByTestId(testIds.copyMeal)).toBeVisible();
    expect(screen.queryByTestId(testIds.editMeal)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.deleteMeal)).not.toBeInTheDocument();
  });

  it('copies the meal with one tap and opens the copy (MEAL-08)', async () => {
    const copy = meal({
      id: 'meal-copy',
      based_on: { meal_id: 'meal-pancakes', name: 'Pfannkuchen', owner: BEN },
    });
    const { fetchMock, user, router } = renderDetail(meal({ owner: BEN, is_owner: false }), {
      'POST /api/meals/meal-pancakes/copy': Response.json(copy, { status: 201 }),
    });

    await user.click(await screen.findByRole('button', { name: 'Copy to my meals' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals/meal-copy'));
    expect(await screen.findByTestId(testIds.mealBasedOn)).toHaveTextContent(
      'Based on Pfannkuchen by Ben',
    );
    expect(requestsTo(fetchMock, 'POST /api/meals/meal-pancakes/copy')).toHaveLength(1);
    // The copy is loaded from the cache the copy request filled.
    expect(requestsTo(fetchMock, 'GET /api/meals/meal-copy')).toHaveLength(0);
  });

  it('links "based on" to the original and renders its names as text', async () => {
    renderDetail(
      meal({
        based_on: { meal_id: 'meal-orig', name: '<i>Omas</i> Pfannkuchen', owner: CARL },
      }),
    );

    const basedOn = await screen.findByTestId(testIds.mealBasedOn);
    expect(basedOn).toHaveTextContent('Based on <i>Omas</i> Pfannkuchen by Carl');
    expect(basedOn.querySelector('i')).toBeNull();
    expect(within(basedOn).getByRole('link')).toHaveAttribute('href', '/meals/meal-orig');
  });

  it('asks to add ingredients when the meal has none', async () => {
    renderDetail(bareMeal());

    expect(
      await screen.findByText('Add ingredients with amounts to see the nutrition.'),
    ).toBeVisible();
    expect(screen.queryByTestId(testIds.mealNutrition)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.mealPhoto)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.mealSourceLink)).not.toBeInTheDocument();
  });

  it('says a meal it cannot see does not exist', async () => {
    mockApi({ ...MEAL_ROUTES, 'GET /api/meals/meal-gone': errorResponse(404, 'common.not_found') });
    renderApp('/meals/meal-gone');

    expect(await screen.findByRole('alert')).toHaveTextContent("This doesn't exist (any more).");
  });
});
