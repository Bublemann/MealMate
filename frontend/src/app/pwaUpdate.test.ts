import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { checkForUpdatesWhenVisible, UPDATE_CHECK_INTERVAL_MS } from './pwaUpdate';

let visibility: DocumentVisibilityState = 'visible';

function setVisibility(state: DocumentVisibilityState): void {
  visibility = state;
  document.dispatchEvent(new Event('visibilitychange'));
}

describe('checkForUpdatesWhenVisible', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
  });

  afterEach(() => {
    vi.useRealTimers();
    visibility = 'visible';
  });

  it('asks for a new service worker when the app comes back after a while', () => {
    const update = vi.fn(() => Promise.resolve());
    const stop = checkForUpdatesWhenVisible({ update });

    setVisibility('hidden');
    vi.advanceTimersByTime(UPDATE_CHECK_INTERVAL_MS);
    expect(update).not.toHaveBeenCalled();

    setVisibility('visible');
    expect(update).toHaveBeenCalledTimes(1);
    stop();
  });

  it('checks at most once per interval', () => {
    const update = vi.fn(() => Promise.resolve());
    const stop = checkForUpdatesWhenVisible({ update }, 1000);

    setVisibility('visible');
    expect(update).not.toHaveBeenCalled(); // the start itself was a navigation, which checked

    vi.advanceTimersByTime(1000);
    setVisibility('visible');
    vi.advanceTimersByTime(999);
    setVisibility('visible');
    expect(update).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(1);
    setVisibility('visible');
    expect(update).toHaveBeenCalledTimes(2);
    stop();
  });

  it('ignores failed checks and stops listening when asked to', async () => {
    const update = vi.fn(() => Promise.reject(new TypeError('Failed to fetch')));
    const stop = checkForUpdatesWhenVisible({ update }, 0);

    setVisibility('visible');
    await expect(update.mock.results[0]?.value).rejects.toThrow('Failed to fetch');

    stop();
    setVisibility('visible');
    expect(update).toHaveBeenCalledTimes(1);
  });
});
