import createClient, { type Middleware } from 'openapi-fetch';
import { ApiError } from './errors';
import type { paths } from './generated/schema';

/** Default deadlines (plan § 8): a timeout counts as "can't reach MealMate" (SYNC-09). */
export const READ_TIMEOUT_MS = 8_000;
export const WRITE_TIMEOUT_MS = 15_000;

const READ_METHODS = new Set(['GET', 'HEAD']);
const NULL_BODY_STATUSES = new Set([204, 205, 304]);

export type FetchFn = (request: Request) => Promise<Response>;

/**
 * A fetch function that gives up after `timeoutMs` (default: by method). The deadline covers the
 * whole exchange including the body, so a connection that stalls mid-response (lie-fi) cannot
 * hang the caller. Timeouts and network failures reject with an ApiError; an abort by the caller
 * (e.g. TanStack Query cancelling a query) rejects with the original AbortError.
 */
export function createTimeoutFetch(timeoutMs?: number): FetchFn {
  return async (request) => {
    const deadline =
      timeoutMs ?? (READ_METHODS.has(request.method) ? READ_TIMEOUT_MS : WRITE_TIMEOUT_MS);
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, deadline);
    const forwardAbort = () => controller.abort(request.signal.reason);
    if (request.signal.aborted) forwardAbort();
    request.signal.addEventListener('abort', forwardAbort, { once: true });

    try {
      const response = await fetch(request, { signal: controller.signal });
      const body = await response.arrayBuffer();
      return new Response(NULL_BODY_STATUSES.has(response.status) ? null : body, {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      });
    } catch (error) {
      if (timedOut) throw new ApiError({ status: 0, code: 'client.timeout' });
      if (request.signal.aborted) throw error;
      throw new ApiError({ status: 0, code: 'client.network' });
    } finally {
      clearTimeout(timer);
      request.signal.removeEventListener('abort', forwardAbort);
    }
  };
}

/** Marks requests as coming from the web app (the backend's CSRF guard for cookie endpoints). */
const clientHeader: Middleware = {
  onRequest({ request }) {
    request.headers.set('X-MealMate-Client', 'web');
    return request;
  },
};

/**
 * What the API client needs from the signed-in session (`features/auth/session.ts` connects it).
 * Kept as an interface so the client doesn't depend on React or the auth feature.
 */
export interface AuthBridge {
  /** The current access token (memory only), or null. */
  accessToken(): string | null;
  /** Resolves once no refresh is in flight, so no request goes out with a stale token. */
  settled(): Promise<void>;
  /** Refreshes the access token (single-flight); true if a new token is available. */
  refresh(): Promise<boolean>;
  /** The server ended the session (expired, or revoked: SYNC-10). */
  sessionEnded(code: SessionEndCode): void;
}

export type SessionEndCode = 'auth.session_expired' | 'auth.session_revoked';

let authBridge: AuthBridge | null = null;

/** Connects the signed-in session to every API client; `null` disconnects it. */
export function connectAuth(bridge: AuthBridge | null): void {
  authBridge = bridge;
}

/** Endpoints that work without an access token; they never wait for or trigger a refresh. */
const PUBLIC_AUTH_PATHS = new Set([
  '/api/auth/login',
  '/api/auth/refresh',
  '/api/auth/logout',
  '/api/auth/join',
  '/api/auth/reset',
  '/api/auth/codes/check',
]);
/** A 401 with one of these codes means "get a new access token and try again" (once). */
const RETRY_CODES = new Set(['auth.token_expired', 'common.unauthorized']);
const END_CODES = new Set<string>(['auth.session_expired', 'auth.session_revoked']);

async function errorCodeOf(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.clone().json();
    if (typeof body === 'object' && body !== null && 'code' in body) {
      return typeof body.code === 'string' ? body.code : null;
    }
  } catch {
    // Not an error envelope.
  }
  return null;
}

/**
 * Adds `Authorization: Bearer …`. On a 401 that asks for a new access token it refreshes once
 * (single-flight, shared by all requests) and retries the request with the new token. A 401
 * saying the session expired or was revoked ends the session (logged-out state, SYNC-10).
 */
function authMiddleware(): Middleware {
  const retryCopies = new Map<string, Request>();

  return {
    async onRequest({ request, schemaPath, id }) {
      const bridge = authBridge;
      if (!bridge || PUBLIC_AUTH_PATHS.has(schemaPath)) return request;
      await bridge.settled();
      const token = bridge.accessToken();
      if (token) request.headers.set('Authorization', `Bearer ${token}`);
      // The body can only be read once: keep a copy for a retry after refreshing.
      retryCopies.set(id, request.clone());
      return request;
    },
    async onResponse({ response, schemaPath, options, id }) {
      const copy = retryCopies.get(id);
      retryCopies.delete(id);
      const bridge = authBridge;
      if (!bridge || response.status !== 401 || PUBLIC_AUTH_PATHS.has(schemaPath)) return;
      const code = await errorCodeOf(response);
      if (code && END_CODES.has(code)) {
        bridge.sessionEnded(code as SessionEndCode);
        return;
      }
      if (!copy || !code || !RETRY_CODES.has(code) || !(await bridge.refresh())) return;
      const token = bridge.accessToken();
      if (token) copy.headers.set('Authorization', `Bearer ${token}`);
      const retried = await options.fetch(copy);
      if (retried.status === 401) {
        const retryCode = await errorCodeOf(retried);
        if (retryCode && END_CODES.has(retryCode)) bridge.sessionEnded(retryCode as SessionEndCode);
      }
      return retried;
    },
    onError({ id }) {
      retryCopies.delete(id);
    },
  };
}

export function createApiClient({ baseUrl = '' }: { baseUrl?: string } = {}) {
  const client = createClient<paths>({ baseUrl, fetch: createTimeoutFetch() });
  client.use(clientHeader, authMiddleware());
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;

/** The app-wide API client. Features call it from their `api.ts` modules only. */
export const api = createApiClient();

/** Per-request timeout override: `api.GET('/api/…', { ...withTimeout(25_000) })`. */
export function withTimeout(timeoutMs: number): { fetch: FetchFn } {
  return { fetch: createTimeoutFetch(timeoutMs) };
}

/** Resolves to the response data, or rejects with an ApiError read from the error envelope. */
export async function unwrap<T>(
  pending: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await pending;
  if (!response.ok) throw ApiError.fromResponse(response.status, error);
  return data as T;
}
