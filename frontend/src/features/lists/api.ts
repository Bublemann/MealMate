import {
  replaceEqualDeep,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import { ApiError, isApiError } from '@/api/errors';
import type { components } from '@/api/generated/schema';
import { useSyncEngine } from '@/features/sync/context';
import { uuidv7 } from '@/lib/uuid';
import { detailKey, FEED_KEY } from './keys';

export { isUnreachable } from '@/api/errors';

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
export type LineNeedsMore = components['schemas']['LineNeedsMore'];
export type Op = components['schemas']['Op'];
export type ExtraAddPayload = Extract<Op, { type: 'extra.add' }>['payload'];
export type ExtraUpdatePayload = Extract<Op, { type: 'extra.update' }>['payload'];

/** SYNC-08: a list on screen is loaded again this often (ms), while the app is visible. */
export const POLL_INTERVAL_MS = 5_000;

const changeKey = (id: string) => ['lists', 'change', id] as const;
const RECENT_MEALS_KEY = ['meals', 'recent'] as const;

function invalidateFeed(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: FEED_KEY });
}

/**
 * The list feed (UI-02): every list I can see, in every state, newest created first, 30 per page
 * (`fetchNextPage` loads the next). Until the server answers, the first page is the local copy
 * (SYNC-09); it holds only my editable drafts and lists being shopped, so it is always asked for.
 */
export function useListFeed() {
  const engine = useSyncEngine();
  return useInfiniteQuery({
    queryKey: FEED_KEY,
    queryFn: ({ pageParam, signal }) =>
      unwrap(
        api.GET('/api/lists', {
          params: { query: pageParam === null ? {} : { cursor: pageParam } },
          signal,
        }),
      ),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor,
    initialData: () => engine.copiedFeed(),
    initialDataUpdatedAt: 0,
  });
}

/**
 * Whether the feed still shows the local copy, which the server's first page hasn't replaced yet
 * (SYNC-09): the copy goes into the cache as loaded at time 0, so that the feed is asked for.
 */
export function showsLocalCopy(feed: { dataUpdatedAt: number }): boolean {
  return feed.dataUpdatedAt === 0;
}

/**
 * Changes per list that wait for their answer (their optimistic state is on screen). While there
 * are any, a load of the list that answers is ignored: it may predate them and undo what is shown.
 * Counted per query client, which holds the cache they protect.
 */
const waitingChanges = new WeakMap<QueryClient, Map<string, number>>();

function waitingFor(queryClient: QueryClient): Map<string, number> {
  let waiting = waitingChanges.get(queryClient);
  if (!waiting) {
    waiting = new Map();
    waitingChanges.set(queryClient, waiting);
  }
  return waiting;
}

function changeStarted(queryClient: QueryClient, listId: string) {
  const waiting = waitingFor(queryClient);
  waiting.set(listId, (waiting.get(listId) ?? 0) + 1);
}

/** Returns how many changes of the list still wait for their answer after this one. */
function changeAnswered(queryClient: QueryClient, listId: string): number {
  const waiting = waitingFor(queryClient);
  const left = Math.max(0, (waiting.get(listId) ?? 0) - 1);
  if (left === 0) waiting.delete(listId);
  else waiting.set(listId, left);
  return left;
}

/**
 * The ETag each loaded list came with, by the object in the cache (SYNC-08). A list put into the
 * cache by a change has none, so the next load fetches it in full.
 */
const etags = new WeakMap<object, string>();

/** Structural sharing that keeps the ETag with the object that ends up in the cache. */
function shareWithEtag(previous: unknown, next: unknown): unknown {
  const shared = replaceEqualDeep(previous, next);
  const etag = typeof next === 'object' && next !== null ? etags.get(next) : undefined;
  if (etag && typeof shared === 'object' && shared !== null) etags.set(shared, etag);
  return shared;
}

/**
 * Loads a list, sending the ETag of the cached copy: an unchanged list answers 304 and the copy
 * stays (SYNC-08). An answer that arrives while changes of the list wait for theirs, or that is
 * older (lower `version`) than the cached copy, is ignored, so polling never undoes a change.
 */
async function loadList(
  queryClient: QueryClient,
  id: string,
  signal: AbortSignal,
): Promise<ListDetail> {
  const cached = queryClient.getQueryData<ListDetail>(detailKey(id));
  const etag = cached ? etags.get(cached) : undefined;
  const { data, error, response } = await api.GET('/api/lists/{list_id}', {
    params: { path: { list_id: id }, header: etag ? { 'if-none-match': etag } : {} },
    signal,
  });
  const current = queryClient.getQueryData<ListDetail>(detailKey(id));
  if (response.status === 304 && current) return current;
  if (!response.ok || !data) throw ApiError.fromResponse(response.status, error);
  const changing = (waitingFor(queryClient).get(id) ?? 0) > 0;
  if (current && (changing || data.version < current.version)) {
    return current;
  }
  const received = response.headers.get('ETag');
  if (received) etags.set(data, received);
  return data;
}

/** The list is gone or no longer mine to see: asking again every few seconds won't help. */
function isFinal(error: unknown): boolean {
  return isApiError(error) && error.status >= 400 && error.status < 500;
}

/**
 * One list with its meals and the aggregated lines, as the server computed them (AGG-01). While
 * it is on screen and the app is visible it is checked for changes every 5 seconds, and at once
 * when the app comes back to the foreground (SYNC-08, LIST-09). Until the server answers, the
 * local copy is shown, and it stays when the server can't be reached (SYNC-09). The view layers
 * the user's waiting ops on top (`usePendingList`).
 */
export function useList(id: string) {
  const queryClient = useQueryClient();
  const engine = useSyncEngine();
  return useQuery({
    queryKey: detailKey(id),
    queryFn: ({ signal }) => loadList(queryClient, id, signal),
    initialData: () => engine.copied(id),
    initialDataUpdatedAt: () => engine.copiedAt(id),
    refetchOnWindowFocus: 'always',
    refetchInterval: (query) => (isFinal(query.state.error) ? false : POLL_INTERVAL_MS),
    structuralSharing: shareWithEtag,
  });
}

/**
 * What makes an action one op (SYNC-05/06): a UUIDv7 and the time of the tap, made when the user
 * acts, not when the op is sent (it may wait in the outbox for a long time). Sending it again
 * keeps both, so the server applies it once.
 */
export interface OpStamp {
  opId: string;
  /** ISO time of the tap. */
  at: string;
}

/** A new stamp for an action the user takes now. */
export function stampOp(): OpStamp {
  return { opId: uuidv7(), at: new Date().toISOString() };
}

/**
 * A change to list `listId` that answers with the whole list. Changes of one list run one after
 * another (scope), and only the answer to the last one is put into the cache: an earlier answer
 * would briefly undo the optimistic state of a change still waiting (e.g. several taps on +).
 * A load of the list that is still running when a change starts is cancelled, and loads that
 * answer while changes wait are ignored, so an older answer can't replace the change's.
 * A failed change is undone by loading the list again instead of guessing.
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
  const update = (change: (list: ListDetail) => ListDetail) =>
    queryClient.setQueryData<ListDetail>(detailKey(listId), (list) => list && change(list));
  return useMutation({
    mutationKey: changeKey(listId),
    scope: { id: `list-${listId}` },
    mutationFn,
    onMutate: async (variables) => {
      changeStarted(queryClient, listId);
      await queryClient.cancelQueries({ queryKey: detailKey(listId) });
      if (optimistic) update(optimistic(variables));
    },
    onSuccess: (list) => {
      if (changeAnswered(queryClient, listId) === 0)
        queryClient.setQueryData(detailKey(listId), list);
      onSuccess?.(queryClient);
    },
    onError: () => {
      changeAnswered(queryClient, listId);
      void queryClient.invalidateQueries({ queryKey: detailKey(listId) });
    },
    onSettled: () => invalidateFeed(queryClient),
  });
}

/** LIST-01: a new draft, shared with the partner while in a couple (CPL-02, set by the server). */
export function useCreateList() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST('/api/lists', { body: {} })),
    onSuccess: (list) => {
      queryClient.setQueryData(detailKey(list.id), list);
      invalidateFeed(queryClient);
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
      invalidateFeed(queryClient);
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
      invalidateFeed(queryClient);
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
 * it while the item is sent again), so a retry after a lost answer doesn't add it twice. While
 * shopping, a free-text item is an `extra.add` op of the outbox instead (SHOP-02, SYNC-03).
 */
export function useAddExtraItem(listId: string) {
  return useListChange(listId, (item: ExtraItemCreate) =>
    unwrap(
      api.POST('/api/lists/{list_id}/extra-items', {
        params: { path: { list_id: listId } },
        body: item,
      }),
    ),
  );
}

/**
 * Changes an extra item; it keeps its kind. While shopping, a free-text item is renamed with an
 * `extra.update` op of the outbox instead (LIST-12, SYNC-03).
 */
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

/** Deletes an extra item; while shopping, a free-text item is an `extra.delete` op instead. */
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

/**
 * LIST-11: freezes the meals and starts shopping; the list view then shows the shopping view.
 * Only drafts can start (else `list.not_draft`).
 */
export function useStartShopping(listId: string) {
  return useListChange(listId, () =>
    unwrap(
      api.POST('/api/lists/{list_id}/start-shopping', { params: { path: { list_id: listId } } }),
    ),
  );
}

/**
 * The shopping actions as ops (plan § 5.8), stamped where the user acted (`stampOp()`). They go
 * through the outbox, online or offline (`useQueueOp` of the sync module): one code path.
 */
export const shoppingOps = {
  /** SHOP-01: check a line off or back on; the most recent tap wins (SYNC-06). */
  check: (key: string, checked: boolean, { opId, at }: OpStamp): Op => ({
    type: 'line.check',
    payload: { line_key: key, checked },
    op_id: opId,
    at,
  }),
  /** SHOP-02: a free-text item with the client's id. */
  addExtra: (payload: ExtraAddPayload, { opId, at }: OpStamp): Op => ({
    type: 'extra.add',
    payload,
    op_id: opId,
    at,
  }),
  /** LIST-12: rename a free-text item (its category stays). */
  updateExtra: (payload: ExtraUpdatePayload, { opId, at }: OpStamp): Op => ({
    type: 'extra.update',
    payload,
    op_id: opId,
    at,
  }),
  removeExtra: (extraId: string, { opId, at }: OpStamp): Op => ({
    type: 'extra.delete',
    payload: { extra_id: extraId },
    op_id: opId,
    at,
  }),
  /** SHOP-04: stamped when *Finish* was tapped: the list counts as finished then. */
  finish: ({ opId, at }: OpStamp): Op => ({ type: 'list.finish', payload: {}, op_id: opId, at }),
};

/** SHOP-06: a done list goes back to shopping, e.g. after finishing by mistake. */
export function useReopenList(listId: string) {
  return useListChange(listId, () =>
    unwrap(api.POST('/api/lists/{list_id}/reopen', { params: { path: { list_id: listId } } })),
  );
}

/**
 * SHOP-06: a new draft of mine with the done list's meals (as they are now), servings and extra
 * items, all unchecked; `left_out` counts the meals that are gone or that I can't see.
 */
export function useShopAgain(listId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/lists/{list_id}/shop-again', { params: { path: { list_id: listId } } }),
      ),
    onSuccess: ({ list }) => {
      queryClient.setQueryData(detailKey(list.id), list);
      invalidateFeed(queryClient);
    },
  });
}

/** MEAL-09: meals I added to lists lately, for the top of the meal picker. */
export function useRecentMeals({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: RECENT_MEALS_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/meals/recent', { signal })),
    enabled,
  });
}
