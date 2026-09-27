import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BEN, CARL, errorResponse, mockApi, requestsTo, TEST_USER } from '@/test/api';
import { CUISINES, ME, MEAL_ROUTES, mealSummary, TAGS } from '@/test/meals';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const ALL = [
  mealSummary('Chili', { cuisine: CUISINES[2] ?? null, thumb_url: '/api/media/c-thumb.webp' }),
  mealSummary('Lasagne', { owner: BEN, cuisine: CUISINES[1] ?? null }),
  mealSummary('Pfannkuchen'),
];

function listMeals(request: Request) {
  const params = new URL(request.url).searchParams;
  if (params.get('q') === 'lasagne' || params.get('cuisine_id') === 'cui-italian') {
    return [ALL[1]];
  }
  return params.size === 0 ? ALL : [];
}

function renderMeals(routes: Record<string, unknown> = {}, user = TEST_USER) {
  const fetchMock = mockApi({
    ...MEAL_ROUTES,
    'GET /api/meals': listMeals,
    ...routes,
  });
  return { fetchMock, ...renderApp('/meals', { user }) };
}

function queries(fetchMock: ReturnType<typeof mockApi>) {
  return requestsTo(fetchMock, 'GET /api/meals').map((request) => new URL(request.url).search);
}

describe('MealsScreen', () => {
  it('lists the meals with thumbnail, owner (if not me) and cuisine', async () => {
    renderMeals();

    const list = await screen.findByTestId(testIds.mealList);
    const cards = within(list).getAllByTestId(testIds.mealCard);
    expect(cards.map((card) => card.textContent)).toEqual([
      'ChiliNordisch',
      'Lasagneby Ben · Italian',
      'Pfannkuchen',
    ]);
    expect(cards[0]).toHaveAttribute('href', '/meals/meal-chili');
    // The thumbnail is decorative: the name is right next to it.
    expect(cards[0]?.querySelector('img')).toHaveAttribute('src', '/api/media/c-thumb.webp');
    expect(cards[0]?.querySelector('img')).toHaveAttribute('alt', '');
    expect(cards[1]?.querySelector('img')).toBeNull();
  });

  it('searches on the server once typing pauses and filters by cuisine and tag', async () => {
    const { fetchMock, user } = renderMeals();
    await screen.findByTestId(testIds.mealList);

    await user.type(screen.getByLabelText('Search meals'), 'lasagne');
    await waitFor(() => expect(queries(fetchMock)).toEqual(['', '?q=lasagne']));
    await waitFor(() => expect(screen.getAllByTestId(testIds.mealCard)).toHaveLength(1));

    await user.clear(screen.getByTestId(testIds.mealSearch));
    await user.selectOptions(screen.getByLabelText('Cuisine'), 'Italian');
    await user.selectOptions(screen.getByLabelText('Tag'), 'vegetarisch');
    await waitFor(() =>
      expect(queries(fetchMock)).toContain('?cuisine_id=cui-italian&tag_id=tag-veggie'),
    );
    expect(screen.getByLabelText('Cuisine')).toHaveDisplayValue('Italian');
  });

  it('offers the tags of the meals I can see in the tag filter, not the whole pool', async () => {
    const { fetchMock } = renderMeals({ 'GET /api/meals/tags': [TAGS[1]] });
    await screen.findByTestId(testIds.mealList);

    const select = screen.getByLabelText('Tag');
    await waitFor(() =>
      expect(
        within(select)
          .getAllByRole('option')
          .map((option) => option.textContent),
      ).toEqual(['All tags', 'vegetarisch']),
    );
    expect(requestsTo(fetchMock, 'GET /api/tags')).toHaveLength(0);
  });

  it('shows a chip per visible user, me first, and marks deactivated users (MEAL-10)', async () => {
    renderMeals();

    const chips = await screen.findByTestId(testIds.mealUserChips);
    expect(chips).toHaveAccessibleName('Show meals of');
    const buttons = within(chips).getAllByRole('button');
    expect(buttons.map((button) => button.textContent)).toEqual([
      'Me',
      'Ben',
      'Carl (deactivated)',
    ]);
    for (const button of buttons) expect(button).toHaveAttribute('aria-pressed', 'true');
  });

  it('switches a chip off at once, saves filter_hidden and loads the meals again', async () => {
    const saved = {
      ...TEST_USER,
      filter_hidden: { meals: [BEN.id], lists: ['someone'] },
    };
    const { fetchMock, user } = renderMeals(
      { 'PATCH /api/me': saved },
      { ...TEST_USER, filter_hidden: { meals: [], lists: ['someone'] } },
    );
    const chips = await screen.findByTestId(testIds.mealUserChips);
    await screen.findByTestId(testIds.mealList);

    await user.click(within(chips).getByRole('button', { name: 'Ben' }));

    expect(within(chips).getByRole('button', { name: 'Ben' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    // Ben's meals disappear right away.
    expect(screen.queryByRole('link', { name: /^Lasagne/ })).not.toBeInTheDocument();
    await waitFor(() => expect(requestsTo(fetchMock, 'PATCH /api/me')).toHaveLength(1));
    await expect(requestsTo(fetchMock, 'PATCH /api/me')[0]?.json()).resolves.toEqual({
      filter_hidden: { meals: [BEN.id], lists: ['someone'] },
    });
    await waitFor(() => expect(queries(fetchMock)).toEqual(['', '']));
  });

  it('switches a chip back on and keeps the others hidden', async () => {
    const { fetchMock, user } = renderMeals(
      {
        'PATCH /api/me': { ...TEST_USER, filter_hidden: { meals: [ME.id], lists: [] } },
      },
      { ...TEST_USER, filter_hidden: { meals: [ME.id, BEN.id], lists: [] } },
    );
    const chips = await screen.findByTestId(testIds.mealUserChips);
    expect(within(chips).getByRole('button', { name: 'Me' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );

    await user.click(within(chips).getByRole('button', { name: 'Ben' }));

    await expect(requestsTo(fetchMock, 'PATCH /api/me')[0]?.json()).resolves.toEqual({
      filter_hidden: { meals: [ME.id], lists: [] },
    });
  });

  it('turns the chip back when saving fails', async () => {
    const { user } = renderMeals({
      'PATCH /api/me': errorResponse(503, 'common.service_unavailable'),
    });
    const chips = await screen.findByTestId(testIds.mealUserChips);

    await user.click(within(chips).getByRole('button', { name: 'Ben' }));

    expect(
      await screen.findByText('MealMate is unavailable right now. Please try again later.'),
    ).toBeVisible();
    expect(within(chips).getByRole('button', { name: 'Ben' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('loads the saved chips again when saving fails, instead of guessing', async () => {
    // Meanwhile Carl was switched off on another device.
    const saved = { ...TEST_USER, filter_hidden: { meals: [CARL.id], lists: [] } };
    const { fetchMock, user } = renderMeals({
      'PATCH /api/me': errorResponse(503, 'common.service_unavailable'),
      'GET /api/me': saved,
    });
    const chips = await screen.findByTestId(testIds.mealUserChips);
    const carl = within(chips).getByRole('button', { name: 'Carl (deactivated)' });
    expect(carl).toHaveAttribute('aria-pressed', 'true');

    await user.click(within(chips).getByRole('button', { name: 'Ben' }));

    await waitFor(() => expect(carl).toHaveAttribute('aria-pressed', 'false'));
    expect(within(chips).getByRole('button', { name: 'Ben' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(requestsTo(fetchMock, 'GET /api/me')).toHaveLength(1);
    await waitFor(() => expect(queries(fetchMock)).toEqual(['', '']));
  });

  it('shows one sentence and one action when there are no meals yet (UI-03)', async () => {
    const { user, router } = renderMeals({ 'GET /api/meals': [] });

    expect(await screen.findByText('No meals yet')).toBeVisible();
    expect(screen.queryByTestId(testIds.mealSearch)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Create meal' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals/new'));
  });

  it('keeps the chips on the empty state while others are visible (MEAL-10)', async () => {
    const { fetchMock, user } = renderMeals({
      'GET /api/meals': [],
      'PATCH /api/me': { ...TEST_USER, filter_hidden: { meals: [BEN.id], lists: [] } },
    });

    expect(await screen.findByText('No meals yet')).toBeVisible();
    const chips = await screen.findByTestId(testIds.mealUserChips);
    expect(
      within(chips)
        .getAllByRole('button')
        .map((button) => button.textContent),
    ).toEqual(['Me', 'Ben', 'Carl (deactivated)']);
    await user.click(within(chips).getByRole('button', { name: 'Ben' }));

    await expect(requestsTo(fetchMock, 'PATCH /api/me')[0]?.json()).resolves.toEqual({
      filter_hidden: { meals: [BEN.id], lists: [] },
    });
  });

  it('shows no chips on the empty state when nobody else is visible', async () => {
    renderMeals({ 'GET /api/meals': [], 'GET /api/users/visible': [ME] });

    expect(await screen.findByText('No meals yet')).toBeVisible();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Create meal' })).toBeVisible());
    expect(screen.queryByTestId(testIds.mealUserChips)).not.toBeInTheDocument();
  });

  it('lets me switch the chips on again after switching all of them off', async () => {
    const { fetchMock, user } = renderMeals(
      {
        'GET /api/meals': [],
        'PATCH /api/me': { ...TEST_USER, filter_hidden: { meals: [BEN.id, CARL.id], lists: [] } },
      },
      { ...TEST_USER, filter_hidden: { meals: [ME.id, BEN.id, CARL.id], lists: [] } },
    );

    const chips = await screen.findByTestId(testIds.mealUserChips);
    expect(screen.getByText('No meal matches.')).toBeVisible();
    for (const button of within(chips).getAllByRole('button')) {
      expect(button).toHaveAttribute('aria-pressed', 'false');
    }
    await user.click(within(chips).getByRole('button', { name: 'Me' }));

    await expect(requestsTo(fetchMock, 'PATCH /api/me')[0]?.json()).resolves.toEqual({
      filter_hidden: { meals: [BEN.id, CARL.id], lists: [] },
    });
  });

  it('says when nothing matches and clears search and filters', async () => {
    const { user } = renderMeals();
    await screen.findByTestId(testIds.mealList);

    await user.type(screen.getByTestId(testIds.mealSearch), 'Quitten');

    expect(await screen.findByText('No meal matches.')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Clear search and filters' }));
    expect(screen.getByTestId(testIds.mealSearch)).toHaveValue('');
    await waitFor(() => expect(screen.getAllByTestId(testIds.mealCard)).toHaveLength(3));
  });

  it('opens the form from "New meal"', async () => {
    const { user, router } = renderMeals();

    await user.click(await screen.findByTestId(testIds.newMeal));

    await waitFor(() => expect(router.state.location.pathname).toBe('/meals/new'));
    expect(await screen.findByRole('heading', { level: 1, name: 'New meal' })).toBeVisible();
  });
});
