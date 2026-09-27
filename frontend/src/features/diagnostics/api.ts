import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';
import { isApiError } from '@/api/errors';
import type { ResultLine } from './results';

export type DiagRequestInfo = components['schemas']['DiagRequestInfo'];

/**
 * The diagnostics endpoints (`/api/auth/diag/*`, only with MEALMATE_DIAGNOSTICS_ENABLED=true).
 * Plain calls rather than TanStack Query hooks: each is a one-off test the owner taps, and the
 * answer must never come from a cache. The shared client sends `X-MealMate-Client` like the app.
 */
export const diagApi = {
  setCookie: () => unwrap(api.POST('/api/auth/diag/set')),
  checkCookie: () => unwrap(api.POST('/api/auth/diag/check')),
  request: () => unwrap(api.GET('/api/auth/diag/request')),
  health: () => unwrap(api.GET('/api/health')),
  version: () => unwrap(api.GET('/api/version')),
};

/** A 404 from a diagnostics endpoint: the server runs without MEALMATE_DIAGNOSTICS_ENABLED. */
export function diagnosticsOff(error: unknown): boolean {
  return isApiError(error) && error.status === 404;
}

/** The result line of a failed call; a 404 carries the hint on how to switch diagnostics on. */
export function errorLine(error: unknown): ResultLine {
  if (diagnosticsOff(error)) {
    return { status: 'failed', value: '404: diagnostics endpoints are off', hint: 'endpointsOff' };
  }
  if (isApiError(error)) {
    return { status: 'failed', value: error.status ? `${error.status} ${error.code}` : error.code };
  }
  return { status: 'failed', value: error instanceof Error ? error.message : String(error) };
}

const LOOPBACK = new Set(['127.0.0.1', '::1', 'localhost']);

/**
 * `client_host=… scheme=… …` with `-` for a missing header. `ok` when it is what the plan expects
 * behind `tailscale serve` (O-3): https, and a client that is not the proxy on loopback. Anything
 * else is `info` rather than `failed`, since a development server over http is fine.
 */
export function requestLine(info: DiagRequestInfo): ResultLine {
  const fields: [string, string | null][] = [
    ['client_host', info.client_host],
    ['scheme', info.scheme],
    ['host', info.host_header],
    ['x-forwarded-for', info.x_forwarded_for],
    ['x-forwarded-proto', info.x_forwarded_proto],
  ];
  const expected = info.scheme === 'https' && !LOOPBACK.has(info.client_host);
  return {
    status: expected ? 'ok' : 'info',
    value: fields.map(([name, value]) => `${name}=${value ?? '-'}`).join(' '),
  };
}
