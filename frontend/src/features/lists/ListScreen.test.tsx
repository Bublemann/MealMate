import { focusManager } from '@tanstack/react-query';
import type { components } from '@/api/generated/schema';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BEN,
  CARL,
  errorResponse,
  goOffline,
  heldRoute,
  mockApi,
  requestsTo,
  TEST_USER,
} from '@/test/api';
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
  shoppingList,
  doneList,
} from '@/test/lists';
import { menuItemNames, openMoreMenu } from '@/test/menu';
import {
  CATEGORIES,
  expectInPageOrder,
  found,
  ingredient,
  summary,
  unitOptions,
  UNITS,
} from '@/test/ingredients';
import { EGGS, FLOUR, foundMeal, MILK, mealSummary } from '@/test/meals';
import { dueItem } from '@/test/recurring';
import { renderApp } from '@/test/render';
import { swipe, tap } from '@/test/swipe';
import { testIds } from '@/testIds';

type Schemas = components['schemas'];

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
  vi.restoreAllMocks();
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

      it('lets a later click through, e.g. from a keyboard, after a swipe', async () => {
        vi.useFakeTimers({ shouldAdvanceTime: true });
        const { fetchMock } = renderList({ [`PATCH ${BASE}/meals/lm-pancakes`]: listDetail() });
        await screen.findByTestId(testIds.listMeals);
        const row = mealRow('Pfannkuchen');

        // No click follows this short swipe, as on a phone.
        swipe(within(row).getByRole('link'), { from: 600, to: 580 });
        vi.advanceTimersByTime(1000);
        fireEvent.click(within(row).getByRole('button', { name: 'More servings of Pfannkuchen' }));

        await waitFor(() =>
          expect(requestsTo(fetchMock, `PATCH ${BASE}/meals/lm-pancakes`)).toHaveLength(1),
        );
        vi.useRealTimers();
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

  describe('sections (LIST-05, D-41)', () => {
    function section(name: string) {
      return screen.getByRole('region', { name });
    }

    it('shows "Meals" with the meal field, then "Items" with the item field, on a draft', async () => {
      renderList();

      await screen.findByTestId(testIds.listLines);
      const meals = section('Meals');
      const items = section('Items');
      expectInPageOrder([meals, items]);
      expect(within(meals).getByTestId(testIds.mealField)).toBeVisible();
      expectInPageOrder([
        within(meals).getByTestId(testIds.mealField),
        within(meals).getByTestId(testIds.listMeals),
      ]);
      expect(within(items).getByTestId(testIds.extraItemInput)).toBeVisible();
      expectInPageOrder([
        within(items).getByTestId(testIds.extraItemInput),
        within(items).getByTestId(testIds.listLines),
      ]);
      // The old way of adding is gone.
      expect(screen.queryByRole('button', { name: 'Add meals' })).not.toBeInTheDocument();
      expect(screen.queryByText(/Pick a matching ingredient/)).not.toBeInTheDocument();
    });

    it('shows both headings on an empty draft', async () => {
      renderList({ [`GET ${BASE}`]: emptyList() });

      expect(await screen.findByRole('heading', { name: 'Meals' })).toBeVisible();
      expect(screen.getByRole('heading', { name: 'Items' })).toBeVisible();
      expect(screen.getByTestId(testIds.mealField)).toBeVisible();
      expect(screen.getByTestId(testIds.extraItemInput)).toBeVisible();
    });

    it('shows both headings without fields on someone else’s list and on a done list', async () => {
      const carls = listDetail({ owner: CARL, can_edit: false, is_owner: false });
      const { unmount } = renderList({ [`GET ${BASE}`]: carls });

      expect(await screen.findByRole('heading', { name: 'Meals' })).toBeVisible();
      expect(screen.getByRole('heading', { name: 'Items' })).toBeVisible();
      expect(screen.queryByTestId(testIds.mealField)).not.toBeInTheDocument();
      expect(screen.queryByTestId(testIds.extraItemInput)).not.toBeInTheDocument();
      unmount();

      renderList({ [`GET ${BASE}`]: doneList() });
      expect(await screen.findByRole('heading', { name: 'Meals' })).toBeVisible();
      expect(screen.getByRole('heading', { name: 'Items' })).toBeVisible();
      expect(screen.queryByTestId(testIds.mealField)).not.toBeInTheDocument();
      expect(screen.queryByTestId(testIds.extraItemInput)).not.toBeInTheDocument();
    });

    it('makes both fields inactive offline on a draft, not hidden (SYNC-03)', async () => {
      const { fetchMock, user } = renderList();
      const mealField = await screen.findByTestId(testIds.mealField);
      const itemField = screen.getByTestId(testIds.extraItemInput);
      await user.type(itemField, 'Kerzen');

      goOffline(fetchMock);

      await waitFor(() => expect(mealField).toBeDisabled());
      expect(itemField).toBeDisabled();
      for (const button of screen.getAllByRole('button', { name: /^Add/ })) {
        expect(button).toBeDisabled();
      }
      expect(screen.queryByTestId(testIds.itemFreeText)).not.toBeInTheDocument();
    });
  });

  describe('meal field (LIST-03, MEAL-09, D-41)', () => {
    const CHILI = mealSummary('Chili', { servings: 4 });
    const LASAGNE = mealSummary('Lasagne', { owner: BEN });
    const PANCAKES = mealSummary('Pfannkuchen');
    const MEALS = [CHILI, LASAGNE, PANCAKES];

    /** The list's meals are these, in this order, each named with its owner's marker. */
    function expectMeals(list: HTMLElement, names: string[]) {
      expect(within(list).getAllByRole('button')).toEqual(
        names.map((name) => within(list).getByRole('button', { name })),
      );
    }

    /** Like the server: `q` matches names, and an equal name is exact. */
    function search(meals: Schemas['MealSummary'][]) {
      return (request: Request) => {
        const q = new URL(request.url).searchParams.get('q')?.toLowerCase();
        if (!q) return meals.map((meal) => foundMeal(meal));
        return meals
          .filter((meal) => meal.name.toLowerCase().includes(q))
          .map((meal) => foundMeal(meal, meal.name.toLowerCase() === q));
      };
    }

    function mealRoutes(routes: Record<string, unknown> = {}) {
      return {
        'GET /api/meals/recent': [CHILI],
        'GET /api/meals': search(MEALS),
        [`POST ${BASE}/meals`]: listDetail(),
        ...routes,
      };
    }

    function queriesSent(fetchMock: ReturnType<typeof mockApi>) {
      return requestsTo(fetchMock, 'GET /api/meals').map((request) =>
        new URL(request.url).searchParams.get('q'),
      );
    }

    it('is a search field and an inactive ＋, without a panel until focused', async () => {
      renderList(mealRoutes());

      const field = await screen.findByTestId(testIds.mealField);
      expect(field).toHaveAccessibleName('Add a meal');
      expect(field).toHaveAttribute('placeholder', 'Search meals');
      expect(field).not.toHaveFocus();
      const meals = screen.getByRole('region', { name: 'Meals' });
      expect(within(meals).getByRole('button', { name: 'Add' })).toBeDisabled();
      expect(screen.queryByTestId(testIds.mealFieldPanel)).not.toBeInTheDocument();
    });

    it('lists recently used meals, then all others A–Z with their owners, when focused empty', async () => {
      const { user } = renderList(mealRoutes());

      await user.click(await screen.findByTestId(testIds.mealField));

      const panel = await screen.findByTestId(testIds.mealFieldPanel);
      const recent = await within(panel).findByRole('list', { name: 'Recently used' });
      // The owner's marker after the name, one's own included (UI-02).
      expectMeals(recent, ['Chili Anna']);
      expect(within(recent).getByRole('img', { name: 'Anna' })).toBeVisible();
      const all = await within(panel).findByRole('list', { name: 'All meals' });
      expectMeals(all, ['Lasagne Ben', 'Pfannkuchen Anna']);
      expect(within(all).getByRole('button', { name: 'Lasagne Ben' })).toBeVisible();
      expect(within(panel).queryByTestId(testIds.mealFieldCreate)).not.toBeInTheDocument();

      // Escape, or a tap elsewhere once it is done, closes it.
      await user.keyboard('{Escape}');
      expect(panel).not.toBeInTheDocument();
      await user.click(screen.getByTestId(testIds.mealField));
      expect(await screen.findByTestId(testIds.mealFieldPanel)).toBeVisible();
      await user.click(screen.getByTestId(testIds.extraItemInput));
      expect(screen.queryByTestId(testIds.mealFieldPanel)).not.toBeInTheDocument();
    });

    it('offers the meals of users the Meals tab hides (MEAL-09, MEAL-10)', async () => {
      const hidingBen = {
        ...TEST_USER,
        filter_hidden: { meals: [BEN.id], lists: [], list_states: [] },
      };
      mockApi({
        ...LIST_ROUTES,
        ...mealRoutes({
          'GET /api/me': hidingBen,
          // Like the server: the user filter on Meals applies unless owners are asked for.
          'GET /api/meals': (request: Request) => {
            const owners = new URL(request.url).searchParams.getAll('owner_ids');
            const meals =
              owners.length > 0
                ? MEALS.filter((meal) => owners.includes(meal.owner.id))
                : MEALS.filter((meal) => meal.owner.id !== BEN.id);
            return meals.map((meal) => foundMeal(meal));
          },
        }),
      });
      const { router, user } = renderApp('/meals', { user: hidingBen });
      const list = await screen.findByTestId(testIds.mealList);
      expect(within(list).queryByText('Lasagne')).not.toBeInTheDocument();

      await act(() => router.navigate(`/lists/${LIST_ID}`));
      await user.click(await screen.findByTestId(testIds.mealField));

      const all = await screen.findByRole('list', { name: 'All meals' });
      await waitFor(() => expectMeals(all, ['Lasagne Ben', 'Pfannkuchen Anna']));
    });

    it('adds a picked meal with the chosen servings, then empties the field and keeps its focus', async () => {
      const { fetchMock, user } = renderList(mealRoutes());
      const field = await screen.findByTestId(testIds.mealField);
      await user.click(field);
      expect(await screen.findByRole('list', { name: 'Recently used' })).toBeVisible();

      await user.type(field, 'lasa');
      const results = await screen.findByRole('list', { name: 'Matching meals' });
      expectMeals(results, ['Lasagne Ben']);
      expect(screen.queryByRole('list', { name: 'Recently used' })).not.toBeInTheDocument();
      await user.click(within(results).getByRole('button', { name: /^Lasagne/ }));

      const dialog = await screen.findByRole('dialog', { name: 'Lasagne' });
      expect(dialog).toBe(screen.getByTestId(testIds.servingsDialog));
      // At the meal's own servings (LIST-04).
      expect(within(dialog).getByRole('group', { name: 'Servings of Lasagne' })).toHaveTextContent(
        '2 servings',
      );
      await user.click(within(dialog).getByRole('button', { name: 'More servings of Lasagne' }));
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));

      // Within the tap: closed, emptied and focused, so iOS keeps the keyboard.
      expect(dialog).not.toBeInTheDocument();
      expect(field).toHaveValue('');
      expect(field).toHaveFocus();
      await expect(bodyOf(fetchMock, `POST ${BASE}/meals`)).resolves.toEqual({
        meal_id: 'meal-lasagne',
        servings: 3,
      });
      // Ready for the next meal: recently used is loaded again.
      await waitFor(() => expect(requestsTo(fetchMock, 'GET /api/meals/recent')).toHaveLength(2));
      expect(field).toHaveFocus();
      expect(await screen.findByRole('list', { name: 'Recently used' })).toBeVisible();
    });

    it('opens the servings pop-up with ＋ or Enter for an exact name, one’s own of two', async () => {
      const mine = mealSummary('Lasagne', { id: 'meal-my-lasagne', servings: 6 });
      const { fetchMock, user } = renderList(
        mealRoutes({ 'GET /api/meals': search([LASAGNE, mine, PANCAKES]) }),
      );
      const field = await screen.findByTestId(testIds.mealField);

      await user.type(field, 'LASAGNE');
      await user.click(screen.getByRole('button', { name: 'Add “LASAGNE”' }));
      let dialog = await screen.findByRole('dialog', { name: 'Lasagne' });
      expect(within(dialog).getByRole('group', { name: 'Servings of Lasagne' })).toHaveTextContent(
        '6 servings',
      );
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));
      await expect(bodyOf(fetchMock, `POST ${BASE}/meals`)).resolves.toEqual({
        meal_id: 'meal-my-lasagne',
        servings: 6,
      });

      await user.type(field, 'Pfannkuchen{Enter}');
      dialog = await screen.findByRole('dialog', { name: 'Pfannkuchen' });
      expect(dialog).toBeVisible();
    });

    it('keeps the options of typed text after Escape or a tap elsewhere, in both fields', async () => {
      const { user } = renderList(mealRoutes({ 'GET /api/ingredients': [] }));
      const mealField = await screen.findByTestId(testIds.mealField);
      const itemField = screen.getByTestId(testIds.extraItemInput);

      await user.type(mealField, 'Quiche');
      await user.keyboard('{Escape}');
      await user.click(itemField);
      expect(screen.getByTestId(testIds.mealFieldCreate)).toBeVisible();

      await user.type(itemField, 'Kerzen');
      await user.keyboard('{Escape}');
      await user.click(mealField);
      expect(screen.getByTestId(testIds.itemFreeText)).toBeVisible();
      expect(screen.getByTestId(testIds.itemNewIngredient)).toBeVisible();
      expect(screen.getByTestId(testIds.mealFieldCreate)).toBeVisible();
    });

    it('says why the search failed, not that no meal matches', async () => {
      const { user } = renderList(
        mealRoutes({
          'GET /api/meals': (request: Request) =>
            new URL(request.url).searchParams.get('q') ? errorResponse(500, 'common.internal') : [],
        }),
      );

      await user.type(await screen.findByTestId(testIds.mealField), 'Quiche');

      const panel = screen.getByTestId(testIds.mealFieldPanel);
      expect(await within(panel).findByRole('alert')).toBeVisible();
      expect(within(panel).queryByText('No meal matches.')).not.toBeInTheDocument();
      expect(within(panel).getByTestId(testIds.mealFieldCreate)).toBeVisible();
    });

    it('opens the meal form with the name for ＋ without an exact match, as its option does', async () => {
      const { router, user } = renderList(mealRoutes());
      const field = await screen.findByTestId(testIds.mealField);

      await user.type(field, 'Quiche');
      const create = await screen.findByTestId(testIds.mealFieldCreate);
      expect(create).toHaveTextContent('“Quiche” as a new meal');
      expect(await screen.findByText('No meal matches.')).toBeVisible();
      await user.click(screen.getByRole('button', { name: 'Add “Quiche”' }));

      await waitFor(() => expect(router.state.location.pathname).toBe('/meals/new'));
      expect(Object.fromEntries(new URLSearchParams(router.state.location.search))).toEqual({
        addToList: LIST_ID,
        name: 'Quiche',
      });
    });

    it('keeps its option in place when a late answer comes, and drops an earlier text’s', async () => {
      const lasa = heldRoute();
      const lasagne = heldRoute();
      const { fetchMock, user } = renderList(
        mealRoutes({
          'GET /api/meals': (request: Request) => {
            const q = new URL(request.url).searchParams.get('q');
            if (q === 'lasa') return lasa.route();
            if (q === 'lasagne') return lasagne.route();
            return MEALS.map((meal) => foundMeal(meal));
          },
        }),
      );
      const field = await screen.findByTestId(testIds.mealField);

      await user.type(field, 'lasa');
      await waitFor(() => expect(queriesSent(fetchMock)).toContain('lasa'));
      await user.type(field, 'gne');
      const panel = screen.getByTestId(testIds.mealFieldPanel);
      const create = within(panel).getByTestId(testIds.mealFieldCreate);
      expect(create).toHaveTextContent('“lasagne” as a new meal');

      // The answer for "lasa" comes after "lasagne" was typed: it isn't shown.
      await lasa.answer([foundMeal(LASAGNE)]);
      expect(within(panel).queryByRole('list', { name: 'Matching meals' })).not.toBeInTheDocument();
      expect(within(panel).getByTestId(testIds.mealFieldCreate)).toBe(create);

      await lasagne.answer([foundMeal(LASAGNE, true)]);
      const results = await within(panel).findByRole('list', { name: 'Matching meals' });
      expect(within(panel).getByTestId(testIds.mealFieldCreate)).toBe(create);
      expectInPageOrder([create, results]);
    });

    it('waits with ＋ for the results of the text in the field', async () => {
      const held = heldRoute();
      const { user } = renderList(
        mealRoutes({
          'GET /api/meals': (request: Request) =>
            new URL(request.url).searchParams.get('q') ? held.route() : [],
        }),
      );
      const field = await screen.findByTestId(testIds.mealField);

      await user.type(field, 'Lasagne');
      await user.click(screen.getByRole('button', { name: 'Add “Lasagne”' }));
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

      await held.answer([foundMeal(LASAGNE, true)]);
      expect(await screen.findByRole('dialog', { name: 'Lasagne' })).toBeVisible();
    });

    it('opens the pop-up again with the reason when the meal could not be added', async () => {
      const { user } = renderList(
        mealRoutes({
          [`POST ${BASE}/meals`]: errorResponse(422, 'common.validation', [
            { loc: ['body', 'meal_id'], code: 'invalid' },
          ]),
        }),
      );

      await user.type(await screen.findByTestId(testIds.mealField), 'Pfannkuchen{Enter}');
      let dialog = await screen.findByRole('dialog', { name: 'Pfannkuchen' });
      await user.click(
        within(dialog).getByRole('button', { name: 'More servings of Pfannkuchen' }),
      );
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));

      dialog = await screen.findByRole('dialog', { name: 'Pfannkuchen' });
      expect(within(dialog).getByText('Please check your input.')).toBeVisible();
      expect(
        within(dialog).getByRole('group', { name: 'Servings of Pfannkuchen' }),
      ).toHaveTextContent('3 servings');
    });
  });

  describe('item field (LIST-06, D-41)', () => {
    const MILK_REWE = summary('Milch', 'dairy_eggs', {
      id: 'ing-milch-rewe',
      brand: 'REWE',
      base_unit: 'ml',
    });
    const MILK_WEIDE = summary('Milch', 'dairy_eggs', {
      id: 'ing-milch-weide',
      brand: 'Weidehof',
      base_unit: 'ml',
    });

    /** Like the server: names starting with `q`, an equal name exact whatever its brand. */
    function search(ingredients: Schemas['IngredientSummary'][]) {
      return (request: Request) => {
        const q = new URL(request.url).searchParams.get('q')?.toLowerCase() ?? '';
        return ingredients
          .filter((ingredient) => ingredient.name.toLowerCase().startsWith(q))
          .map((ingredient) => found(ingredient, ingredient.name.toLowerCase() === q));
      };
    }

    const routes = {
      'GET /api/ingredients': search([FLOUR, MILK, EGGS]),
      'GET /api/units': UNITS,
      [`POST ${BASE}/extra-items`]: Response.json(listDetail(), { status: 201 }),
    };

    async function pick(user: ReturnType<typeof renderApp>['user'], name: string) {
      const field = await screen.findByTestId(testIds.extraItemInput);
      await user.type(field, name);
      const results = await screen.findByRole('list', { name: 'Matching ingredients' });
      await user.click(
        await within(results).findByRole('button', { name: new RegExp(`^${name}`) }),
      );
      return screen.findByTestId(testIds.amountDialog);
    }

    it('is a search field with ＋, its options under it: free text, then a new ingredient', async () => {
      const { user } = renderList(routes);

      const field = await screen.findByTestId(testIds.extraItemInput);
      expect(field).toHaveAccessibleName('Add an item');
      expect(field).toHaveAttribute('placeholder', 'Search items');
      await user.type(field, 'Me');

      const freeText = screen.getByTestId(testIds.itemFreeText);
      const newIngredient = screen.getByTestId(testIds.itemNewIngredient);
      expect(freeText).toHaveTextContent('“Me” as an item');
      expect(newIngredient).toHaveTextContent('“Me” as a new ingredient');
      const results = await screen.findByRole('list', { name: 'Matching ingredients' });
      expectInPageOrder([field, freeText, newIngredient, results]);
      expect(screen.getByRole('button', { name: 'Add “Me”' })).toBeEnabled();
    });

    it('adds a picked ingredient with amount and unit, then empties the field and keeps its focus', async () => {
      const { fetchMock, user } = renderList(routes);

      const dialog = await pick(user, 'Mehl');
      expect(dialog).toHaveAccessibleName('Mehl');
      const amount = within(dialog).getByLabelText('Amount (optional)');
      // The cursor is in the amount.
      expect(amount).toHaveFocus();
      expect(within(dialog).getByLabelText('Unit')).toHaveValue('g');
      await user.type(amount, '450');
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));

      const field = screen.getByTestId(testIds.extraItemInput);
      expect(dialog).not.toBeInTheDocument();
      expect(field).toHaveValue('');
      expect(field).toHaveFocus();
      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(1),
      );
      await expect(bodyOf(fetchMock, `POST ${BASE}/extra-items`)).resolves.toEqual({
        id: A_UUID_V7,
        ingredient_id: FLOUR.id,
        amount: 450,
        unit: 'g',
      });
      expect(field).toHaveFocus();
    });

    it('adds a linked item without an amount, and checks a typed amount', async () => {
      const { fetchMock, user } = renderList(routes);

      const dialog = await pick(user, 'Mehl');
      await user.type(within(dialog).getByLabelText('Amount (optional)'), '1,5,0');
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));
      expect(within(dialog).getByText('Invalid format')).toBeVisible();
      expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(0);

      await user.clear(within(dialog).getByLabelText('Amount (optional)'));
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));
      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(1),
      );
      await expect(bodyOf(fetchMock, `POST ${BASE}/extra-items`)).resolves.toEqual({
        id: A_UUID_V7,
        ingredient_id: FLOUR.id,
      });
    });

    it('offers the units that fit, and starts with the last one while it fits (REF-02, MEAL-02)', async () => {
      const { user } = renderList(routes);

      let dialog = await pick(user, 'Mehl');
      let unit = within(dialog).getByLabelText('Unit');
      expect(unitOptions(unit)).toEqual([
        ['g', false],
        ['kg', false],
        ['tbsp', false],
        ['tsp', false],
      ]);
      await user.selectOptions(unit, 'tbsp');
      await user.type(within(dialog).getByLabelText('Amount (optional)'), '2{Enter}');
      // Spoons fit millilitres too.
      dialog = await pick(user, 'Milch');
      unit = within(dialog).getByLabelText('Unit');
      expect(unit).toHaveValue('tbsp');
      expect(unitOptions(unit).map(([label]) => label)).toEqual(['ml', 'l', 'tbsp', 'tsp']);
      await user.keyboard('{Escape}');
      // Eggs are counted in pieces: the spoons go.
      await user.clear(screen.getByTestId(testIds.extraItemInput));
      dialog = await pick(user, 'Eier');
      unit = within(dialog).getByLabelText('Unit');
      expect(unit).toHaveValue('piece');
      expect(unitOptions(unit)).toEqual([['pcs', false]]);
      expect(screen.queryByText(/doesn't fit/)).not.toBeInTheDocument();
    });

    it('opens the amount pop-up with ＋ for the only ingredient of that name, whatever its brand', async () => {
      const { user } = renderList({ ...routes, 'GET /api/ingredients': search([MILK_REWE]) });

      await user.type(await screen.findByTestId(testIds.extraItemInput), 'milch');
      await user.click(screen.getByRole('button', { name: 'Add “milch”' }));

      const dialog = await screen.findByTestId(testIds.amountDialog);
      expect(dialog).toHaveAccessibleName('Milch (REWE)');
      expect(within(dialog).getByLabelText('Unit')).toHaveValue('ml');
    });

    it('does nothing with ＋ when several brands have that name: the results stay', async () => {
      const { user } = renderList({
        ...routes,
        'GET /api/ingredients': search([MILK_REWE, MILK_WEIDE]),
      });

      await user.type(await screen.findByTestId(testIds.extraItemInput), 'Milch');
      const results = await screen.findByRole('list', { name: 'Matching ingredients' });
      await user.click(screen.getByRole('button', { name: 'Add “Milch”' }));

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(within(results).getAllByRole('button')).toHaveLength(2);
      expect(screen.getByTestId(testIds.extraItemInput)).toHaveValue('Milch');
    });

    it('adds free text with Enter without a match: amount first, in Other', async () => {
      const { fetchMock, user } = renderList(routes);

      const field = await screen.findByTestId(testIds.extraItemInput);
      await user.type(field, 'Geburtstagskerzen{Enter}');
      const dialog = await screen.findByTestId(testIds.freeTextDialog);
      expect(dialog).toHaveAccessibleName('Geburtstagskerzen');
      const amount = within(dialog).getByLabelText('Amount (optional)');
      expect(amount).toHaveFocus();
      expect(within(dialog).getByLabelText('Category')).toHaveDisplayValue('Other');
      await user.type(amount, '2 Packungen{Enter}');

      expect(field).toHaveValue('');
      expect(field).toHaveFocus();
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

    it('puts free text into the chosen category, also for text that is an ingredient', async () => {
      const { fetchMock, user } = renderList(routes);

      await user.type(await screen.findByTestId(testIds.extraItemInput), 'Mehl');
      await user.click(screen.getByTestId(testIds.itemFreeText));
      const dialog = await screen.findByTestId(testIds.freeTextDialog);
      // By value: user-event compares option labels as HTML (`&amp;`).
      await user.selectOptions(within(dialog).getByLabelText('Category'), 'cat-dairy_eggs');
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));

      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(1),
      );
      await expect(bodyOf(fetchMock, `POST ${BASE}/extra-items`)).resolves.toEqual({
        id: A_UUID_V7,
        text: 'Mehl',
        category_id: 'cat-dairy_eggs',
      });
    });

    it('creates a new ingredient with the typed name, then asks for its amount (ING-04)', async () => {
      const created = ingredient({ id: 'ing-quitten', name: 'Quitten', category_id: 'cat-other' });
      const { fetchMock, user } = renderList({
        ...routes,
        'POST /api/ingredients': Response.json(created, { status: 201 }),
      });

      await user.type(await screen.findByTestId(testIds.extraItemInput), 'Quitten');
      await user.click(screen.getByTestId(testIds.itemNewIngredient));
      const form = await screen.findByRole('dialog', { name: 'New ingredient' });
      expect(within(form).getByLabelText('Name')).toHaveValue('Quitten');
      await user.click(within(form).getByRole('button', { name: 'Save' }));

      const dialog = await screen.findByTestId(testIds.amountDialog);
      expect(dialog).toHaveAccessibleName('Quitten');
      expect(form).not.toBeInTheDocument();
      await user.type(within(dialog).getByLabelText('Amount (optional)'), '3');
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));

      await expect(bodyOf(fetchMock, `POST ${BASE}/extra-items`)).resolves.toEqual({
        id: A_UUID_V7,
        ingredient_id: 'ing-quitten',
        amount: 3,
        unit: 'g',
      });
      expect(screen.getByTestId(testIds.extraItemInput)).toHaveFocus();
    });

    it('keeps its options in place when a late answer comes, and drops an earlier text’s', async () => {
      const mi = heldRoute();
      const { fetchMock, user } = renderList({
        ...routes,
        'GET /api/ingredients': (request: Request) =>
          new URL(request.url).searchParams.get('q') === 'Mi'
            ? mi.route()
            : search([FLOUR, MILK, EGGS])(request),
      });
      const field = await screen.findByTestId(testIds.extraItemInput);

      await user.type(field, 'Mi');
      await waitFor(() =>
        expect(requestsTo(fetchMock, 'GET /api/ingredients').length).toBeGreaterThan(0),
      );
      await user.type(field, 'x');
      const options = [
        screen.getByTestId(testIds.itemFreeText),
        screen.getByTestId(testIds.itemNewIngredient),
      ];

      await mi.answer([found(MILK)]);
      expect(await screen.findByText('“Mix” as an item')).toBe(options[0]?.lastChild);
      expect(screen.queryByRole('list', { name: 'Matching ingredients' })).not.toBeInTheDocument();
      expect(screen.getByTestId(testIds.itemFreeText)).toBe(options[0]);
      expect(screen.getByTestId(testIds.itemNewIngredient)).toBe(options[1]);
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

      const field = await screen.findByTestId(testIds.extraItemInput);
      await user.type(field, 'Kerzen{Enter}');
      await user.click(
        within(await screen.findByTestId(testIds.freeTextDialog)).getByRole('button', {
          name: 'Add',
        }),
      );
      // The pop-up opens again with what went wrong.
      const dialog = await screen.findByTestId(testIds.freeTextDialog);
      expect(await within(dialog).findByRole('alert')).toHaveTextContent(
        "Can't reach MealMate. Are you online?",
      );
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));
      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(2),
      );
      await user.type(field, 'Servietten{Enter}');
      await user.click(
        within(await screen.findByTestId(testIds.freeTextDialog)).getByRole('button', {
          name: 'Add',
        }),
      );

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

    it('shows the server’s field errors next to the field, in the pop-up opened again', async () => {
      const { user } = renderList({
        ...routes,
        [`POST ${BASE}/extra-items`]: errorResponse(422, 'common.validation', [
          { loc: ['body', 'amount'], code: 'out_of_range' },
        ]),
      });

      let dialog = await pick(user, 'Mehl');
      await user.type(within(dialog).getByLabelText('Amount (optional)'), '999999');
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));

      dialog = await screen.findByTestId(testIds.amountDialog);
      expect(await within(dialog).findByText('Out of range')).toBeVisible();
      expect(within(dialog).getByLabelText('Amount (optional)')).toHaveValue('999999');
      expect(screen.queryByText('Please check your input.')).not.toBeInTheDocument();
    });
  });

  describe('"Fällig" box (LIST-16, D-42)', () => {
    const TOOTHPASTE = dueItem({
      ingredient: summary('Zahnpasta', 'other', {
        id: 'ing-zahnpasta',
        brand: 'Elmex',
        base_unit: 'g',
      }),
      due_on: '2026-10-25',
      days_until_due: 0,
      last_purchased_on: '2025-12-20',
      last_amount: null,
    });
    const DUE = [dueItem(), TOOTHPASTE];
    const withDue = (overrides: Partial<Schemas['ListDetail']> = {}) =>
      listDetail({ due_items: DUE, ...overrides });

    beforeEach(() => {
      vi.useFakeTimers({ toFake: ['Date'] });
      vi.setSystemTime(new Date('2026-10-25T10:00:00'));
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    function dueRows() {
      return within(screen.getByTestId(testIds.dueBox)).getAllByTestId(testIds.dueItem);
    }

    it('shows the due items below the item field and above the lines, in the server’s order', async () => {
      renderList({ [`GET ${BASE}`]: withDue() });

      const box = await screen.findByTestId(testIds.dueBox);
      expect(box).toHaveAccessibleName('Due');
      const items = screen.getByRole('region', { name: 'Items' });
      expect(items).toContainElement(box);
      expectInPageOrder([
        within(items).getByTestId(testIds.extraItemInput),
        box,
        within(items).getByTestId(testIds.listLines),
      ]);
      expect(dueRows().map((row) => row.textContent)).toEqual([
        'Klopapierdue for 3 days · last 24/09',
        'Zahnpasta (Elmex)due today · last 20/12/2025',
      ]);
    });

    it('words the rows in German and names ＋ and ✕ after the ingredient (A11Y-01)', async () => {
      const { authSession } = renderList({ [`GET ${BASE}`]: withDue() });
      authSession.setUser({ ...authSession.getState().user!, language: 'de' });
      const { changeLanguage } = await import('@/i18n');
      await changeLanguage('de');

      const box = await screen.findByRole('region', { name: 'Fällig' });
      expect(dueRows().map((row) => row.textContent)).toEqual([
        'Klopapierfällig seit 3 Tagen · zuletzt 24.09.',
        'Zahnpasta (Elmex)fällig heute · zuletzt 20.12.2025',
      ]);
      expect(within(box).getByRole('button', { name: 'Klopapier hinzufügen' })).toBeEnabled();
      expect(within(box).getByRole('button', { name: 'Klopapier ausblenden' })).toBeEnabled();
      expect(
        within(box).getByRole('button', { name: 'Zahnpasta (Elmex) hinzufügen' }),
      ).toBeEnabled();
      expect(
        within(box).getByRole('button', { name: 'Zahnpasta (Elmex) ausblenden' }),
      ).toBeEnabled();
    });

    it('adds an item with ＋ through the amount pop-up, the last amount filled in, and it leaves the box', async () => {
      const { fetchMock, user } = renderList({
        [`GET ${BASE}`]: withDue(),
        'GET /api/units': UNITS,
        [`POST ${BASE}/extra-items`]: Response.json(
          withDue({ due_items: [TOOTHPASTE], version: 4 }),
          {
            status: 201,
          },
        ),
      });

      await user.click(await screen.findByRole('button', { name: 'Add Klopapier' }));
      const dialog = await screen.findByTestId(testIds.amountDialog);
      expect(dialog).toHaveAccessibleName('Klopapier');
      expect(within(dialog).getByLabelText('Amount (optional)')).toHaveValue('12');
      expect(within(dialog).getByLabelText('Unit')).toHaveValue('piece');
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));

      expect(dialog).not.toBeInTheDocument();
      // The row leaves: the focus goes on to the next row's ＋, not into the item field.
      await waitFor(() =>
        expect(screen.getByRole('button', { name: 'Add Zahnpasta (Elmex)' })).toHaveFocus(),
      );
      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(1),
      );
      await expect(bodyOf(fetchMock, `POST ${BASE}/extra-items`)).resolves.toEqual({
        id: A_UUID_V7,
        ingredient_id: 'ing-klopapier',
        amount: 12,
        unit: 'piece',
      });
      await waitFor(() =>
        expect(dueRows().map((row) => row.textContent)).toEqual([
          'Zahnpasta (Elmex)due today · last 20/12/2025',
        ]),
      );
    });

    it('takes the row out at once, so a second ＋ can’t add it twice, and brings it back on an error', async () => {
      const post = heldRoute();
      const { user } = renderList({
        [`GET ${BASE}`]: withDue(),
        'GET /api/units': UNITS,
        [`POST ${BASE}/extra-items`]: post.route,
      });

      await user.click(await screen.findByRole('button', { name: 'Add Klopapier' }));
      const dialog = await screen.findByTestId(testIds.amountDialog);
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));

      expect(dueRows().map((row) => row.textContent)).toEqual([
        'Zahnpasta (Elmex)due today · last 20/12/2025',
      ]);
      await post.answer(errorResponse(409, 'list.not_draft'));
      expect(await screen.findByTestId(testIds.amountDialog)).toBeVisible();
      await user.keyboard('{Escape}');
      await waitFor(() => expect(dueRows()).toHaveLength(2));
    });

    describe('focus when a row leaves (A11Y-01)', () => {
      /** The server hides what it is asked to and answers with the rest. */
      function hiding(due: Schemas['DueItem'][]) {
        let left = due;
        return {
          [`GET ${BASE}`]: () => withDue({ due_items: left }),
          ...Object.fromEntries(
            due.map((item) => [
              `POST ${BASE}/due-items/${item.ingredient.id}/hide`,
              () => {
                left = left.filter((other) => other !== item);
                return withDue({ due_items: left, version: 4 });
              },
            ]),
          ),
        };
      }

      /** Long enough for Radix to hand the focus back after a pop-up closed. */
      async function settle() {
        await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
      }

      it('goes to the item field when ＋ added the only due item', async () => {
        const { user } = renderList({
          [`GET ${BASE}`]: withDue({ due_items: [dueItem()] }),
          'GET /api/units': UNITS,
          [`POST ${BASE}/extra-items`]: Response.json(withDue({ due_items: [] }), { status: 201 }),
        });

        await user.click(await screen.findByRole('button', { name: 'Add Klopapier' }));
        const dialog = await screen.findByTestId(testIds.amountDialog);
        await user.click(within(dialog).getByRole('button', { name: 'Add' }));

        await waitFor(() => expect(screen.queryByTestId(testIds.dueBox)).not.toBeInTheDocument());
        await settle();
        expect(screen.getByTestId(testIds.extraItemInput)).toHaveFocus();
      });

      it('goes back to ＋ when the pop-up is cancelled', async () => {
        const { user } = renderList({ [`GET ${BASE}`]: withDue(), 'GET /api/units': UNITS });

        const plus = await screen.findByRole('button', { name: 'Add Zahnpasta (Elmex)' });
        await user.click(plus);
        await screen.findByTestId(testIds.amountDialog);
        await user.keyboard('{Escape}');

        await settle();
        expect(plus).toHaveFocus();
      });

      it('goes to the item field when ✕ hid the only due item', async () => {
        const { user } = renderList(hiding([dueItem()]));

        await user.click(await screen.findByRole('button', { name: 'Hide Klopapier' }));

        await waitFor(() => expect(screen.queryByTestId(testIds.dueBox)).not.toBeInTheDocument());
        await settle();
        expect(screen.getByTestId(testIds.extraItemInput)).toHaveFocus();
      });

      it('goes to the ✕ of the row that takes its place, or of the one above', async () => {
        const { user } = renderList(hiding(DUE));

        await user.click(await screen.findByRole('button', { name: 'Hide Klopapier' }));
        await waitFor(() =>
          expect(screen.getByRole('button', { name: 'Hide Zahnpasta (Elmex)' })).toHaveFocus(),
        );
        await settle();
        expect(screen.getByRole('button', { name: 'Hide Zahnpasta (Elmex)' })).toHaveFocus();

        await user.keyboard('{Enter}');
        await waitFor(() => expect(screen.queryByTestId(testIds.dueBox)).not.toBeInTheDocument());
        expect(screen.getByTestId(testIds.extraItemInput)).toHaveFocus();
      });

      it('goes to the ✕ of the row above when the last row is hidden', async () => {
        const { user } = renderList(hiding(DUE));

        await user.click(await screen.findByRole('button', { name: 'Hide Zahnpasta (Elmex)' }));

        await waitFor(() =>
          expect(screen.getByRole('button', { name: 'Hide Klopapier' })).toHaveFocus(),
        );
      });
    });

    describe('when ✕ fails', () => {
      const failing = (due: () => Schemas['DueItem'][]) => ({
        [`GET ${BASE}`]: () => withDue({ due_items: due() }),
        'GET /api/units': UNITS,
        [`POST ${BASE}/due-items/ing-klopapier/hide`]: errorResponse(409, 'list.not_draft'),
      });
      const NOT_DRAFT = "This list is no longer a draft, so this can't be changed any more.";

      it('says why and brings the row back, until the due items change', async () => {
        let due = DUE;
        const { fetchMock, user } = renderList(failing(() => due));

        await user.click(await screen.findByRole('button', { name: 'Hide Klopapier' }));

        expect(await screen.findByText(NOT_DRAFT)).toBeVisible();
        await waitFor(() => expect(dueRows()).toHaveLength(2));
        // A later load that changes the due items clears it.
        due = [dueItem()];
        const loads = requestsTo(fetchMock, `GET ${BASE}`).length;
        act(() => {
          focusManager.setFocused(false);
          focusManager.setFocused(true);
        });
        await waitFor(() =>
          expect(requestsTo(fetchMock, `GET ${BASE}`).length).toBeGreaterThan(loads),
        );
        await waitFor(() => expect(dueRows()).toHaveLength(1));
        expect(screen.queryByText(NOT_DRAFT)).not.toBeInTheDocument();
      });

      it('clears the error with the next action in the box', async () => {
        const { user } = renderList(failing(() => DUE));

        await user.click(await screen.findByRole('button', { name: 'Hide Klopapier' }));
        expect(await screen.findByText(NOT_DRAFT)).toBeVisible();
        await waitFor(() => expect(dueRows()).toHaveLength(2));

        await user.click(screen.getByRole('button', { name: 'Add Zahnpasta (Elmex)' }));
        expect(screen.queryByText(NOT_DRAFT)).not.toBeInTheDocument();
      });
    });

    it('opens the amount pop-up empty, on the base unit, without a last amount', async () => {
      const { fetchMock, user } = renderList({
        [`GET ${BASE}`]: withDue(),
        'GET /api/units': UNITS,
        [`POST ${BASE}/extra-items`]: Response.json(withDue({ due_items: [dueItem()] }), {
          status: 201,
        }),
      });

      await user.click(await screen.findByRole('button', { name: 'Add Zahnpasta (Elmex)' }));
      const dialog = await screen.findByTestId(testIds.amountDialog);
      expect(dialog).toHaveAccessibleName('Zahnpasta (Elmex)');
      expect(within(dialog).getByLabelText('Amount (optional)')).toHaveValue('');
      expect(within(dialog).getByLabelText('Unit')).toHaveValue('g');
      await user.click(within(dialog).getByRole('button', { name: 'Add' }));

      await waitFor(() =>
        expect(requestsTo(fetchMock, `POST ${BASE}/extra-items`)).toHaveLength(1),
      );
      await expect(bodyOf(fetchMock, `POST ${BASE}/extra-items`)).resolves.toEqual({
        id: A_UUID_V7,
        ingredient_id: 'ing-zahnpasta',
      });
    });

    it('keeps its rows in place while a pop-up is open, and follows the list once it closes', async () => {
      let partnerAdded = false;
      const { fetchMock, user } = renderList({
        // Ben adds Klopapier meanwhile: the next load no longer has it.
        [`GET ${BASE}`]: () =>
          partnerAdded ? withDue({ due_items: [TOOTHPASTE], version: 4 }) : withDue(),
        'GET /api/units': UNITS,
      });
      await user.click(await screen.findByRole('button', { name: 'Add Zahnpasta (Elmex)' }));
      const dialog = await screen.findByTestId(testIds.amountDialog);

      partnerAdded = true;
      const loads = requestsTo(fetchMock, `GET ${BASE}`).length;
      act(() => {
        focusManager.setFocused(false);
        focusManager.setFocused(true);
      });
      await waitFor(() =>
        expect(requestsTo(fetchMock, `GET ${BASE}`).length).toBeGreaterThan(loads),
      );
      await act(() => new Promise((resolve) => setTimeout(resolve, 50)));
      expect(dueRows()).toHaveLength(2);

      await user.keyboard('{Escape}');
      expect(dialog).not.toBeInTheDocument();
      await waitFor(() => expect(dueRows()).toHaveLength(1));
      expect(dueRows()[0]).toHaveTextContent('Zahnpasta (Elmex)');
    });

    it('keeps the box offline with ＋ and ✕ inactive, not hidden (SYNC-03, D-10)', async () => {
      const { fetchMock } = renderList({ [`GET ${BASE}`]: withDue() });
      const box = await screen.findByTestId(testIds.dueBox);

      goOffline(fetchMock);

      await waitFor(() =>
        expect(within(box).getByRole('button', { name: 'Add Klopapier' })).toBeDisabled(),
      );
      expect(dueRows()).toHaveLength(2);
      for (const button of within(box).getAllByRole('button')) {
        expect(button).toBeDisabled();
      }
    });

    it('shows no box when nothing is due, on a done list or on someone else’s list', async () => {
      const { unmount } = renderList();
      await screen.findByTestId(testIds.extraItemInput);
      expect(screen.queryByTestId(testIds.dueBox)).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: 'Due' })).not.toBeInTheDocument();
      unmount();

      // Whatever the list detail carries (the server sends none there).
      const carls = withDue({ owner: CARL, can_edit: false, is_owner: false });
      const second = renderList({ [`GET ${BASE}`]: carls });
      await screen.findByTestId(testIds.listReadOnly);
      expect(screen.queryByTestId(testIds.dueBox)).not.toBeInTheDocument();
      expect(screen.queryByText('Klopapier')).not.toBeInTheDocument();
      second.unmount();

      renderList({ [`GET ${BASE}`]: doneList({ due_items: DUE }) });
      await screen.findByTestId(testIds.listDone);
      expect(screen.queryByTestId(testIds.dueBox)).not.toBeInTheDocument();
      expect(screen.queryByText('Klopapier')).not.toBeInTheDocument();
    });

    it('hides an item with ✕ at once, without asking, and it stays hidden when the list is loaded again', async () => {
      const HIDE = `POST ${BASE}/due-items/ing-klopapier/hide`;
      let hidden = false;
      const { fetchMock, user } = renderList({
        // Ben's draft, shared with me: a hide counts for both of us (CPL-03).
        [`GET ${BASE}`]: () =>
          withDue({
            owner: BEN,
            is_owner: false,
            shared_with_partner: true,
            due_items: hidden ? [TOOTHPASTE] : DUE,
          }),
        [HIDE]: () => {
          hidden = true;
          return withDue({
            owner: BEN,
            is_owner: false,
            shared_with_partner: true,
            due_items: [TOOTHPASTE],
            version: 4,
          });
        },
      });

      await user.click(await screen.findByRole('button', { name: 'Hide Klopapier' }));

      expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
      expect(dueRows().map((row) => row.textContent)).toEqual([
        'Zahnpasta (Elmex)due today · last 20/12/2025',
      ]);
      await waitFor(() => expect(requestsTo(fetchMock, HIDE)).toHaveLength(1));
      const loads = requestsTo(fetchMock, `GET ${BASE}`).length;
      act(() => {
        focusManager.setFocused(false);
        focusManager.setFocused(true);
      });
      await waitFor(() =>
        expect(requestsTo(fetchMock, `GET ${BASE}`).length).toBeGreaterThan(loads),
      );
      expect(dueRows().map((row) => row.textContent)).toEqual([
        'Zahnpasta (Elmex)due today · last 20/12/2025',
      ]);
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
        const row = within(screen.getByTestId(testIds.listLines))
          .getAllByTestId(testIds.listLine)
          .find((line) => within(line).queryByRole('button', { name: /^Milch/ }));
        return within(row!).queryByRole('button', { name: 'Hide', hidden: true });
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

      it('keeps a line that was swiped only a little or scrolled past, and ignores the mouse', async () => {
        const { fetchMock } = renderList({ [HIDE]: milkHidden });
        await screen.findByTestId(testIds.listLines);

        swipe(milk(), { from: 600, to: 560 });
        expect(hideAction()).not.toBeInTheDocument();
        swipe(milk(), { from: 600, to: 450, dy: 200 });
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

  describe('⋯ menu (D-39)', () => {
    const carls = listDetail({ owner: CARL, is_owner: false, can_edit: false });
    const bens = listDetail({ owner: BEN, is_owner: false, shared_with_partner: true });

    beforeEach(() => {
      // As on the iPhone, which has a share sheet: export reads "Share as text".
      Object.defineProperty(navigator, 'share', {
        value: () => Promise.resolve(),
        configurable: true,
      });
    });

    it.each([
      {
        role: 'owner in a couple, draft',
        routes: { 'GET /api/couple': IN_COUPLE },
        items: ['Rename', 'Share as text', 'Shared with Ben (off)', 'Delete'],
      },
      {
        role: 'owner in a couple, shopping',
        routes: {
          'GET /api/couple': IN_COUPLE,
          [`GET ${BASE}`]: shoppingList({ shared_with_partner: true }),
        },
        items: ['Rename', 'Share as text', 'Shared with Ben (on)', 'Delete'],
      },
      { role: 'owner without a partner', routes: {}, items: ['Rename', 'Share as text', 'Delete'] },
      {
        role: 'partner on a shared list (CPL-03)',
        routes: { 'GET /api/couple': IN_COUPLE, [`GET ${BASE}`]: bens },
        items: ['Rename', 'Share as text'],
      },
      {
        role: 'someone else’s list (VIS-03)',
        routes: { [`GET ${BASE}`]: carls },
        items: ['Copy to my lists', 'Share as text'],
      },
      {
        role: 'owner of a done list (LIST-13, SHOP-06)',
        routes: { 'GET /api/couple': IN_COUPLE, [`GET ${BASE}`]: doneList() },
        items: ['Shop again', 'Reopen', 'Share as text', 'Delete'],
      },
      {
        role: 'partner on a shared done list',
        routes: { [`GET ${BASE}`]: doneList({ owner: BEN, is_owner: false }) },
        items: ['Shop again', 'Reopen', 'Share as text'],
      },
      {
        role: 'another user’s done list',
        routes: { [`GET ${BASE}`]: doneList({ owner: CARL, is_owner: false, can_edit: false }) },
        items: ['Copy to my lists', 'Shop again', 'Share as text'],
      },
    ])('offers the items of the $role in order', async ({ routes, items }) => {
      const { user } = renderList(routes);
      await screen.findByTestId(testIds.screenList);
      await screen.findByRole('heading', { level: 2, name: 'Items' });

      const menu = await openMoreMenu(user);

      expect(menuItemNames(menu)).toEqual(items);
      // Their buttons are gone from the screen.
      for (const id of [testIds.renameList, testIds.exportList, testIds.deleteList]) {
        expect(screen.queryAllByTestId(id).every((element) => menu.contains(element))).toBe(true);
      }
      if (items.includes('Delete')) {
        const remove = within(menu).getByRole('menuitem', { name: 'Delete' });
        expect(menu.lastElementChild).toBe(remove);
        expect(remove.previousElementSibling).toHaveAttribute('role', 'separator');
      }
    });

    it('is a button named "More actions" in the strip, which arrows and Escape work (A11Y-02)', async () => {
      const { user } = renderList();
      await screen.findByTestId(testIds.listLines);
      const button = screen.getByRole('button', { name: 'More actions' });
      expect(within(screen.getByTestId(testIds.detailStrip)).getByTestId(testIds.moreActions)).toBe(
        button,
      );
      expect(button).toHaveAttribute('aria-haspopup', 'menu');

      button.focus();
      await user.keyboard('{Enter}');
      const menu = await screen.findByRole('menu');
      expect(within(menu).getByRole('menuitem', { name: 'Rename' })).toHaveFocus();
      await user.keyboard('{ArrowDown}');
      expect(within(menu).getByRole('menuitem', { name: 'Share as text' })).toHaveFocus();
      await user.keyboard('{ArrowDown}');
      expect(within(menu).getByRole('menuitem', { name: 'Delete' })).toHaveFocus();
      await user.keyboard('{ArrowUp}');
      expect(within(menu).getByRole('menuitem', { name: 'Share as text' })).toHaveFocus();

      await user.keyboard('{Escape}');
      await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
      expect(button).toHaveFocus();
    });

    it('closes on a tap outside, which does nothing else', async () => {
      const { fetchMock, user } = renderList({ [`PATCH ${BASE}/meals/lm-pancakes`]: listDetail() });
      await screen.findByTestId(testIds.listLines);

      const more = screen.getByRole('button', { name: 'More servings of Pfannkuchen' });
      await openMoreMenu(user);
      await user.click(more);

      await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
      // The servings didn't change: the tap only closed the menu.
      expect(requestsTo(fetchMock, `PATCH ${BASE}/meals/lm-pancakes`)).toHaveLength(0);
      // The next tap works as usual.
      await user.click(more);
      await waitFor(() =>
        expect(requestsTo(fetchMock, `PATCH ${BASE}/meals/lm-pancakes`)).toHaveLength(1),
      );
    });

    it('is not shown before the list is there', async () => {
      renderList({ [`GET ${BASE}`]: heldRoute().route });

      expect(await screen.findByTestId(testIds.backLink)).toBeVisible();
      expect(screen.queryByTestId(testIds.moreActions)).not.toBeInTheDocument();
    });

    it('keeps the read-only note on screen, without a button (VIS-03)', async () => {
      const { user } = renderList({ [`GET ${BASE}`]: carls });

      const note = await screen.findByTestId(testIds.listReadOnly);
      expect(note).toHaveTextContent(
        "This is Carl's list. You can look at it and copy it, but not change it.",
      );
      expect(within(note).queryByRole('button')).not.toBeInTheDocument();
      expect(screen.getByTestId(testIds.listMeals)).toHaveTextContent('4 servings');
      expect(screen.queryByRole('group', { name: /^Servings of/ })).not.toBeInTheDocument();
      expect(screen.queryByTestId(testIds.mealField)).not.toBeInTheDocument();
      expect(screen.queryByTestId(testIds.extraItemInput)).not.toBeInTheDocument();
      expect(screen.queryByTestId(testIds.floatingBar)).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Remove/ })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /^Restore/ })).not.toBeInTheDocument();

      await user.click(
        within(screen.getByTestId(testIds.listLines)).getByRole('button', { name: /^Mehl/ }),
      );
      const dialog = await screen.findByRole('dialog', { name: 'Mehl' });
      expect(within(dialog).queryByRole('button', { name: /Remove|Edit/ })).not.toBeInTheDocument();
    });

    it('copies someone else’s list to mine and says how many meals were left out (VIS-03/06)', async () => {
      const copy = emptyList({ id: 'list-copy', name: 'Wochenende' });
      const { fetchMock, user, router } = renderList({
        [`GET ${BASE}`]: carls,
        [`POST ${BASE}/copy`]: Response.json({ list: copy, left_out: 2 }, { status: 201 }),
        'GET /api/lists/list-copy': copy,
      });

      const menu = await openMoreMenu(user);
      await user.click(within(menu).getByTestId(testIds.copyList));

      await waitFor(() => expect(router.state.location.pathname).toBe('/lists/list-copy'));
      expect(await screen.findByTestId(testIds.listLeftOut)).toHaveTextContent(
        "2 meals were left out: you can't see them, or they no longer exist.",
      );
      expect(requestsTo(fetchMock, `POST ${BASE}/copy`)).toHaveLength(1);
      expect(await screen.findByTestId(testIds.mealField)).toBeVisible();
    });

    it('says nothing about left-out meals when all were copied', async () => {
      const copy = emptyList({ id: 'list-copy' });
      const { user, router } = renderList({
        [`GET ${BASE}`]: carls,
        [`POST ${BASE}/copy`]: Response.json({ list: copy, left_out: 0 }, { status: 201 }),
        'GET /api/lists/list-copy': copy,
      });

      await user.click(within(await openMoreMenu(user)).getByTestId(testIds.copyList));

      await waitFor(() => expect(router.state.location.pathname).toBe('/lists/list-copy'));
      expect(await screen.findByTestId(testIds.mealField)).toBeVisible();
      expect(screen.queryByTestId(testIds.listLeftOut)).not.toBeInTheDocument();
    });

    it('shows an error of an action in an alert below the title', async () => {
      const { user } = renderList({
        [`GET ${BASE}`]: carls,
        [`POST ${BASE}/copy`]: errorResponse(403, 'common.forbidden'),
      });

      await user.click(within(await openMoreMenu(user)).getByTestId(testIds.copyList));

      const alert = await screen.findByRole('alert');
      expect(alert).toHaveTextContent("You're not allowed to do that.");
      const heading = screen.getByRole('heading', { level: 1 });
      expect(
        heading.compareDocumentPosition(alert) & Node.DOCUMENT_POSITION_FOLLOWING,
      ).toBeTruthy();
    });

    describe('share switch (CPL-02)', () => {
      it('is a switch item named after the partner that toggles with the menu still open', async () => {
        const { fetchMock, user } = renderList({
          'GET /api/couple': IN_COUPLE,
          [`PATCH ${BASE}`]: listDetail({ shared_with_partner: true }),
        });
        await screen.findByTestId(testIds.listLines);

        const menu = await openMoreMenu(user);
        const toggle = within(menu).getByRole('menuitemcheckbox', { name: 'Shared with Ben' });
        expect(toggle).toBe(screen.getByTestId(testIds.shareListSwitch));
        expect(toggle).not.toBeChecked();
        await user.click(toggle);

        expect(menu).toBeInTheDocument();
        await waitFor(() => expect(toggle).toBeChecked());
        expect(screen.getByRole('menu')).toBe(menu);
        await expect(bodyOf(fetchMock, `PATCH ${BASE}`)).resolves.toEqual({
          shared_with_partner: true,
        });
        // No hint and no badge on the screen.
        await user.keyboard('{Escape}');
        await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
        expect(document.body).not.toHaveTextContent(/sees this list|Shared with Ben/);
      });

      it('is not shown to the partner, who may still edit a shared list (CPL-03)', async () => {
        const { user } = renderList({
          'GET /api/couple': IN_COUPLE,
          [`GET ${BASE}`]: bens,
        });
        expect(await screen.findByTestId(testIds.mealField)).toBeVisible();
        expect(screen.queryByTestId(testIds.listReadOnly)).not.toBeInTheDocument();

        const menu = await openMoreMenu(user);
        expect(within(menu).queryByTestId(testIds.shareListSwitch)).not.toBeInTheDocument();
      });
    });

    it('renames the list, and an empty name goes back to the default (LIST-02)', async () => {
      const { fetchMock, user } = renderList({
        [`PATCH ${BASE}`]: async (request: Request) => {
          const { name } = (await request.json()) as { name: string | null };
          return listDetail({ name });
        },
      });

      await user.click(within(await openMoreMenu(user)).getByTestId(testIds.renameList));
      let dialog = await screen.findByRole('dialog', { name: 'Rename list' });
      const field = within(dialog).getByLabelText('Name');
      // The cursor is in the name, so typing can start at once.
      await waitFor(() => expect(field).toHaveFocus());
      expect(field).toHaveValue('Wochenende');
      await user.clear(field);
      await user.type(field, 'Grillabend');
      await user.click(within(dialog).getByRole('button', { name: 'Save' }));

      expect(
        await screen.findByRole('heading', { level: 1, name: 'Grillabend (26/09/2026)' }),
      ).toBeVisible();
      await expect(bodyOf(fetchMock, `PATCH ${BASE}`)).resolves.toEqual({ name: 'Grillabend' });
      await waitFor(() => expect(screen.getByTestId(testIds.moreActions)).toHaveFocus());

      await user.click(within(await openMoreMenu(user)).getByTestId(testIds.renameList));
      dialog = await screen.findByRole('dialog', { name: 'Rename list' });
      expect(within(dialog).getByLabelText('Name')).toHaveValue('Grillabend');
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
      await user.click(within(await openMoreMenu(user)).getByTestId(testIds.renameList));
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

      await user.click(within(await openMoreMenu(user)).getByTestId(testIds.deleteList));
      const confirm = await screen.findByRole('alertdialog', {
        name: 'Delete Wochenende (26/09/2026)?',
      });
      await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
      await user.click(within(confirm).getByRole('button', { name: 'Delete' }));

      await waitFor(() => expect(router.state.location.pathname).toBe('/lists'));
      expect(requestsTo(fetchMock, `DELETE ${BASE}`)).toHaveLength(1);
    });

    it('puts the focus back on ⋯ when deleting is cancelled (LIST-13)', async () => {
      const { fetchMock, user } = renderList({ [`DELETE ${BASE}`]: null });

      await user.click(within(await openMoreMenu(user)).getByTestId(testIds.deleteList));
      const confirm = await screen.findByRole('alertdialog');
      await user.click(within(confirm).getByRole('button', { name: 'Cancel' }));

      await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
      await waitFor(() => expect(screen.getByTestId(testIds.moreActions)).toHaveFocus());
      expect(requestsTo(fetchMock, `DELETE ${BASE}`)).toHaveLength(0);
    });

    it('disables what needs a connection offline, and export still works (SYNC-03, EXP-03)', async () => {
      const share = vi.fn(() => Promise.resolve());
      Object.defineProperty(navigator, 'share', { value: share, configurable: true });
      const { user, fetchMock } = renderList({ 'GET /api/couple': IN_COUPLE });
      await screen.findByTestId(testIds.listLines);
      goOffline(fetchMock);

      const button = await screen.findByRole('button', { name: 'More actions' });
      expect(button).toBeEnabled();
      const menu = await openMoreMenu(user);
      for (const id of [testIds.renameList, testIds.shareListSwitch, testIds.deleteList]) {
        expect(within(menu).getByTestId(id)).toHaveAttribute('aria-disabled', 'true');
      }
      const exportItem = within(menu).getByTestId(testIds.exportList);
      expect(exportItem).not.toHaveAttribute('aria-disabled');

      await user.click(exportItem);
      expect(share).toHaveBeenCalledTimes(1);
    });

    describe('export (EXP-01/02)', () => {
      it('opens the share sheet with the list as text, within the tap', async () => {
        const share = vi.fn(() => Promise.resolve());
        Object.defineProperty(navigator, 'share', { value: share, configurable: true });
        const { user } = renderList();
        await screen.findByTestId(testIds.listLines);

        const menu = await openMoreMenu(user);
        const item = within(menu).getByRole('menuitem', { name: 'Share as text' });
        fireEvent.click(item);

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

      it('copies the text where there is no share sheet, and says so below the title', async () => {
        Reflect.deleteProperty(navigator, 'share');
        const { user } = renderList();
        await screen.findByTestId(testIds.listLines);
        const menu = await openMoreMenu(user);
        const item = within(menu).getByTestId(testIds.exportList);
        // After user-event's setup: it would replace the clipboard with its own.
        const writeText = vi.fn(() => Promise.resolve());
        Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
        expect(item).toHaveTextContent('Copy as text');

        fireEvent.click(item);

        const message = await screen.findByText('Copied – paste the list into a note or message.');
        expect(message).toHaveAttribute('aria-live', 'polite');
        const heading = screen.getByRole('heading', { level: 1 });
        expect(
          heading.compareDocumentPosition(message) & Node.DOCUMENT_POSITION_FOLLOWING,
        ).toBeTruthy();
        expect(writeText).toHaveBeenCalledWith(expect.stringContaining('- Mehl: 850 g'));
      });
    });
  });

  it('says when the list does not exist (any more)', async () => {
    renderList({}, '/lists/gone');

    expect(await screen.findByText("This doesn't exist (any more).")).toBeVisible();
  });

  it('opens with an empty list and says what to do', async () => {
    renderList({ 'GET /api/lists/list-new': emptyList() }, '/lists/list-new');

    expect(
      await screen.findByText('No meals yet. Add some and the items below fill themselves.'),
    ).toBeVisible();
    expect(screen.getByText('Nothing to buy yet.')).toBeVisible();
    expect(document.body).not.toHaveTextContent(FORMER_REMINDER);
    expect(screen.queryByTestId(testIds.hiddenLines)).not.toBeInTheDocument();
    // Only a list opened from "+ New list" starts with the meal field's list showing.
    expect(screen.queryByTestId(testIds.mealFieldPanel)).not.toBeInTheDocument();
  });
});
