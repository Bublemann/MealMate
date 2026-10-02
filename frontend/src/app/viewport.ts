import { useSyncExternalStore } from 'react';

/**
 * Less than this between the layout and the visible viewport is no on-screen keyboard but, say, a
 * hardware keyboard's shortcut bar.
 */
const KEYBOARD_MIN_HEIGHT = 120;

type Listener = () => void;

const listeners = new Set<Listener>();
let keyboardOpen = false;

function setKeyboardOpen(open: boolean): void {
  if (open === keyboardOpen) return;
  keyboardOpen = open;
  for (const listener of listeners) listener();
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Whether the on-screen keyboard is open, while `watchViewport` runs (UI-01). */
export function useKeyboardOpen(): boolean {
  return useSyncExternalStore(subscribe, () => keyboardOpen);
}

/** Sets a CSS variable on <html>, unless it already has that value. */
function setVariable(name: string, px: number): void {
  const style = document.documentElement.style;
  const value = `${Math.round(px)}px`;
  if (style.getPropertyValue(name) !== value) style.setProperty(name, value);
}

/**
 * Watches the visible viewport for the on-screen keyboard (UI-01, D-28). iOS doesn't resize the
 * page for it, nor does it support the viewport-meta or VirtualKeyboard ways to ask for that; it
 * only shows less of the page (`visualViewport`), scrolled to the focused field. This sets
 * `--visible-top` and `--keyboard-inset` on <html>, where the visible part starts and how far the
 * keyboard reaches up from the bottom edge, so pop-ups can fit in between (tokens.css). Where the
 * API is missing, nothing happens. Returns a function that stops watching.
 */
export function watchViewport(): () => void {
  const viewport = window.visualViewport;
  if (!viewport) return () => undefined;

  const update = () => {
    // Pinch-zoom shrinks the visible part too, but the keyboard's room is only known unzoomed
    // (scale 1, give or take rounding). Zoomed, the page is laid out as without the API (A11Y-02).
    const zoomed = Math.abs(viewport.scale - 1) > 0.01;
    // The layout viewport, which fixed elements are placed in. The larger of the two, in case a
    // browser reports the visible part as innerHeight (clientHeight: the viewport while the
    // browser's toolbars show, never shrunk by the keyboard).
    const layout = Math.max(window.innerHeight, document.documentElement.clientHeight);
    const top = zoomed ? 0 : viewport.offsetTop;
    const keyboard = zoomed ? 0 : layout - viewport.height;
    setVariable('--visible-top', top);
    setVariable('--keyboard-inset', Math.max(0, keyboard - top));
    setKeyboardOpen(keyboard >= KEYBOARD_MIN_HEIGHT);
  };
  update();
  viewport.addEventListener('resize', update);
  viewport.addEventListener('scroll', update);
  return () => {
    viewport.removeEventListener('resize', update);
    viewport.removeEventListener('scroll', update);
    document.documentElement.style.removeProperty('--visible-top');
    document.documentElement.style.removeProperty('--keyboard-inset');
    setKeyboardOpen(false);
  };
}
