import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import type { Me } from '@/features/auth/storage';
import { heldRoute, mockApi, TEST_ADMIN } from '@/test/api';
import { APPLES, expectInPageOrder, REFERENCE_ROUTES } from '@/test/ingredients';
import { LIST_ID, LIST_ROUTES, listDetail } from '@/test/lists';
import { meal, MEAL_ROUTES } from '@/test/meals';
import { renderApp } from '@/test/render';
import { testIds, type TestId } from '@/testIds';
import { DetailStrip } from './DetailStrip';

// The diagnostics screen holds the scanner; jsdom has no camera to decode anything from.
vi.mock('@/features/scanner/decoder', () => ({
  loadDecoder: () => Promise.resolve(),
  decodeVideoFrame: () => Promise.resolve(null),
}));

const PANCAKES = meal();

interface DetailScreen {
  name: string;
  path: string;
  routes?: Record<string, unknown>;
  user?: Me;
  title: string;
  back: string;
  to: string;
  /** The screen the back link opens. */
  parent: TestId;
  /** It has actions, so its strip ends with the ⋯ button (D-39). */
  actions?: true;
}

const SCREENS: DetailScreen[] = [
  {
    name: 'a shopping list',
    path: `/lists/${LIST_ID}`,
    routes: LIST_ROUTES,
    title: 'Wochenende (26/09/2026)',
    back: 'All lists',
    to: '/lists',
    parent: testIds.screenLists,
    actions: true,
  },
  {
    name: 'a meal',
    path: `/meals/${PANCAKES.id}`,
    routes: { ...MEAL_ROUTES, [`GET /api/meals/${PANCAKES.id}`]: PANCAKES },
    title: 'Pfannkuchen',
    back: 'All meals',
    to: '/meals',
    parent: testIds.screenMeals,
    actions: true,
  },
  {
    name: 'the meal form, editing',
    path: `/meals/${PANCAKES.id}/edit`,
    routes: { ...MEAL_ROUTES, [`GET /api/meals/${PANCAKES.id}`]: PANCAKES },
    title: 'Edit Pfannkuchen',
    back: 'Pfannkuchen',
    to: `/meals/${PANCAKES.id}`,
    parent: testIds.screenMeal,
  },
  {
    name: 'the meal form, a new meal',
    path: '/meals/new',
    routes: MEAL_ROUTES,
    title: 'New meal',
    back: 'All meals',
    to: '/meals',
    parent: testIds.screenMeals,
  },
  {
    name: 'the meal form, a new meal for a list (LIST-02)',
    path: `/meals/new?addToList=${LIST_ID}`,
    routes: LIST_ROUTES,
    title: 'New meal',
    back: 'Wochenende (26/09/2026)',
    to: `/lists/${LIST_ID}`,
    parent: testIds.screenList,
  },
  {
    name: 'an ingredient',
    path: `/ingredients/${APPLES.id}`,
    routes: {
      ...REFERENCE_ROUTES,
      [`GET /api/ingredients/${APPLES.id}`]: APPLES,
      'GET /api/ingredients': [],
    },
    title: 'Äpfel',
    back: 'All ingredients',
    to: '/ingredients',
    parent: testIds.screenIngredients,
    actions: true,
  },
  {
    name: 'an admin page (ADM-01)',
    path: '/me/admin/users',
    routes: { 'GET /api/me': TEST_ADMIN, 'GET /api/admin/users': [] },
    user: TEST_ADMIN,
    title: 'Users',
    back: 'Settings',
    to: '/me',
    parent: testIds.screenMe,
  },
  {
    name: 'the diagnostics',
    path: '/diag',
    routes: { 'GET /api/me': TEST_ADMIN },
    user: TEST_ADMIN,
    title: 'Diagnostics',
    back: 'Settings',
    to: '/me',
    parent: testIds.screenMe,
  },
];

/**
 * The strip at the top of every detail screen (UI-01, D-46): "‹ parent" on the left, a slot for
 * the screen's ⋯ button on the right, and the screen's title below it.
 */
describe('DetailStrip', () => {
  it.each(SCREENS)(
    'leads from $name to its parent, above the title',
    async ({ path, routes, user: signedIn, title, back, to, parent }) => {
      mockApi(routes);
      const { user, router } = renderApp(path, signedIn ? { user: signedIn } : {});

      const heading = await screen.findByRole('heading', { level: 1, name: title });
      const strip = screen.getByTestId(testIds.detailStrip);
      const link = within(strip).getByTestId(testIds.backLink);
      // The meal form names a list once its answer is in.
      await waitFor(() => expect(link).toHaveAccessibleName(back));
      expect(link).toHaveAttribute('href', to);
      expectInPageOrder([strip, heading]);

      // A fixed parent: the app was opened right here, so there is no history to go back in.
      await user.click(link);
      expect(await screen.findByTestId(parent)).toBeVisible();
      expect(router.state.location.pathname).toBe(to);
    },
  );

  it.each(SCREENS.filter(({ actions }) => actions))(
    'ends with the ⋯ button after the back link on $name (D-39)',
    async ({ path, routes, user: signedIn, title }) => {
      mockApi(routes);
      const { user } = renderApp(path, signedIn ? { user: signedIn } : {});
      await screen.findByRole('heading', { level: 1, name: title });
      const strip = screen.getByTestId(testIds.detailStrip);
      const more = await within(strip).findByRole('button', { name: 'More actions' });

      expect(more).toHaveAttribute('data-testid', testIds.moreActions);
      expect(more).toBeEnabled();
      await user.tab();
      expect(within(strip).getByTestId(testIds.backLink)).toHaveFocus();
      await user.tab();
      expect(more).toHaveFocus();
    },
  );

  // No ⋯ on screens without actions: nothing that does nothing.
  it.each(SCREENS.filter(({ actions }) => !actions))(
    'has nothing visible or focusable in its right-hand slot on $name',
    async ({ path, routes, user: signedIn, title }) => {
      mockApi(routes);
      const { user } = renderApp(path, signedIn ? { user: signedIn } : {});
      await screen.findByRole('heading', { level: 1, name: title });
      const strip = screen.getByTestId(testIds.detailStrip);
      const link = within(strip).getByTestId(testIds.backLink);

      expect(strip.textContent).toBe(link.textContent);
      await user.tab();
      expect(link).toHaveFocus();
      await user.tab();
      expect(strip).not.toContainElement(document.activeElement as HTMLElement | null);
    },
  );

  it('names a long meal in full for screen readers', async () => {
    const name =
      'Omas sonntägliche Lasagne mit drei Sorten Käse und frischem Basilikum aus dem Garten';
    const long = meal({ name });
    mockApi({ ...MEAL_ROUTES, [`GET /api/meals/${long.id}`]: long });
    renderApp(`/meals/${long.id}/edit`);

    const link = await screen.findByRole('link', { name });
    expect(link).toHaveAttribute('data-testid', testIds.backLink);
  });

  it('names a list in the meal form as a shopping list until its name is known', async () => {
    const list = heldRoute();
    mockApi({ ...LIST_ROUTES, [`GET /api/lists/${LIST_ID}`]: list.route });
    renderApp(`/meals/new?addToList=${LIST_ID}`);

    const link = await screen.findByTestId(testIds.backLink);
    expect(link).toHaveAccessibleName('Shopping list');
    expect(link).toHaveAttribute('href', `/lists/${LIST_ID}`);

    await list.answer(listDetail());
    await waitFor(() => expect(link).toHaveAccessibleName('Wochenende (26/09/2026)'));
  });

  it("puts a screen's button at the right, after the back link", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <DetailStrip
          back={{ to: '/lists', label: 'All lists' }}
          action={<button type="button">More actions</button>}
        />
      </MemoryRouter>,
    );

    const strip = screen.getByTestId(testIds.detailStrip);
    await user.tab();
    expect(within(strip).getByTestId(testIds.backLink)).toHaveFocus();
    await user.tab();
    expect(within(strip).getByRole('button', { name: 'More actions' })).toHaveFocus();
  });
});
