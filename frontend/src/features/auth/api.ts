import { useMutation, useQuery } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';
import { useAuthSession } from './context';

type LoginRequest = components['schemas']['LoginRequest'];
type JoinRequest = components['schemas']['JoinRequest'];
type ResetRequest = components['schemas']['ResetRequest'];
export type CodeKind = components['schemas']['CodeInfo']['kind'];

export function useLogin() {
  const session = useAuthSession();
  return useMutation({
    mutationFn: (body: LoginRequest) => unwrap(api.POST('/api/auth/login', { body })),
    onSuccess: (data) => session.signIn(data),
  });
}

export function useJoin() {
  const session = useAuthSession();
  return useMutation({
    mutationFn: (body: JoinRequest) => unwrap(api.POST('/api/auth/join', { body })),
    onSuccess: (data) => session.signIn(data),
  });
}

export function useResetPassword() {
  const session = useAuthSession();
  return useMutation({
    mutationFn: (body: ResetRequest) => unwrap(api.POST('/api/auth/reset', { body })),
    onSuccess: (data) => session.signIn(data),
  });
}

/** Logs out on the server, then locally (rejects, keeping the user signed in, if unreachable). */
export function useLogout() {
  const session = useAuthSession();
  return useMutation({ mutationFn: () => session.logout() });
}

/** Checks an invite or reset code without consuming it (ACC-04). */
export function useCodeCheck(code: string | null) {
  return useQuery({
    queryKey: ['auth', 'code', code],
    queryFn: ({ signal }) =>
      unwrap(api.POST('/api/auth/codes/check', { body: { code: code ?? '' }, signal })),
    enabled: code !== null,
    retry: false,
    staleTime: Infinity,
  });
}
