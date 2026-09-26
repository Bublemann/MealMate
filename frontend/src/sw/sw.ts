/// <reference lib="webworker" />
import { clientsClaim } from 'workbox-core';
import {
  cleanupOutdatedCaches,
  createHandlerBoundToURL,
  precacheAndRoute,
  type PrecacheEntry,
} from 'workbox-precaching';
import { NavigationRoute, registerRoute } from 'workbox-routing';
import { NAVIGATION_DENYLIST } from './navigation';

declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: (PrecacheEntry | string)[];
};

// The update prompt asks the waiting worker to take over (see src/app/UpdatePrompt.tsx).
self.addEventListener('message', (event) => {
  if ((event.data as { type?: unknown } | null)?.type === 'SKIP_WAITING') {
    void self.skipWaiting();
  }
});

// The app shell (index.html, JS, CSS, icons, translations) is served from the precache.
// Nothing under /api is ever cached: the manifest only lists build output.
precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

// Navigations open the precached shell instantly, even on lie-fi; /api is never handled.
registerRoute(
  new NavigationRoute(createHandlerBoundToURL('/index.html'), {
    denylist: [...NAVIGATION_DENYLIST],
  }),
);

clientsClaim();
