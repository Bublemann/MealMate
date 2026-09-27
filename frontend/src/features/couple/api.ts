import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';

export type CoupleState = components['schemas']['CoupleState'];
export type CoupleRequest = components['schemas']['CoupleRequest'];
export type UserRef = components['schemas']['UserRef'];
export type RequestAction = 'accept' | 'decline' | 'cancel';

const COUPLE_KEY = ['couple'] as const;

export function useCouple() {
  return useQuery({
    queryKey: COUPLE_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/couple', { signal })),
  });
}

/** All active users except me, by display name (CPL-01 picker). */
export function useUsers() {
  return useQuery({
    queryKey: ['users'],
    queryFn: ({ signal }) => unwrap(api.GET('/api/users', { signal })),
  });
}

export function useSendCoupleRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (userId: string) =>
      unwrap(api.POST('/api/couple/requests', { body: { user_id: userId } })),
    onSuccess: (state) => queryClient.setQueryData(COUPLE_KEY, state),
  });
}

export function useAnswerCoupleRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ requestId, action }: { requestId: string; action: RequestAction }) => {
      const params = { path: { request_id: requestId } };
      switch (action) {
        case 'accept':
          return unwrap(api.POST('/api/couple/requests/{request_id}/accept', { params }));
        case 'decline':
          return unwrap(api.POST('/api/couple/requests/{request_id}/decline', { params }));
        case 'cancel':
          return unwrap(api.POST('/api/couple/requests/{request_id}/cancel', { params }));
      }
    },
    onSuccess: (state) => queryClient.setQueryData(COUPLE_KEY, state),
    // Another request may have been answered meanwhile (e.g. the target is now in a couple).
    onError: () => queryClient.invalidateQueries({ queryKey: COUPLE_KEY }),
  });
}

export function useEndCouple() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.DELETE('/api/couple')),
    onSettled: () => queryClient.invalidateQueries({ queryKey: COUPLE_KEY }),
  });
}
