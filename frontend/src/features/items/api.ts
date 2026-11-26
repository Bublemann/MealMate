import {
  keepPreviousData,
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { api, unwrap, withLongTimeout } from '@/api/client';
import { isApiError } from '@/api/errors';
import type { components } from '@/api/generated/schema';
import { NOTICES_KEY, RECURRING_KEY } from '@/features/recurring/api';
import { CATEGORIES_KEY } from '@/features/reference/api';

export type Item = components['schemas']['Item'];
export type ItemSummary = components['schemas']['ItemSummary'];
export type ItemSearchResult = components['schemas']['ItemSearchResult'];
export type ItemCreate = components['schemas']['ItemCreate'];
export type ItemUpdate = components['schemas']['ItemUpdate'];
export type ItemMerge = components['schemas']['ItemMerge'];
export type BaseUnit = Item['base_unit'];
export type NutrientValues = components['schemas']['NutrientValues'];
export type PendingUpdateField = components['schemas']['PendingUpdateField'];
export type OffProposal = components['schemas']['ProductProposal'];
export type OffSearchPage = components['schemas']['OffSearchPage'];
export type OffSearchResult = OffSearchPage['results'][number];
/** A field that came from Open Food Facts and was changed by a user (BAR-04). */
export type EditedField = Item['user_edited_fields'][number];

/**
 * An Open Food Facts search waits for Open Food Facts like a barcode lookup does (up to about 15 s
 * on the server), so it gets the lookup's deadline; running out of it means "Open Food Facts is
 * slow".
 */
export const OFF_TIMEOUT_MS = 25_000;

export const ITEMS_KEY = ['items'] as const;
const listKey = (query: string, categoryIds: readonly string[]) =>
  [...ITEMS_KEY, 'list', query, categoryIds] as const;
const detailKey = (id: string) => [...ITEMS_KEY, 'detail', id] as const;

/** Lists and similarity hints show names, categories and counts, which may have changed. */
function invalidateSearches(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: [...ITEMS_KEY, 'list'] });
  void queryClient.invalidateQueries({ queryKey: [...ITEMS_KEY, 'similar'] });
}

/**
 * The categories count their items, which decides whether the filter panel offers
 * *Uncategorized* (ING-03): a saved, merged or deleted item may have changed the counts.
 */
function invalidateCategoryCounts(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: CATEGORIES_KEY });
}

/** A summary as the lists show it, from a full item (e.g. one just created). */
export function toSummary(item: Item): ItemSummary {
  const { id, name, brand, barcode, source, category_id, base_unit } = item;
  return { id, name, brand, barcode, source, category_id, base_unit };
}

/**
 * Items matching `query` (ignoring case, umlauts and accents: ING-03), or all of them when
 * it is empty, sorted by the server; with `categoryIds`, only those in any of these categories.
 */
export function itemsQuery(query: string, categoryIds: readonly string[] = []) {
  const q = query.trim();
  return queryOptions({
    queryKey: listKey(q, categoryIds),
    queryFn: ({ signal }) =>
      unwrap(
        api.GET('/api/items', {
          // Left out when empty: `category_id=a&category_id=b` for several (ING-03).
          params: {
            query: {
              q: q || undefined,
              category_id: categoryIds.length > 0 ? [...categoryIds] : undefined,
            },
          },
          signal,
        }),
      ),
  });
}

/** `itemsQuery` on screen: the previous result stays while the next one loads. */
export function useItems(
  query: string,
  { enabled = true, categoryIds = [] }: { enabled?: boolean; categoryIds?: readonly string[] } = {},
) {
  return useQuery({
    ...itemsQuery(query, categoryIds),
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Items with a name like `name`, for the "similar item exists" hint (ING-03). */
export function useSimilarItems(name: string) {
  const trimmed = name.trim();
  return useQuery({
    queryKey: [...ITEMS_KEY, 'similar', trimmed],
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/items/similar', { params: { query: { name: trimmed } }, signal })),
    enabled: trimmed.length > 0,
  });
}

export function useItem(id: string) {
  return useQuery({
    queryKey: detailKey(id),
    queryFn: ({ signal }) =>
      unwrap(
        api.GET('/api/items/{item_id}', {
          params: { path: { item_id: id } },
          signal,
        }),
      ),
  });
}

/** ING-01: anyone can create an item. */
export function useCreateItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ItemCreate) => unwrap(api.POST('/api/items', { body })),
    onSuccess: (item) => {
      queryClient.setQueryData(detailKey(item.id), item);
      invalidateSearches(queryClient);
      invalidateCategoryCounts(queryClient);
    },
  });
}

/**
 * ING-01/02: anyone can edit any item. Only changed fields are sent: a changed field that
 * came from Open Food Facts is marked as edited by a user (BAR-04).
 */
export function useUpdateItem(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ItemUpdate) =>
      unwrap(
        api.PATCH('/api/items/{item_id}', {
          params: { path: { item_id: id } },
          body,
        }),
      ),
    onSuccess: (item) => {
      queryClient.setQueryData(detailKey(id), item);
      invalidateSearches(queryClient);
      invalidateCategoryCounts(queryClient);
    },
  });
}

/**
 * What a base-unit change or a merge would leave not fitting (D-33): the amounts, and the meals
 * and drafts they are on. The server refuses such a change (409 `item.unit_mismatch`) until
 * the request accepts it (`accept_unit_mismatch`); nothing is converted then.
 */
export interface UnitMismatch {
  meals: number;
  lists: number;
  amounts: number;
}

/** The counts of a base-unit change or merge refused for amounts that won't fit, else null. */
export function unitMismatch(error: unknown): UnitMismatch | null {
  if (!isApiError(error) || error.code !== 'item.unit_mismatch') return null;
  const count = (key: keyof UnitMismatch) => {
    const value = error.params[key];
    return typeof value === 'number' ? value : 0;
  };
  return { meals: count('meals'), lists: count('lists'), amounts: count('amounts') };
}

/**
 * Gives an existing item the scanned barcode ("This is already in MealMate"): the next scan
 * finds it (BAR-02). Only for an item without a barcode: the caller checks what it shows,
 * and the server refuses to replace one (409 `item.has_barcode`) in case that was stale.
 * The edit form changes a barcode with PATCH instead.
 */
export function useLinkBarcode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, barcode }: { id: string; barcode: string }) =>
      unwrap(
        api.POST('/api/items/{item_id}/barcode', {
          params: { path: { item_id: id } },
          body: { barcode },
        }),
      ),
    onSuccess: (item) => {
      queryClient.setQueryData(detailKey(item.id), item);
      invalidateSearches(queryClient);
    },
  });
}

/**
 * BAR-06: takes Open Food Facts' newer values for the user-edited fields (`apply`), or keeps the
 * user's values and stops proposing this Open Food Facts version (`ignore`).
 */
export function usePendingUpdate(id: string, action: 'apply' | 'ignore') {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => {
      const params = { params: { path: { item_id: id } } };
      return unwrap(
        action === 'apply'
          ? api.POST('/api/items/{item_id}/pending-update/apply', params)
          : api.POST('/api/items/{item_id}/pending-update/ignore', params),
      );
    },
    onSuccess: (item) => {
      queryClient.setQueryData(detailKey(id), item);
      invalidateSearches(queryClient);
    },
  });
}

/**
 * Searches Open Food Facts by name (one page of up to 20 proposals). A mutation, not a query: it
 * runs only when the user taps "Search" or presses Enter, never while typing (BAR-08), and the
 * server has its own cache and rate limit for it.
 */
export function useOffSearch() {
  return useMutation({
    mutationFn: ({ q, page }: { q: string; page: number }) =>
      unwrap(
        api.GET('/api/items/off-search', {
          params: { query: { q, page } },
          ...withLongTimeout(OFF_TIMEOUT_MS),
        }),
      ),
  });
}

/**
 * After a merge or delete: the lists reload, and the gone item's own queries are only
 * marked stale (its screen is still open until the caller navigates away, so no refetch now).
 * Recurring items move or go with it, and the admin may have kept it as one: their set and
 * notices load again (LIST-16, D-51).
 */
function forgetItem(queryClient: QueryClient, id: string) {
  invalidateSearches(queryClient);
  invalidateCategoryCounts(queryClient);
  void queryClient.invalidateQueries({ queryKey: RECURRING_KEY });
  void queryClient.invalidateQueries({ queryKey: NOTICES_KEY });
  void queryClient.invalidateQueries({ queryKey: detailKey(id), refetchType: 'none' });
  void queryClient.invalidateQueries({ queryKey: ['admin', 'events'] });
}

/**
 * ING-05 (admin): moves every reference of `id` to `into_id`, then deletes `id`; refused while
 * amounts of `id` wouldn't fit `into_id`, unless the body accepts that (`unitMismatch`).
 */
export function useMergeItem(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ItemMerge) =>
      unwrap(
        api.POST('/api/admin/items/{item_id}/merge', {
          params: { path: { item_id: id } },
          body,
        }),
      ),
    onSuccess: (target) => {
      forgetItem(queryClient, id);
      queryClient.setQueryData(detailKey(target.id), target);
    },
  });
}

/** ING-05 (admin): only while nothing references the item (`item.in_use`). */
export function useDeleteItem(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE('/api/admin/items/{item_id}', {
          params: { path: { item_id: id } },
        }),
      ),
    onSuccess: () => forgetItem(queryClient, id),
  });
}
