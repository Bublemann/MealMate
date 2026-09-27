import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  IDB_OPEN_TIMEOUT_MS,
  readIndexedDbMarker,
  trackLine,
  writeIndexedDbMarker,
} from './probes';

type Handler = (() => void) | null;

/**
 * A stand-in for `indexedDB` (jsdom has none). `open` says how the open request ends (`hang`:
 * never, like Safari at times); `transaction` whether the transactions complete or abort after
 * their request has succeeded. Events come in a later task, as in a browser.
 */
function stubIndexedDb({
  open = 'success',
  transaction = 'complete',
}: {
  open?: 'success' | 'error' | 'blocked' | 'hang';
  transaction?: 'complete' | 'abort';
} = {}) {
  const data = new Map<string, unknown>();

  function createTransaction() {
    const tx = {
      error: null as DOMException | null,
      oncomplete: null as Handler,
      onerror: null as Handler,
      onabort: null as Handler,
      objectStore: () => store,
    };
    function request(run: () => unknown) {
      const req = { result: undefined as unknown, error: null, onsuccess: null as Handler };
      setTimeout(() => {
        req.result = run();
        req.onsuccess?.();
        if (transaction === 'abort') {
          data.clear();
          tx.error = new DOMException('Disk full', 'QuotaExceededError');
          tx.onabort?.();
        } else {
          tx.oncomplete?.();
        }
      });
      return req;
    }
    const store = {
      get: (key: string) => request(() => data.get(key)),
      put: (value: unknown, key: string) =>
        request(() => {
          data.set(key, value);
          return key;
        }),
    };
    return tx;
  }

  const db = { close: vi.fn(), createObjectStore: vi.fn(), transaction: vi.fn(createTransaction) };
  const openRequest = {
    result: db,
    error: new DOMException('Broken', 'UnknownError'),
    onsuccess: null as Handler,
    onerror: null as Handler,
    onblocked: null as Handler,
    onupgradeneeded: null as Handler,
  };
  vi.stubGlobal('indexedDB', {
    open: vi.fn(() => {
      setTimeout(() => {
        if (open === 'success') openRequest.onsuccess?.();
        if (open === 'error') openRequest.onerror?.();
        if (open === 'blocked') openRequest.onblocked?.();
      });
      return openRequest;
    }),
  });
  return { db, openRequest };
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('IndexedDB marker', () => {
  it('writes the marker and reads it back once the transactions have completed', async () => {
    const { db } = stubIndexedDb();

    expect(await readIndexedDbMarker()).toEqual({ status: 'info', value: 'no marker' });
    expect(await writeIndexedDbMarker(new Date('2026-09-27T18:30:00Z'))).toEqual({
      status: 'ok',
      value: 'marker from 2026-09-27T18:30:00.000Z',
    });
    expect(db.close).toHaveBeenCalledTimes(3);
  });

  it('fails a write whose transaction aborts, although its request succeeded', async () => {
    const { db } = stubIndexedDb({ transaction: 'abort' });

    expect(await writeIndexedDbMarker(new Date())).toEqual({
      status: 'failed',
      value: 'QuotaExceededError: Disk full',
    });
    expect(db.close).toHaveBeenCalled();
  });

  it('reports an open that fails or is blocked by another tab', async () => {
    stubIndexedDb({ open: 'error' });
    expect(await readIndexedDbMarker()).toEqual({
      status: 'failed',
      value: 'UnknownError: Broken',
    });

    stubIndexedDb({ open: 'blocked' });
    expect(await readIndexedDbMarker()).toEqual({
      status: 'failed',
      value: 'Error: indexedDB.open blocked by another tab',
    });
  });

  it('gives up on an open that never ends, and closes the database if it opens later', async () => {
    vi.useFakeTimers();
    const { db, openRequest } = stubIndexedDb({ open: 'hang' });

    const pending = readIndexedDbMarker();
    await vi.advanceTimersByTimeAsync(IDB_OPEN_TIMEOUT_MS - 1);
    let done = false;
    void pending.then(() => (done = true));
    await vi.advanceTimersByTimeAsync(0);
    expect(done).toBe(false);

    await vi.advanceTimersByTimeAsync(1);
    expect(await pending).toEqual({ status: 'failed', value: 'indexedDB.open timed out' });
    openRequest.onsuccess?.();
    expect(db.close).toHaveBeenCalledTimes(1);
    expect(db.transaction).not.toHaveBeenCalled();
  });
});

describe('trackLine', () => {
  const track = {
    getSettings: () => ({ width: 1920, height: 1080, facingMode: 'environment' }),
  } as unknown as MediaStreamTrack;

  it('shows the frame size next to the settings, so a turned image is visible (O-6)', () => {
    expect(trackLine(track, { videoWidth: 1080, videoHeight: 1920 }).value).toMatch(
      /^settings 1920×1080, frames 1080×1920, facingMode environment, screen /,
    );
    // Before the first frame the preview's size is 0×0: not known yet.
    expect(trackLine(track, { videoWidth: 0, videoHeight: 0 }).value).toContain('frames ?');
    expect(trackLine(track).value).toContain('frames ?');
  });
});
