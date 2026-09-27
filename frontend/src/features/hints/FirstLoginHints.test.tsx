import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { mockApi } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import { HINT_STORAGE_KEYS } from './hints';

const IPHONE_SAFARI =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';

describe('FirstLoginHints', () => {
  it('suggests "Add to Home Screen" in iOS Safari and "Keep Tailscale on"', async () => {
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(IPHONE_SAFARI);
    mockApi();
    renderApp('/lists');

    expect(await screen.findByTestId(testIds.hintHomeScreen)).toHaveTextContent(
      'Add MealMate to your Home Screen',
    );
    expect(screen.getByTestId(testIds.hintTailscale)).toHaveTextContent('Keep Tailscale on');
  });

  it('does not suggest the Home Screen elsewhere or inside the Home Screen app', async () => {
    mockApi();
    const desktop = renderApp('/lists');
    expect(await screen.findByTestId(testIds.hintTailscale)).toBeVisible();
    expect(screen.queryByTestId(testIds.hintHomeScreen)).not.toBeInTheDocument();
    desktop.unmount();

    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue(IPHONE_SAFARI);
    Object.defineProperty(navigator, 'standalone', { value: true, configurable: true });
    try {
      renderApp('/lists');
      expect(await screen.findByTestId(testIds.hintTailscale)).toBeVisible();
      expect(screen.queryByTestId(testIds.hintHomeScreen)).not.toBeInTheDocument();
    } finally {
      Reflect.deleteProperty(navigator, 'standalone');
    }
  });

  it('remembers a dismissed hint on this device', async () => {
    mockApi();
    const first = renderApp('/lists');

    await first.user.click(
      await screen.findByRole('button', { name: 'Hide tip: Keep Tailscale on' }),
    );

    expect(screen.queryByTestId(testIds.hintTailscale)).not.toBeInTheDocument();
    expect(localStorage.getItem(HINT_STORAGE_KEYS.tailscale)).not.toBeNull();
    first.unmount();

    renderApp('/lists');
    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    expect(screen.queryByTestId(testIds.hintTailscale)).not.toBeInTheDocument();
  });
});
