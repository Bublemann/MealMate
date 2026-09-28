import { act, waitFor } from '@testing-library/react';
import { expect, vi } from 'vitest';
import type { components } from '@/api/generated/schema';

type Schemas = components['schemas'];

export const VERSION_INFO = {
  version: '2.0.0-alpha.1',
  commit: '0123456789abcdef0123456789abcdef01234567',
  source_url: 'https://github.com/Bublemann/MealMate/tree/0123456789abcdef0123456789abcdef01234567',
};

export const TEST_USER: Schemas['Me'] = {
  id: '0190c0de-0000-7000-8000-000000000001',
  username: 'anna',
  display_name: 'Anna',
  role: 'user',
  language: 'en',
  meals_public: true,
  lists_public: true,
  filter_hidden: { meals: [], lists: [] },
  created_at: '2026-09-01T10:00:00Z',
};

export const TEST_ADMIN: Schemas['Me'] = {
  ...TEST_USER,
  id: '0190c0de-0000-7000-8000-00000000000a',
  username: 'admin',
  display_name: 'Admin',
  role: 'admin',
};

export function userRef(name: string, id: string, deactivated = false): Schemas['UserRef'] {
  return { id, display_name: name, deactivated };
}

export const BEN = userRef('Ben', '0190c0de-0000-7000-8000-000000000002');
export const CARL = userRef('Carl', '0190c0de-0000-7000-8000-000000000003');

export function loginResponse(user: Schemas['Me'] = TEST_USER): Schemas['LoginResponse'] {
  return { access_token: 'fresh-access-token', expires_in: 900, user };
}

export const NO_COUPLE: Schemas['CoupleState'] = {
  partner: null,
  since: null,
  outgoing: null,
  incoming: [],
};

export function errorResponse(status: number, code: string, fields: unknown[] = []): Response {
  return Response.json({ code, params: {}, fields }, { status });
}

type Handler = (request: Request) => unknown;

/** Answers for the calls the signed-in app shell and the Me screen make. */
export const DEFAULT_ROUTES: Record<string, unknown> = {
  'GET /api/version': VERSION_INFO,
  'GET /api/me': TEST_USER,
  'GET /api/me/sessions': [
    {
      id: 's1',
      user_agent:
        'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1',
      created_at: '2026-09-01T10:00:00Z',
      last_used_at: '2026-09-26T08:00:00Z',
      current: true,
    },
  ],
  'GET /api/me/security': {
    password_changed_at: null,
    password_reset_at: null,
    password_reset_by: null,
  },
  'GET /api/couple': NO_COUPLE,
  'GET /api/users': [BEN, CARL],
  // The Lists tab, where the app opens: no lists yet, nobody else visible.
  'GET /api/lists': [],
  // The sync module's local copy (SYNC-02): nothing to keep yet.
  'GET /api/lists/sync': { lists: [], generated_at: '2026-09-26T10:00:00Z' },
  'GET /api/users/visible': [],
};

/**
 * Stubs `fetch` with a tiny router: keys are `METHOD /path` (add `?query` to match it too), values
 * are a JSON body (200), a Response, or a function of the Request returning either. Unknown routes
 * answer 404 `common.not_found`. Returns the mock, whose calls hold the Requests.
 */
export function mockApi(routes: Record<string, unknown> = {}) {
  const table = { ...DEFAULT_ROUTES, ...routes };
  const fetchMock = vi.fn(async (request: Request) => {
    const url = new URL(request.url);
    const key = `${request.method} ${url.pathname}`;
    const entry = `${key}${url.search}` in table ? table[`${key}${url.search}`] : table[key];
    if (entry === undefined) return errorResponse(404, 'common.not_found');
    const value = typeof entry === 'function' ? await (entry as Handler)(request.clone()) : entry;
    if (value instanceof Response) return value.clone();
    if (value === null) return new Response(null, { status: 204 });
    return Response.json(value);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** The requests sent to `METHOD /path`, in order. */
export function requestsTo(fetchMock: ReturnType<typeof mockApi>, route: string): Request[] {
  return fetchMock.mock.calls
    .map(([request]) => request)
    .filter((request) => `${request.method} ${new URL(request.url).pathname}` === route);
}

/**
 * `PATCH /api/me` that saves what it is sent but answers only when the test says so (`answer`
 * answers the oldest waiting request).
 */
export function slowFilterSaves() {
  const waiting: (() => void)[] = [];
  const route = async (request: Request) => {
    const { filter_hidden } = (await request.json()) as Pick<Schemas['Me'], 'filter_hidden'>;
    await new Promise<void>((resolve) => waiting.push(resolve));
    return { ...TEST_USER, filter_hidden };
  };
  const answer = async (count: number) => {
    await waitFor(() => expect(waiting).toHaveLength(count));
    act(() => waiting[count - 1]?.());
  };
  return { route, answer };
}

/**
 * A route that answers only when the test says so: `answer(body)` answers every request waiting
 * so far with `body` (JSON), e.g. to look at a screen while its first load is still running.
 */
export function heldRoute() {
  const waiting: ((body: unknown) => void)[] = [];
  const route = () => new Promise<unknown>((resolve) => waiting.push(resolve));
  const answer = async (body: unknown) => {
    await waitFor(() => expect(waiting.length).toBeGreaterThan(0));
    act(() => {
      for (const resolve of waiting.splice(0)) resolve(body);
    });
  };
  return { route, answer };
}

interface NodeProcess {
  getBuiltinModule(id: 'node:buffer'): { File: typeof File };
}

/**
 * Node's own FormData and File. Vitest's bridge from jsdom's FormData and Blobs to Node's Request
 * fails with jsdom 30, so a test that uploads a file stubs the global FormData with Node's
 * (`vi.stubGlobal('FormData', FormData)`) and picks a Node File: Request then takes the body as
 * it is and sets the multipart boundary, as a browser does. Read the sent body with `text()`:
 * Node's multipart parser also trips over jsdom's global File.
 */
export async function nodeFormClasses(): Promise<{ FormData: typeof FormData; File: typeof File }> {
  const form = await new Response(new URLSearchParams()).formData();
  const { process } = globalThis as unknown as { process: NodeProcess };
  return {
    FormData: form.constructor as typeof FormData,
    File: process.getBuiltinModule('node:buffer').File,
  };
}
