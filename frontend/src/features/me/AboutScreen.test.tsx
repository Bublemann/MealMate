import { onlineManager } from '@tanstack/react-query';
import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { mockApi, requestsTo, VERSION_INFO } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';

describe('AboutScreen', () => {
  it('shows the running version and links to its exact source revision', async () => {
    const fetchMock = mockApi();
    renderApp('/me/about');

    expect(await screen.findByTestId(testIds.appVersion)).toHaveTextContent(VERSION_INFO.version);
    expect(requestsTo(fetchMock, 'GET /api/version')).toHaveLength(1);

    const sourceLink = screen.getByTestId(testIds.sourceLink);
    expect(sourceLink).toHaveAccessibleName(/^Source code \(AGPL-3\.0\)/);
    expect(within(sourceLink).getByText('(opens in a new tab)')).toHaveClass('sr-only');
    expect(sourceLink).toHaveAttribute('href', VERSION_INFO.source_url);
    expect(sourceLink).toHaveAttribute('target', '_blank');
    expect(sourceLink).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('credits Open Food Facts', async () => {
    mockApi();
    renderApp('/me/about');

    const link = await screen.findByRole('link', { name: /^Open Food Facts/ });
    expect(link).toHaveAttribute('href', 'https://world.openfoodfacts.org');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(link.closest('p')).toHaveTextContent(
      /^Nutrition data: Open Food Facts\s*\(opens in a new tab\)\s*\(ODbL\)$/,
    );
  });

  it('shows a translated error when the version cannot be loaded', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
    renderApp('/me/about');

    expect((await screen.findAllByText("Can't reach MealMate. Are you online?"))[0]).toBeVisible();
    expect(screen.queryByTestId(testIds.appVersion)).not.toBeInTheDocument();
    expect(screen.queryByTestId(testIds.sourceLink)).not.toBeInTheDocument();
  });

  it('says it cannot reach MealMate instead of loading forever while offline', async () => {
    onlineManager.setOnline(false);
    try {
      vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));
      renderApp('/me/about');

      expect(
        (await screen.findAllByText("Can't reach MealMate. Are you online?"))[0],
      ).toBeVisible();
      await waitFor(() => expect(screen.queryByText('Loading…')).not.toBeInTheDocument());
    } finally {
      onlineManager.setOnline(true);
    }
  });
});
