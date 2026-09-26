import { onlineManager } from '@tanstack/react-query';
import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LANGUAGE_STORAGE_KEY } from '@/i18n';
import { renderApp, VERSION_INFO } from '@/test/render';
import { testIds } from '@/testIds';

function stubVersionApi() {
  const fetchMock = vi.fn<(request: Request) => Promise<Response>>(() =>
    Promise.resolve(Response.json(VERSION_INFO)),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('MeScreen', () => {
  it('shows the running version and links to its exact source revision', async () => {
    const fetchMock = stubVersionApi();
    renderApp('/me');

    expect(await screen.findByTestId(testIds.appVersion)).toHaveTextContent(VERSION_INFO.version);
    const request = fetchMock.mock.calls[0]?.[0];
    expect(new URL(request?.url ?? '').pathname).toBe('/api/version');

    const sourceLink = screen.getByTestId(testIds.sourceLink);
    expect(sourceLink).toHaveAccessibleName(/^Source code \(AGPL-3\.0\)/);
    expect(within(sourceLink).getByText('(opens in a new tab)')).toHaveClass('sr-only');
    expect(sourceLink).toHaveAttribute('href', VERSION_INFO.source_url);
    expect(sourceLink).toHaveAttribute('target', '_blank');
    expect(sourceLink).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('credits Open Food Facts', async () => {
    stubVersionApi();
    renderApp('/me');

    const link = await screen.findByRole('link', { name: /^Open Food Facts/ });
    expect(link).toHaveAttribute('href', 'https://world.openfoodfacts.org');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link.closest('p')).toHaveTextContent(
      /^Nutrition data: Open Food Facts\s*\(opens in a new tab\)\s*\(ODbL\)$/,
    );
  });

  it('shows a translated error when the version cannot be loaded', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    renderApp('/me');

    expect(await screen.findByText("Can't reach MealMate. Are you online?")).toBeVisible();
    expect(screen.queryByTestId(testIds.appVersion)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.sourceLink)).not.toBeInTheDocument();
  });

  it('says it cannot reach MealMate instead of loading forever while offline', async () => {
    onlineManager.setOnline(false);
    try {
      vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
      renderApp('/me');

      expect(await screen.findByText("Can't reach MealMate. Are you online?")).toBeVisible();
      expect(screen.queryByText('Loading…')).not.toBeInTheDocument();
    } finally {
      onlineManager.setOnline(true);
    }
  });

  it('switches the language and remembers the choice', async () => {
    stubVersionApi();
    const { user } = renderApp('/me');

    const select = screen.getByRole('combobox', { name: 'Language' });
    expect(select).toBe(screen.getByTestId(testIds.languageSelect));
    expect(select).toHaveValue('en');
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual([
      'Deutsch',
      'English',
    ]);

    await user.selectOptions(select, 'Deutsch');

    expect(await screen.findByRole('heading', { level: 1, name: 'Profil' })).toBeVisible();
    expect(screen.getByRole('combobox', { name: 'Sprache' })).toHaveValue('de');
    expect(screen.getByTestId(testIds.tabLists)).toHaveTextContent('Listen');
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('de');
    expect(document.documentElement.lang).toBe('de');

    await user.selectOptions(select, 'English');

    expect(await screen.findByRole('heading', { level: 1, name: 'Me' })).toBeVisible();
    expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en');
  });
});
