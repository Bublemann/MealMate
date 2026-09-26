type Listener = () => void;

const listeners = new Set<Listener>();
let applyUpdate: (() => Promise<void>) | null = null;

function notify(): void {
  for (const listener of listeners) listener();
}

/**
 * State of the "new version available" prompt, fed by the service-worker registration in
 * main.tsx and read by UpdatePrompt through useSyncExternalStore.
 */
export const pwaUpdate = {
  subscribe: (listener: Listener): (() => void) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
  isAvailable: (): boolean => applyUpdate !== null,
  /** A new service worker is waiting; `apply` activates it and reloads the page. */
  announce: (apply: () => Promise<void>): void => {
    applyUpdate = apply;
    notify();
  },
  /** Hides the prompt; the waiting version is offered again on the next start. */
  dismiss: (): void => {
    applyUpdate = null;
    notify();
  },
  apply: async (): Promise<void> => {
    await applyUpdate?.();
  },
};

/** How often a return to the app may ask the server for a new service worker. */
export const UPDATE_CHECK_INTERVAL_MS = 5 * 60 * 1000;

/**
 * Browsers only look for a new sw.js on navigations. A Home Screen app that comes back from the
 * background does not navigate, so it would keep running an old build and never show the update
 * prompt. This asks for an update whenever the app becomes visible again, at most every
 * `intervalMs`. Returns a function that stops it.
 */
export function checkForUpdatesWhenVisible(
  registration: { update: () => Promise<unknown> },
  intervalMs = UPDATE_CHECK_INTERVAL_MS,
): () => void {
  let lastCheck = Date.now();
  const onVisibilityChange = () => {
    if (document.visibilityState !== 'visible' || Date.now() - lastCheck < intervalMs) return;
    lastCheck = Date.now();
    // Offline or unreachable: the next return to the app tries again.
    registration.update().catch(() => undefined);
  };
  document.addEventListener('visibilitychange', onVisibilityChange);
  return () => document.removeEventListener('visibilitychange', onVisibilityChange);
}
