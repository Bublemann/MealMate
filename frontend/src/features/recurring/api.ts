import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';

export type RecurringItem = components['schemas']['RecurringItem'];
export type RecurringItemList = components['schemas']['RecurringItemList'];
export type Notice = components['schemas']['Notice'];
export type NoticeList = components['schemas']['NoticeList'];
export type RecurringItemUpdate = components['schemas']['RecurringItemUpdate'];

/**
 * A new recurring item as the pop-up makes it. The server's create has no `automatic` (a new item
 * adapts from its second purchase on); turned off, a second request sets the interval by hand.
 */
export type NewRecurringItem = components['schemas']['RecurringItemCreate'] & {
  automatic: boolean;
};

export const RECURRING_KEY = ['recurring-items'] as const;
export const NOTICES_KEY = ['me', 'notices'] as const;

/**
 * The caller's set of recurring items (LIST-16), in the server's order (due first): one cache
 * entry for the page "Regelmäßige Artikel", its row on the Settings tab and the ingredient's ⋯
 * menu, so they always agree.
 */
export const recurringQuery = queryOptions({
  queryKey: RECURRING_KEY,
  queryFn: ({ signal }) => unwrap(api.GET('/api/recurring-items', { signal })),
});

/**
 * The caller's unread notices (D-51), newest first: one cache entry for the page, its row and
 * the count on the Settings tab's gear.
 */
export const noticesQuery = queryOptions({
  queryKey: NOTICES_KEY,
  queryFn: ({ signal }) => unwrap(api.GET('/api/me/notices', { signal })),
});

export function useRecurringItems() {
  return useQuery(recurringQuery);
}

export function useNotices() {
  return useQuery(noticesQuery);
}

/** The item of `ingredientId` in the set, if the ingredient is recurring already. */
export function itemOf(
  list: RecurringItemList | undefined,
  ingredientId: string,
): RecurringItem | undefined {
  return list?.items.find((item) => item.ingredient.id === ingredientId);
}

/**
 * Every change of the set loads it again, whatever the answer: the server sorts it and counts what
 * is due, also when the second request of a create failed after the first one made the item.
 */
function useRefreshSet() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: RECURRING_KEY });
}

export function useCreateRecurringItem() {
  const refresh = useRefreshSet();
  return useMutation({
    mutationFn: async ({ automatic, ...body }: NewRecurringItem) => {
      const item = await unwrap(api.POST('/api/recurring-items', { body }));
      if (automatic) return item;
      return unwrap(
        api.PATCH('/api/recurring-items/{item_id}', {
          params: { path: { item_id: item.id } },
          body: { automatic: false },
        }),
      );
    },
    onSettled: refresh,
  });
}

/** Sends only the fields that changed (`RecurringItemUpdate`). */
export function useUpdateRecurringItem(id: string) {
  const refresh = useRefreshSet();
  return useMutation({
    mutationFn: (body: RecurringItemUpdate) =>
      unwrap(
        api.PATCH('/api/recurring-items/{item_id}', { params: { path: { item_id: id } }, body }),
      ),
    onSettled: refresh,
  });
}

/** "Nicht mehr regelmäßig". */
export function useDeleteRecurringItem(id: string) {
  const refresh = useRefreshSet();
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE('/api/recurring-items/{item_id}', { params: { path: { item_id: id } } })),
    onSettled: refresh,
  });
}

/** The unread notices that count on the Settings tab's gear (D-51). */
export function unreadNotices(list: NoticeList): number {
  return list.count;
}

/**
 * Marks a notice as read for this user only (D-51). The answer has no body, so the notice leaves
 * the cache at once: the page, its row and the gear's count drop without waiting for a reload.
 */
export function useDismissNotice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      unwrap(
        api.POST('/api/me/notices/{notice_id}/dismiss', { params: { path: { notice_id: id } } }),
      ),
    onSuccess: (_, id) => {
      queryClient.setQueryData<NoticeList>(NOTICES_KEY, (list) => {
        if (!list) return list;
        const notices = list.notices.filter((notice) => notice.id !== id);
        return { notices, count: list.count - (list.notices.length - notices.length) };
      });
      void queryClient.invalidateQueries({ queryKey: NOTICES_KEY });
    },
  });
}
