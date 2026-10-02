import { act, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mockApi } from '@/test/api';
import { renderApp } from '@/test/render';
import { testIds } from '@/testIds';
import { pwaUpdate } from './pwaUpdate';

/** The layout viewport of an iPhone 15 in portrait, in CSS pixels. */
const SCREEN = 852;
/** About the height of its keyboard with the suggestion bar. */
const KEYBOARD = 336;

/** A stand-in for `window.visualViewport`, which jsdom lacks: no keyboard, not zoomed. */
class FakeVisualViewport extends EventTarget {
  offsetTop = 0;
  height = SCREEN;
  scale = 1;

  /** Resizes the visible area, as the keyboard or pinch-zoom do. */
  change(values: Partial<Pick<FakeVisualViewport, 'height' | 'scale'>>) {
    Object.assign(this, values);
    act(() => {
      this.dispatchEvent(new Event('resize'));
    });
  }

  /** Moves the visible area down the page, as iOS does to show the focused field. */
  scroll(offsetTop: number) {
    this.offsetTop = offsetTop;
    act(() => {
      this.dispatchEvent(new Event('scroll'));
    });
  }
}

function stubVisualViewport(): FakeVisualViewport {
  vi.stubGlobal('innerHeight', SCREEN);
  const viewport = new FakeVisualViewport();
  vi.stubGlobal('visualViewport', viewport);
  return viewport;
}

/**
 * The visible area a pop-up gets: the edges its position and height are calculated from
 * (tokens.css). jsdom can't apply the stylesheet, so where the pop-up ends up is checked on a real
 * iPhone (QA-06).
 */
function visibleArea(element: HTMLElement) {
  const style = getComputedStyle(element);
  return {
    top: style.getPropertyValue('--visible-top'),
    keyboardInset: style.getPropertyValue('--keyboard-inset'),
  };
}

describe('on-screen keyboard (UI-01)', () => {
  afterEach(() => {
    act(() => pwaUpdate.dismiss());
  });

  it('hides the tab bar while the keyboard is open', async () => {
    const viewport = stubVisualViewport();
    mockApi();
    renderApp('/lists');
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' });

    viewport.change({ height: SCREEN - KEYBOARD });
    expect(nav).not.toBeVisible();

    viewport.change({ height: SCREEN });
    expect(nav).toBeVisible();
  });

  it('hides the update prompt while the keyboard is open', async () => {
    const viewport = stubVisualViewport();
    mockApi();
    renderApp('/lists');
    act(() => pwaUpdate.announce(() => Promise.resolve()));
    expect(await screen.findByTestId(testIds.updatePrompt)).toBeVisible();

    viewport.change({ height: SCREEN - KEYBOARD });
    expect(screen.queryByTestId(testIds.updatePrompt)).not.toBeInTheDocument();

    viewport.change({ height: SCREEN });
    expect(screen.getByTestId(testIds.updatePrompt)).toBeVisible();
  });

  it('shows an update that arrived while typing once the keyboard closes', async () => {
    const viewport = stubVisualViewport();
    mockApi();
    renderApp('/lists');
    await screen.findByRole('navigation', { name: 'Main navigation' });

    viewport.change({ height: SCREEN - KEYBOARD });
    act(() => pwaUpdate.announce(() => Promise.resolve()));
    expect(screen.queryByTestId(testIds.updatePrompt)).not.toBeInTheDocument();

    viewport.change({ height: SCREEN });
    // Added to the live region only now, so screen readers announce it then.
    expect(screen.getByTestId(testIds.updatePrompt)).toBeVisible();
  });

  it('gives pop-ups the visible area above the keyboard', async () => {
    const viewport = stubVisualViewport();
    mockApi();
    const { user } = renderApp('/me');
    await user.click(await screen.findByTestId(testIds.changePasswordButton));
    const dialog = await screen.findByRole('dialog', { name: 'Change password' });

    viewport.change({ height: SCREEN - KEYBOARD });
    expect(visibleArea(dialog)).toEqual({ top: '0px', keyboardInset: '336px' });

    viewport.scroll(100);
    expect(visibleArea(dialog)).toEqual({ top: '100px', keyboardInset: '236px' });

    viewport.change({ height: SCREEN });
    viewport.scroll(0);
    expect(visibleArea(dialog)).toEqual({ top: '0px', keyboardInset: '0px' });
  });

  it('does not take pinch-zoom for an open keyboard (A11Y-02)', async () => {
    const viewport = stubVisualViewport();
    mockApi();
    const { user } = renderApp('/me');
    act(() => pwaUpdate.announce(() => Promise.resolve()));
    const prompt = await screen.findByTestId(testIds.updatePrompt);

    // Zoomed in to twice the size, the visible part is half the page, at its lower end.
    viewport.change({ scale: 2, height: SCREEN / 2 });
    viewport.scroll(SCREEN / 2);
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeVisible();
    expect(prompt).toBeVisible();

    await user.click(screen.getByTestId(testIds.changePasswordButton));
    const dialog = await screen.findByRole('dialog', { name: 'Change password' });
    expect(visibleArea(dialog)).toEqual({ top: '0px', keyboardInset: '0px' });
  });

  it('changes nothing where the browser lacks the visible-viewport API', async () => {
    vi.stubGlobal('visualViewport', undefined);
    mockApi();
    const { user } = renderApp('/me');

    expect(await screen.findByRole('navigation', { name: 'Main navigation' })).toBeVisible();
    await user.click(screen.getByTestId(testIds.changePasswordButton));
    const dialog = await screen.findByRole('dialog', { name: 'Change password' });
    // Unset, so the pop-up takes the defaults from tokens.css: the whole viewport.
    expect(visibleArea(dialog)).toEqual({ top: '', keyboardInset: '' });
  });
});
