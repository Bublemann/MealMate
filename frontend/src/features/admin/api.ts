import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';
import { CATEGORIES_KEY } from '@/features/reference/api';

export type AdminUser = components['schemas']['AdminUser'];
export type AdminUserUpdate = components['schemas']['AdminUserUpdate'];
export type Invite = components['schemas']['Invite'];
export type AdminEvent = components['schemas']['AdminEvent'];

const USERS_KEY = ['admin', 'users'] as const;
const INVITES_KEY = ['admin', 'invites'] as const;
const EVENTS_KEY = ['admin', 'events'] as const;

export function useAdminUsers() {
  return useQuery({
    queryKey: USERS_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/admin/users', { signal })),
  });
}

/** Role change, deactivation and reactivation (ADM-01, ADM-02). */
export function useUpdateUser(userId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AdminUserUpdate) =>
      unwrap(
        api.PATCH('/api/admin/users/{user_id}', { params: { path: { user_id: userId } }, body }),
      ),
    onSuccess: (user) => {
      queryClient.setQueryData<AdminUser[]>(USERS_KEY, (users) =>
        users?.map((existing) => (existing.id === user.id ? user : existing)),
      );
      void queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
    },
  });
}

/** ADM-03 */
export function useDeleteUser(userId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE('/api/admin/users/{user_id}', { params: { path: { user_id: userId } } })),
    onSuccess: () => {
      queryClient.setQueryData<AdminUser[]>(USERS_KEY, (users) =>
        users?.filter((user) => user.id !== userId),
      );
      void queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
    },
  });
}

/** ACC-10: a single-use link that sets a new password and ends the user's sessions. */
export function useCreateResetLink(userId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/admin/users/{user_id}/reset-link', {
          params: { path: { user_id: userId } },
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: EVENTS_KEY }),
  });
}

export function useInvites() {
  return useQuery({
    queryKey: INVITES_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/admin/invites', { signal })),
  });
}

/** ACC-02/03: the link is only returned now; the server keeps just a hash of the code. */
export function useCreateInvite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (tailscaleShareUrl: string | null) =>
      unwrap(api.POST('/api/admin/invites', { body: { tailscale_share_url: tailscaleShareUrl } })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: INVITES_KEY });
      void queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
    },
  });
}

export function useRevokeInvite() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (inviteId: string) =>
      unwrap(
        api.DELETE('/api/admin/invites/{invite_id}', { params: { path: { invite_id: inviteId } } }),
      ),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: INVITES_KEY });
      void queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
    },
  });
}

export function useAdminEvents() {
  return useQuery({
    queryKey: EVENTS_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/admin/events', { signal })),
  });
}

/** REF-01: the store's walking order; the answer is the new order of every category. */
export function useReorderCategories() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (categoryIds: string[]) =>
      unwrap(api.PUT('/api/admin/categories/order', { body: { category_ids: categoryIds } })),
    onSuccess: (categories) => {
      queryClient.setQueryData(CATEGORIES_KEY, categories);
      void queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
    },
  });
}
