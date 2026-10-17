import { act, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import i18n from '@/i18n';
import { BEN, CARL, errorResponse, mockApi, requestsTo } from '@/test/api';
import { bareMeal, EGGS, FLOUR, meal, MEAL_ROUTES } from '@/test/meals';
import { chooseFromMenu, menuItemNames, openMoreMenu } from '@/test/menu';
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
  afterEach(() => {
    vi.restoreAllMocks();
  });

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
              ingredient_brand: null,
              reason: 'unknown_value',
              nutrient: 'sugar',
            },
            {
              ingredient_id: EGGS.id,
              ingredient_name: 'Eier',
              ingredient_brand: null,
              reason: 'unknown_value',
              nutrient: 'fat',
            },
            {
              ingredient_id: 'ing-x',
              ingredient_name: 'Rübe',
              ingredient_brand: null,
              reason: 'unit_mismatch',
              nutrient: null,
            },
            {
              ingredient_id: 'ing-y',
              ingredient_name: 'Zimt',
              ingredient_brand: null,
              reason: 'unknown_value',
              nutrient: null,
            },
            {
              ingredient_id: 'ing-z',
              ingredient_name: 'Brötchen',
              ingredient_brand: null,
              reason: 'no_piece_weight',
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
      'Rübe: Einheit passt nicht',
      'Zimt: Nährwerte unbekannt',
      'Brötchen: Gewicht pro Stück fehlt',
    ]);
    expect(screen.getByTestId(testIds.mealEstimate)).toHaveTextContent('Schätzung');
  });

  it('offers the owner "Edit", "Copy" and, red and last, "Delete" in the ⋯ menu (MEAL-07, D-39)', async () => {
    const { user } = renderDetail();
    await screen.findByTestId(testIds.mealIngredients);

    const menu = await openMoreMenu(user);

    expect(menuItemNames(menu)).toEqual(['Edit', 'Copy', 'Delete']);
    const remove = within(menu).getByTestId(testIds.deleteMeal);
    expect(menu.lastElementChild).toBe(remove);
    expect(remove.previousElementSibling).toHaveAttribute('role', 'separator');
    // No buttons of their own on the screen.
    await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
    expect(screen.queryByTestId(testIds.copyMeal)).not.toBeInTheDocument();
  });

  it('opens the meal form from "Edit"', async () => {
    const { user, router } = renderDetail();

    await chooseFromMenu(user, testIds.editMeal);

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals/meal-pancakes/edit'));
  });

  it('deletes after asking, and goes back to Meals', async () => {
    const { fetchMock, user, router } = renderDetail(meal(), {
      'DELETE /api/meals/meal-pancakes': null,
    });

    await chooseFromMenu(user, testIds.deleteMeal);
    const confirm = await screen.findByRole('alertdialog', { name: 'Delete Pfannkuchen?' });
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals'));
    expect(requestsTo(fetchMock, 'DELETE /api/meals/meal-pancakes')).toHaveLength(1);
  });

  it("shows the owner and only \"Copy\" on someone else's meal (VIS-04, MEAL-08)", async () => {
    const { user } = renderDetail(meal({ owner: BEN, is_owner: false }));

    expect(await screen.findByText('by Ben')).toBeVisible();
    expect(menuItemNames(await openMoreMenu(user))).toEqual(['Copy']);
  });

  it('copies the meal and opens the copy (MEAL-08)', async () => {
    const copy = meal({
      id: 'meal-copy',
      based_on: { meal_id: 'meal-pancakes', name: 'Pfannkuchen', owner: BEN },
    });
    const { fetchMock, user, router } = renderDetail(meal({ owner: BEN, is_owner: false }), {
      'POST /api/meals/meal-pancakes/copy': Response.json(copy, { status: 201 }),
    });

    await chooseFromMenu(user, testIds.copyMeal);

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals/meal-copy'));
    expect(await screen.findByTestId(testIds.mealBasedOn)).toHaveTextContent(
      'Based on Pfannkuchen by Ben',
    );
    expect(requestsTo(fetchMock, 'POST /api/meals/meal-pancakes/copy')).toHaveLength(1);
    // The copy is loaded from the cache the copy request filled.
    expect(requestsTo(fetchMock, 'GET /api/meals/meal-copy')).toHaveLength(0);
  });

  it('shows why a copy failed in an alert below the title', async () => {
    const { user } = renderDetail(meal({ owner: BEN, is_owner: false }), {
      'POST /api/meals/meal-pancakes/copy': errorResponse(404, 'common.not_found'),
    });

    await chooseFromMenu(user, testIds.copyMeal);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("This doesn't exist (any more).");
    const heading = screen.getByRole('heading', { level: 1, name: 'Pfannkuchen' });
    expect(heading.compareDocumentPosition(alert) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('disables its items offline, while ⋯ still opens (SYNC-03)', async () => {
    const { fetchMock, user } = renderDetail();
    await screen.findByTestId(testIds.mealIngredients);
    fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')));
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    act(() => {
      window.dispatchEvent(new Event('offline'));
    });

    const menu = await openMoreMenu(user);

    for (const id of [testIds.editMeal, testIds.copyMeal, testIds.deleteMeal]) {
      expect(within(menu).getByTestId(id)).toHaveAttribute('aria-disabled', 'true');
    }
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
