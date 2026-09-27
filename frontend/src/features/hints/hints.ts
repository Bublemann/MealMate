import { isStandalone, readStorage } from '@/features/auth/storage';
import { isIosSafari } from '@/lib/userAgent';

/** Dismissed hints are remembered per device (they describe the device, not the user). */
export const HINT_STORAGE_KEYS = {
  homeScreen: 'mm.hint.homeScreen.dismissed',
  tailscale: 'mm.hint.tailscale.dismissed',
} as const;

export type Hint = keyof typeof HINT_STORAGE_KEYS;

/** The hints to show on this device, in order. */
export function initialHints(): Hint[] {
  const hints: Hint[] = [];
  // "Add to Home Screen" only exists in Safari on iOS, and only matters outside the app.
  if (isIosSafari(navigator.userAgent, navigator.maxTouchPoints) && !isStandalone()) {
    hints.push('homeScreen');
  }
  hints.push('tailscale');
  return hints.filter((hint) => readStorage(HINT_STORAGE_KEYS[hint]) === null);
}
