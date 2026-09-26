import { useQuery } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';

/** The running version and the link to its exact source revision (LIC-02). */
export function useVersionInfo() {
  return useQuery({
    queryKey: ['version'],
    queryFn: ({ signal }) => unwrap(api.GET('/api/version', { signal })),
    // A new version arrives with a reload (service-worker update), never while running.
    staleTime: Infinity,
  });
}
