import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';
import { LISTS_KEY } from '@/features/lists/keys';

export type WalkingOrder = components['schemas']['WalkingOrder'];
export type WalkingOrderCategory = components['schemas']['WalkingOrderCategory'];

export const WALKING_ORDER_KEY = ['walking-order'] as const;
// Saves and "follow the admins" go out one after another, in the order they were made.
const WALKING_ORDER_SCOPE = { id: 'walking-order' };

/**
 * The caller's walking order (REF-01, D-48): their couple's while in one, else their own; the
 * admins' one while `follows_admin`.
 */
export const walkingOrderQuery = queryOptions({
  queryKey: WALKING_ORDER_KEY,
  queryFn: ({ signal }) => unwrap(api.GET('/api/walking-order', { signal })),
});

export function useWalkingOrder() {
  return useQuery(walkingOrderQuery);
}

/** The lists are grouped in the viewer's order: the ones in the cache load again. */
function useRefreshLists() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: [...LISTS_KEY, 'detail'] });
}

interface OrderSave {
  categoryIds: string[];
  /** The category the user moved, no longer new; none when the switch was turned off. */
  movedId?: string;
}

/**
 * Keeps an order as the own one, which stops following the admins' (D-48). The answer is the
 * order as saved; a failed save loads it again, in case the partner changed it meanwhile.
 */
export function useSaveWalkingOrder() {
  const queryClient = useQueryClient();
  const refreshLists = useRefreshLists();
  return useMutation({
    scope: WALKING_ORDER_SCOPE,
    mutationFn: ({ categoryIds, movedId }: OrderSave) =>
      unwrap(
        api.PUT('/api/walking-order', {
          body: { category_ids: categoryIds, ...(movedId ? { moved_id: movedId } : {}) },
        }),
      ),
    onSuccess: async (order) => {
      // A reload after an earlier failure must not overwrite this newer order.
      await queryClient.cancelQueries({ queryKey: WALKING_ORDER_KEY });
      queryClient.setQueryData(WALKING_ORDER_KEY, order);
      void refreshLists();
    },
    onError: () => {
      // Not awaited: the screen puts the order back at once.
      void queryClient.invalidateQueries({ queryKey: WALKING_ORDER_KEY });
    },
  });
}

/** "Reihenfolge der Verwaltung übernehmen" back on: the own order goes (D-48). */
export function useFollowAdminOrder() {
  const queryClient = useQueryClient();
  const refreshLists = useRefreshLists();
  return useMutation({
    scope: WALKING_ORDER_SCOPE,
    mutationFn: () => unwrap(api.DELETE('/api/walking-order')),
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: WALKING_ORDER_KEY });
      void refreshLists();
    },
  });
}
