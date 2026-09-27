import {
  replaceEqualDeep,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import { ApiError, isApiError, type ErrorCode } from '@/api/errors';
import type { components } from '@/api/generated/schema';
import { useAuthSession, useCurrentUser } from '@/features/auth/context';
import { FILTER_HIDDEN_KEY } from '@/features/meals/api';
import { uuidv7 } from '@/lib/uuid';

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
type Op = components['schemas']['OpsRequest']['ops'][number];
export type ExtraAddPayload = Extract<Op, { type: 'extra.add' }>['payload'];
export type ExtraUpdatePayload = Extract<Op, { type: 'extra.update' }>['payload'];

/** SYNC-08: a list on screen is loaded again this often (ms), while the app is visible. */
export const POLL_INTERVAL_MS = 5_000;

/** `mine`: my drafts and my partner's shared ones; `others`: other lists I may look at (UI-02). */
export type ListScope = 'mine' | 'others';

const LISTS_KEY = ['lists'] as const;
const SUMMARIES_KEY = [...LISTS_KEY, 'summaries'] as const;
const summariesKey = (scope: ListScope) => [...SUMMARIES_KEY, scope] as const;
const detailKey = (id: string) => [...LISTS_KEY, 'detail', id] as const;
const changeKey = (id: string) => [...LISTS_KEY, 'change', id] as const;
// Below ['meals'], so everything that reloads the meals reloads these too.
const historyKey = [...SUMMARIES_KEY, 'history'] as const;
const RECENT_MEALS_KEY = ['meals', 'recent'] as const;
const VISIBLE_USERS_KEY = ['users', 'visible', 'lists'] as const;

function invalidateSummaries(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: SUMMARIES_KEY });
}

/** Lists in `scope` that are drafts or being shopped, most recently edited first (UI-02). */
export function useLists(scope: ListScope) {
  return useQuery({
    queryKey: summariesKey(scope),
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/lists', { params: { query: { scope } }, signal })),
  });
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
 * when the app comes back to the foreground (SYNC-08, LIST-09).
 */
export function useList(id: string) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: detailKey(id),
    queryFn: ({ signal }) => loadList(queryClient, id, signal),
    refetchOnWindowFocus: 'always',
    refetchInterval: (query) => (isFinal(query.state.error) ? false : POLL_INTERVAL_MS),
    structuralSharing: shareWithEtag,
  });
}

/** Whether a failed load means the server couldn't be reached (SYNC-07/09). */
export function isUnreachable(error: unknown): boolean {
  return !isApiError(error) || error.status === 0 || error.status >= 500;
}

/** An op the server turned down (plan § 5.8); `list` is the list as it is now. */
export class OpRejectedError extends ApiError {
  readonly list: ListDetail;

  constructor(code: ErrorCode, list: ListDetail) {
    super({ status: 409, code });
    this.list = list;
  }
}

/**
 * What makes an action one op (SYNC-05/06): a UUIDv7 and the time of the tap, made when the user
 * acts, not when the op is sent (a change may wait for the ones before it). Sending the same
 * action again (a retry) keeps both, so the server applies it once.
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
 * Sends ops through `POST /lists/{id}/ops`, the endpoint the offline outbox uses too (plan § 5.8).
 * Resolves to the list as it is now; rejects with an OpRejectedError if the server turned an op
 * down.
 */
async function sendOps(listId: string, ops: Op[]): Promise<ListDetail> {
  const { results, list } = await unwrap(
    api.POST('/api/lists/{list_id}/ops', {
      params: { path: { list_id: listId } },
      body: { ops },
    }),
  );
  const rejected = results.find((result) => result.status === 'rejected');
  if (rejected) throw new OpRejectedError(rejected.code ?? 'common.internal', list);
  return list;
}

/**
 * A change to list `listId` that answers with the whole list. Changes of one list run one after
 * another (scope), and only the answer to the last one is put into the cache: an earlier answer
 * would briefly undo the optimistic state of a change still waiting (e.g. several taps on +).
 * A load of the list that is still running when a change starts is cancelled, and loads that
 * answer while changes wait are ignored, so an older answer can't replace the change's.
 * A failed change is undone on screen where it says how (`revert`), and the list is loaded again
 * instead of guessing; an op the server turned down brings the list as it is now.
 */
function useListChange<Variables>(
  listId: string,
  mutationFn: (variables: Variables) => Promise<ListDetail>,
  {
    optimistic,
    revert,
    onSuccess,
  }: {
    /** The change as it will look, applied to the cached list right away. */
    optimistic?: (variables: Variables) => (list: ListDetail) => ListDetail;
    /** Undoes the optimistic change on the cached list, given the list from before it. */
    revert?: (variables: Variables, before: ListDetail) => (list: ListDetail) => ListDetail;
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
      const before = queryClient.getQueryData<ListDetail>(detailKey(listId));
      await queryClient.cancelQueries({ queryKey: detailKey(listId) });
      if (optimistic) update(optimistic(variables));
      return { before };
    },
    onSuccess: (list) => {
      if (changeAnswered(queryClient, listId) === 0)
        queryClient.setQueryData(detailKey(listId), list);
      onSuccess?.(queryClient);
    },
    onError: (error, variables, context) => {
      const waiting = changeAnswered(queryClient, listId);
      if (error instanceof OpRejectedError) {
        if (waiting === 0) queryClient.setQueryData(detailKey(listId), error.list);
      } else if (revert && context?.before) {
        update(revert(variables, context.before));
      }
      void queryClient.invalidateQueries({ queryKey: detailKey(listId) });
    },
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
 * it while the item is sent again), so a retry after a lost answer doesn't add it twice. While
 * shopping, a free-text item is sent as an `extra.add` op instead (SHOP-02), as offline (SYNC-03),
 * with the stamp the input keeps along with the id.
 */
export function useAddExtraItem(listId: string) {
  return useListChange(listId, (item: ExtraItemCreate | ({ op: ExtraAddPayload } & OpStamp)) =>
    'op' in item
      ? sendOps(listId, [{ type: 'extra.add', payload: item.op, op_id: item.opId, at: item.at }])
      : unwrap(
          api.POST('/api/lists/{list_id}/extra-items', {
            params: { path: { list_id: listId } },
            body: item,
          }),
        ),
  );
}

/**
 * Changes an extra item; it keeps its kind. While shopping, a free-text item is renamed with an
 * `extra.update` op instead (LIST-12), as offline (M6).
 */
export function useUpdateExtraItem(listId: string) {
  return useListChange(
    listId,
    (
      change: { extraId: string; body: ExtraItemUpdate } | ({ op: ExtraUpdatePayload } & OpStamp),
    ) =>
      'op' in change
        ? sendOps(listId, [
            { type: 'extra.update', payload: change.op, op_id: change.opId, at: change.at },
          ])
        : unwrap(
            api.PATCH('/api/lists/{list_id}/extra-items/{extra_id}', {
              params: { path: { list_id: listId, extra_id: change.extraId } },
              body: change.body,
            }),
          ),
  );
}

/** Deletes an extra item; while shopping, a free-text item through an `extra.delete` op. */
export function useRemoveExtraItem(listId: string) {
  return useListChange(listId, (item: string | ({ extraId: string } & OpStamp)) =>
    typeof item === 'string'
      ? unwrap(
          api.DELETE('/api/lists/{list_id}/extra-items/{extra_id}', {
            params: { path: { list_id: listId, extra_id: item } },
          }),
        )
      : sendOps(listId, [
          {
            type: 'extra.delete',
            payload: { extra_id: item.extraId },
            op_id: item.opId,
            at: item.at,
          },
        ]),
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

export interface CheckLine extends OpStamp {
  key: string;
  checked: boolean;
}

/**
 * SHOP-01: checks a line off or back on through the ops (the most recent tap wins, SYNC-06), with
 * the stamp of the tap (`stampOp()` where it happened). The line moves at once, marked as checked
 * by me; if sending fails it moves back.
 */
export function useCheckLine(listId: string) {
  const me = useCurrentUser();
  return useListChange(
    listId,
    ({ key, checked, opId, at }: CheckLine) =>
      sendOps(listId, [
        { type: 'line.check', payload: { line_key: key, checked }, op_id: opId, at },
      ]),
    {
      optimistic:
        ({ key, checked, at }) =>
        (list) => ({
          ...list,
          lines: list.lines.map((line) =>
            line.key === key
              ? {
                  ...line,
                  checked,
                  checked_at: at,
                  checked_by: checked
                    ? { id: me.id, display_name: me.display_name, deactivated: false }
                    : null,
                  new: false,
                  needs_more: null,
                }
              : line,
          ),
        }),
      revert:
        ({ key }, before) =>
        (list) => {
          const previous = before.lines.find((line) => line.key === key);
          if (!previous) return list;
          return {
            ...list,
            lines: list.lines.map((line) =>
              line.key === key
                ? {
                    ...line,
                    checked: previous.checked,
                    checked_at: previous.checked_at,
                    checked_by: previous.checked_by,
                    new: previous.new,
                    needs_more: previous.needs_more,
                  }
                : line,
            ),
          };
        },
    },
  );
}

/**
 * SHOP-04: finishes shopping (the `list.finish` op, stamped when *Finish* was tapped: the list
 * counts as finished then); the list moves to the history.
 */
export function useFinishList(listId: string) {
  return useListChange(listId, ({ opId, at }: OpStamp) =>
    sendOps(listId, [{ type: 'list.finish', payload: {}, op_id: opId, at }]),
  );
}

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
      invalidateSummaries(queryClient);
    },
  });
}

/** SHOP-05: done lists in my history (mine and my partner's shared ones), newest first. */
export function useListHistory() {
  return useQuery({
    queryKey: historyKey,
    queryFn: ({ signal }) => unwrap(api.GET('/api/lists/history', { signal })),
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
