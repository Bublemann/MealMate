import { useQueries } from '@tanstack/react-query';
import { coupleQuery, waitingRequests } from '@/features/couple/api';
import { noticesQuery, unreadNotices } from '@/features/recurring/api';

/** While the app is visible the count is checked this often, never in the background (D-51). */
const CHECK_INTERVAL_MS = 60_000;

/**
 * The sources of the count on the Settings tab's gear (UI-07, D-51): what waits for the user to
 * act on. Each is one entry: what to load (the query its page and row use, so they share one cache
 * entry) and how to count it (`select`). A spec adds a source here; the tab bar stays as it is. Due recurring items are no source: every draft shows them already.
 */
const COUNT_SOURCES = [
  { ...coupleQuery, select: waitingRequests },
  { ...noticesQuery, select: unreadNotices },
];

/**
 * The count on the gear: the sum of its sources, loaded with the app shell once signed in. It is
 * loaded again when the app returns to the foreground with data older than the usual 30 s (the
 * query library's focus refetch), and every 60 s while visible. Offline or after a failed refresh
 * it keeps the last count; before the first answer it is 0.
 */
export function useSettingsCount(): number {
  return useQueries({
    queries: COUNT_SOURCES.map((source) => ({
      ...source,
      refetchInterval: CHECK_INTERVAL_MS,
      refetchIntervalInBackground: false,
    })),
    combine: (results) => results.reduce((sum, { data }) => sum + (data ?? 0), 0),
  });
}
