import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  connectAuth,
  createApiClient,
  onReachability,
  READ_TIMEOUT_MS,
  unwrap,
  withLongTimeout,
  withTimeout,
  WRITE_TIMEOUT_MS,
  type AuthBridge,
} from './client';
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

  it('says whether each request reached the server (SYNC-07)', async () => {
    const seen: boolean[] = [];
    const stop = onReachability((reachable) => seen.push(reachable));
    const answers = [
      () => Promise.resolve(jsonResponse(VERSION)),
      () => Promise.resolve(jsonResponse({ code: 'common.not_found' }, 404)),
      () => Promise.resolve(jsonResponse({ code: 'common.internal' }, 502)),
      () => Promise.reject(new TypeError('Failed to fetch')),
    ];
    vi.stubGlobal(
      'fetch',
      vi.fn(() => answers.shift()!()),
    );

    for (let i = 0; i < 4; i += 1) await api.GET('/api/version').catch(() => undefined);
    stop();
    await api.GET('/api/version').catch(() => undefined);

    expect(seen).toEqual([true, true, false, false]);
  });

  it('counts an error of the app itself as reached, a gateway’s 5xx not (SYNC-07)', async () => {
    const seen: boolean[] = [];
    const stop = onReachability((reachable) => seen.push(reachable));
    const envelope = (code: string) => ({ code, params: {}, fields: [] });
    const answers = [
      // The server answered: busy, or not configured. MealMate is there.
      () => Promise.resolve(jsonResponse(envelope('off.busy'), 503)),
      () => Promise.resolve(jsonResponse(envelope('admin.public_url_missing'), 500)),
      // A proxy or gateway in between answered for it.
      () => Promise.resolve(new Response('<h1>Bad Gateway</h1>', { status: 502 })),
      () => Promise.resolve(jsonResponse({ message: 'upstream timed out' }, 504)),
    ];
    vi.stubGlobal(
      'fetch',
      vi.fn(() => answers.shift()!()),
    );

    for (let i = 0; i < 4; i += 1) await api.GET('/api/version').catch(() => undefined);
    stop();

    expect(seen).toEqual([true, true, false, false]);
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

    it('lets a long-deadline request time out without saying MealMate is gone', async () => {
      const seen: boolean[] = [];
      const stop = onReachability((reachable) => seen.push(reachable));
      vi.stubGlobal('fetch', hangingFetch());

      const slow = api.GET('/api/version', { ...withLongTimeout(25_000) }).catch((e: unknown) => e);
      await vi.advanceTimersByTimeAsync(25_000);
      await expect(slow).resolves.toMatchObject({ code: 'client.timeout' });
      expect(seen).toEqual([]);

      // A request with the usual deadline still does.
      const normal = api.GET('/api/version', { ...withTimeout(1_000) }).catch((e: unknown) => e);
      await vi.advanceTimersByTimeAsync(1_000);
      await expect(normal).resolves.toMatchObject({ code: 'client.timeout' });
      stop();
      expect(seen).toEqual([false]);
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

describe('auth middleware', () => {
  const api = createApiClient({ baseUrl: BASE_URL });

  function fakeBridge(token = 'old-token') {
    let current: string | null = token;
    const bridge = {
      accessToken: vi.fn(() => current),
      settled: vi.fn(() => Promise.resolve()),
      refresh: vi.fn(() => {
        current = 'new-token';
        return Promise.resolve(true);
      }),
      sessionEnded: vi.fn(),
    } satisfies AuthBridge;
    connectAuth(bridge);
    return bridge;
  }

  /** Answers 401 with `code` to the old token and 200 (echoing the body) to the new one. */
  function expiringServer(code = 'auth.token_expired') {
    const fetchMock = vi.fn(async (request: Request) => {
      if (request.headers.get('Authorization') !== 'Bearer new-token') {
        return jsonResponse({ code, params: {}, fields: [] }, 401);
      }
      const body: unknown = request.method === 'GET' ? VERSION : await request.json();
      return jsonResponse(body);
    });
    vi.stubGlobal('fetch', fetchMock);
    return fetchMock;
  }

  it('sends the access token', async () => {
    fakeBridge('abc');
    const fetchMock = vi.fn<(request: Request) => Promise<Response>>(() =>
      Promise.resolve(jsonResponse(VERSION)),
    );
    vi.stubGlobal('fetch', fetchMock);

    await unwrap(api.GET('/api/version'));

    expect(fetchMock.mock.calls[0]?.[0].headers.get('Authorization')).toBe('Bearer abc');
  });

  it.each(['auth.token_expired', 'common.unauthorized'])(
    'refreshes once on %s and retries with the new token and the same body',
    async (code) => {
      const bridge = fakeBridge();
      const fetchMock = expiringServer(code);

      await expect(
        unwrap(api.PATCH('/api/me', { body: { display_name: 'Anna' } })),
      ).resolves.toEqual({ display_name: 'Anna' });

      expect(bridge.refresh).toHaveBeenCalledOnce();
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(fetchMock.mock.calls[1]?.[0].headers.get('Authorization')).toBe('Bearer new-token');
    },
  );

  it('gives up after one retry', async () => {
    const bridge = fakeBridge();
    bridge.refresh.mockImplementation(() => Promise.resolve(true)); // token stays old
    const fetchMock = expiringServer();

    await expect(unwrap(api.GET('/api/version'))).rejects.toMatchObject({
      status: 401,
      code: 'auth.token_expired',
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(bridge.refresh).toHaveBeenCalledOnce();
  });

  it('returns the 401 when the refresh fails', async () => {
    const bridge = fakeBridge();
    bridge.refresh.mockImplementation(() => Promise.resolve(false));
    const fetchMock = expiringServer();

    await expect(unwrap(api.GET('/api/version'))).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it.each(['auth.session_revoked', 'auth.session_expired'])(
    'ends the session on %s without refreshing',
    async (code) => {
      const bridge = fakeBridge();
      expiringServer(code);

      await expect(unwrap(api.GET('/api/version'))).rejects.toMatchObject({ code });
      expect(bridge.sessionEnded).toHaveBeenCalledWith(code);
      expect(bridge.refresh).not.toHaveBeenCalled();
    },
  );

  it('leaves the public auth endpoints alone', async () => {
    const bridge = fakeBridge();
    const fetchMock = expiringServer('auth.invalid_credentials');

    await expect(
      unwrap(api.POST('/api/auth/login', { body: { username: 'a', password: 'b' } })),
    ).rejects.toMatchObject({ code: 'auth.invalid_credentials' });

    expect(bridge.settled).not.toHaveBeenCalled();
    expect(bridge.refresh).not.toHaveBeenCalled();
    expect(fetchMock.mock.calls[0]?.[0].headers.get('Authorization')).toBeNull();
  });

  it('waits for a refresh in flight before sending', async () => {
    const bridge = fakeBridge();
    let settle: () => void = () => undefined;
    bridge.settled.mockImplementation(() => new Promise<void>((resolve) => (settle = resolve)));
    const fetchMock = vi.fn<(request: Request) => Promise<Response>>(() =>
      Promise.resolve(jsonResponse(VERSION)),
    );
    vi.stubGlobal('fetch', fetchMock);

    const pending = unwrap(api.GET('/api/version'));
    await Promise.resolve();
    expect(fetchMock).not.toHaveBeenCalled();
    settle();

    await expect(pending).resolves.toEqual(VERSION);
  });
});
