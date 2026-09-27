import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderApp, VERSION_INFO } from '@/test/render';
import { testIds } from '@/testIds';

const TABS = [
  { tab: testIds.tabLists, screen: testIds.screenLists, path: '/lists', title: 'Lists' },
  { tab: testIds.tabMeals, screen: testIds.screenMeals, path: '/meals', title: 'Meals' },
  {
    tab: testIds.tabIngredients,
    screen: testIds.screenIngredients,
    path: '/ingredients',
    title: 'Ingredients',
  },
  { tab: testIds.tabMe, screen: testIds.screenMe, path: '/me', title: 'Me' },
];

describe('Layout', () => {
  it('opens on Lists with the four tabs in the bottom navigation', async () => {
    const { router } = renderApp('/');

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    expect(router.state.location.pathname).toBe('/lists');

    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.dataset.testid)).toEqual(TABS.map(({ tab }) => tab));
    expect(links.map((link) => link.textContent)).toEqual(TABS.map(({ title }) => title));
    expect(screen.getByTestId(testIds.tabLists)).toHaveAttribute('aria-current', 'page');
  });

  it('navigates between the tabs', async () => {
    vi.stubGlobal('fetch', () => Promise.resolve(Response.json(VERSION_INFO)));
    const { router, user } = renderApp('/lists');

    for (const { tab, screen: screenId, path, title } of [...TABS].reverse()) {
      await user.click(screen.getByTestId(tab));

      expect(router.state.location.pathname).toBe(path);
      const current = screen.getByTestId(screenId);
      expect(within(current).getByRole('heading', { level: 1 })).toHaveTextContent(title);
      for (const other of TABS) {
        const link = screen.getByTestId(other.tab);
        if (other.tab === tab) expect(link).toHaveAttribute('aria-current', 'page');
        else expect(link).not.toHaveAttribute('aria-current');
      }
    }
  });

  it('sends unknown paths to Lists', async () => {
    const { router } = renderApp('/does/not/exist');

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    expect(router.state.location.pathname).toBe('/lists');
  });

  it.each([
    ['/lists', 'No shopping lists yet', 'New list'],
    ['/meals', 'No meals yet', 'Create meal'],
    ['/ingredients', 'No ingredients yet', 'Add ingredient'],
  ])('shows an empty state with its main action on %s', async (path, title, action) => {
    renderApp(path);

    expect(await screen.findByRole('heading', { level: 2, name: title })).toBeVisible();
    // The actions are wired up when their features arrive (M3–M5a).
    expect(screen.getByRole('button', { name: action })).toBeDisabled();
  });
});
