import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';
import { useAuthSession } from '@/features/auth/context';

type MeUpdate = components['schemas']['MeUpdate'];
type PasswordChange = components['schemas']['PasswordChange'];
export type SessionInfo = components['schemas']['SessionInfo'];
export type SystemInfo = components['schemas']['SystemInfo'];

const SESSIONS_KEY = ['me', 'sessions'] as const;

/** The running version and the link to its exact source revision (LIC-02). */
export function useVersionInfo() {
  return useQuery({
    queryKey: ['version'],
    queryFn: ({ signal }) => unwrap(api.GET('/api/version', { signal })),
    // A new version arrives with a reload (service-worker update), never while running.
    staleTime: Infinity,
  });
}

/** The admin system info's key, which a requested backup refreshes. */
export const SYSTEM_KEY = ['admin', 'system'] as const;

/**
 * ADM-01: version, and the last backup and free disk space as the server last reported them,
 * for admins only. Here rather than in the admin api, so that the System row on the Settings tab
 * shares the System page's cache entry without loading the admin chunk (PERF-03).
 */
export function useSystemInfo() {
  return useQuery({
    queryKey: SYSTEM_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/admin/system', { signal })),
  });
}

/** Loads the profile when the Settings tab opens, so changes made on another device show up. */
export function useMeRefresh() {
  const session = useAuthSession();
  return useQuery({
    queryKey: ['me'],
    queryFn: async ({ signal }) => {
      const me = await unwrap(api.GET('/api/me', { signal }));
      session.setUser(me);
      return me;
    },
  });
}

/** Changes display name, language or privacy switches (ACC-13, VIS-02, I18N-01). */
export function useUpdateMe() {
  const session = useAuthSession();
  return useMutation({
    mutationFn: (body: MeUpdate) => unwrap(api.PATCH('/api/me', { body })),
    onSuccess: (me) => session.setUser(me),
  });
}

/** Changes the password; the server logs out every other device (ACC-09). */
export function useChangePassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PasswordChange) => unwrap(api.POST('/api/me/password', { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: SESSIONS_KEY }),
  });
}

export function useSessions() {
  return useQuery({
    queryKey: SESSIONS_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/me/sessions', { signal })),
  });
}

export function useRevokeSession() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) =>
      unwrap(
        api.DELETE('/api/me/sessions/{session_id}', {
          params: { path: { session_id: sessionId } },
        }),
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: SESSIONS_KEY }),
  });
}

/** Password changes and resets, for the notice in Settings → Security (ACC-10). */
export function useSecurityInfo() {
  return useQuery({
    queryKey: ['me', 'security'],
    queryFn: ({ signal }) => unwrap(api.GET('/api/me/security', { signal })),
  });
}

export function useLogoutAll() {
  const session = useAuthSession();
  return useMutation({ mutationFn: () => session.logoutAll() });
}
