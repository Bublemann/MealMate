import type { components } from '@/api/generated/schema';

export type Me = components['schemas']['Me'];

/**
 * localStorage keys. Keys starting with `mm.user.` belong to the signed-in user and are deleted
 * when the session ends (logout, expiry, revocation: SYNC-10). The others describe the device and
 * stay (UI language, Home Screen marker, dismissed hints).
 */
export const USER_KEY_PREFIX = 'mm.user.';
export const PROFILE_STORAGE_KEY = `${USER_KEY_PREFIX}profile`;
/** Set once the Home Screen app has started for the first time (plan § 5.4, fork). */
export const STANDALONE_MARKER_KEY = 'mm.standalone.initialized';

// Storage can be unavailable (private browsing, blocked site data); every access is guarded.
export function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // The value then lasts for this visit only.
  }
}

/** Deletes every user-specific key (`mm.user.*`). */
export function clearUserStorage(): void {
  try {
    const keys = Array.from({ length: localStorage.length }, (_, i) => localStorage.key(i));
    for (const key of keys) {
      if (key?.startsWith(USER_KEY_PREFIX)) localStorage.removeItem(key);
    }
  } catch {
    // Nothing stored.
  }
}

/** The profile of the last signed-in user, shown when the server can't be reached at start. */
export function readCachedProfile(): Me | null {
  const raw = readStorage(PROFILE_STORAGE_KEY);
  if (!raw) return null;
  try {
    const value: unknown = JSON.parse(raw);
    return typeof value === 'object' && value !== null && 'id' in value && 'username' in value
      ? (value as Me)
      : null;
  } catch {
    return null;
  }
}

export function cacheProfile(user: Me): void {
  writeStorage(PROFILE_STORAGE_KEY, JSON.stringify(user));
}

/** True when running as the Home Screen app (iOS: navigator.standalone). */
export function isStandalone(): boolean {
  const iosStandalone = (navigator as Navigator & { standalone?: boolean }).standalone === true;
  return iosStandalone || window.matchMedia?.('(display-mode: standalone)').matches === true;
}
