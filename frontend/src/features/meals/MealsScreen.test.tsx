import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import {
  BEN,
  CARL,
  errorResponse,
  heldRoute,
  mockApi,
  requestsTo,
  slowFilterSaves,
  TEST_USER,
} from '@/test/api';
import { CUISINES, ME, meal, MEAL_ROUTES, mealSummary, TAGS } from '@/test/meals';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const CHILI = mealSummary('Chili', {
  cuisine: CUISINES[2] ?? null,
  tags: [TAGS[0]!],
  thumb_url: '/api/media/c-thumb.webp',
});
const LASAGNE = mealSummary('Lasagne', {
  owner: BEN,
  cuisine: CUISINES[1] ?? null,
  tags: [TAGS[0]!, TAGS[1]!],
});
const PANCAKES = mealSummary('Pfannkuchen', { tags: [TAGS[1]!] });
const ALL = [CHILI, LASAGNE, PANCAKES];

/**
 * The server's answer: the meals of the owners not hidden in the saved user filter, in any of the
 * cuisines and with every tag asked for (MEAL-09, MEAL-10), then the search.
 */
function listMeals(hidden: () => readonly string[]) {
  return (request: Request) => {
    const params = new URL(request.url).searchParams;
    const cuisines = params.getAll('cuisine_id');
    const tags = params.getAll('tag_id');
    const q = params.get('q');
    return ALL.filter((meal) => !hidden().includes(meal.owner.id))
      .filter((meal) => !cuisines.length || cuisines.includes(meal.cuisine?.id ?? ''))
      .filter((meal) => tags.every((tag) => meal.tags.some((other) => other.id === tag)))
      .filter((meal) => !q || meal.name.toLowerCase().includes(q.toLowerCase()));
  };
}

function renderMeals(routes: Record<string, unknown> = {}, user = TEST_USER) {
  let hidden: readonly string[] = user.filter_hidden.meals;
  const fetchMock = mockApi({
    ...MEAL_ROUTES,
    'GET /api/meals': listMeals(() => hidden),
    // Saves the user filter, as the server does.
    'PATCH /api/me': async (request: Request) => {
      const body = (await request.json()) as Pick<typeof TEST_USER, 'filter_hidden'>;
      hidden = body.filter_hidden.meals;
      return { ...user, filter_hidden: body.filter_hidden };
    },
    ...routes,
  });
  return { fetchMock, ...renderApp('/meals', { user }) };
}

function searches(fetchMock: ReturnType<typeof mockApi>) {
  return requestsTo(fetchMock, 'GET /api/meals').map((request) => new URL(request.url).search);
}

/** The bodies of the profile saves, read from copies so a waitFor can read them again. */
async function savedFilters(fetchMock: ReturnType<typeof mockApi>) {
  return Promise.all(
    requestsTo(fetchMock, 'PATCH /api/me').map((request) => request.clone().json()),
  );
}

/** The rows' texts, also while the filter panel hides the list from screen readers. */
function rowTexts() {
  const list = screen.queryByTestId(testIds.mealList);
  return list
    ? within(list)
        .getAllByTestId(testIds.mealCard)
        .map((row) => row.textContent)
    : [];
}

type User = ReturnType<typeof renderApp>['user'];

async function openPanel(user: User) {
  await user.click(screen.getByTestId(testIds.filterButton));
  return screen.findByRole('dialog', { name: 'Filters' });
}

function group(panel: HTMLElement, name: string) {
  return within(panel).getByRole('group', { name });
}

/** The checkboxes' names: the text of the label each one sits in. */
function checkboxNames(element: HTMLElement) {
  return within(element)
    .getAllByRole('checkbox')
    .map((box) => (box as HTMLInputElement).labels?.[0]?.textContent);
}

describe('MealsScreen', () => {
  it('shows the pinned block at once and the placeholder only below it (UI-01, UI-03)', async () => {
    const meals = heldRoute();
    renderMeals({ 'GET /api/meals': meals.route });

    expect(await screen.findByText('Loading…')).toBeVisible();
    expect(screen.getByLabelText('Search meals')).toBeVisible();
    expect(screen.getByTestId(testIds.filterButton)).toHaveAccessibleName('Filters');
    expect(screen.getByTestId(testIds.newMeal)).toHaveAccessibleName('New meal');

    await meals.answer([]);
    expect(await screen.findByText('No meals yet')).toBeVisible();
    expect(screen.queryByTestId(testIds.loadingState)).toBeNull();
    expect(screen.getByLabelText('Search meals')).toBeVisible();
    expect(screen.getByTestId(testIds.filterButton)).toHaveAccessibleName('Filters');
    expect(screen.getByTestId(testIds.newMeal)).toHaveAccessibleName('New meal');
  });

  it('keeps the same pinned block when the first meals arrive (UI-01)', async () => {
    const meals = heldRoute();
    renderMeals({ 'GET /api/meals': meals.route });
    await screen.findByTestId(testIds.loadingState);
    const pinned = [
      screen.getByLabelText('Search meals'),
      screen.getByTestId(testIds.filterButton),
      screen.getByTestId(testIds.newMeal),
    ];

    await meals.answer(ALL);

    expect(await screen.findByTestId(testIds.mealList)).toBeVisible();
    expect(screen.queryByTestId(testIds.loadingState)).toBeNull();
    // The very same elements: nothing above the list was rebuilt or moved.
    expect([
      screen.getByLabelText('Search meals'),
      screen.getByTestId(testIds.filterButton),
      screen.getByTestId(testIds.newMeal),
    ]).toEqual(pinned);
  });

  it('lists the meals with thumbnail, cuisine and the owner’s marker, mine too (MEAL-09)', async () => {
    renderMeals();

    const list = await screen.findByTestId(testIds.mealList);
    expect(list).toHaveAccessibleName('Meals');
    const rows = within(list).getAllByTestId(testIds.mealCard);
    // No "by Ben" any more: the marker says whose meal it is.
    expect(rows.map((row) => row.textContent)).toEqual([
      'ChiliNordischA',
      'LasagneItalianB',
      'PfannkuchenA',
    ]);
    expect(within(rows[0]!).getByRole('img', { name: 'Anna' })).toHaveTextContent('A');
    expect(within(rows[1]!).getByRole('img', { name: 'Ben' })).toHaveTextContent('B');
    expect(within(rows[2]!).getByRole('img', { name: 'Anna' })).toBeVisible();
    expect(rows[0]).toHaveAttribute('href', '/meals/meal-chili');
    // The thumbnail is decorative: the name is right next to it.
    expect(rows[0]?.querySelector('img')).toHaveAttribute('src', '/api/media/c-thumb.webp');
    expect(rows[0]?.querySelector('img')).toHaveAttribute('alt', '');
    expect(rows[1]?.querySelector('img')).toBeNull();
  });

  it('searches on the server once typing pauses', async () => {
    const { fetchMock, user } = renderMeals();
    await screen.findByTestId(testIds.mealList);

    await user.type(screen.getByLabelText('Search meals'), 'lasagne');

    await waitFor(() => expect(searches(fetchMock)).toEqual(['', '?q=lasagne']));
    await waitFor(() => expect(rowTexts()).toEqual(['LasagneItalianB']));
  });

  it('turns the tile into “Create …”, which opens the form with that name (MEAL-09)', async () => {
    const { router, user } = renderMeals();
    await screen.findByTestId(testIds.mealList);
    const tile = screen.getByTestId(testIds.newMeal);

    await user.type(screen.getByLabelText('Search meals'), ' Lasagne al forno ');
    expect(tile).toHaveAccessibleName('Create “Lasagne al forno”');
    await user.click(tile);

    expect(await screen.findByRole('heading', { level: 1, name: 'New meal' })).toBeVisible();
    expect(router.state.location.pathname).toBe('/meals/new');
    expect(within(screen.getByTestId(testIds.mealForm)).getByLabelText('Name')).toHaveValue(
      'Lasagne al forno',
    );
  });

  it('opens an empty form from “New meal”', async () => {
    const { router, user } = renderMeals();

    await user.click(await screen.findByTestId(testIds.newMeal));

    expect(await screen.findByRole('heading', { level: 1, name: 'New meal' })).toBeVisible();
    expect(router.state.location.pathname).toBe('/meals/new');
    expect(router.state.location.search).toBe('');
    expect(within(screen.getByTestId(testIds.mealForm)).getByLabelText('Name')).toHaveValue('');
  });

  it('offers the user filter, cuisines and tags in the panel, all at their default (UI-01, MEAL-09, MEAL-10)', async () => {
    const { fetchMock, user } = renderMeals();
    await screen.findByTestId(testIds.mealList);

    const panel = await openPanel(user);

    expect(panel).toBe(screen.getByTestId(testIds.filterPanel));
    expect(within(panel).getAllByTestId(testIds.filterGroup)).toEqual([
      group(panel, 'Meals by'),
      group(panel, 'Cuisines'),
      group(panel, 'Tags'),
    ]);
    const names = (name: string) => checkboxNames(group(panel, name));
    await waitFor(() => expect(names('Cuisines')).toEqual(['German', 'Italian', 'Nordisch']));
    // The tags of the meals I can see, not the whole pool.
    expect(names('Tags')).toEqual(['schnell', 'vegetarisch']);
    expect(requestsTo(fetchMock, 'GET /api/tags')).toHaveLength(0);
    // Me first, my partner and everyone else whose meals I can see.
    expect(names('Meals by')).toEqual(['Me', 'Ben', 'Carl (deactivated)']);
    within(group(panel, 'Cuisines'))
      .getAllByRole('checkbox')
      .forEach((box) => expect(box).not.toBeChecked());
    within(group(panel, 'Tags'))
      .getAllByRole('checkbox')
      .forEach((box) => expect(box).not.toBeChecked());
    within(group(panel, 'Meals by'))
      .getAllByRole('checkbox')
      .forEach((box) => expect(box).toBeChecked());
  });

  it('shows meals of any ticked cuisine and with every ticked tag, at once (MEAL-09)', async () => {
    const { fetchMock, user } = renderMeals();
    await screen.findByTestId(testIds.mealList);
    const button = screen.getByTestId(testIds.filterButton);
    const panel = await openPanel(user);
    const cuisines = group(panel, 'Cuisines');
    const tags = group(panel, 'Tags');

    await user.click(await within(cuisines).findByRole('checkbox', { name: 'Italian' }));
    await waitFor(() => expect(rowTexts()).toEqual(['LasagneItalianB']));
    await user.click(within(cuisines).getByRole('checkbox', { name: 'Nordisch' }));
    await waitFor(() => expect(rowTexts()).toEqual(['ChiliNordischA', 'LasagneItalianB']));
    expect(button).toHaveAccessibleName('Filters, 1 active');

    await user.click(within(tags).getByRole('checkbox', { name: 'schnell' }));
    await user.click(within(tags).getByRole('checkbox', { name: 'vegetarisch' }));

    await waitFor(() => expect(rowTexts()).toEqual(['LasagneItalianB']));
    expect(button).toHaveAccessibleName('Filters, 2 active');
    expect(button).toHaveTextContent('2');
    expect(searches(fetchMock).at(-1)).toBe(
      '?cuisine_id=cui-italian&cuisine_id=cui-nordic&tag_id=tag-quick&tag_id=tag-veggie',
    );
  });

  it('unticks a user at once, saves the user filter and loads the meals again (MEAL-10)', async () => {
    const { fetchMock, user } = renderMeals(
      {},
      { ...TEST_USER, filter_hidden: { meals: [], lists: ['someone'] } },
    );
    await screen.findByTestId(testIds.mealList);
    const button = screen.getByTestId(testIds.filterButton);
    const users = group(await openPanel(user), 'Meals by');

    await user.click(await within(users).findByRole('checkbox', { name: 'Ben' }));

    expect(within(users).getByRole('checkbox', { name: 'Ben' })).not.toBeChecked();
    // Ben's meals disappear right away.
    expect(rowTexts()).toEqual(['ChiliNordischA', 'PfannkuchenA']);
    expect(button).toHaveAccessibleName('Filters, 1 active');
    await waitFor(async () =>
      expect(await savedFilters(fetchMock)).toEqual([
        { filter_hidden: { meals: [BEN.id], lists: ['someone'] } },
      ]),
    );
    await waitFor(() => expect(searches(fetchMock)).toEqual(['', '']));
  });

  it('ticks a user again and keeps the others hidden (MEAL-10)', async () => {
    const { fetchMock, user } = renderMeals(
      {},
      { ...TEST_USER, filter_hidden: { meals: [ME.id, BEN.id], lists: [] } },
    );
    // Carl has no meals.
    expect(await screen.findByText('No matches')).toBeVisible();
    const users = group(await openPanel(user), 'Meals by');
    expect(await within(users).findByRole('checkbox', { name: 'Me' })).not.toBeChecked();

    await user.click(within(users).getByRole('checkbox', { name: 'Ben' }));

    await waitFor(async () =>
      expect(await savedFilters(fetchMock)).toEqual([
        { filter_hidden: { meals: [ME.id], lists: [] } },
      ]),
    );
    await waitFor(() => expect(rowTexts()).toEqual(['LasagneItalianB']));
  });

  it('keeps quick changes while earlier ones are still being saved (MEAL-10)', async () => {
    const saves = slowFilterSaves();
    const { fetchMock, user } = renderMeals({ 'PATCH /api/me': saves.route });
    await screen.findByTestId(testIds.mealList);
    const users = group(await openPanel(user), 'Meals by');
    const box = (name: string) => within(users).getByRole('checkbox', { name });
    await within(users).findByRole('checkbox', { name: 'Ben' });

    await user.click(box('Ben'));
    await user.click(box('Carl (deactivated)'));
    // The first save answers while the second waits: it doesn't know about Carl yet.
    await saves.answer(1);
    await user.click(box('Ben'));
    await saves.answer(2);
    await saves.answer(3);

    await waitFor(() => expect(requestsTo(fetchMock, 'PATCH /api/me')).toHaveLength(3));
    expect((await savedFilters(fetchMock))[2]).toEqual({
      filter_hidden: { meals: [CARL.id], lists: [] },
    });
    expect(box('Ben')).toBeChecked();
    expect(box('Carl (deactivated)')).not.toBeChecked();
  });

  it('ticks the user again and says so when saving fails (MEAL-10)', async () => {
    const { user } = renderMeals({
      'PATCH /api/me': errorResponse(503, 'common.service_unavailable'),
    });
    await screen.findByTestId(testIds.mealList);
    const users = group(await openPanel(user), 'Meals by');

    await user.click(await within(users).findByRole('checkbox', { name: 'Ben' }));

    expect(
      await within(users).findByText('MealMate is unavailable right now. Please try again later.'),
    ).toBeVisible();
    expect(within(users).getByRole('checkbox', { name: 'Ben' })).toBeChecked();
    expect(rowTexts()).toEqual(['ChiliNordischA', 'LasagneItalianB', 'PfannkuchenA']);
  });

  it('loads the saved user filter again when saving fails, instead of guessing (MEAL-10)', async () => {
    // Meanwhile Carl was unticked on another device.
    const saved = { ...TEST_USER, filter_hidden: { meals: [CARL.id], lists: [] } };
    const { fetchMock, user } = renderMeals({
      'PATCH /api/me': errorResponse(503, 'common.service_unavailable'),
      'GET /api/me': saved,
    });
    await screen.findByTestId(testIds.mealList);
    const users = group(await openPanel(user), 'Meals by');
    const carl = await within(users).findByRole('checkbox', { name: 'Carl (deactivated)' });
    expect(carl).toBeChecked();

    await user.click(within(users).getByRole('checkbox', { name: 'Ben' }));

    await waitFor(() => expect(carl).not.toBeChecked());
    expect(within(users).getByRole('checkbox', { name: 'Ben' })).toBeChecked();
    expect(requestsTo(fetchMock, 'GET /api/me')).toHaveLength(1);
    await waitFor(() => expect(searches(fetchMock)).toEqual(['', '']));
  });

  it('resets cuisines, tags and users with “Reset” but keeps the search (UI-01)', async () => {
    const { fetchMock, user } = renderMeals(
      {},
      { ...TEST_USER, filter_hidden: { meals: [BEN.id], lists: [] } },
    );
    await screen.findByTestId(testIds.mealList);
    const search = screen.getByLabelText('Search meals');
    await user.type(search, 'a');
    const button = screen.getByTestId(testIds.filterButton);
    const panel = await openPanel(user);
    await user.click(
      await within(group(panel, 'Cuisines')).findByRole('checkbox', { name: 'Italian' }),
    );
    await user.click(within(group(panel, 'Tags')).getByRole('checkbox', { name: 'schnell' }));
    await waitFor(() => expect(button).toHaveAccessibleName('Filters, 3 active'));

    await user.click(within(panel).getByRole('button', { name: 'Reset' }));

    for (const name of ['Cuisines', 'Tags']) {
      within(group(panel, name))
        .getAllByRole('checkbox')
        .forEach((box) => expect(box).not.toBeChecked());
    }
    within(group(panel, 'Meals by'))
      .getAllByRole('checkbox')
      .forEach((box) => expect(box).toBeChecked());
    expect(button).toHaveAccessibleName('Filters');
    expect(search).toHaveValue('a');
    expect((await savedFilters(fetchMock)).at(-1)).toEqual({
      filter_hidden: { meals: [], lists: [] },
    });
    await waitFor(() =>
      expect(rowTexts()).toEqual(['ChiliNordischA', 'LasagneItalianB', 'PfannkuchenA']),
    );
    // The panel stays open until "Done", which gives the focus back to the button.
    await user.click(within(panel).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(panel).not.toBeInTheDocument());
    expect(button).toHaveFocus();
  });

  it('says “No matches”; “Reset filters” clears the search and resets every group (UI-03)', async () => {
    const { fetchMock, user } = renderMeals();
    await screen.findByTestId(testIds.mealList);
    const search = screen.getByLabelText('Search meals');
    const button = screen.getByTestId(testIds.filterButton);
    const panel = await openPanel(user);
    await user.click(
      await within(group(panel, 'Cuisines')).findByRole('checkbox', { name: 'German' }),
    );
    await user.click(within(group(panel, 'Tags')).getByRole('checkbox', { name: 'vegetarisch' }));
    await user.click(within(group(panel, 'Meals by')).getByRole('checkbox', { name: 'Ben' }));
    await user.click(within(panel).getByRole('button', { name: 'Done' }));
    await user.type(search, 'Quitten');

    expect(await screen.findByText('No matches')).toBeVisible();
    expect(screen.queryByText('No meals yet')).toBeNull();
    // The tile offers to create it; there is no other "Create" button.
    expect(screen.getAllByRole('button', { name: 'Create “Quitten”' })).toEqual([
      screen.getByTestId(testIds.newMeal),
    ]);
    await user.click(screen.getByRole('button', { name: 'Reset filters' }));

    expect(search).toHaveValue('');
    expect(button).toHaveAccessibleName('Filters');
    await waitFor(() =>
      expect(rowTexts()).toEqual(['ChiliNordischA', 'LasagneItalianB', 'PfannkuchenA']),
    );
    expect((await savedFilters(fetchMock)).at(-1)).toEqual({
      filter_hidden: { meals: [], lists: [] },
    });
  });

  it('shows one line under the pinned block when there are no meals yet (UI-03)', async () => {
    const { user, router } = renderMeals({ 'GET /api/meals': [] });

    expect(await screen.findByText('No meals yet')).toBeVisible();
    const tab = screen.getByTestId(testIds.screenMeals);
    expect(within(tab).queryAllByRole('heading', { level: 2 })).toEqual([]);
    // Only the pinned block's filter button and tile.
    expect(within(tab).getAllByRole('button')).toEqual([
      screen.getByTestId(testIds.filterButton),
      screen.getByTestId(testIds.newMeal),
    ]);
    await user.click(screen.getByTestId(testIds.newMeal));

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals/new'));
  });

  it('keeps the filter button when every user is unticked, so they can be ticked again (MEAL-10, UI-03)', async () => {
    const { fetchMock, user } = renderMeals(
      {},
      { ...TEST_USER, filter_hidden: { meals: [ME.id, BEN.id, CARL.id], lists: [] } },
    );

    // Nothing to show is no empty tab here: the user filter hides everything.
    expect(await screen.findByText('No matches')).toBeVisible();
    expect(screen.queryByText('No meals yet')).toBeNull();
    const button = screen.getByTestId(testIds.filterButton);
    await waitFor(() => expect(button).toHaveAccessibleName('Filters, 1 active'));
    const users = group(await openPanel(user), 'Meals by');
    within(users)
      .getAllByRole('checkbox')
      .forEach((box) => expect(box).not.toBeChecked());

    await user.click(within(users).getByRole('checkbox', { name: 'Me' }));

    await waitFor(async () =>
      expect(await savedFilters(fetchMock)).toEqual([
        { filter_hidden: { meals: [BEN.id, CARL.id], lists: [] } },
      ]),
    );
    await waitFor(() => expect(rowTexts()).toEqual(['ChiliNordischA', 'PfannkuchenA']));
  });

  it('keeps the search, cuisines and tags until the app closes, but not in the address or browser storage (UI-01)', async () => {
    const { router, unmount, user } = renderMeals({
      'GET /api/meals/meal-lasagne': meal({ id: 'meal-lasagne', name: 'Lasagne', owner: BEN }),
    });
    await screen.findByTestId(testIds.mealList);
    await user.type(screen.getByLabelText('Search meals'), 'lasagne');
    const panel = await openPanel(user);
    await user.click(
      await within(group(panel, 'Cuisines')).findByRole('checkbox', { name: 'Italian' }),
    );
    await user.click(within(group(panel, 'Tags')).getByRole('checkbox', { name: 'vegetarisch' }));
    await user.click(within(panel).getByRole('button', { name: 'Done' }));
    await waitFor(() => expect(rowTexts()).toEqual(['LasagneItalianB']));

    // Open the meal and come back through the tab bar.
    await user.click(screen.getByTestId(testIds.mealCard));
    expect(await screen.findByRole('heading', { level: 1, name: 'Lasagne' })).toBeVisible();
    await user.click(screen.getByTestId(testIds.tabMeals));

    expect(await screen.findByLabelText('Search meals')).toHaveValue('lasagne');
    expect(screen.getByTestId(testIds.newMeal)).toHaveAccessibleName('Create “lasagne”');
    expect(screen.getByTestId(testIds.filterButton)).toHaveAccessibleName('Filters, 2 active');
    await waitFor(() => expect(rowTexts()).toEqual(['LasagneItalianB']));
    const again = await openPanel(user);
    expect(
      within(group(again, 'Cuisines')).getByRole('checkbox', { name: 'Italian' }),
    ).toBeChecked();
    expect(
      within(group(again, 'Tags')).getByRole('checkbox', { name: 'vegetarisch' }),
    ).toBeChecked();
    expect(router.state.location.search).toBe('');
    const stored = [localStorage, sessionStorage].flatMap((storage) =>
      Object.keys(storage).map((key) => `${key}=${storage.getItem(key)}`),
    );
    expect(stored.join('\n')).not.toContain('lasagne');
    expect(stored.join('\n')).not.toContain('cui-italian');
    expect(stored.join('\n')).not.toContain('tag-veggie');

    // Started again, the app has forgotten them.
    unmount();
    renderMeals();
    expect(await screen.findByLabelText('Search meals')).toHaveValue('');
    expect(screen.getByTestId(testIds.filterButton)).toHaveAccessibleName('Filters');
  });

  it('does not call a filled tab empty while all meals load again (UI-03)', async () => {
    const again = heldRoute();
    let fullLoads = 0;
    const { queryClient, user } = renderMeals({
      'GET /api/meals': (request: Request) => {
        if (new URL(request.url).searchParams.get('q')) return [];
        fullLoads += 1;
        return fullLoads === 1 ? ALL : again.route();
      },
    });
    await screen.findByTestId(testIds.mealList);
    await user.type(screen.getByLabelText('Search meals'), 'Quitten');
    expect(await screen.findByText('No matches')).toBeVisible();

    // The cache has dropped the unused full list (after its gcTime), so it is loaded again.
    queryClient.removeQueries({ queryKey: ['meals', 'list', {}], exact: true });
    await user.click(screen.getByRole('button', { name: 'Reset filters' }));
    await waitFor(() => expect(fullLoads).toBe(2));

    expect(screen.queryByText('No meals yet')).toBeNull();
    expect(screen.getByTestId(testIds.loadingState)).toBeVisible();
    await again.answer(ALL);
    await waitFor(() => expect(rowTexts()).toHaveLength(ALL.length));
  });

  it('does not call the tab empty while the meals load again after ticking users (MEAL-10, UI-03)', async () => {
    const again = heldRoute();
    let loads = 0;
    const { user } = renderMeals(
      { 'GET /api/meals': () => (++loads === 1 ? [] : again.route()) },
      { ...TEST_USER, filter_hidden: { meals: [ME.id, BEN.id, CARL.id], lists: [] } },
    );
    expect(await screen.findByText('No matches')).toBeVisible();

    await user.click(screen.getByRole('button', { name: 'Reset filters' }));

    // The answer from before ticked nobody: it says nothing about the meals of everyone.
    expect(screen.queryByText('No meals yet')).toBeNull();
    await waitFor(() => expect(loads).toBe(2));
    expect(screen.queryByText('No meals yet')).toBeNull();
    expect(screen.getByTestId(testIds.loadingState)).toBeVisible();
    await again.answer(ALL);
    await waitFor(() => expect(rowTexts()).toHaveLength(ALL.length));
  });

  it('keeps users hidden who can’t be seen right now (MEAL-10)', async () => {
    // Someone unticked earlier has made their meals private since.
    const { fetchMock, user } = renderMeals(
      {},
      { ...TEST_USER, filter_hidden: { meals: ['user-private'], lists: [] } },
    );
    await screen.findByTestId(testIds.mealList);
    const button = screen.getByTestId(testIds.filterButton);
    const panel = await openPanel(user);
    const users = group(panel, 'Meals by');
    await within(users).findByRole('checkbox', { name: 'Ben' });
    // Everyone visible is ticked: the group is at its default, and "Reset" has nothing to save.
    expect(button).toHaveAccessibleName('Filters');
    await user.click(within(panel).getByRole('button', { name: 'Reset' }));
    expect(requestsTo(fetchMock, 'PATCH /api/me')).toHaveLength(0);

    await user.click(within(users).getByRole('checkbox', { name: 'Ben' }));
    await waitFor(async () =>
      expect(await savedFilters(fetchMock)).toEqual([
        { filter_hidden: { meals: ['user-private', BEN.id], lists: [] } },
      ]),
    );
    await user.click(within(panel).getByRole('button', { name: 'Reset' }));
    await waitFor(async () =>
      expect((await savedFilters(fetchMock)).at(-1)).toEqual({
        filter_hidden: { meals: ['user-private'], lists: [] },
      }),
    );
  });

  it('forgets a ticked tag once no meal I can see has it any more (MEAL-09)', async () => {
    let tags = TAGS;
    const { queryClient, user } = renderMeals({ 'GET /api/meals/tags': () => tags });
    await screen.findByTestId(testIds.mealList);
    const button = screen.getByTestId(testIds.filterButton);
    const panel = await openPanel(user);
    await user.click(
      await within(group(panel, 'Tags')).findByRole('checkbox', { name: 'vegetarisch' }),
    );
    await waitFor(() => expect(rowTexts()).toEqual(['LasagneItalianB', 'PfannkuchenA']));
    await user.click(within(panel).getByRole('button', { name: 'Done' }));

    // Meanwhile the last vegetarian meals lost the tag.
    tags = [TAGS[0]!];
    await queryClient.invalidateQueries({ queryKey: ['meals', 'tags'] });

    await waitFor(() => expect(button).toHaveAccessibleName('Filters'));
    await waitFor(() => expect(rowTexts()).toHaveLength(ALL.length));
  });

  it('shows in the panel when a group’s choices cannot be loaded', async () => {
    const { user } = renderMeals({
      'GET /api/users/visible': errorResponse(503, 'common.service_unavailable'),
    });
    await screen.findByTestId(testIds.mealList);

    const users = group(await openPanel(user), 'Meals by');

    expect(
      await within(users).findByText('MealMate is unavailable right now. Please try again later.'),
    ).toBeVisible();
    expect(within(users).queryByTestId(testIds.loadingState)).toBeNull();
    expect(within(users).queryAllByRole('checkbox')).toEqual([]);
  });

  it('shows a translated error when the meals cannot be loaded', async () => {
    renderMeals({ 'GET /api/meals': errorResponse(503, 'common.service_unavailable') });

    expect(
      await screen.findByText('MealMate is unavailable right now. Please try again later.'),
    ).toBeVisible();
    expect(screen.getByTestId(testIds.newMeal)).toBeVisible();
  });
});
