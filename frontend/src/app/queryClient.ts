import { QueryClient } from '@tanstack/react-query';
import { isApiError } from '@/api/errors';

/** Retries once for timeouts, network failures and server errors, never for 4xx answers. */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (failureCount >= 1) return false;
  return !isApiError(error) || error.status === 0 || error.status >= 500;
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: shouldRetry,
        // Always send the request, also when the browser reports being offline: the client's
        // timeout and network errors then show "can't reach MealMate" (SYNC-09). In the default
        // mode queries pause instead and the screen would stay on "Loading…".
        networkMode: 'always',
      },
    },
  });
}
