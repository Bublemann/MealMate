import { act } from '@testing-library/react';
import { vi } from 'vitest';

/** The layout viewport of an iPhone 15 in portrait, in CSS pixels. */
export const VIEWPORT_HEIGHT = 852;
/** About the height of its keyboard with the suggestion bar. */
export const KEYBOARD_HEIGHT = 336;

/** A stand-in for `window.visualViewport`, which jsdom lacks: no keyboard, not zoomed. */
export class FakeVisualViewport extends EventTarget {
  offsetTop = 0;
  height = VIEWPORT_HEIGHT;
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

/**
 * Stubs `visualViewport` (before rendering the app, which starts watching it in its providers):
 * `change({ height: VIEWPORT_HEIGHT - KEYBOARD_HEIGHT })` opens the on-screen keyboard (UI-01).
 */
export function stubVisualViewport(): FakeVisualViewport {
  vi.stubGlobal('innerHeight', VIEWPORT_HEIGHT);
  const viewport = new FakeVisualViewport();
  vi.stubGlobal('visualViewport', viewport);
  return viewport;
}
