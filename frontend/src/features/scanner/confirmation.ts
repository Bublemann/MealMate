import type { DecodedBarcode } from './decoder';

/** How soon after its first reading a code must be read again to count. */
export const CONFIRM_WINDOW_MS = 1500;

/**
 * Takes a camera scan only once two frames within CONFIRM_WINDOW_MS read the same code. A single
 * blurred or curved frame can yield another valid code (the check digit misses some misreads),
 * which the lookup then reports as "not found"; two frames agreeing make that unlikely, at the
 * cost of one more frame. Frames in between may find nothing or another code: every code keeps
 * its own first reading for the window, so a misread between two good frames (A B A) does not
 * push the good code out, and alternating readings still confirm.
 *
 * Returns a function that is given each code read with the time it was read (`performance.now()`)
 * and returns the code once it is confirmed, else null.
 */
export function createConfirmation(
  windowMs = CONFIRM_WINDOW_MS,
): (decoded: DecodedBarcode, now: number) => DecodedBarcode | null {
  // First reading by code; entries older than the window are dropped, which keeps it small.
  const firstSeen = new Map<string, number>();
  return (decoded, now) => {
    for (const [text, at] of firstSeen) {
      if (now - at > windowMs) firstSeen.delete(text);
    }
    if (firstSeen.has(decoded.text)) {
      firstSeen.clear(); // a new confirmation needs two new readings
      return decoded;
    }
    firstSeen.set(decoded.text, now);
    return null;
  };
}
