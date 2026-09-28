import { describe, expect, it, vi } from 'vitest';
import { classifyShareError, shareLine, tryShare } from './share';

describe('classifyShareError', () => {
  it('tells a cancelled sheet from an expired user activation', () => {
    expect(classifyShareError(new DOMException('Share canceled', 'AbortError'))).toEqual({
      kind: 'cancelled',
    });
    expect(classifyShareError(new DOMException('No activation', 'NotAllowedError'))).toEqual({
      kind: 'activationExpired',
    });
    expect(classifyShareError(new TypeError('bad data'))).toEqual({
      kind: 'error',
      name: 'TypeError',
    });
    expect(classifyShareError('odd')).toEqual({ kind: 'error', name: 'odd' });
  });
});

describe('tryShare', () => {
  it('calls share synchronously, before its first await', async () => {
    const share = vi.fn(() => Promise.resolve());
    const pending = tryShare('hello', share);

    expect(share).toHaveBeenCalledWith({ text: 'hello' });
    expect(await pending).toEqual({ kind: 'shared' });
  });

  it('reports the rejection of share', async () => {
    const share = vi.fn(() => Promise.reject(new DOMException('', 'NotAllowedError')));
    expect(await tryShare('hello', share)).toEqual({ kind: 'activationExpired' });
  });

  it('reports a browser without share', async () => {
    expect(await tryShare('hello', undefined)).toEqual({ kind: 'unsupported' });
  });
});

describe('shareLine', () => {
  it('counts a sheet that opened as ok, and names the waiting time', () => {
    expect(shareLine({ kind: 'shared' })).toEqual({ status: 'ok', value: 'shared' });
    expect(shareLine({ kind: 'cancelled' }, 3012.4)).toEqual({
      status: 'ok',
      value: 'AbortError: sheet opened, cancelled by the user (shared 3012 ms after the tap)',
    });
    expect(shareLine({ kind: 'activationExpired' }, 6001)).toEqual({
      status: 'failed',
      value: 'NotAllowedError: user activation expired (shared 6001 ms after the tap)',
    });
    expect(shareLine({ kind: 'unsupported' })).toMatchObject({ status: 'failed' });
    expect(shareLine({ kind: 'error', name: 'TypeError' })).toEqual({
      status: 'failed',
      value: 'TypeError',
    });
  });
});
