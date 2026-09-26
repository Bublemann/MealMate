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

export function createApiClient({ baseUrl = '' }: { baseUrl?: string } = {}) {
  const client = createClient<paths>({ baseUrl, fetch: createTimeoutFetch() });
  client.use(clientHeader);
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
