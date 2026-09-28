import { describe, expect, it } from 'vitest';
import { ApiError } from '@/api/errors';
import { diagnosticsOff, errorLine, requestLine } from './api';

describe('errorLine', () => {
  it('turns a 404 into the hint to switch the diagnostics endpoints on', () => {
    const notFound = new ApiError({ status: 404, code: 'common.not_found' });

    expect(diagnosticsOff(notFound)).toBe(true);
    expect(errorLine(notFound)).toEqual({
      status: 'failed',
      value: '404: diagnostics endpoints are off',
      hint: 'endpointsOff',
    });
  });

  it('names other failures by status and code', () => {
    const unreachable = new ApiError({ status: 0, code: 'client.network' });

    expect(diagnosticsOff(unreachable)).toBe(false);
    expect(errorLine(unreachable)).toEqual({ status: 'failed', value: 'client.network' });
    expect(errorLine(new ApiError({ status: 503, code: 'common.service_unavailable' }))).toEqual({
      status: 'failed',
      value: '503 common.service_unavailable',
    });
    expect(errorLine(new Error('boom'))).toEqual({ status: 'failed', value: 'boom' });
    expect(diagnosticsOff(new Error('boom'))).toBe(false);
  });
});

describe('requestLine', () => {
  const behindTailscale = {
    client_host: '100.101.102.103',
    scheme: 'https',
    host_header: 'mealmate.example.ts.net',
    x_forwarded_for: '100.101.102.103',
    x_forwarded_proto: 'https',
  };

  it('is ok when the app sees the phone over https (O-3)', () => {
    expect(requestLine(behindTailscale)).toEqual({
      status: 'ok',
      value:
        'client_host=100.101.102.103 scheme=https host=mealmate.example.ts.net ' +
        'x-forwarded-for=100.101.102.103 x-forwarded-proto=https',
    });
  });

  it('only informs about the proxy address or plain http', () => {
    const loopback = { ...behindTailscale, client_host: '127.0.0.1', x_forwarded_for: null };

    expect(requestLine(loopback)).toMatchObject({ status: 'info' });
    expect(requestLine(loopback).value).toContain('x-forwarded-for=-');
    expect(requestLine({ ...behindTailscale, scheme: 'http' })).toMatchObject({ status: 'info' });
  });
});
