import { fireEvent } from '@testing-library/react';

interface SwipeOptions {
  /** Where the finger goes down and where it lets go, in px from the left. */
  from: number;
  to: number;
  /** How far it drifts down meanwhile (px). */
  dy?: number;
  pointerType?: 'touch' | 'pen' | 'mouse';
  pointerId?: number;
  /** Lets go with `pointercancel`, as when the browser takes over to scroll. */
  cancel?: boolean;
}

/**
 * A swipe across `element` (something inside a row, where the finger lands), as the pointer
 * events a phone sends: down, a few moves, up. jsdom lays nothing out, so a row counts as wide as
 * the window (1024 px) and its action as 6 rem of 16 px (96 px).
 */
export function swipe(
  element: Element,
  { from, to, dy = 2, pointerType = 'touch', pointerId = 1, cancel = false }: SwipeOptions,
) {
  const y = 10;
  const pointer = { pointerId, pointerType, isPrimary: true };
  fireEvent.pointerDown(element, { ...pointer, clientX: from, clientY: y });
  const steps = 4;
  for (let step = 1; step <= steps; step++) {
    fireEvent.pointerMove(element, {
      ...pointer,
      clientX: from + ((to - from) * step) / steps,
      clientY: y + (dy * step) / steps,
    });
  }
  const end = { ...pointer, clientX: to, clientY: y + dy };
  if (cancel) fireEvent.pointerCancel(element, end);
  else fireEvent.pointerUp(element, end);
}

/** A tap with the finger: down and up in one place, then the click the browser sends. */
export function tap(element: Element) {
  const pointer = { pointerId: 9, pointerType: 'touch', isPrimary: true, clientX: 10, clientY: 10 };
  fireEvent.pointerDown(element, pointer);
  fireEvent.pointerUp(element, pointer);
  fireEvent.click(element);
}
