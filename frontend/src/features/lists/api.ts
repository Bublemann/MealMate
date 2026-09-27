import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';
import { useAuthSession, useCurrentUser } from '@/features/auth/context';
import { FILTER_HIDDEN_KEY } from '@/features/meals/api';

export type ListDetail = components['schemas']['ListDetail'];
export type ListSummary = components['schemas']['ListSummary'];
export type ListMealEntry = components['schemas']['ListMealEntry'];
export type ListLine = components['schemas']['ListLine'];
export type LineSource = components['schemas']['LineSource'];
export type ExtraItem = components['schemas']['ExtraItem'];
export type ExtraItemCreate = components['schemas']['ExtraItemCreate'];
export type ExtraItemUpdate = components['schemas']['ExtraItemUpdate'];
export type ListUpdate = components['schemas']['ListUpdate'];
export type ListCopyResult = components['schemas']['ListCopyResult'];

/** `mine`: my drafts and my partner's shared ones; `others`: other lists I may look at (UI-02). */
export type ListScope = 'mine' | 'others';

const LISTS_KEY = ['lists'] as const;
const SUMMARIES_KEY = [...LISTS_KEY, 'summaries'] as const;
const summariesKey = (scope: ListScope) => [...SUMMARIES_KEY, scope] as const;
const detailKey = (id: string) => [...LISTS_KEY, 'detail', id] as const;
const changeKey = (id: string) => [...LISTS_KEY, 'change', id] as const;
// Below ['meals'], so everything that reloads the meals reloads these too.
const RECENT_MEALS_KEY = ['meals', 'recent'] as const;
const VISIBLE_USERS_KEY = ['users', 'visible', 'lists'] as const;

function invalidateSummaries(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: SUMMARIES_KEY });
}

/** Lists in `scope`, most recently edited first; drafts only until M5b adds shopping. */
export function useLists(scope: ListScope) {
  return useQuery({
    queryKey: summariesKey(scope),
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/lists', { params: { query: { scope } }, signal })),
  });
}

/**
 * One list with its meals and the aggregated lines, as the server computed them (AGG-01). It is
 * loaded again whenever the app comes back to the foreground, so changes made on another device
 * or by the partner show up (LIST-09; M5b adds polling).
 */
export function useList(id: string) {
  return useQuery({
    queryKey: detailKey(id),
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/lists/{list_id}', { params: { path: { list_id: id } }, signal })),
    refetchOnWindowFocus: 'always',
  });
}

/**
 * A change to list `listId` that answers with the whole list. Changes of one list run one after
 * another (scope), and only the answer to the last one is put into the cache: an earlier answer
 * would briefly undo the optimistic state of a change still waiting (e.g. several taps on +).
 * A load of the list that is still running when a change starts is cancelled, so its older answer
 * can't replace the change's. A failed change loads the list again instead of guessing.
 */
function useListChange<Variables>(
  listId: string,
  mutationFn: (variables: Variables) => Promise<ListDetail>,
  {
    optimistic,
    onSuccess,
  }: {
    /** The change as it will look, applied to the cached list right away. */
    optimistic?: (variables: Variables) => (list: ListDetail) => ListDetail;
    onSuccess?: (queryClient: QueryClient) => void;
  } = {},
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: changeKey(listId),
    scope: { id: `list-${listId}` },
    mutationFn,
    onMutate: async (variables) => {
      await queryClient.cancelQueries({ queryKey: detailKey(listId) });
      if (!optimistic) return;
      const update = optimistic(variables);
      queryClient.setQueryData<ListDetail>(detailKey(listId), (list) => list && update(list));
    },
    onSuccess: (list) => {
      // This change still counts as running here.
      if (queryClient.isMutating({ mutationKey: changeKey(listId) }) <= 1) {
        queryClient.setQueryData(detailKey(listId), list);
      }
      onSuccess?.(queryClient);
    },
    onError: () => queryClient.invalidateQueries({ queryKey: detailKey(listId) }),
    onSettled: () => invalidateSummaries(queryClient),
  });
}

/** LIST-01: a new draft, shared with the partner while in a couple (CPL-02, set by the server). */
export function useCreateList() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/lists', { body: {} })),
    onSuccess: (list) => {
      queryClient.setQueryData(detailKey(list.id), list);
      invalidateSummaries(queryClient);
    },
  });
}

/** Rename (editors, LIST-02; `name: null` goes back to the default) and share switch (owner). */
export function useUpdateList(listId: string) {
  return useListChange(listId, (body: ListUpdate) =>
    unwrap(api.PATCH('/api/lists/{list_id}', { params: { path: { list_id: listId } }, body })),
  );
}

/** LIST-13: owner only. The detail is only marked stale: its screen is left right away. */
export function useDeleteList(listId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE('/api/lists/{list_id}', { params: { path: { list_id: listId } } })),
    onSuccess: () => {
      invalidateSummaries(queryClient);
      void queryClient.invalidateQueries({ queryKey: detailKey(listId), refetchType: 'none' });
    },
  });
}

/** VIS-03: a new draft of mine with what I can see of the list; `left_out` counts the rest. */
export function useCopyList(listId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(api.POST('/api/lists/{list_id}/copy', { params: { path: { list_id: listId } } })),
    onSuccess: ({ list }) => {
      queryClient.setQueryData(detailKey(list.id), list);
      invalidateSummaries(queryClient);
    },
  });
}

export interface AddMeal {
  mealId: string;
  /** Default: the meal's own servings (LIST-04). */
  servings?: number;
}

/** LIST-03/04: a meal already on the list gets more servings instead of a second entry. */
export function useAddListMeal(listId: string) {
  return useListChange(
    listId,
    ({ mealId, servings }: AddMeal) =>
      unwrap(
        api.POST('/api/lists/{list_id}/meals', {
          params: { path: { list_id: listId } },
          body: { meal_id: mealId, ...(servings === undefined ? {} : { servings }) },
        }),
      ),
    {
      onSuccess: (queryClient) =>
        void queryClient.invalidateQueries({ queryKey: RECENT_MEALS_KEY }),
    },
  );
}

/** LIST-04: servings 1–99; the number changes at once, the lines when the server answered. */
export function useSetListMealServings(listId: string) {
  return useListChange(
    listId,
    ({ listMealId, servings }: { listMealId: string; servings: number }) =>
      unwrap(
        api.PATCH('/api/lists/{list_id}/meals/{list_meal_id}', {
          params: { path: { list_id: listId, list_meal_id: listMealId } },
          body: { servings },
        }),
      ),
    {
      optimistic:
        ({ listMealId, servings }) =>
        (list) => ({
          ...list,
          meals: list.meals.map((meal) => (meal.id === listMealId ? { ...meal, servings } : meal)),
        }),
    },
  );
}

/** Also removes detached meals ("no longer available", LIST-15). */
export function useRemoveListMeal(listId: string) {
  return useListChange(listId, (listMealId: string) =>
    unwrap(
      api.DELETE('/api/lists/{list_id}/meals/{list_meal_id}', {
        params: { path: { list_id: listId, list_meal_id: listMealId } },
      }),
    ),
  );
}

/**
 * LIST-06: a linked or free-text extra item. Its id comes with it (made by the input, which keeps
 * it while the item is sent again), so a retry after a lost answer doesn't add it twice.
 */
export function useAddExtraItem(listId: string) {
  return useListChange(listId, (body: ExtraItemCreate) =>
    unwrap(
      api.POST('/api/lists/{list_id}/extra-items', {
        params: { path: { list_id: listId } },
        body,
      }),
    ),
  );
}

export function useUpdateExtraItem(listId: string) {
  return useListChange(listId, ({ extraId, body }: { extraId: string; body: ExtraItemUpdate }) =>
    unwrap(
      api.PATCH('/api/lists/{list_id}/extra-items/{extra_id}', {
        params: { path: { list_id: listId, extra_id: extraId } },
        body,
      }),
    ),
  );
}

export function useRemoveExtraItem(listId: string) {
  return useListChange(listId, (extraId: string) =>
    unwrap(
      api.DELETE('/api/lists/{list_id}/extra-items/{extra_id}', {
        params: { path: { list_id: listId, extra_id: extraId } },
      }),
    ),
  );
}

/** LIST-07: removes a line for this list only, or restores it; it moves at once. */
export function useSetLineHidden(listId: string) {
  return useListChange(
    listId,
    ({ key, hidden }: { key: string; hidden: boolean }) => {
      const params = { path: { list_id: listId, line_key: key } };
      return unwrap(
        hidden
          ? api.POST('/api/lists/{list_id}/lines/{line_key}/hide', { params })
          : api.POST('/api/lists/{list_id}/lines/{line_key}/unhide', { params }),
      );
    },
    {
      optimistic:
        ({ key, hidden }) =>
        (list) => ({
          ...list,
          lines: list.lines.map((line) => (line.key === key ? { ...line, hidden } : line)),
        }),
    },
  );
}

/** MEAL-09: meals I added to lists lately, for the top of the meal picker. */
export function useRecentMeals({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: RECENT_MEALS_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/meals/recent', { signal })),
    enabled,
  });
}

/** Everyone whose lists I can see, me first (UI-02, VIS-02). */
export function useListUsers() {
  return useQuery({
    queryKey: VISIBLE_USERS_KEY,
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/users/visible', { params: { query: { for: 'lists' } }, signal })),
  });
}

/**
 * Switches a user's chip on Others' lists (UI-02), like the meal chips (MEAL-10): at once on
 * screen, saved in `filter_hidden.lists`, and the lists load again once it is saved. The saved
 * state only replaces the chips once no other toggle is waiting. When saving fails, the profile
 * and the lists are loaded again instead of going back to a snapshot.
 */
export function useToggleListChip() {
  const session = useAuthSession();
  const user = useCurrentUser();
  const queryClient = useQueryClient();
  const reloadOthers = () =>
    void queryClient.invalidateQueries({ queryKey: summariesKey('others') });
  return useMutation({
    // The same key and scope as the meal chips: each save sends both lists of hidden users.
    mutationKey: FILTER_HIDDEN_KEY,
    scope: { id: FILTER_HIDDEN_KEY.join('-') },
    mutationFn: (hidden: string[]) =>
      unwrap(
        api.PATCH('/api/me', {
          body: {
            filter_hidden: {
              meals: session.getState().user?.filter_hidden.meals ?? [],
              lists: hidden,
            },
          },
        }),
      ),
    onMutate: (hidden) => {
      const current = session.getState().user ?? user;
      session.setUser({ ...current, filter_hidden: { ...current.filter_hidden, lists: hidden } });
    },
    onError: async () => {
      reloadOthers();
      try {
        session.setUser(await unwrap(api.GET('/api/me')));
      } catch {
        // Offline: the chips stay as they are until the next successful load.
      }
    },
    onSuccess: (me) => {
      // This save still counts as running here.
      if (queryClient.isMutating({ mutationKey: FILTER_HIDDEN_KEY }) <= 1) session.setUser(me);
      reloadOthers();
    },
  });
}
