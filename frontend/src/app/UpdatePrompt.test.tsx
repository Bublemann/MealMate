import { act, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import { pwaUpdate } from './pwaUpdate';

describe('UpdatePrompt', () => {
  afterEach(() => {
    act(() => pwaUpdate.dismiss());
  });

  it('stays hidden until a new version is waiting', async () => {
    renderApp('/lists');

    expect(await screen.findByTestId(testIds.screenLists)).toBeVisible();
    expect(screen.queryByTestId(testIds.updatePrompt)).not.toBeInTheDocument();
  });

  it('reloads into the new version on request', async () => {
    const apply = vi.fn(() => Promise.resolve());
    const { user } = renderApp('/lists');

    act(() => pwaUpdate.announce(apply));
    const prompt = await screen.findByTestId(testIds.updatePrompt);
    expect(prompt).toHaveTextContent('A new version of MealMate is available.');
    await user.click(within(prompt).getByRole('button', { name: 'Reload' }));

    expect(apply).toHaveBeenCalledOnce();
  });

  it('can be dismissed', async () => {
    const apply = vi.fn(() => Promise.resolve());
    const { user } = renderApp('/lists');

    act(() => pwaUpdate.announce(apply));
    await user.click(await screen.findByRole('button', { name: 'Later' }));

    expect(screen.queryByTestId(testIds.updatePrompt)).not.toBeInTheDocument();
    expect(apply).not.toHaveBeenCalled();
  });
});
