import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';
import { INGREDIENTS_KEY } from '@/features/ingredients/api';
import { LISTS_KEY } from '@/features/lists/keys';
import { CATEGORIES_KEY, type Category } from '@/features/reference/api';
import { notDeletedCategories } from '@/features/reference/categories';

export type AdminUser = components['schemas']['AdminUser'];
export type AdminUserUpdate = components['schemas']['AdminUserUpdate'];
export type Invite = components['schemas']['Invite'];
export type AdminEvent = components['schemas']['AdminEvent'];
export type SystemInfo = components['schemas']['SystemInfo'];
export type BackupStatus = components['schemas']['BackupStatus'];
export type DiskStatus = components['schemas']['DiskStatus'];
export type CategoryNames = components['schemas']['CategoryNames'];

const USERS_KEY = ['admin', 'users'] as const;
const INVITES_KEY = ['admin', 'invites'] as const;
const EVENTS_KEY = ['admin', 'events'] as const;
const SYSTEM_KEY = ['admin', 'system'] as const;
// Changes to the categories are sent one after another, in the order they were made, also after
// the screen has closed (ADM-01): no change overtakes another, so a new category never arrives
// before an order that doesn't name it yet.
const CATEGORIES_SCOPE = { id: 'admin-categories' };

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

/**
 * REF-01: the store's walking order; the answer is the new order of every category. A failed
 * order loads the categories again, in case another admin changed them meanwhile.
 */
export function useReorderCategories() {
  const queryClient = useQueryClient();
  return useMutation({
    scope: CATEGORIES_SCOPE,
    mutationFn: (categoryIds: string[]) => {
      // A category added after the tap was saved before this order (the scope): it stays last.
      // Deleted categories are no longer in the order (D-30).
      const added = notDeletedCategories(queryClient.getQueryData<Category[]>(CATEGORIES_KEY) ?? [])
        .map(({ id }) => id)
        .filter((id) => !categoryIds.includes(id));
      return unwrap(
        api.PUT('/api/admin/categories/order', {
          body: { category_ids: [...categoryIds, ...added] },
        }),
      );
    },
    onSuccess: async (categories) => {
      // A reload after an earlier failure must not overwrite this newer order.
      await queryClient.cancelQueries({ queryKey: CATEGORIES_KEY });
      queryClient.setQueryData(CATEGORIES_KEY, categories);
      void queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
    },
    onError: () => {
      // Not awaited: the screen puts the order back at once.
      void queryClient.invalidateQueries({ queryKey: CATEGORIES_KEY });
    },
  });
}

/** REF-01: a new category with both names; it goes last in the walking order. */
export function useCreateCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    scope: CATEGORIES_SCOPE,
    mutationFn: (names: CategoryNames) =>
      unwrap(api.POST('/api/admin/categories', { body: { names } })),
    onSuccess: async (category) => {
      // A reload after a failed order must not overwrite the new category.
      await queryClient.cancelQueries({ queryKey: CATEGORIES_KEY });
      queryClient.setQueryData<Category[]>(
        CATEGORIES_KEY,
        (categories) => categories && [...categories, category],
      );
      void queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
    },
  });
}

/** REF-01: new names for a category, seeded ones included; every list shows them. */
export function useRenameCategory(categoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    scope: CATEGORIES_SCOPE,
    mutationFn: (names: CategoryNames) =>
      unwrap(
        api.PATCH('/api/admin/categories/{category_id}', {
          params: { path: { category_id: categoryId } },
          body: { names },
        }),
      ),
    onSuccess: async (category) => {
      // A reload after a failed order must not overwrite the new names.
      await queryClient.cancelQueries({ queryKey: CATEGORIES_KEY });
      queryClient.setQueryData<Category[]>(CATEGORIES_KEY, (categories) =>
        categories?.map((existing) => (existing.id === category.id ? category : existing)),
      );
      void queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
    },
  });
}

/** ADM-01: what deleting a category would move, for the confirmation; loaded once it opens. */
export function useCategoryUsage(categoryId: string, { enabled }: { enabled: boolean }) {
  return useQuery({
    queryKey: ['admin', 'categories', categoryId, 'usage'],
    queryFn: ({ signal }) =>
      unwrap(
        api.GET('/api/admin/categories/{category_id}/usage', {
          params: { path: { category_id: categoryId } },
          signal,
        }),
      ),
    enabled,
    // The counts change whenever someone edits an ingredient or a list.
    staleTime: 0,
  });
}

/**
 * REF-01: deletes a category. Its ingredients move to *Uncategorized* and its free-text items on
 * drafts to *Other*, so the categories, the ingredients and the lists are loaded again. Until the
 * categories are back, the cached one is marked as deleted: lists being shopped and done lists
 * still name it (D-30), but pickers and the order no longer offer it.
 */
export function useDeleteCategory(categoryId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    scope: CATEGORIES_SCOPE,
    mutationFn: () =>
      unwrap(
        api.DELETE('/api/admin/categories/{category_id}', {
          params: { path: { category_id: categoryId } },
        }),
      ),
    onSuccess: async () => {
      // A reload after a failed order must not bring the category back.
      await queryClient.cancelQueries({ queryKey: CATEGORIES_KEY });
      queryClient.setQueryData<Category[]>(CATEGORIES_KEY, (categories) =>
        categories?.map((existing) =>
          existing.id === categoryId ? { ...existing, deleted: true } : existing,
        ),
      );
      for (const queryKey of [CATEGORIES_KEY, INGREDIENTS_KEY, LISTS_KEY, EVENTS_KEY]) {
        void queryClient.invalidateQueries({ queryKey });
      }
    },
  });
}

/** ADM-01: version, and the last backup and free disk space as the server last reported them. */
export function useSystemInfo() {
  return useQuery({
    queryKey: SYSTEM_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/admin/system', { signal })),
  });
}

/** OPS-08: asks the server for a backup now; it starts within a minute. */
export function useRequestBackup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/admin/backup')),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: SYSTEM_KEY });
      void queryClient.invalidateQueries({ queryKey: EVENTS_KEY });
    },
  });
}
