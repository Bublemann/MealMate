import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import i18n from '@/i18n';
import { mockApi, TEST_USER } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

const TABS = [
  {
    tab: testIds.tabLists,
    screen: testIds.screenLists,
    path: '/lists',
    title: 'Shopping lists',
    de: 'Einkaufslisten',
  },
  {
    tab: testIds.tabMeals,
    screen: testIds.screenMeals,
    path: '/meals',
    title: 'Meals',
    de: 'Gerichte',
  },
  {
    tab: testIds.tabIngredients,
    screen: testIds.screenIngredients,
    path: '/ingredients',
    title: 'Ingredients',
    de: 'Zutaten',
  },
  {
    tab: testIds.tabMe,
    screen: testIds.screenMe,
    path: '/me',
    title: 'Settings',
    de: 'Einstellungen',
  },
];

describe('Layout', () => {
  it('opens on Lists with the four tabs in the bottom navigation', async () => {
    mockApi();
    const { router } = renderApp('/');

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    expect(router.state.location.pathname).toBe('/lists');

    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    const links = within(nav).getAllByRole('link');
    expect(links.map((link) => link.dataset.testid)).toEqual(TABS.map(({ tab }) => tab));
    expect(links.map((link) => link.textContent)).toEqual(TABS.map(({ title }) => title));
    expect(screen.getByTestId(testIds.tabLists)).toHaveAttribute('aria-current', 'page');
  });

  it('names the icon-only tabs by their text, not by aria-labels', async () => {
    mockApi();
    renderApp('/lists');

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    for (const { tab, title } of TABS) {
      const link = screen.getByTestId(tab);
      expect(link).toHaveAccessibleName(title);
      expect(link).not.toHaveAttribute('aria-label');
    }
  });

  it('navigates between the tabs, each with its headline as its one level-1 heading (D-44)', async () => {
    mockApi();
    const { router, user } = renderApp('/lists');

    for (const { tab, screen: screenId, path, title } of [...TABS].reverse()) {
      await user.click(screen.getByTestId(tab));

      expect(router.state.location.pathname).toBe(path);
      // The headline, the same text as the tab's name, also labels the screen (UI-01).
      const current = screen.getByTestId(screenId);
      expect(screen.getAllByRole('heading', { level: 1 })).toEqual([
        within(current).getByRole('heading', { level: 1, name: title }),
      ]);
      expect(screen.getByRole('region', { name: title })).toBe(current);
      for (const other of TABS) {
        const link = screen.getByTestId(other.tab);
        if (other.tab === tab) expect(link).toHaveAttribute('aria-current', 'page');
        else expect(link).not.toHaveAttribute('aria-current');
      }
    }
  });

  it('names the tabs and their screens by the German headlines (D-44)', async () => {
    const anna = { ...TEST_USER, language: 'de' as const };
    mockApi({ 'GET /api/me': anna });
    await i18n.changeLanguage('de');
    const { user } = renderApp('/lists', { user: anna });

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    for (const { tab, screen: screenId, de } of [...TABS].reverse()) {
      expect(screen.getByTestId(tab)).toHaveAccessibleName(de);
      await user.click(screen.getByTestId(tab));

      const current = screen.getByTestId(screenId);
      expect(screen.getAllByRole('heading', { level: 1 })).toEqual([
        within(current).getByRole('heading', { level: 1, name: de }),
      ]);
      expect(screen.getByRole('region', { name: de })).toBe(current);
    }
  });

  it('sends unknown paths to Lists', async () => {
    mockApi();
    const { router } = renderApp('/does/not/exist');

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    expect(router.state.location.pathname).toBe('/lists');
  });

  it('shows an empty /lists with its "New list" tile', async () => {
    mockApi();
    renderApp('/lists');

    expect(await screen.findByText('No lists yet')).toBeVisible();
    expect(screen.getByRole('button', { name: 'New list' })).toBeEnabled();
  });
});
