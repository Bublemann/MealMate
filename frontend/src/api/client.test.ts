import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiClient, READ_TIMEOUT_MS, unwrap, withTimeout, WRITE_TIMEOUT_MS } from './client';
import { ApiError } from './errors';

const BASE_URL = 'http://mealmate.test';
const VERSION = { version: '2.0.0', commit: 'abc123', source_url: 'https://example.test/tree/abc' };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** A fetch that never answers on its own and, like fetch, rejects once its signal aborts. */
function hangingFetch() {
  return vi.fn(
    (_request: Request, init?: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        const signal = init?.signal;
        const abort = () => reject(new DOMException('The operation was aborted.', 'AbortError'));
        if (signal?.aborted) abort();
        signal?.addEventListener('abort', abort);
      }),
  );
}

describe('api client', () => {
  const api = createApiClient({ baseUrl: BASE_URL });

  it('returns data and marks requests as coming from the web client', async () => {
    const fetchMock = vi.fn<(request: Request) => Promise<Response>>(() =>
      Promise.resolve(jsonResponse(VERSION)),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(unwrap(api.GET('/api/version'))).resolves.toEqual(VERSION);

    const request = fetchMock.mock.calls[0]?.[0];
    expect(request?.url).toBe(`${BASE_URL}/api/version`);
    expect(request?.headers.get('X-MealMate-Client')).toBe('web');
  });

  it('turns the error envelope into an ApiError', async () => {
    const envelope = {
      code: 'common.validation',
      params: { max: 3, name: 'x', flag: true, nested: { dropped: 1 } },
      fields: [
        { loc: ['body', 'name', 0], code: 'too_long' },
        { loc: 'not-a-list', code: 'invalid' },
      ],
    };
    vi.stubGlobal('fetch', () => Promise.resolve(jsonResponse(envelope, 422)));

    const error = await unwrap(api.GET('/api/version')).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 422,
      code: 'common.validation',
      params: { max: 3, name: 'x', flag: true },
      fields: [{ loc: ['body', 'name', 0], code: 'too_long' }],
    });
  });

  it('falls back to common.internal when the body is not an envelope', async () => {
    vi.stubGlobal('fetch', () =>
      Promise.resolve(new Response('<h1>Bad Gateway</h1>', { status: 502 })),
    );

    await expect(unwrap(api.GET('/api/version'))).rejects.toMatchObject({
      status: 502,
      code: 'common.internal',
      params: {},
      fields: [],
    });
  });

  it('reports a network failure as client.network', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('Failed to fetch')));

    await expect(api.GET('/api/version')).rejects.toMatchObject({
      status: 0,
      code: 'client.network',
    });
  });

  it('passes a caller abort through unchanged', async () => {
    vi.stubGlobal('fetch', hangingFetch());
    const controller = new AbortController();

    const pending = api.GET('/api/version', { signal: controller.signal });
    controller.abort();

    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
  });

  describe('timeouts', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('aborts reads after the read deadline', async () => {
      vi.stubGlobal('fetch', hangingFetch());

      const result = api.GET('/api/version').catch((e: unknown) => e);
      await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS - 1);
      await vi.advanceTimersByTimeAsync(1);

      await expect(result).resolves.toMatchObject({ status: 0, code: 'client.timeout' });
    });

    it('gives writes the longer write deadline', async () => {
      vi.stubGlobal('fetch', hangingFetch());
      let settled = false;

      const result = api
        .POST('/api/auth/diag/check')
        .catch((e: unknown) => e)
        .finally(() => (settled = true));
      await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS);
      expect(settled).toBe(false);
      await vi.advanceTimersByTimeAsync(WRITE_TIMEOUT_MS - READ_TIMEOUT_MS);

      await expect(result).resolves.toMatchObject({ code: 'client.timeout' });
    });

    it('accepts a per-request override', async () => {
      vi.stubGlobal('fetch', hangingFetch());
      let settled = false;

      const result = api
        .GET('/api/version', { ...withTimeout(25_000) })
        .catch((e: unknown) => e)
        .finally(() => (settled = true));
      await vi.advanceTimersByTimeAsync(WRITE_TIMEOUT_MS);
      expect(settled).toBe(false);
      await vi.advanceTimersByTimeAsync(25_000 - WRITE_TIMEOUT_MS);

      await expect(result).resolves.toMatchObject({ code: 'client.timeout' });
    });

    it('keeps the deadline running while the body is still arriving', async () => {
      // Like a real fetch: headers arrive, the body stalls, and an abort errors the body stream.
      vi.stubGlobal('fetch', (_request: Request, init?: RequestInit) => {
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            controller.enqueue(new TextEncoder().encode('{"version":'));
            init?.signal?.addEventListener('abort', () =>
              controller.error(new DOMException('The operation was aborted.', 'AbortError')),
            );
          },
        });
        return Promise.resolve(new Response(body, { status: 200 }));
      });

      const result = api.GET('/api/version').catch((e: unknown) => e);
      await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS);

      await expect(result).resolves.toMatchObject({ code: 'client.timeout' });
    });
  });
});
