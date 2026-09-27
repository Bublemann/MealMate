import { api, type AuthBridge, type SessionEndCode } from '@/api/client';
import { ApiError, isApiError } from '@/api/errors';
import type { components } from '@/api/generated/schema';
import i18n, { changeLanguage } from '@/i18n';
import {
  cacheProfile,
  clearUserStorage,
  isStandalone,
  readCachedProfile,
  readStorage,
  STANDALONE_MARKER_KEY,
  writeStorage,
  type Me,
} from './storage';

export type LoginResponse = components['schemas']['LoginResponse'];

/**
 * - `loading`: the start-up refresh is still running;
 * - `authenticated`: a user is signed in (`offline` if the server couldn't be reached at start and
 *   the cached profile is shown; requests then refresh first);
 * - `anonymous`: nobody is signed in; `reason` says why a session ended, if one did;
 * - `unreachable`: the server couldn't be reached at start and there is no cached profile.
 */
export type AuthStatus = 'loading' | 'authenticated' | 'anonymous' | 'unreachable';
export type EndReason = 'logged_out' | 'expired' | 'revoked' | 'login_required';

export interface AuthState {
  status: AuthStatus;
  user: Me | null;
  offline: boolean;
  reason: EndReason | null;
}

type Outcome = 'ok' | 'ended' | 'unreachable';

/** The cross-tab lock that serialises refreshes (plan § 8). */
export const REFRESH_LOCK = 'mm-refresh';

export interface AuthSession extends AuthBridge {
  getState: () => AuthState;
  subscribe: (listener: () => void) => () => void;
  /** The start-up refresh: forks on the first Home Screen start (plan § 5.4). Idempotent. */
  start(): Promise<void>;
  /** Tries the start-up refresh again after `unreachable`. */
  retry(): Promise<void>;
  /** Stores the result of login, join or reset. */
  signIn(response: LoginResponse): void;
  /** Stores a changed profile (e.g. from PATCH /me) and follows its language. */
  setUser(user: Me): void;
  /** Logs out on the server, then forgets the user locally. Rejects if the server can't be reached. */
  logout(): Promise<void>;
  /** Logs out every device of the user, including this one. */
  logoutAll(): Promise<void>;
  /** Called whenever a session ends locally, so cached server data can be dropped. */
  onEnd(listener: () => void): () => void;
}

export interface AuthSessionOptions {
  /** Start already signed in (tests). */
  initial?: { user: Me; accessToken: string };
}

/** Holds the access token (memory only) and the signed-in user, outside React. */
export function createAuthSession({ initial }: AuthSessionOptions = {}): AuthSession {
  let state: AuthState = initial
    ? { status: 'authenticated', user: initial.user, offline: false, reason: null }
    : { status: 'loading', user: null, offline: false, reason: null };
  let accessToken: string | null = initial?.accessToken ?? null;
  let inflight: Promise<Outcome> | null = null;
  let startup: Promise<void> | null = initial ? Promise.resolve() : null;
  const listeners = new Set<() => void>();
  const endListeners = new Set<() => void>();

  function setState(next: Partial<AuthState>): void {
    state = { ...state, ...next };
    for (const listener of listeners) listener();
  }

  function followLanguage(user: Me): void {
    if (i18n.resolvedLanguage !== user.language) void changeLanguage(user.language);
  }

  function applyLogin(response: LoginResponse): void {
    accessToken = response.access_token;
    cacheProfile(response.user);
    followLanguage(response.user);
    setState({ status: 'authenticated', user: response.user, offline: false, reason: null });
  }

  function end(reason: EndReason | null): void {
    const wasSignedIn = state.user !== null;
    accessToken = null;
    // SYNC-10: the cached profile and every other user-specific key go with the session.
    clearUserStorage();
    setState({ status: 'anonymous', user: null, offline: false, reason });
    // Only a session that was in use has server data to drop; at start-up there is none yet, and
    // clearing then would cut off public queries in flight (e.g. the invite code check).
    if (wasSignedIn) for (const listener of endListeners) listener();
  }

  function endReasonFor(code: string, wasSignedIn: boolean): EndReason | null {
    if (code === 'auth.session_revoked') return 'revoked';
    if (code === 'auth.login_required') return 'login_required';
    return wasSignedIn ? 'expired' : null;
  }

  async function requestRefresh(fork: boolean): Promise<Outcome> {
    // "Expired" only makes sense to someone who was signed in on this device.
    const wasSignedIn = state.user !== null || readCachedProfile() !== null;
    try {
      const { data, error, response } = await api.POST('/api/auth/refresh', {
        body: { fork },
      });
      if (data) {
        applyLogin(data);
        return 'ok';
      }
      const apiError = ApiError.fromResponse(response.status, error);
      if (response.status >= 500) return 'unreachable';
      end(endReasonFor(apiError.code, wasSignedIn));
      return 'ended';
    } catch (error) {
      if (isApiError(error) && error.status === 0) return 'unreachable';
      throw error;
    }
  }

  /** One refresh at a time: in this tab via the shared promise, across tabs via Web Locks. */
  function refreshOnce(fork = false): Promise<Outcome> {
    inflight ??= (async () => {
      try {
        const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined;
        return locks
          ? await locks.request(REFRESH_LOCK, () => requestRefresh(fork))
          : await requestRefresh(fork);
      } finally {
        inflight = null;
      }
    })();
    return inflight;
  }

  async function runStartup(): Promise<void> {
    const fork = isStandalone() && readStorage(STANDALONE_MARKER_KEY) === null;
    const outcome = await refreshOnce(fork);
    // Any answer from the server settles the first start; a network failure tries again next time.
    if (fork && outcome !== 'unreachable') writeStorage(STANDALONE_MARKER_KEY, '1');
    if (outcome !== 'unreachable') return;
    const cached = readCachedProfile();
    if (cached) setState({ status: 'authenticated', user: cached, offline: true, reason: null });
    else setState({ status: 'unreachable' });
  }

  return {
    getState: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    onEnd(listener) {
      endListeners.add(listener);
      return () => endListeners.delete(listener);
    },
    start() {
      startup ??= runStartup();
      return startup;
    },
    async retry() {
      setState({ status: 'loading' });
      startup = runStartup();
      return startup;
    },
    signIn: applyLogin,
    setUser(user) {
      cacheProfile(user);
      followLanguage(user);
      setState({ user });
    },
    async logout() {
      const { response, error } = await api.POST('/api/auth/logout');
      if (!response.ok) throw ApiError.fromResponse(response.status, error);
      end('logged_out');
    },
    async logoutAll() {
      const { response, error } = await api.POST('/api/auth/logout-all');
      // The session may already be gone; either way nobody is signed in any more.
      if (!response.ok && response.status !== 401) {
        throw ApiError.fromResponse(response.status, error);
      }
      end('logged_out');
    },

    // AuthBridge (used by the API client middleware)
    accessToken: () => accessToken,
    async settled() {
      if (inflight) await inflight.catch(() => undefined);
    },
    async refresh() {
      const outcome = await refreshOnce();
      if (outcome === 'unreachable') return false;
      return outcome === 'ok' && accessToken !== null;
    },
    sessionEnded(code: SessionEndCode) {
      if (state.status !== 'authenticated') return;
      end(code === 'auth.session_revoked' ? 'revoked' : 'expired');
    },
  };
}
