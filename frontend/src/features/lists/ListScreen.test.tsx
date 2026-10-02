import { focusManager } from '@tanstack/react-query';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BEN, CARL, errorResponse, mockApi, requestsTo } from '@/test/api';
import {
  emptyList,
  LIST_ID,
  LIST_ROUTES,
  listDetail,
  listMeal,
  LINES,
  PRIVATE_MEAL,
  DETACHED_MEAL,
  FLOUR_EXTRA_ID,
} from '@/test/lists';
import { CATEGORIES } from '@/test/ingredients';
import { FLOUR, MILK, mealSummary } from '@/test/meals';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const BASE = `/api/lists/${LIST_ID}`;
const IN_COUPLE = { partner: BEN, since: '2026-09-01T10:00:00Z', outgoing: null, incoming: [] };
/** The client makes the ids of extra items. */
const A_UUID_V7: unknown = expect.stringMatching(
  /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
);

function renderList(routes: Record<string, unknown> = {}, path = `/lists/${LIST_ID}`) {
  const fetchMock = mockApi({ ...LIST_ROUTES, ...routes });
  return { fetchMock, ...renderApp(path) };
}

async function bodyOf(fetchMock: ReturnType<typeof mockApi>, route: string, index = 0) {
  const request = requestsTo(fetchMock, route)[index];
  if (!request) throw new Error(`no request to ${route}`);
  return (await request.json()) as unknown;
}

function lineTexts(container: HTMLElement) {
  return within(container)
    .getAllByTestId(testIds.listLine)
    .map((line) => line.textContent);
}

afterEach(() => {
  focusManager.setFocused(undefined);
  Reflect.deleteProperty(navigator, 'share');
  Reflect.deleteProperty(navigator, 'clipboard');
});

describe('ListScreen', () => {
  it('shows the display name and the meals at the top (LIST-02, LIST-05)', async () => {
    renderList();

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Wochenende (26/09/2026)' }),
    ).toBeVisible();
    const meals = await screen.findByTestId(testIds.listMeals);
    const entries = within(meals).getAllByTestId(testIds.listMeal);
    expect(entries.map((entry) => entry.getAttribute('aria-label'))).toEqual([
      'Pfannkuchen',
      'Private meal (3 servings)',
      'Alter Eintopf',
    ]);
    const [pancakes, hidden, detached] = entries as [HTMLElement, HTMLElement, HTMLElement];
    expect(within(pancakes).getByRole('link', { name: 'Pfannkuchen' })).toHaveAttribute(
      'href',
      '/meals/meal-pancakes',
    );
    expect(pancakes.querySelector('img')).toHaveAttribute('alt', '');
    expect(
      within(pancakes).getByRole('group', { name: 'Servings of Pfannkuchen' }),
    ).toHaveTextContent('4 servings');
    // A meal I can't see: no name, photo or link (VIS-06).
    expect(within(hidden).queryByRole('link')).not.toBeInTheDocument();
    expect(hidden.querySelector('img')).toBeNull();
    expect(hidden).toHaveTextContent('Private meal (3 servings)');
    // Detached (LIST-15).
    expect(within(detached).getByText('no longer available')).toBeVisible();
    expect(within(detached).queryByRole('link')).not.toBeInTheDocument();
    expect(within(detached).getByRole('button', { name: 'Remove Alter Eintopf' })).toBeEnabled();
  });

  it('groups the lines by category in the server’s order, with formatted amounts (AGG)', async () => {
    renderList();

    const lines = await screen.findByTestId(testIds.listLines);
    expect(
      within(lines)
        .getAllByRole('heading', { level: 3 })
        .map((heading) => heading.textContent),
    ).toEqual(['Fruit & vegetables', 'Dairy & eggs', 'Other']);
    expect(lineTexts(lines)).toEqual([
      'Zwiebeln2 pcs',
      'Milch1.5 l',
      'Geburtstagskerzen2 Packungen',
      'Mehl850 g',
      'Salz',
    ]);
    expect(within(lines).getByRole('list', { name: 'Dairy & eggs' })).toHaveTextContent('Milch');
    // Removed lines are collapsed below (LIST-07), the reminder is the last row (LIST-14).
    expect(screen.getByTestId(testIds.hiddenLines)).toHaveTextContent('Removed (1)');
    expect(screen.getByTestId(testIds.listReminder)).toHaveTextContent(
      "Reminder: Didn't forget anything? Toilet paper? Salt?",
    );
  });

  it('shows the German formats and texts', async () => {
    const { authSession } = renderList();
    authSession.setUser({ ...authSession.getState().user!, language: 'de' });
    const { changeLanguage } = await import('@/i18n');
    await changeLanguage('de');

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Wochenende (26.09.2026)' }),
    ).toBeVisible();
    const lines = await screen.findByTestId(testIds.listLines);
    expect(lineTexts(lines)).toContain('Milch1,5 l');
    expect(lineTexts(lines)).toContain('Salz');
    expect(screen.getByText('Privates Gericht (3 Portionen)')).toBeVisible();
  });

  it('names the headings as the server names the categories, in the UI language (I18N-04)', async () => {
    const renamed = CATEGORIES.map((category) =>
      category.key === 'dairy_eggs'
        ? { ...category, names: { de: 'Kühlregal', en: 'Fridge aisle' } }
        : category,
    );
    const { authSession } = renderList({ 'GET /api/categories': renamed });

    const lines = await screen.findByTestId(testIds.listLines);
    expect(within(lines).getByRole('list', { name: 'Fridge aisle' })).toHaveTextContent('Milch');

    authSession.setUser({ ...authSession.getState().user!, language: 'de' });
    const { changeLanguage } = await import('@/i18n');
    await changeLanguage('de');
    expect(await within(lines).findByRole('list', { name: 'Kühlregal' })).toHaveTextContent(
      'Milch',
    );
    expect(within(lines).getByRole('list', { name: 'Obst & Gemüse' })).toBeVisible();
  });

  it('shows the English name of a category that has none in the UI language (I18N-01)', async () => {
    // As for a UI language added later, before admins fill in its names.
    const untranslated = CATEGORIES.map((category) =>
      category.key === 'dairy_eggs' ? { ...category, names: { en: 'Fridge aisle' } } : category,
    ) as typeof CATEGORIES;
    const { authSession } = renderList({ 'GET /api/categories': untranslated });
    authSession.setUser({ ...authSession.getState().user!, language: 'de' });
    const { changeLanguage } = await import('@/i18n');
    await changeLanguage('de');

    const lines = await screen.findByTestId(testIds.listLines);
    expect(within(lines).getByRole('list', { name: 'Fridge aisle' })).toHaveTextContent('Milch');
  });

  it('changes servings with − and + at once and saves each step (LIST-04)', async () => {
    const { fetchMock, user } = renderList({
      [`PATCH ${BASE}/meals/lm-pancakes`]: async (request: Request) => {
        const { servings } = (await request.json()) as { servings: number };
        return listDetail({ meals: [listMeal({ servings }), PRIVATE_MEAL, DETACHED_MEAL] });
      },
    });
    const group = await screen.findByRole('group', { name: 'Servings of Pfannkuchen' });

    await user.click(within(group).getByRole('button', { name: 'More servings of Pfannkuchen' }));
    await user.click(within(group).getByRole('button', { name: 'More servings of Pfannkuchen' }));
    expect(group).toHaveTextContent('6 servings');

    await waitFor(() =>
      expect(requestsTo(fetchMock, `PATCH ${BASE}/meals/lm-pancakes`)).toHaveLength(2),
    );
    await expect(bodyOf(fetchMock, `PATCH ${BASE}/meals/lm-pancakes`, 0)).resolves.toEqual({
      servings: 5,
    });
    await expect(bodyOf(fetchMock, `PATCH ${BASE}/meals/lm-pancakes`, 1)).resolves.toEqual({
      servings: 6,
    });
    await user.click(within(group).getByRole('button', { name: 'Fewer servings of Pfannkuchen' }));
    await waitFor(() => expect(group).toHaveTextContent('5 servings'));
  });

  it('keeps servings between 1 and 99', async () => {
    renderList({
      [`GET ${BASE}`]: listDetail({ meals: [listMeal({ servings: 1 })] }),
    });

    const group = await screen.findByRole('group', { name: 'Servings of Pfannkuchen' });
    expect(
      within(group).getByRole('button', { name: 'Fewer servings of Pfannkuchen' }),
    ).toBeDisabled();
  });

  it('removes a meal from the list', async () => {
    const { fetchMock, user } = renderList({
      [`DELETE ${BASE}/meals/lm-detached`]: listDetail({ meals: [listMeal(), PRIVATE_MEAL] }),
    });

    await user.click(await screen.findByRole('button', { name: 'Remove Alter Eintopf' }));

    await waitFor(() =>
      expect(
        screen.getAllByTestId(testIds.listMeal).map((entry) => entry.textContent),
      ).not.toContain(expect.stringContaining('Alter Eintopf')),
    );
    expect(requestsTo(fetchMock, `DELETE ${BASE}/meals/lm-detached`)).toHaveLength(1);
  });

  describe('meal picker', () => {
    const CHILI = mealSummary('Chili', { servings: 4 });
    const LASAGNE = mealSummary('Lasagne', { owner: BEN });
    const PANCAKES = mealSummary('Pfannkuchen');

    function pickerRoutes(routes: Record<string, unknown> = {}) {
      return {
        'GET /api/meals/recent': [CHILI],
        'GET /api/meals': (request: Request) =>
          new URL(request.url).searchParams.get('q') === 'lasagne'
            ? [LASAGNE]
            : [CHILI, LASAGNE, PANCAKES],
        [`POST ${BASE}/meals`]: listDetail(),
        ...routes,
      };
    }

    it('offers recently used meals first, then the others (MEAL-09)', async () => {
      const { user } = renderList(pickerRoutes());

      await user.click(await screen.findByTestId(testIds.addMeals));
      const dialog = await screen.findByRole('dialog', { name: 'Add meals' });

      const recent = await within(dialog).findByTestId(testIds.mealPickerRecent);
      expect(recent).toHaveAccessibleName('Recently used');
      expect(
        within(recent)
          .getAllByRole('listitem')
          .map((item) => item.getAttribute('aria-label')),
      ).toEqual(['Chili']);
      const all = await within(dialog).findByTestId(testIds.mealPickerResults);
      expect(all).toHaveAccessibleName('All meals');
      expect(
        within(all)
          .getAllByRole('listitem')
          .map((item) => item.getAttribute('aria-label')),
      ).toEqual(['Lasagne', 'Pfannkuchen']);
      expect(within(all).getByText('by Ben')).toBeVisible();
      expect(within(dialog).getByTestId(testIds.mealPickerCreate)).toHaveAttribute(
        'href',
        `/meals/new?addToList=${LIST_ID}`,
      );
    });

    it('adds a meal with the chosen servings and stays open for more (LIST-03/04)', async () => {
      const { fetchMock, user } = renderList(pickerRoutes());

      await user.click(await screen.findByTestId(testIds.addMeals));
      const dialog = await screen.findByRole('dialog', { name: 'Add meals' });
      const row = await within(dialog).findByRole('listitem', { name: 'Lasagne' });
      expect(within(row).getByRole('group', { name: 'Servings of Lasagne' })).toHaveTextContent(
        '2 servings',
      );
      await user.click(within(row).getByRole('button', { name: 'More servings of Lasagne' }));
      await user.click(within(row).getByRole('button', { name: 'Add Lasagne' }));

      expect(await within(row).findByText('Lasagne added.')).toBeVisible();
      await expect(bodyOf(fetchMock, `POST ${BASE}/meals`)).resolves.toEqual({
        meal_id: 'meal-lasagne',
        servings: 3,
      });
      expect(within(row).getByRole('group', { name: 'Servings of Lasagne' })).toHaveTextContent(
        '2 servings',
      );
      // Recently used is loaded again.
      await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/meals/recent')).toHaveLength(2));
      await user.click(within(dialog).getByRole('button', { name: 'Done' }));
      expect(dialog).not.toBeInTheDocument();
    });

    it('searches all visible meals', async () => {
      const { user } = renderList(pickerRoutes());

      await user.click(await screen.findByTestId(testIds.addMeals));
      const dialog = await screen.findByRole('dialog', { name: 'Add meals' });
      await user.type(within(dialog).getByLabelText('Search meals'), 'lasagne');

      const results = await within(dialog).findByRole('list', { name: 'Matching meals' });
      await waitFor(() =>
        expect(
          within(results)
            .getAllByRole('listitem')
            .map((item) => item.getAttribute('aria-label')),
        ).toEqual(['Lasagne']),
      );
      expect(within(dialog).queryByTestId(testIds.mealPickerRecent)).not.toBeInTheDocument();
    });

    it('shows why a meal could not be added', async () => {
      const { user } = renderList(
        pickerRoutes({
          [`POST ${BASE}/meals`]: errorResponse(422, 'common.validation', [
            { loc: ['body', 'meal_id'], code: 'invalid' },
          ]),
        }),
      );

      await user.click(await screen.findByTestId(testIds.addMeals));
      const dialog = await screen.findByRole('dialog', { name: 'Add meals' });
      const row = await within(dialog).findByRole('listitem', { name: 'Pfannkuchen' });
      await user.click(within(row).getByRole('button', { name: 'Add Pfannkuchen' }));

      expect(await within(row).findByText('Please check your input.')).toBeVisible();
    });
  });

  describe('extra items (LIST-06)', () => {
    async function pickSuggestion(user: ReturnType<typeof renderApp>['user'], name: string) {
      const suggestions = await screen.findByRole('list', { name: 'Matching ingredients' });
      await user.click(within(suggestions).getByRole('button', { name: new RegExp(`^${name}`) }));
    }

    const routes = {
      'GET /api/ingredients': (request: Request) =>
        new URL(request.url).searchParams.get('q') === 'Mehl' ? [FLOUR] : [],
      'GET /api/units': [
        { unit: 'g', kind: 'mass' },
        { unit: 'kg', kind: 'mass' },
        { unit: 'piece', kind: 'count' },
      ],
      [`POST ${BASE}/extra-items`]: Response.json(listDetail(), { status: 201 }),
    };

    it('adds a picked ingredient with amount and unit as a linked item', async () => {
      const { fetchMock, user } = renderList(routes);

      const input = await screen.findByTestId(testIds.extraItemInput);
      expect(input).toHaveAccessibleName('Add an item');
      await user.type(input, 'Mehl');
      await pickSuggestion(user, 'Mehl');

      const form = screen.getByRole('form', { name: 'Add an item' });
      expect(within(form).getByText('Mehl')).toBeVisible();
      expect(within(form).getByLabelText('Unit')).toHaveValue('g');
      await user.type(within(form).getByLabelText('Amount (optional)'), '450');
      await user.click(within(form).getByRole('button', { name: 'Add Mehl' }));

      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(1),
      );
      const body = (await bodyOf(fetchMock, `POST ${BASE}/extra-items`)) as Record<string, unknown>;
      expect(body).toEqual({
        id: A_UUID_V7,
        ingredient_id: FLOUR.id,
        amount: 450,
        unit: 'g',
      });
      // Ready for the next item.
      expect(await screen.findByTestId(testIds.extraItemInput)).toHaveValue('');
    });

    it('adds a linked item without an amount, and checks a typed amount', async () => {
      const { fetchMock, user } = renderList(routes);

      await user.type(await screen.findByTestId(testIds.extraItemInput), 'Mehl');
      await pickSuggestion(user, 'Mehl');
      const form = screen.getByRole('form', { name: 'Add an item' });
      await user.type(within(form).getByLabelText('Amount (optional)'), '1,5,0');
      await user.click(within(form).getByRole('button', { name: 'Add Mehl' }));
      expect(within(form).getByText('Invalid format')).toBeVisible();
      expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(0);

      await user.clear(within(form).getByLabelText('Amount (optional)'));
      await user.click(within(form).getByRole('button', { name: 'Add Mehl' }));
      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(1),
      );
      await expect(bodyOf(fetchMock, `POST ${BASE}/extra-items`)).resolves.toEqual({
        id: A_UUID_V7,
        ingredient_id: FLOUR.id,
      });
    });

    it('lets me go back from a picked ingredient to typing', async () => {
      const { user } = renderList(routes);

      await user.type(await screen.findByTestId(testIds.extraItemInput), 'Mehl');
      await pickSuggestion(user, 'Mehl');
      await user.click(screen.getByRole('button', { name: "Don't use Mehl" }));

      expect(screen.getByTestId(testIds.extraItemInput)).toHaveValue('Mehl');
    });

    it('adds typed text with Enter as a free-text item in Other', async () => {
      const { fetchMock, user } = renderList(routes);

      const input = await screen.findByTestId(testIds.extraItemInput);
      await user.type(input, 'Geburtstagskerzen');
      const form = screen.getByRole('form', { name: 'Add an item' });
      expect(within(form).getByLabelText('Category')).toHaveDisplayValue('Other');
      await user.type(within(form).getByLabelText('Amount (optional)'), '2 Packungen');
      await user.type(input, '{Enter}');

      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(1),
      );
      await expect(bodyOf(fetchMock, `POST ${BASE}/extra-items`)).resolves.toEqual({
        id: A_UUID_V7,
        text: 'Geburtstagskerzen',
        amount_text: '2 Packungen',
        category_id: 'cat-other',
      });
    });

    it('puts a free-text item into the chosen category', async () => {
      const { fetchMock, user } = renderList(routes);

      await user.type(await screen.findByTestId(testIds.extraItemInput), 'Kerzen');
      const form = screen.getByRole('form', { name: 'Add an item' });
      // By value: user-event compares option labels as HTML (`&amp;`).
      await user.selectOptions(within(form).getByLabelText('Category'), 'cat-dairy_eggs');
      expect(within(form).getByLabelText('Category')).toHaveDisplayValue('Dairy & eggs');
      await user.click(within(form).getByRole('button', { name: 'Add Kerzen' }));

      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(1),
      );
      await expect(bodyOf(fetchMock, `POST ${BASE}/extra-items`)).resolves.toEqual({
        id: A_UUID_V7,
        text: 'Kerzen',
        category_id: 'cat-dairy_eggs',
      });
    });

    it('sends an item again with the same id after an error, and the next one with a new id', async () => {
      let attempts = 0;
      const { fetchMock, user } = renderList({
        ...routes,
        [`POST ${BASE}/extra-items`]: () => {
          attempts += 1;
          // The answer to the first try is lost: the item may well be on the list already.
          if (attempts === 1) throw new TypeError('Failed to fetch');
          return Response.json(listDetail(), { status: 201 });
        },
      });

      await user.type(await screen.findByTestId(testIds.extraItemInput), 'Kerzen{Enter}');
      expect(await screen.findByRole('alert')).toHaveTextContent(
        "Can't reach MealMate. Are you online?",
      );
      await user.click(screen.getByRole('button', { name: 'Add Kerzen' }));
      await waitFor(() => expect(screen.getByTestId(testIds.extraItemInput)).toHaveValue(''));
      await user.type(screen.getByTestId(testIds.extraItemInput), 'Servietten{Enter}');

      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(3),
      );
      const [first, again, next] = (await Promise.all(
        [0, 1, 2].map((index) => bodyOf(fetchMock, `POST ${BASE}/extra-items`, index)),
      )) as { id: string; text: string }[];
      expect(first).toEqual({ id: A_UUID_V7, text: 'Kerzen', category_id: 'cat-other' });
      expect(again).toEqual(first);
      expect(next).toEqual({ id: A_UUID_V7, text: 'Servietten', category_id: 'cat-other' });
      expect(next?.id).not.toBe(first?.id);
    });

    it('shows the server’s field errors next to the field', async () => {
      const { user } = renderList({
        ...routes,
        [`POST ${BASE}/extra-items`]: errorResponse(422, 'common.validation', [
          { loc: ['body', 'amount'], code: 'out_of_range' },
        ]),
      });

      await user.type(await screen.findByTestId(testIds.extraItemInput), 'Mehl');
      await pickSuggestion(user, 'Mehl');
      await user.type(screen.getByLabelText('Amount (optional)'), '999999');
      await user.click(screen.getByRole('button', { name: 'Add Mehl' }));

      expect(await screen.findByText('Out of range')).toBeVisible();
      expect(screen.queryByText('Please check your input.')).not.toBeInTheDocument();
    });
  });

  describe('sources, removing and restoring lines (LIST-07/08)', () => {
    const milkHidden = listDetail({
      lines: LINES.map((line) => (line.name === 'Milch' ? { ...line, hidden: true } : line)),
    });
    const HIDE = `POST ${BASE}/lines/i%3A${MILK.id}/hide`;
    const UNHIDE = `POST ${BASE}/lines/i%3A${MILK.id}/unhide`;

    it('shows where a line comes from, private meals without their name', async () => {
      const { user } = renderList();

      const lines = await screen.findByTestId(testIds.listLines);
      await user.click(within(lines).getByRole('button', { name: /^Milch/ }));

      const dialog = await screen.findByRole('dialog', { name: 'Milch' });
      expect(dialog).toBe(screen.getByTestId(testIds.lineSources));
      expect(dialog).toHaveTextContent('1.5 l');
      expect(
        within(dialog)
          .getAllByRole('listitem')
          .map((item) => item.textContent),
      ).toEqual(['Pfannkuchen (4 servings)', 'Private meal (3 servings)']);
    });

    it('removes a line for this list from its sources and restores it', async () => {
      const { fetchMock, user } = renderList({ [HIDE]: milkHidden, [UNHIDE]: listDetail() });

      const lines = await screen.findByTestId(testIds.listLines);
      await user.click(within(lines).getByRole('button', { name: /^Milch/ }));
      const dialog = await screen.findByRole('dialog', { name: 'Milch' });
      await user.click(within(dialog).getByRole('button', { name: 'Remove Milch for this list' }));

      expect(dialog).not.toBeInTheDocument();
      expect(lineTexts(lines)).not.toContain('Milch1.5 l');
      const removed = screen.getByTestId(testIds.hiddenLines);
      expect(removed).toHaveTextContent('Removed (2)');
      await waitFor(() => expect(requestsTo(fetchMock, HIDE)).toHaveLength(1));

      await user.click(within(removed).getByText('Removed (2)'));
      await user.click(within(removed).getByRole('button', { name: 'Restore Milch' }));

      await waitFor(() => expect(lineTexts(lines)).toContain('Milch1.5 l'));
      expect(requestsTo(fetchMock, UNHIDE)).toHaveLength(1);
      expect(screen.getByTestId(testIds.hiddenLines)).toHaveTextContent('Removed (1)');
    });

    it('removes a line when it is swiped to the left', async () => {
      const { fetchMock } = renderList({ [HIDE]: milkHidden });

      const lines = await screen.findByTestId(testIds.listLines);
      const button = within(lines).getByRole('button', { name: /^Milch/ });
      const row = button.parentElement as HTMLElement;
      fireEvent.pointerDown(row, { pointerId: 1, pointerType: 'touch', clientX: 300, clientY: 10 });
      fireEvent.pointerMove(row, { pointerId: 1, pointerType: 'touch', clientX: 250, clientY: 12 });
      fireEvent.pointerMove(row, { pointerId: 1, pointerType: 'touch', clientX: 150, clientY: 12 });
      fireEvent.pointerUp(row, { pointerId: 1, pointerType: 'touch', clientX: 150, clientY: 12 });
      fireEvent.click(button);

      await waitFor(() => expect(requestsTo(fetchMock, HIDE)).toHaveLength(1));
      // The swipe did not also open the line's sources.
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('keeps a line that was swiped only a little, and ignores the mouse', async () => {
      const { fetchMock } = renderList({ [HIDE]: milkHidden });

      const lines = await screen.findByTestId(testIds.listLines);
      const row = within(lines).getByRole('button', { name: /^Milch/ })
        .parentElement as HTMLElement;
      fireEvent.pointerDown(row, { pointerId: 1, pointerType: 'touch', clientX: 300, clientY: 10 });
      fireEvent.pointerMove(row, { pointerId: 1, pointerType: 'touch', clientX: 260, clientY: 10 });
      fireEvent.pointerUp(row, { pointerId: 1, pointerType: 'touch', clientX: 260, clientY: 10 });
      fireEvent.pointerDown(row, { pointerId: 2, pointerType: 'mouse', clientX: 300, clientY: 10 });
      fireEvent.pointerMove(row, { pointerId: 2, pointerType: 'mouse', clientX: 100, clientY: 10 });
      fireEvent.pointerUp(row, { pointerId: 2, pointerType: 'mouse', clientX: 100, clientY: 10 });

      expect(lineTexts(lines)).toContain('Milch1.5 l');
      expect(requestsTo(fetchMock, HIDE)).toHaveLength(0);
    });

    it('edits and removes an extra item from its line', async () => {
      const { fetchMock, user } = renderList({
        [`PATCH ${BASE}/extra-items/${FLOUR_EXTRA_ID}`]: listDetail(),
        [`DELETE ${BASE}/extra-items/${FLOUR_EXTRA_ID}`]: listDetail(),
      });

      const lines = await screen.findByTestId(testIds.listLines);
      await user.click(within(lines).getByRole('button', { name: /^Mehl/ }));
      let dialog = await screen.findByRole('dialog', { name: 'Mehl' });
      expect(
        within(dialog)
          .getAllByRole('listitem')
          .map((item) => item.textContent),
      ).toEqual([
        expect.stringContaining('Pfannkuchen (4 servings)'),
        expect.stringContaining('Added as an item450 g'),
      ]);
      await user.click(within(dialog).getByRole('button', { name: 'Edit the item Mehl' }));

      const edit = await screen.findByRole('dialog', { name: 'Edit item' });
      const amount = within(edit).getByLabelText('Amount (optional)');
      expect(amount).toHaveFocus();
      expect(amount).toHaveValue('450');
      await user.clear(amount);
      await user.type(amount, '0,5');
      await user.selectOptions(within(edit).getByLabelText('Unit'), 'kg');
      await user.click(within(edit).getByRole('button', { name: 'Save' }));

      await waitFor(() => expect(edit).not.toBeInTheDocument());
      await expect(
        bodyOf(fetchMock, `PATCH ${BASE}/extra-items/${FLOUR_EXTRA_ID}`),
      ).resolves.toEqual({ amount: 0.5, unit: 'kg' });

      await user.click(within(lines).getByRole('button', { name: /^Mehl/ }));
      dialog = await screen.findByRole('dialog', { name: 'Mehl' });
      await user.click(within(dialog).getByRole('button', { name: 'Remove the item Mehl' }));
      await waitFor(() =>
        expect(requestsTo(fetchMock, `DELETE ${BASE}/extra-items/${FLOUR_EXTRA_ID}`)).toHaveLength(
          1,
        ),
      );
    });

    it('edits a free-text item and clears its amount', async () => {
      const { fetchMock, user } = renderList({
        [`PATCH ${BASE}/extra-items/0190c0de-0000-7000-8000-0000000000c1`]: listDetail(),
      });

      const lines = await screen.findByTestId(testIds.listLines);
      await user.click(within(lines).getByRole('button', { name: /^Geburtstagskerzen/ }));
      const dialog = await screen.findByRole('dialog', { name: 'Geburtstagskerzen' });
      await user.click(
        within(dialog).getByRole('button', { name: 'Edit the item Geburtstagskerzen' }),
      );
      const edit = await screen.findByRole('dialog', { name: 'Edit item' });
      expect(within(edit).getByLabelText('Name')).toHaveFocus();
      await user.clear(within(edit).getByLabelText('Name'));
      await user.type(within(edit).getByLabelText('Name'), 'Kerzen');
      await user.clear(within(edit).getByLabelText('Amount (optional)'));
      await user.click(within(edit).getByRole('button', { name: 'Save' }));

      await waitFor(() => expect(edit).not.toBeInTheDocument());
      await expect(
        bodyOf(fetchMock, `PATCH ${BASE}/extra-items/0190c0de-0000-7000-8000-0000000000c1`),
      ).resolves.toEqual({ text: 'Kerzen', amount_text: null, category_id: 'cat-other' });
    });
  });

  describe('someone else’s list (read-only)', () => {
    const carls = listDetail({ owner: CARL, is_owner: false, can_edit: false });

    it('shows the same list without editing controls (VIS-03)', async () => {
      const { user } = renderList({ [`GET ${BASE}`]: carls });

      expect(await screen.findByTestId(testIds.listReadOnly)).toHaveTextContent(
        "This is Carl's list. You can look at it and copy it, but not change it.",
      );
      expect(screen.getByTestId(testIds.listMeals)).toHaveTextContent('4 servings');
      expect(screen.queryByRole('group', { name: /^Servings of/ })).not.toBeInTheDocument();
      expect(screen.queryByTestId(testIds.addMeals)).not.toBeInTheDocument();
      expect(screen.queryByTestId(testIds.extraItemInput)).not.toBeInTheDocument();
      expect(screen.queryByTestId(testIds.renameList)).not.toBeInTheDocument();
      expect(screen.queryByTestId(testIds.deleteList)).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Remove/ })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Restore/ })).not.toBeInTheDocument();
      expect(screen.getByTestId(testIds.exportList)).toBeVisible();

      await user.click(
        within(screen.getByTestId(testIds.listLines)).getByRole('button', { name: /^Mehl/ }),
      );
      const dialog = await screen.findByRole('dialog', { name: 'Mehl' });
      expect(within(dialog).queryByRole('button', { name: /Remove|Edit/ })).not.toBeInTheDocument();
    });

    it('copies it to my lists and says how many meals were left out (VIS-03/06)', async () => {
      const copy = emptyList({ id: 'list-copy', name: 'Wochenende' });
      const { fetchMock, user, router } = renderList({
        [`GET ${BASE}`]: carls,
        [`POST ${BASE}/copy`]: Response.json({ list: copy, left_out: 2 }, { status: 201 }),
        'GET /api/lists/list-copy': copy,
      });

      await user.click(await screen.findByTestId(testIds.copyList));

      await waitFor(() => expect(router.state.location.pathname).toBe('/lists/list-copy'));
      expect(await screen.findByTestId(testIds.listLeftOut)).toHaveTextContent(
        "2 meals were left out: you can't see them, or they no longer exist.",
      );
      expect(requestsTo(fetchMock, `POST ${BASE}/copy`)).toHaveLength(1);
      expect(await screen.findByTestId(testIds.addMeals)).toBeVisible();
    });

    it('says nothing about left-out meals when all were copied', async () => {
      const copy = emptyList({ id: 'list-copy' });
      const { user, router } = renderList({
        [`GET ${BASE}`]: carls,
        [`POST ${BASE}/copy`]: Response.json({ list: copy, left_out: 0 }, { status: 201 }),
        'GET /api/lists/list-copy': copy,
      });

      await user.click(await screen.findByTestId(testIds.copyList));

      await waitFor(() => expect(router.state.location.pathname).toBe('/lists/list-copy'));
      expect(await screen.findByTestId(testIds.addMeals)).toBeVisible();
      expect(screen.queryByTestId(testIds.listLeftOut)).not.toBeInTheDocument();
    });
  });

  describe('share switch (CPL-02)', () => {
    it('is shown to the owner in a couple, named after the partner, and saves', async () => {
      const { fetchMock, user } = renderList({
        'GET /api/couple': IN_COUPLE,
        [`PATCH ${BASE}`]: listDetail({ shared_with_partner: true }),
      });

      const toggle = await screen.findByRole('switch', { name: 'Shared with Ben' });
      expect(toggle).toBe(screen.getByTestId(testIds.shareListSwitch));
      expect(toggle).not.toBeChecked();
      await user.click(toggle);

      await waitFor(() => expect(toggle).toBeChecked());
      await expect(bodyOf(fetchMock, `PATCH ${BASE}`)).resolves.toEqual({
        shared_with_partner: true,
      });
    });

    it('is not shown without a partner', async () => {
      renderList();

      await screen.findByTestId(testIds.listLines);
      expect(screen.queryByTestId(testIds.shareListSwitch)).not.toBeInTheDocument();
    });

    it('is not shown to the partner, who may still edit a shared list (CPL-03)', async () => {
      renderList({
        'GET /api/couple': { ...IN_COUPLE, partner: BEN },
        [`GET ${BASE}`]: listDetail({ owner: BEN, is_owner: false, shared_with_partner: true }),
      });

      expect(await screen.findByTestId(testIds.renameList)).toBeVisible();
      expect(screen.getByTestId(testIds.addMeals)).toBeVisible();
      expect(screen.queryByTestId(testIds.shareListSwitch)).not.toBeInTheDocument();
      expect(screen.queryByTestId(testIds.deleteList)).not.toBeInTheDocument();
      expect(screen.queryByTestId(testIds.listReadOnly)).not.toBeInTheDocument();
    });
  });

  it('renames the list, and an empty name goes back to the default (LIST-02)', async () => {
    const { fetchMock, user } = renderList({
      [`PATCH ${BASE}`]: async (request: Request) => {
        const { name } = (await request.json()) as { name: string | null };
        return listDetail({ name });
      },
    });

    await user.click(await screen.findByTestId(testIds.renameList));
    let dialog = await screen.findByRole('dialog', { name: 'Rename list' });
    const field = within(dialog).getByLabelText('Name');
    // The cursor is in the name, so typing can start at once.
    expect(field).toHaveFocus();
    expect(field).toHaveValue('Wochenende');
    await user.clear(field);
    await user.type(field, 'Grillabend');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Grillabend (26/09/2026)' }),
    ).toBeVisible();
    await expect(bodyOf(fetchMock, `PATCH ${BASE}`)).resolves.toEqual({ name: 'Grillabend' });

    await user.click(screen.getByTestId(testIds.renameList));
    dialog = await screen.findByRole('dialog', { name: 'Rename list' });
    await user.clear(within(dialog).getByLabelText('Name'));
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Shopping list (26/09/2026)' }),
    ).toBeVisible();
    await expect(bodyOf(fetchMock, `PATCH ${BASE}`, 1)).resolves.toEqual({ name: null });
  });

  it('keeps a change when a load of the list that started before it answers later', async () => {
    let loads = 0;
    let answerReload: (() => void) | undefined;
    const { user } = renderList({
      [`GET ${BASE}`]: () => {
        loads += 1;
        if (loads === 1) return listDetail();
        // Back in the foreground: this load still has the old name and answers late.
        return new Promise((resolve) => {
          answerReload = () => resolve(listDetail());
        });
      },
      [`PATCH ${BASE}`]: listDetail({ name: 'Grillabend' }),
    });
    await screen.findByRole('heading', { level: 1, name: 'Wochenende (26/09/2026)' });

    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await waitFor(() => expect(answerReload).toBeDefined());
    await user.click(screen.getByTestId(testIds.renameList));
    const dialog = await screen.findByRole('dialog', { name: 'Rename list' });
    await user.clear(within(dialog).getByLabelText('Name'));
    await user.type(within(dialog).getByLabelText('Name'), 'Grillabend');
    await user.click(within(dialog).getByRole('button', { name: 'Save' }));
    const heading = await screen.findByRole('heading', {
      level: 1,
      name: 'Grillabend (26/09/2026)',
    });
    await act(async () => {
      answerReload?.();
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(heading).toHaveTextContent('Grillabend (26/09/2026)');
  });

  it('deletes the list after asking and goes back to Lists (LIST-13)', async () => {
    const { fetchMock, user, router } = renderList({ [`DELETE ${BASE}`]: null });

    await user.click(await screen.findByRole('button', { name: 'Delete Wochenende (26/09/2026)' }));
    const confirm = await screen.findByRole('alertdialog', {
      name: 'Delete Wochenende (26/09/2026)?',
    });
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/lists'));
    expect(requestsTo(fetchMock, `DELETE ${BASE}`)).toHaveLength(1);
  });

  describe('export (EXP-01/02)', () => {
    it('opens the share sheet with the list as text, within the tap', async () => {
      const share = vi.fn(() => Promise.resolve());
      Object.defineProperty(navigator, 'share', { value: share, configurable: true });
      renderList();

      const button = await screen.findByRole('button', { name: 'Share as text' });
      await screen.findByTestId(testIds.listLines);
      fireEvent.click(button);

      expect(share).toHaveBeenCalledTimes(1);
      const [[{ text }]] = share.mock.calls as unknown as [[{ text: string }]];
      expect(text.startsWith('Wochenende (26/09/2026)\n\n4× Pfannkuchen\n3× Private meal')).toBe(
        true,
      );
      expect(text).toContain('Dairy & eggs\n- Milch: 1.5 l');
      expect(text).not.toContain('Eier');
      expect(text.endsWith("Didn't forget anything? Toilet paper? Salt?")).toBe(true);
    });

    it('copies the text where there is no share sheet', async () => {
      renderList();
      const button = await screen.findByTestId(testIds.exportList);
      // After rendering: user-event would replace the clipboard with its own.
      const writeText = vi.fn(() => Promise.resolve());
      Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });

      fireEvent.click(button);

      expect(
        await screen.findByText('Copied – paste the list into a note or message.'),
      ).toBeVisible();
      expect(screen.getByTestId(testIds.exportList)).toHaveTextContent('Copy as text');
      expect(writeText).toHaveBeenCalledWith(expect.stringContaining('- Mehl: 850 g'));
    });
  });

  it('says when the list does not exist (any more)', async () => {
    renderList({}, '/lists/gone');

    expect(await screen.findByText("This doesn't exist (any more).")).toBeVisible();
  });

  it('opens with an empty list and says what to do', async () => {
    renderList({ 'GET /api/lists/list-new': emptyList() }, '/lists/list-new');

    expect(
      await screen.findByText('No meals yet. Add some and the shopping list below fills itself.'),
    ).toBeVisible();
    expect(screen.getByText('Nothing to buy yet.')).toBeVisible();
    expect(screen.getByTestId(testIds.listReminder)).toHaveTextContent('Got your shopping bags?');
    expect(screen.queryByTestId(testIds.hiddenLines)).not.toBeInTheDocument();
    // Only a list opened from "+ New list" starts with the picker.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
