import { focusManager } from '@tanstack/react-query';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BEN, CARL, errorResponse, heldRoute, mockApi, requestsTo, TEST_USER } from '@/test/api';
import {
  emptyList,
  FORMER_REMINDER,
  LIST_ID,
  LIST_ROUTES,
  listDetail,
  listMeal,
  LINES,
  PRIVATE_MEAL,
  DETACHED_MEAL,
  EXTRA_ITEMS,
  FLOUR_EXTRA_ID,
} from '@/test/lists';
import { CATEGORIES, unitOptions, UNITS } from '@/test/ingredients';
import { EGGS, FLOUR, MILK, mealSummary } from '@/test/meals';
import { renderApp } from '@/test/render';
import { swipe, tap } from '@/test/swipe';
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

/** No signal: requests fail and the browser says it is offline (SYNC-03). */
function goOffline(fetchMock: ReturnType<typeof mockApi>) {
  fetchMock.mockImplementation(() => Promise.reject(new TypeError('Failed to fetch')));
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
  act(() => {
    window.dispatchEvent(new Event('offline'));
  });
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
    // Hidden lines are collapsed below (LIST-07); no reminder follows them (D-43).
    expect(screen.getByTestId(testIds.hiddenLines)).toHaveTextContent('Hidden (1)');
    expect(document.body).not.toHaveTextContent(FORMER_REMINDER);
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
        ? { ...category, names: { de: 'Kühlregal', en: 'Chilled goods' } }
        : category,
    );
    const { authSession } = renderList({ 'GET /api/categories': renamed });

    const lines = await screen.findByTestId(testIds.listLines);
    expect(within(lines).getByRole('list', { name: 'Chilled goods' })).toHaveTextContent('Milch');

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
      category.key === 'dairy_eggs' ? { ...category, names: { en: 'Chilled goods' } } : category,
    ) as typeof CATEGORIES;
    const { authSession } = renderList({ 'GET /api/categories': untranslated });
    authSession.setUser({ ...authSession.getState().user!, language: 'de' });
    const { changeLanguage } = await import('@/i18n');
    await changeLanguage('de');

    const lines = await screen.findByTestId(testIds.listLines);
    expect(within(lines).getByRole('list', { name: 'Chilled goods' })).toHaveTextContent('Milch');
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

  describe('meal rows (LIST-04, D-40)', () => {
    const REMOVE_PANCAKES = `DELETE ${BASE}/meals/lm-pancakes`;

    function mealRow(name: string) {
      return within(screen.getByTestId(testIds.listMeals)).getByRole('listitem', { name });
    }

    it('removes a meal at once with its "Remove" button, without asking', async () => {
      const held = heldRoute();
      const { fetchMock, user } = renderList({ [REMOVE_PANCAKES]: held.route });
      await screen.findByTestId(testIds.listMeals);

      // Shown on focus and hover, always there for screen readers.
      const remove = within(mealRow('Pfannkuchen')).getByTestId(testIds.removeListMeal);
      expect(remove).toHaveAccessibleName('Remove Pfannkuchen');
      expect(remove).toHaveTextContent('Remove');
      await user.click(remove);

      // Gone before the server answered; no confirmation.
      expect(screen.queryByRole('listitem', { name: 'Pfannkuchen' })).not.toBeInTheDocument();
      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
      await held.answer(listDetail({ meals: [PRIVATE_MEAL, DETACHED_MEAL] }));
      expect(requestsTo(fetchMock, REMOVE_PANCAKES)).toHaveLength(1);
      expect(screen.getAllByTestId(testIds.listMeal)).toHaveLength(2);
    });

    it('has the compact stepper, its number read as "99 servings", up to 99 (A11Y-01)', async () => {
      renderList({ [`GET ${BASE}`]: listDetail({ meals: [listMeal({ servings: 99 })] }) });

      const group = await screen.findByRole('group', { name: 'Servings of Pfannkuchen' });
      expect(within(group).getByText('99 servings')).toBeInTheDocument();
      expect(
        within(group).getByRole('button', { name: 'More servings of Pfannkuchen' }),
      ).toBeDisabled();
      expect(
        within(group).getByRole('button', { name: 'Fewer servings of Pfannkuchen' }),
      ).toBeEnabled();
    });

    it('names the stepper and "Entfernen" in German', async () => {
      const { authSession } = renderList();
      authSession.setUser({ ...authSession.getState().user!, language: 'de' });
      const { changeLanguage } = await import('@/i18n');
      await changeLanguage('de');

      const group = await screen.findByRole('group', { name: 'Portionen: Pfannkuchen' });
      expect(within(group).getByText('4 Portionen')).toBeInTheDocument();
      expect(within(group).getByRole('button', { name: 'Weniger Portionen: Pfannkuchen' })).toBe(
        within(group).getAllByRole('button')[0],
      );
      expect(
        within(group).getByRole('button', { name: 'Mehr Portionen: Pfannkuchen' }),
      ).toBeVisible();
      const remove = within(mealRow('Pfannkuchen')).getByTestId(testIds.removeListMeal);
      expect(remove).toHaveAccessibleName('Pfannkuchen entfernen');
      expect(remove).toHaveTextContent('Entfernen');
    });

    it('shows the servings instead of the stepper, without swiping, on a read-only list', async () => {
      renderList({
        [`GET ${BASE}`]: listDetail({ owner: CARL, is_owner: false, can_edit: false }),
      });
      await screen.findByTestId(testIds.listMeals);

      const pancakes = mealRow('Pfannkuchen');
      expect(within(pancakes).getByText('4 servings')).toBeVisible();
      expect(within(pancakes).queryByRole('group')).not.toBeInTheDocument();
      expect(within(pancakes).queryByRole('button')).not.toBeInTheDocument();
      // A meal I can't see says its servings in its name (VIS-06).
      expect(mealRow('Private meal (3 servings)')).toHaveTextContent(
        /^Private meal \(3 servings\)$/,
      );
      swipe(within(pancakes).getByRole('link'), { from: 600, to: 450 });
      expect(within(pancakes).queryByRole('button', { hidden: true })).not.toBeInTheDocument();
    });

    it('turns off the swipe, "Remove" and the stepper offline (SYNC-03)', async () => {
      const { fetchMock } = renderList();
      await screen.findByTestId(testIds.listMeals);
      goOffline(fetchMock);

      const pancakes = mealRow('Pfannkuchen');
      await waitFor(() =>
        expect(within(pancakes).getByTestId(testIds.removeListMeal)).toBeDisabled(),
      );
      for (const button of within(pancakes).getAllByRole('button', { name: /servings of/ })) {
        expect(button).toBeDisabled();
      }
      swipe(within(pancakes).getByRole('link'), { from: 900, to: 300 });
      expect(
        within(pancakes).queryByRole('button', { name: 'Remove', hidden: true }),
      ).not.toBeInTheDocument();
      expect(requestsTo(fetchMock, REMOVE_PANCAKES)).toHaveLength(0);
    });

    it('brings a meal back when removing it failed', async () => {
      const { user } = renderList({
        [REMOVE_PANCAKES]: errorResponse(500, 'common.internal'),
      });
      await screen.findByTestId(testIds.listMeals);

      await user.click(within(mealRow('Pfannkuchen')).getByTestId(testIds.removeListMeal));

      expect(await screen.findByRole('listitem', { name: 'Pfannkuchen' })).toBeVisible();
      expect(screen.getByRole('alert')).toBeVisible();
    });

    describe('swiping', () => {
      /** The action a swipe reveals; screen readers use the row's own buttons instead. */
      function swipeAction(name: string) {
        return within(mealRow(name)).queryByRole('button', { name: 'Remove', hidden: true });
      }

      it('reveals a "Remove" that removes the meal without asking', async () => {
        const { fetchMock, router } = renderList({
          [REMOVE_PANCAKES]: listDetail({ meals: [PRIVATE_MEAL, DETACHED_MEAL] }),
        });
        await screen.findByTestId(testIds.listMeals);
        const link = within(mealRow('Pfannkuchen')).getByRole('link', { name: 'Pfannkuchen' });

        swipe(link, { from: 600, to: 450 });
        // The browser's click after the swipe doesn't open the meal.
        fireEvent.click(link);

        expect(router.state.location.pathname).toBe(`/lists/${LIST_ID}`);
        const action = swipeAction('Pfannkuchen');
        expect(action).toBeInTheDocument();
        expect(requestsTo(fetchMock, REMOVE_PANCAKES)).toHaveLength(0);
        tap(action!);

        await waitFor(() =>
          expect(screen.queryByRole('listitem', { name: 'Pfannkuchen' })).not.toBeInTheDocument(),
        );
        expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
        expect(requestsTo(fetchMock, REMOVE_PANCAKES)).toHaveLength(1);
      });

      it('removes the meal at once when swiped all the way through', async () => {
        const { fetchMock, router } = renderList({
          [REMOVE_PANCAKES]: listDetail({ meals: [PRIVATE_MEAL, DETACHED_MEAL] }),
        });
        await screen.findByTestId(testIds.listMeals);
        const link = within(mealRow('Pfannkuchen')).getByRole('link', { name: 'Pfannkuchen' });

        // Past half the row (jsdom's rows are as wide as the window, 1024 px).
        swipe(link, { from: 900, to: 300 });

        await waitFor(() =>
          expect(screen.queryByRole('listitem', { name: 'Pfannkuchen' })).not.toBeInTheDocument(),
        );
        expect(requestsTo(fetchMock, REMOVE_PANCAKES)).toHaveLength(1);
        expect(router.state.location.pathname).toBe(`/lists/${LIST_ID}`);
      });

      it('stays closed after a small or a mostly vertical movement, and for the mouse', async () => {
        const { fetchMock } = renderList();
        await screen.findByTestId(testIds.listMeals);
        const link = within(mealRow('Pfannkuchen')).getByRole('link', { name: 'Pfannkuchen' });

        swipe(link, { from: 600, to: 560 });
        expect(swipeAction('Pfannkuchen')).not.toBeInTheDocument();
        // Scrolling the list.
        swipe(link, { from: 600, to: 450, dy: 200 });
        expect(swipeAction('Pfannkuchen')).not.toBeInTheDocument();
        swipe(link, { from: 900, to: 300, pointerType: 'mouse' });
        expect(swipeAction('Pfannkuchen')).not.toBeInTheDocument();
        expect(requestsTo(fetchMock, REMOVE_PANCAKES)).toHaveLength(0);
      });

      it('works with a pen as with a finger', async () => {
        renderList();
        await screen.findByTestId(testIds.listMeals);

        swipe(within(mealRow('Pfannkuchen')).getByRole('link'), {
          from: 600,
          to: 450,
          pointerType: 'pen',
        });

        expect(swipeAction('Pfannkuchen')).toBeInTheDocument();
      });

      it('closes when swiped back, scrolled or tapped, without opening the meal', async () => {
        const { router } = renderList();
        await screen.findByTestId(testIds.listMeals);
        const link = within(mealRow('Pfannkuchen')).getByRole('link', { name: 'Pfannkuchen' });

        swipe(link, { from: 600, to: 450 });
        swipe(link, { from: 450, to: 600 });
        expect(swipeAction('Pfannkuchen')).not.toBeInTheDocument();

        swipe(link, { from: 600, to: 450 });
        // The browser takes over to scroll.
        swipe(link, { from: 450, to: 450, dy: 100, cancel: true });
        expect(swipeAction('Pfannkuchen')).not.toBeInTheDocument();

        swipe(link, { from: 600, to: 450 });
        tap(link);
        expect(swipeAction('Pfannkuchen')).not.toBeInTheDocument();
        expect(router.state.location.pathname).toBe(`/lists/${LIST_ID}`);
      });

      it('keeps one row open at a time, and closes it on a tap elsewhere', async () => {
        renderList();
        await screen.findByTestId(testIds.listMeals);

        swipe(within(mealRow('Pfannkuchen')).getByRole('link'), { from: 600, to: 450 });
        swipe(within(mealRow('Alter Eintopf')).getByText('Alter Eintopf'), {
          from: 600,
          to: 450,
        });

        expect(swipeAction('Pfannkuchen')).not.toBeInTheDocument();
        expect(swipeAction('Alter Eintopf')).toBeInTheDocument();
        tap(screen.getByRole('heading', { level: 1 }));
        expect(swipeAction('Alter Eintopf')).not.toBeInTheDocument();
      });
    });
  });

  describe('meal picker', () => {
    const CHILI = mealSummary('Chili', { servings: 4 });
    const LASAGNE = mealSummary('Lasagne', { owner: BEN });
    const PANCAKES = mealSummary('Pfannkuchen');
    const MEALS = [CHILI, LASAGNE, PANCAKES];

    /** The meals of one of the picker's sections, by their rows' names. */
    function rowNames(section: HTMLElement) {
      return within(section)
        .getAllByRole('listitem')
        .map((item) => item.getAttribute('aria-label'));
    }

    function pickerRoutes(routes: Record<string, unknown> = {}) {
      return {
        'GET /api/meals/recent': [CHILI],
        'GET /api/meals': (request: Request) =>
          new URL(request.url).searchParams.get('q') === 'lasagne' ? [LASAGNE] : MEALS,
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
      expect(rowNames(recent)).toEqual(['Chili']);
      const all = await within(dialog).findByTestId(testIds.mealPickerResults);
      expect(all).toHaveAccessibleName('All meals');
      expect(rowNames(all)).toEqual(['Lasagne', 'Pfannkuchen']);
      // Whose meal it is shows as the owner's marker, one's own included (UI-02).
      const lasagne = within(all).getByRole('listitem', { name: 'Lasagne' });
      expect(within(lasagne).getByRole('img', { name: 'Ben' })).toHaveTextContent('B');
      const pancakes = within(all).getByRole('listitem', { name: 'Pfannkuchen' });
      expect(within(pancakes).getByRole('img', { name: 'Anna' })).toHaveTextContent('A');
      expect(within(dialog).queryByText('by Ben')).not.toBeInTheDocument();
      expect(within(dialog).getByTestId(testIds.mealPickerCreate)).toHaveAttribute(
        'href',
        `/meals/new?addToList=${LIST_ID}`,
      );
    });

    it('opens without the keyboard: the search field is not focused (MEAL-09)', async () => {
      const { user } = renderList(pickerRoutes());

      await user.click(await screen.findByTestId(testIds.addMeals));
      const dialog = await screen.findByRole('dialog', { name: 'Add meals' });

      await within(dialog).findByTestId(testIds.mealPickerRecent);
      expect(within(dialog).getByLabelText('Search meals')).not.toHaveFocus();
      // The focus is in the picker, so screen readers announce it.
      expect(dialog).toHaveFocus();
    });

    it('offers the meals of users the Meals tab hides (MEAL-09, MEAL-10)', async () => {
      const hidingBen = {
        ...TEST_USER,
        filter_hidden: { meals: [BEN.id], lists: [], list_states: [] },
      };
      mockApi({
        ...LIST_ROUTES,
        ...pickerRoutes({
          'GET /api/me': hidingBen,
          // Like the server: the user filter on Meals applies unless owners are asked for.
          'GET /api/meals': (request: Request) => {
            const owners = new URL(request.url).searchParams.getAll('owner_ids');
            return owners.length > 0
              ? MEALS.filter((meal) => owners.includes(meal.owner.id))
              : MEALS.filter((meal) => meal.owner.id !== BEN.id);
          },
        }),
      });
      const { router, user } = renderApp('/meals', { user: hidingBen });
      const list = await screen.findByTestId(testIds.mealList);
      expect(within(list).queryByText('Lasagne')).not.toBeInTheDocument();

      await act(() => router.navigate(`/lists/${LIST_ID}`));
      await user.click(await screen.findByTestId(testIds.addMeals));
      const dialog = await screen.findByRole('dialog', { name: 'Add meals' });

      const recent = await within(dialog).findByTestId(testIds.mealPickerRecent);
      expect(rowNames(recent)).toEqual(['Chili']);
      const all = await within(dialog).findByTestId(testIds.mealPickerResults);
      await waitFor(() => expect(rowNames(all)).toEqual(['Lasagne', 'Pfannkuchen']));
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
      await waitFor(() => expect(rowNames(results)).toEqual(['Lasagne']));
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
      'GET /api/ingredients': (request: Request) => {
        const q = new URL(request.url).searchParams.get('q');
        return [FLOUR, MILK, EGGS].filter((ingredient) => ingredient.name === q);
      },
      'GET /api/units': UNITS,
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

    it('offers the units that fit the picked ingredient and keeps one only while it fits (REF-02)', async () => {
      const { user } = renderList(routes);

      async function pick(name: string) {
        const input = await screen.findByTestId(testIds.extraItemInput);
        await user.clear(input);
        await user.type(input, name);
        // The suggestions of the previous search stay until the new ones arrive.
        const suggestions = await screen.findByRole('list', { name: 'Matching ingredients' });
        await user.click(
          await within(suggestions).findByRole('button', { name: new RegExp(`^${name}`) }),
        );
        return within(screen.getByRole('form', { name: 'Add an item' })).getByLabelText('Unit');
      }

      let unit = await pick('Mehl');
      expect(unitOptions(unit)).toEqual([
        ['g', false],
        ['kg', false],
        ['tbsp', false],
        ['tsp', false],
      ]);
      await user.selectOptions(unit, 'tbsp');
      await user.click(screen.getByRole('button', { name: "Don't use Mehl" }));
      // Spoons fit millilitres too.
      unit = await pick('Milch');
      expect(unit).toHaveValue('tbsp');
      expect(unitOptions(unit).map(([label]) => label)).toEqual(['ml', 'l', 'tbsp', 'tsp']);
      await user.click(screen.getByRole('button', { name: "Don't use Milch" }));
      // Eggs are counted in pieces: the spoons go.
      unit = await pick('Eier');
      expect(unit).toHaveValue('piece');
      expect(unitOptions(unit)).toEqual([['pcs', false]]);
      expect(screen.queryByText(/doesn't fit/)).not.toBeInTheDocument();
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

    it('hides a line for this list from its sources and restores it', async () => {
      const { fetchMock, user } = renderList({ [HIDE]: milkHidden, [UNHIDE]: listDetail() });

      const lines = await screen.findByTestId(testIds.listLines);
      await user.click(within(lines).getByRole('button', { name: /^Milch/ }));
      const dialog = await screen.findByRole('dialog', { name: 'Milch' });
      const hide = within(dialog).getByRole('button', { name: 'Hide Milch' });
      expect(hide).toHaveTextContent('Hide');
      await user.click(hide);

      expect(dialog).not.toBeInTheDocument();
      expect(lineTexts(lines)).not.toContain('Milch1.5 l');
      const hidden = screen.getByTestId(testIds.hiddenLines);
      expect(hidden).toHaveTextContent('Hidden (2)');
      await waitFor(() => expect(requestsTo(fetchMock, HIDE)).toHaveLength(1));

      await user.click(within(hidden).getByText('Hidden (2)'));
      await user.click(within(hidden).getByRole('button', { name: 'Restore Milch' }));

      await waitFor(() => expect(lineTexts(lines)).toContain('Milch1.5 l'));
      expect(requestsTo(fetchMock, UNHIDE)).toHaveLength(1);
      expect(screen.getByTestId(testIds.hiddenLines)).toHaveTextContent('Hidden (1)');
    });

    describe('swiping (D-40)', () => {
      function milk() {
        return within(screen.getByTestId(testIds.listLines)).getByRole('button', {
          name: /^Milch/,
        });
      }

      function hideAction() {
        return within(milk().closest('li')!).queryByRole('button', { name: 'Hide', hidden: true });
      }

      it('reveals a "Hide" that hides the line, without opening its sources', async () => {
        const { fetchMock } = renderList({ [HIDE]: milkHidden });
        await screen.findByTestId(testIds.listLines);

        swipe(milk(), { from: 600, to: 450 });
        fireEvent.click(milk());

        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
        expect(requestsTo(fetchMock, HIDE)).toHaveLength(0);
        tap(hideAction()!);

        await waitFor(() => expect(requestsTo(fetchMock, HIDE)).toHaveLength(1));
        expect(screen.getByTestId(testIds.hiddenLines)).toHaveTextContent('Hidden (2)');
      });

      it('hides a line at once when swiped all the way through', async () => {
        const { fetchMock } = renderList({ [HIDE]: milkHidden });
        await screen.findByTestId(testIds.listLines);

        swipe(milk(), { from: 900, to: 300 });

        await waitFor(() => expect(requestsTo(fetchMock, HIDE)).toHaveLength(1));
        expect(screen.getByTestId(testIds.hiddenLines)).toHaveTextContent('Hidden (2)');
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });

      it('keeps a line that was swiped only a little, and ignores the mouse', async () => {
        const { fetchMock } = renderList({ [HIDE]: milkHidden });
        await screen.findByTestId(testIds.listLines);

        swipe(milk(), { from: 600, to: 560 });
        expect(hideAction()).not.toBeInTheDocument();
        swipe(milk(), { from: 900, to: 300, pointerType: 'mouse' });
        expect(hideAction()).not.toBeInTheDocument();
        expect(lineTexts(screen.getByTestId(testIds.listLines))).toContain('Milch1.5 l');
        expect(requestsTo(fetchMock, HIDE)).toHaveLength(0);
      });

      it('closes an open meal when a line is swiped: one row open at a time', async () => {
        renderList();
        await screen.findByTestId(testIds.listLines);
        const meals = screen.getByTestId(testIds.listMeals);

        swipe(within(meals).getByRole('link', { name: 'Pfannkuchen' }), { from: 600, to: 450 });
        swipe(milk(), { from: 600, to: 450 });

        expect(within(meals).queryByRole('button', { name: 'Remove', hidden: true })).toBeNull();
        expect(hideAction()).toBeInTheDocument();
      });

      it('doesn’t swipe offline (SYNC-03)', async () => {
        const { fetchMock } = renderList();
        await screen.findByTestId(testIds.listLines);
        goOffline(fetchMock);
        await waitFor(() => expect(screen.getByTestId(testIds.offlineBanner)).toBeVisible());

        swipe(milk(), { from: 900, to: 300 });

        expect(hideAction()).not.toBeInTheDocument();
        expect(requestsTo(fetchMock, HIDE)).toHaveLength(0);
      });
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

    it('marks an older item whose unit doesn’t fit and offers only units that do (LIST-06)', async () => {
      const [flour, ...others] = EXTRA_ITEMS;
      if (!flour) throw new Error('the flour item is missing');
      const pieces = { ...flour, amount: 2, unit: 'piece' as const, unit_fits: false };
      const { fetchMock, user } = renderList({
        [`GET ${BASE}`]: listDetail({ extra_items: [pieces, ...others] }),
        [`PATCH ${BASE}/extra-items/${FLOUR_EXTRA_ID}`]: listDetail(),
      });

      const lines = await screen.findByTestId(testIds.listLines);
      await user.click(within(lines).getByRole('button', { name: /^Mehl/ }));
      const dialog = await screen.findByRole('dialog', { name: 'Mehl' });
      await user.click(within(dialog).getByRole('button', { name: 'Edit the item Mehl' }));
      const edit = await screen.findByRole('dialog', { name: 'Edit item' });
      const unit = within(edit).getByLabelText('Unit');

      expect(unit).toHaveDisplayValue('pcs');
      expect(unit).toHaveAccessibleDescription("Unit doesn't fit Mehl");
      expect(unit).toBeInvalid();
      // Mehl is counted in grams: pieces can't be chosen again.
      expect(unitOptions(unit)).toEqual([
        ['g', false],
        ['kg', false],
        ['tbsp', false],
        ['tsp', false],
        ['pcs', true],
      ]);
      await user.clear(within(edit).getByLabelText('Amount (optional)'));
      await user.type(within(edit).getByLabelText('Amount (optional)'), '120');
      await user.selectOptions(unit, 'g');
      expect(within(edit).queryByText("Unit doesn't fit Mehl")).not.toBeInTheDocument();
      await user.click(within(edit).getByRole('button', { name: 'Save' }));

      await waitFor(() => expect(edit).not.toBeInTheDocument());
      await expect(
        bodyOf(fetchMock, `PATCH ${BASE}/extra-items/${FLOUR_EXTRA_ID}`),
      ).resolves.toEqual({ amount: 120, unit: 'g' });
    });

    it('sends an older item back unchanged, with the amount it has', async () => {
      const [flour, ...others] = EXTRA_ITEMS;
      if (!flour) throw new Error('the flour item is missing');
      const third = { ...flour, amount: 1 / 3, unit: 'piece' as const, unit_fits: false };
      const { fetchMock, user } = renderList({
        [`GET ${BASE}`]: listDetail({ extra_items: [third, ...others] }),
        [`PATCH ${BASE}/extra-items/${FLOUR_EXTRA_ID}`]: listDetail(),
      });

      const lines = await screen.findByTestId(testIds.listLines);
      await user.click(within(lines).getByRole('button', { name: /^Mehl/ }));
      const dialog = await screen.findByRole('dialog', { name: 'Mehl' });
      await user.click(within(dialog).getByRole('button', { name: 'Edit the item Mehl' }));
      const edit = await screen.findByRole('dialog', { name: 'Edit item' });
      expect(within(edit).getByLabelText('Amount (optional)')).toHaveValue('0.333');
      await user.click(within(edit).getByRole('button', { name: 'Save' }));

      // Not rounded to what the field shows: the server keeps the item as it is (D-33).
      await waitFor(() => expect(edit).not.toBeInTheDocument());
      await expect(
        bodyOf(fetchMock, `PATCH ${BASE}/extra-items/${FLOUR_EXTRA_ID}`),
      ).resolves.toEqual({ amount: 1 / 3, unit: 'piece' });
    });

    it('starts a linked item without an amount on its base unit', async () => {
      const [flour, ...others] = EXTRA_ITEMS;
      if (!flour) throw new Error('the flour item is missing');
      const bare = { ...flour, amount: null, unit: null };
      const { fetchMock, user } = renderList({
        [`GET ${BASE}`]: listDetail({ extra_items: [bare, ...others] }),
        [`PATCH ${BASE}/extra-items/${FLOUR_EXTRA_ID}`]: listDetail(),
      });

      const lines = await screen.findByTestId(testIds.listLines);
      await user.click(within(lines).getByRole('button', { name: /^Mehl/ }));
      const dialog = await screen.findByRole('dialog', { name: 'Mehl' });
      await user.click(within(dialog).getByRole('button', { name: 'Edit the item Mehl' }));
      const edit = await screen.findByRole('dialog', { name: 'Edit item' });

      await waitFor(() => expect(within(edit).getByLabelText('Unit')).toHaveDisplayValue('g'));
      await user.type(within(edit).getByLabelText('Amount (optional)'), '300');
      expect(within(edit).getByLabelText('Unit')).toBeValid();
      await user.click(within(edit).getByRole('button', { name: 'Save' }));

      await waitFor(() => expect(edit).not.toBeInTheDocument());
      await expect(
        bodyOf(fetchMock, `PATCH ${BASE}/extra-items/${FLOUR_EXTRA_ID}`),
      ).resolves.toEqual({ amount: 300, unit: 'g' });
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
      // It ends with the lines (D-43).
      expect(text.endsWith('- Mehl: 850 g\n- Salz')).toBe(true);
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
    expect(document.body).not.toHaveTextContent(FORMER_REMINDER);
    expect(screen.queryByTestId(testIds.hiddenLines)).not.toBeInTheDocument();
    // Only a list opened from "+ New list" starts with the picker.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
