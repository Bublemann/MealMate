/**
 * Navigations the service worker never answers with the app shell: the API, including the bare
 * `/api`, which the backend answers with a JSON 404. Workbox's NavigationRoute matches these
 * against the pathname plus query string.
 */
export const NAVIGATION_DENYLIST: readonly RegExp[] = [/^\/api(?:[/?]|$)/];
