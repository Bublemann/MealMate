import { type ResultLine, yesNo } from './results';

/**
 * Readings of the browser for the diagnostics screen. Each returns a result line and never
 * throws: an API that is missing or refuses is itself a finding.
 *
 * The storage test leaves the IndexedDB database `mealmate-diag` and the localStorage key
 * `mm.diag.marker` on every device it ran on: removing this screen in M9 doesn't remove them, so
 * that change should delete both at start-up (`indexedDB.deleteDatabase`, `removeItem`).
 */

type IosNavigator = Navigator & { standalone?: boolean };

function describeError(error: unknown): string {
  return error instanceof DOMException || error instanceof Error
    ? `${error.name}: ${error.message}`
    : String(error);
}

function mediaMatches(query: string): boolean {
  return window.matchMedia?.(query).matches === true;
}

/** `standalone` or `browser`, the way the app itself decides (see features/auth/storage). */
export function displayMode(): 'standalone' | 'browser' {
  const iosStandalone = (navigator as IosNavigator).standalone === true;
  return iosStandalone || mediaMatches('(display-mode: standalone)') ? 'standalone' : 'browser';
}

export function displayModeLine(): ResultLine {
  const iosStandalone = (navigator as IosNavigator).standalone;
  return {
    status: 'info',
    value:
      `${displayMode()} (display-mode standalone: ` +
      `${yesNo(mediaMatches('(display-mode: standalone)'))}, ` +
      `navigator.standalone: ${String(iosStandalone)})`,
  };
}

export function colorSchemeLine(): ResultLine {
  return { status: 'info', value: mediaMatches('(prefers-color-scheme: dark)') ? 'dark' : 'light' };
}

export function screenLine(): ResultLine {
  const orientation = typeof screen.orientation === 'object' ? screen.orientation.type : '-';
  return {
    status: 'info',
    value:
      `screen ${screen.width}×${screen.height} @${window.devicePixelRatio}x, ` +
      `viewport ${window.innerWidth}×${window.innerHeight}, orientation ${orientation}`,
  };
}

export function onlineLine(): ResultLine {
  return { status: 'info', value: navigator.onLine ? 'online' : 'offline' };
}

/** Whether a service worker controls the page, and the state of its registration. */
export async function serviceWorkerLine(): Promise<ResultLine> {
  if (!('serviceWorker' in navigator)) return { status: 'failed', value: 'no service worker API' };
  const controlled = navigator.serviceWorker.controller !== null;
  try {
    const registration = await navigator.serviceWorker.getRegistration();
    const states = registration
      ? [
          `active ${registration.active?.state ?? '-'}`,
          `waiting ${registration.waiting?.state ?? '-'}`,
          `installing ${registration.installing?.state ?? '-'}`,
        ].join(', ')
      : 'not registered';
    return {
      status: controlled ? 'ok' : 'info',
      value: `controller: ${yesNo(controlled)}; registration: ${states}`,
    };
  } catch (error) {
    return { status: 'failed', value: `controller: ${yesNo(controlled)}; ${describeError(error)}` };
  }
}

/**
 * How the document of this app start was served. Moving to /diag inside the app is no new
 * navigation, so this is the load the Home Screen app started with (at `/`, its start_url). A
 * navigation the service worker answered has a `workerStart` and, from the precache, usually
 * `transferSize` 0; `deliveryType` is newer and not everywhere.
 */
export function navigationLine(): ResultLine {
  const controlled = 'serviceWorker' in navigator && navigator.serviceWorker.controller !== null;
  const [first] = performance.getEntriesByType?.('navigation') ?? [];
  if (!first || !('workerStart' in first)) {
    return { status: 'info', value: `controller: ${yesNo(controlled)}; no navigation timing` };
  }
  const entry = first as PerformanceNavigationTiming & { deliveryType?: string };
  const delivery = entry.deliveryType;
  const byWorker = entry.workerStart > 0;
  return {
    status: byWorker ? 'ok' : 'info',
    value:
      `served by service worker: ${yesNo(byWorker)} (controller: ${yesNo(controlled)}, ` +
      `workerStart ${Math.round(entry.workerStart)} ms, transferSize ${entry.transferSize}, ` +
      `deliveryType ${delivery || '-'}, type ${entry.type})`,
  };
}

const IDB_NAME = 'mealmate-diag';
const IDB_STORE = 'markers';
const IDB_KEY = 'marker';
/**
 * How long `indexedDB.open` may take. Safari has been known to leave it pending forever (neither
 * success nor error), which would leave the result at "not run" instead of saying so.
 */
export const IDB_OPEN_TIMEOUT_MS = 5000;

class IdbOpenTimeout extends Error {}

/**
 * Opens the database, or rejects when it fails, is blocked by another tab or takes too long. A
 * database that opens after that is closed again at once, so it doesn't block a later open.
 */
function openMarkerDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const settle = (finish: () => void) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      finish();
    };
    const request = indexedDB.open(IDB_NAME, 1);
    const timer = setTimeout(() => settle(() => reject(new IdbOpenTimeout())), IDB_OPEN_TIMEOUT_MS);
    request.onupgradeneeded = () => request.result.createObjectStore(IDB_STORE);
    request.onsuccess = () => {
      if (settled) request.result.close();
      settle(() => resolve(request.result));
    };
    request.onerror = () =>
      settle(() => reject(request.error ?? new Error('indexedDB.open failed')));
    // Another tab holds an older version open, so the upgrade has to wait for it.
    request.onblocked = () =>
      settle(() => reject(new Error('indexedDB.open blocked by another tab')));
  });
}

/**
 * Runs `run` in a transaction. The result counts once the transaction has completed: a write is
 * only durable then, and a request can succeed in a transaction that aborts afterwards.
 */
async function markerTransaction<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await openMarkerDb();
  try {
    return await new Promise<T>((resolve, reject) => {
      const transaction = db.transaction(IDB_STORE, mode);
      const request = run(transaction.objectStore(IDB_STORE));
      const failed = () =>
        reject(transaction.error ?? request.error ?? new Error('IndexedDB transaction failed'));
      transaction.oncomplete = () => resolve(request.result);
      transaction.onerror = failed;
      transaction.onabort = failed;
    });
  } finally {
    db.close();
  }
}

function markerLine(marker: unknown): ResultLine {
  return typeof marker === 'string'
    ? { status: 'ok', value: `marker from ${marker}` }
    : { status: 'info', value: 'no marker' };
}

/** The marker in the IndexedDB database `mealmate-diag` (plain API: no dependency for M1). */
export async function readIndexedDbMarker(): Promise<ResultLine> {
  if (typeof indexedDB === 'undefined') return { status: 'failed', value: 'no IndexedDB' };
  try {
    return markerLine(await markerTransaction('readonly', (store) => store.get(IDB_KEY)));
  } catch (error) {
    return idbFailure(error);
  }
}

function idbFailure(error: unknown): ResultLine {
  return {
    status: 'failed',
    value: error instanceof IdbOpenTimeout ? 'indexedDB.open timed out' : describeError(error),
  };
}

export async function writeIndexedDbMarker(now: Date): Promise<ResultLine> {
  if (typeof indexedDB === 'undefined') return { status: 'failed', value: 'no IndexedDB' };
  try {
    await markerTransaction('readwrite', (store) => store.put(now.toISOString(), IDB_KEY));
    return readIndexedDbMarker();
  } catch (error) {
    return idbFailure(error);
  }
}

/** A device key (`mm.` but not `mm.user.`), so a logout doesn't delete it (README). */
export const LOCAL_MARKER_KEY = 'mm.diag.marker';

export function readLocalMarker(): ResultLine {
  try {
    return markerLine(localStorage.getItem(LOCAL_MARKER_KEY));
  } catch (error) {
    return { status: 'failed', value: describeError(error) };
  }
}

export function writeLocalMarker(now: Date): ResultLine {
  try {
    localStorage.setItem(LOCAL_MARKER_KEY, now.toISOString());
    return readLocalMarker();
  } catch (error) {
    return { status: 'failed', value: describeError(error) };
  }
}

const NO_STORAGE_MANAGER: ResultLine = { status: 'failed', value: 'navigator.storage is missing' };

function storageManager(): StorageManager | undefined {
  return (navigator as Navigator & { storage?: StorageManager }).storage;
}

export async function persistedLine(): Promise<ResultLine> {
  const storage = storageManager();
  if (!storage?.persisted) return NO_STORAGE_MANAGER;
  try {
    const persisted = await storage.persisted();
    return { status: persisted ? 'ok' : 'info', value: `persisted: ${String(persisted)}` };
  } catch (error) {
    return { status: 'failed', value: describeError(error) };
  }
}

export async function persistLine(): Promise<ResultLine> {
  const storage = storageManager();
  if (!storage?.persist) return NO_STORAGE_MANAGER;
  try {
    const granted = await storage.persist();
    return { status: granted ? 'ok' : 'failed', value: `persist() answered ${String(granted)}` };
  } catch (error) {
    return { status: 'failed', value: describeError(error) };
  }
}

function megabytes(bytes: number | undefined): string {
  return bytes === undefined ? '?' : `${(bytes / 1_000_000).toFixed(1)} MB`;
}

export async function estimateLine(): Promise<ResultLine> {
  const storage = storageManager();
  if (!storage?.estimate) return NO_STORAGE_MANAGER;
  try {
    const { usage, quota } = await storage.estimate();
    return { status: 'info', value: `usage ${megabytes(usage)} of quota ${megabytes(quota)}` };
  } catch (error) {
    return { status: 'failed', value: describeError(error) };
  }
}

/**
 * The camera track's settings next to the size of the frames the preview shows and the screen's
 * orientation, for the iOS 26 rotation issue (O-6): a rotated image shows as frames whose width
 * and height are swapped against the settings. The frame size is `?` until frames arrive.
 */
export function trackLine(
  track: MediaStreamTrack,
  video?: Pick<HTMLVideoElement, 'videoWidth' | 'videoHeight'> | null,
): ResultLine {
  const settings = typeof track.getSettings === 'function' ? track.getSettings() : {};
  const orientation = typeof screen.orientation === 'object' ? screen.orientation.type : '-';
  const frames = video?.videoWidth ? `${video.videoWidth}×${video.videoHeight}` : '?';
  return {
    status: 'info',
    value:
      `settings ${settings.width ?? '?'}×${settings.height ?? '?'}, frames ${frames}, ` +
      `facingMode ${settings.facingMode ?? '-'}, screen ${orientation}`,
  };
}
