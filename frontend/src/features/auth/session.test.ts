import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, connectAuth, unwrap } from '@/api/client';
import i18n from '@/i18n';
import {
  errorResponse,
  loginResponse,
  mockApi,
  requestsTo,
  TEST_USER,
  VERSION_INFO,
} from '@/test/api';
import { createAuthSession, REFRESH_LOCK } from './session';
import { PROFILE_STORAGE_KEY, STANDALONE_MARKER_KEY } from './storage';

function standalone(matches: boolean) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query: string) => ({ matches: matches && query === '(display-mode: standalone)' })),
  );
}

function stubLocks() {
  const request = vi.fn((_name: string, callback: () => Promise<unknown>) => callback());
  Object.defineProperty(navigator, 'locks', { value: { request }, configurable: true });
  return request;
}

async function refreshBody(fetchMock: ReturnType<typeof mockApi>, index = 0): Promise<unknown> {
  return requestsTo(fetchMock, 'POST /api/auth/refresh')[index]?.json();
}

afterEach(() => {
  Reflect.deleteProperty(navigator, 'locks');
});

describe('auth session start-up', () => {
  it('refreshes once and signs the user in', async () => {
    const fetchMock = mockApi({ 'POST /api/auth/refresh': loginResponse() });
    const session = createAuthSession();
    expect(session.getState().status).toBe('loading');

    await Promise.all([session.start(), session.start()]);

    expect(requestsTo(fetchMock, 'POST /api/auth/refresh')).toHaveLength(1);
    expect(session.getState()).toMatchObject({ status: 'authenticated', user: TEST_USER });
    expect(session.accessToken()).toBe('fresh-access-token');
    await expect(refreshBody(fetchMock)).resolves.toEqual({ fork: false });
    const [request] = requestsTo(fetchMock, 'POST /api/auth/refresh');
    expect(request?.headers.get('X-MealMate-Client')).toBe('web');
    expect(JSON.parse(localStorage.getItem(PROFILE_STORAGE_KEY) ?? 'null')).toEqual(TEST_USER);
  });

  it('follows the language stored on the server', async () => {
    mockApi({ 'POST /api/auth/refresh': loginResponse({ ...TEST_USER, language: 'de' }) });

    await createAuthSession().start();

    expect(i18n.resolvedLanguage).toBe('de');
  });

  it('is signed out without a session, and says "expired" only to a known user', async () => {
    mockApi({ 'POST /api/auth/refresh': errorResponse(401, 'auth.session_expired') });

    const fresh = createAuthSession();
    await fresh.start();
    expect(fresh.getState()).toMatchObject({ status: 'anonymous', reason: null });

    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(TEST_USER));
    const returning = createAuthSession();
    await returning.start();
    expect(returning.getState()).toMatchObject({ status: 'anonymous', reason: 'expired' });
    expect(localStorage.getItem(PROFILE_STORAGE_KEY)).toBeNull();
  });

  it('shows the cached profile when the server is unreachable', async () => {
    mockApi({ 'POST /api/auth/refresh': () => Promise.reject(new TypeError('Failed to fetch')) });
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(TEST_USER));

    const session = createAuthSession();
    await session.start();

    expect(session.getState()).toMatchObject({
      status: 'authenticated',
      offline: true,
      user: TEST_USER,
    });
    expect(session.accessToken()).toBeNull();
  });

  it('reports "unreachable" without a cached profile and can try again', async () => {
    let reachable = false;
    mockApi({
      'POST /api/auth/refresh': () =>
        reachable ? loginResponse() : Promise.reject(new TypeError('Failed to fetch')),
    });
    const session = createAuthSession();

    await session.start();
    expect(session.getState().status).toBe('unreachable');

    reachable = true;
    await session.retry();
    expect(session.getState().status).toBe('authenticated');
  });

  it('treats a server error like an unreachable server', async () => {
    mockApi({ 'POST /api/auth/refresh': errorResponse(503, 'common.service_unavailable') });
    const session = createAuthSession();

    await session.start();

    expect(session.getState().status).toBe('unreachable');
  });
});

describe('Home Screen fork (plan § 5.4)', () => {
  it('forks on the first standalone start and sets the marker', async () => {
    standalone(true);
    const fetchMock = mockApi({ 'POST /api/auth/refresh': loginResponse() });

    await createAuthSession().start();

    await expect(refreshBody(fetchMock)).resolves.toEqual({ fork: true });
    expect(localStorage.getItem(STANDALONE_MARKER_KEY)).not.toBeNull();

    await createAuthSession().start();
    await expect(refreshBody(fetchMock, 1)).resolves.toEqual({ fork: false });
  });

  it('also accepts iOS navigator.standalone', async () => {
    Object.defineProperty(navigator, 'standalone', { value: true, configurable: true });
    try {
      const fetchMock = mockApi({ 'POST /api/auth/refresh': loginResponse() });
      await createAuthSession().start();
      await expect(refreshBody(fetchMock)).resolves.toEqual({ fork: true });
    } finally {
      Reflect.deleteProperty(navigator, 'standalone');
    }
  });

  it('does not fork in the browser', async () => {
    standalone(false);
    const fetchMock = mockApi({ 'POST /api/auth/refresh': loginResponse() });

    await createAuthSession().start();

    await expect(refreshBody(fetchMock)).resolves.toEqual({ fork: false });
    expect(localStorage.getItem(STANDALONE_MARKER_KEY)).toBeNull();
  });

  it('asks for one login when the fork is refused, and does not fork again', async () => {
    standalone(true);
    mockApi({ 'POST /api/auth/refresh': errorResponse(401, 'auth.login_required') });
    const session = createAuthSession();

    await session.start();

    expect(session.getState()).toMatchObject({ status: 'anonymous', reason: 'login_required' });
    expect(localStorage.getItem(STANDALONE_MARKER_KEY)).not.toBeNull();
  });

  it('tries the fork again next time when the server was unreachable', async () => {
    standalone(true);
    mockApi({ 'POST /api/auth/refresh': () => Promise.reject(new TypeError('Failed to fetch')) });

    await createAuthSession().start();

    expect(localStorage.getItem(STANDALONE_MARKER_KEY)).toBeNull();
  });
});

describe('refresh', () => {
  it('is single-flight within the tab and runs under the cross-tab lock', async () => {
    const locks = stubLocks();
    let answer: (response: Response) => void = () => undefined;
    const fetchMock = mockApi({
      'POST /api/auth/refresh': () => new Promise<Response>((resolve) => (answer = resolve)),
    });
    const session = createAuthSession({ initial: { user: TEST_USER, accessToken: 'old' } });

    const results = Promise.all([session.refresh(), session.refresh(), session.refresh()]);
    await vi.waitFor(() => expect(requestsTo(fetchMock, 'POST /api/auth/refresh')).toHaveLength(1));
    answer(Response.json(loginResponse()));

    await expect(results).resolves.toEqual([true, true, true]);
    expect(requestsTo(fetchMock, 'POST /api/auth/refresh')).toHaveLength(1);
    expect(locks).toHaveBeenCalledOnce();
    expect(locks.mock.calls[0]?.[0]).toBe(REFRESH_LOCK);
    expect(session.accessToken()).toBe('fresh-access-token');

    // Once settled, the next refresh is a new request.
    mockApi({ 'POST /api/auth/refresh': loginResponse() });
    await expect(session.refresh()).resolves.toBe(true);
  });

  it('works without the Web Locks API', async () => {
    expect('locks' in navigator).toBe(false);
    mockApi({ 'POST /api/auth/refresh': loginResponse() });
    const session = createAuthSession({ initial: { user: TEST_USER, accessToken: 'old' } });

    await expect(session.refresh()).resolves.toBe(true);
  });
});

describe('session end (SYNC-10)', () => {
  it('wipes the user data when the server reports the session as revoked', () => {
    const session = createAuthSession({ initial: { user: TEST_USER, accessToken: 'token' } });
    const onEnd = vi.fn();
    session.onEnd(onEnd);
    localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(TEST_USER));
    localStorage.setItem('mm.user.something', 'x');
    localStorage.setItem('mm.language', 'de');
    localStorage.setItem(STANDALONE_MARKER_KEY, '1');

    session.sessionEnded('auth.session_revoked');

    expect(session.getState()).toMatchObject({
      status: 'anonymous',
      user: null,
      reason: 'revoked',
    });
    expect(session.accessToken()).toBeNull();
    expect(onEnd).toHaveBeenCalledOnce();
    expect(localStorage.getItem(PROFILE_STORAGE_KEY)).toBeNull();
    expect(localStorage.getItem('mm.user.something')).toBeNull();
    // Device settings stay.
    expect(localStorage.getItem('mm.language')).toBe('de');
    expect(localStorage.getItem(STANDALONE_MARKER_KEY)).toBe('1');
  });

  it("drops the previous user's data when someone else signs in", () => {
    const session = createAuthSession({ initial: { user: TEST_USER, accessToken: 'token' } });
    const onEnd = vi.fn();
    session.onEnd(onEnd);
    localStorage.setItem('mm.user.something', 'x');
    const ben = { ...TEST_USER, id: '0190c0de-0000-7000-8000-000000000002', username: 'ben' };

    session.signIn(loginResponse(ben));

    expect(onEnd).toHaveBeenCalledOnce();
    expect(localStorage.getItem('mm.user.something')).toBeNull();
    expect(JSON.parse(localStorage.getItem(PROFILE_STORAGE_KEY) ?? 'null')).toEqual(ben);
    expect(session.getState()).toMatchObject({ status: 'authenticated', user: ben, reason: null });
    expect(session.accessToken()).toBe('fresh-access-token');
  });

  it('keeps the data when the same user signs in again', () => {
    const session = createAuthSession({ initial: { user: TEST_USER, accessToken: 'token' } });
    const onEnd = vi.fn();
    session.onEnd(onEnd);
    localStorage.setItem('mm.user.something', 'x');

    session.signIn(loginResponse({ ...TEST_USER, display_name: 'Anna M.' }));

    expect(onEnd).not.toHaveBeenCalled();
    expect(localStorage.getItem('mm.user.something')).toBe('x');
    expect(session.getState().user?.display_name).toBe('Anna M.');
  });

  it('ends the session when a refresh finds it revoked', async () => {
    mockApi({ 'POST /api/auth/refresh': errorResponse(401, 'auth.session_revoked') });
    const session = createAuthSession({ initial: { user: TEST_USER, accessToken: 'old' } });

    await expect(session.refresh()).resolves.toBe(false);

    expect(session.getState()).toMatchObject({ status: 'anonymous', reason: 'revoked' });
  });

  it('logs out on the server, then locally', async () => {
    const fetchMock = mockApi({ 'POST /api/auth/logout': null });
    const session = createAuthSession({ initial: { user: TEST_USER, accessToken: 'token' } });

    await session.logout();

    expect(requestsTo(fetchMock, 'POST /api/auth/logout')).toHaveLength(1);
    expect(session.getState()).toMatchObject({ status: 'anonymous', reason: 'logged_out' });
  });

  it('keeps the user signed in when the logout request fails', async () => {
    mockApi({ 'POST /api/auth/logout': errorResponse(500, 'common.internal') });
    const session = createAuthSession({ initial: { user: TEST_USER, accessToken: 'token' } });

    await expect(session.logout()).rejects.toMatchObject({ code: 'common.internal' });

    expect(session.getState().status).toBe('authenticated');
  });
});

describe('API client with a session', () => {
  it('waits for the start-up refresh before sending a request', async () => {
    let answer: (response: Response) => void = () => undefined;
    const fetchMock = mockApi({
      'POST /api/auth/refresh': () => new Promise<Response>((resolve) => (answer = resolve)),
      'GET /api/version': VERSION_INFO,
    });
    const session = createAuthSession();
    connectAuth(session);

    void session.start();
    const version = unwrap(api.GET('/api/version'));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    answer(Response.json(loginResponse()));

    await expect(version).resolves.toEqual(VERSION_INFO);
    const [request] = requestsTo(fetchMock, 'GET /api/version');
    expect(request?.headers.get('Authorization')).toBe('Bearer fresh-access-token');
  });
});
