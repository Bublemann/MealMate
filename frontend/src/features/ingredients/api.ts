import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { api, unwrap, withLongTimeout } from '@/api/client';
import type { components } from '@/api/generated/schema';

export type Ingredient = components['schemas']['Ingredient'];
export type IngredientSummary = components['schemas']['IngredientSummary'];
export type IngredientCreate = components['schemas']['IngredientCreate'];
export type IngredientUpdate = components['schemas']['IngredientUpdate'];
export type BaseUnit = Ingredient['base_unit'];
export type NutrientValues = components['schemas']['NutrientValues'];
export type PendingUpdateField = components['schemas']['PendingUpdateField'];
export type OffProposal = components['schemas']['ProductProposal'];
export type OffSearchPage = components['schemas']['OffSearchPage'];
export type OffSearchResult = OffSearchPage['results'][number];
/** A field that came from Open Food Facts and was changed by a user (BAR-04). */
export type EditedField = Ingredient['user_edited_fields'][number];

/**
 * An Open Food Facts search waits for Open Food Facts like a barcode lookup does (up to about 15 s
 * on the server), so it gets the lookup's deadline; running out of it means "Open Food Facts is
 * slow".
 */
export const OFF_TIMEOUT_MS = 25_000;

const INGREDIENTS_KEY = ['ingredients'] as const;
const listKey = (query: string) => [...INGREDIENTS_KEY, 'list', query] as const;
const detailKey = (id: string) => [...INGREDIENTS_KEY, 'detail', id] as const;

/** Lists and similarity hints show names, categories and counts, which may have changed. */
function invalidateSearches(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: [...INGREDIENTS_KEY, 'list'] });
  void queryClient.invalidateQueries({ queryKey: [...INGREDIENTS_KEY, 'similar'] });
}

/** A summary as the lists show it, from a full ingredient (e.g. one just created). */
export function toSummary(ingredient: Ingredient): IngredientSummary {
  const { id, name, brand, barcode, source, category_id, base_unit } = ingredient;
  return { id, name, brand, barcode, source, category_id, base_unit };
}

/**
 * Ingredients matching `query` (ignoring case, umlauts and accents: ING-03), or all of them when
 * it is empty, sorted by the server. The previous result stays while the next one loads.
 */
export function useIngredients(query: string, { enabled = true }: { enabled?: boolean } = {}) {
  const q = query.trim();
  return useQuery({
    queryKey: listKey(q),
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/ingredients', { params: { query: q ? { q } : {} }, signal })),
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Ingredients with a name like `name`, for the "similar ingredient exists" hint (ING-03). */
export function useSimilarIngredients(name: string) {
  const trimmed = name.trim();
  return useQuery({
    queryKey: [...INGREDIENTS_KEY, 'similar', trimmed],
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/ingredients/similar', { params: { query: { name: trimmed } }, signal })),
    enabled: trimmed.length > 0,
  });
}

export function useIngredient(id: string) {
  return useQuery({
    queryKey: detailKey(id),
    queryFn: ({ signal }) =>
      unwrap(
        api.GET('/api/ingredients/{ingredient_id}', {
          params: { path: { ingredient_id: id } },
          signal,
        }),
      ),
  });
}

/** ING-01: anyone can create an ingredient. */
export function useCreateIngredient() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: IngredientCreate) => unwrap(api.POST('/api/ingredients', { body })),
    onSuccess: (ingredient) => {
      queryClient.setQueryData(detailKey(ingredient.id), ingredient);
      invalidateSearches(queryClient);
    },
  });
}

/**
 * ING-01/02: anyone can edit any ingredient. Only changed fields are sent: a changed field that
 * came from Open Food Facts is marked as edited by a user (BAR-04).
 */
export function useUpdateIngredient(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: IngredientUpdate) =>
      unwrap(
        api.PATCH('/api/ingredients/{ingredient_id}', {
          params: { path: { ingredient_id: id } },
          body,
        }),
      ),
    onSuccess: (ingredient) => {
      queryClient.setQueryData(detailKey(id), ingredient);
      invalidateSearches(queryClient);
    },
  });
}

/**
 * Gives an existing ingredient the scanned barcode ("This is already in MealMate"): the next scan
 * finds it (BAR-02). Only for an ingredient without a barcode: the caller checks what it shows,
 * and the server refuses to replace one (409 `ingredient.has_barcode`) in case that was stale.
 * The edit form changes a barcode with PATCH instead.
 */
export function useLinkBarcode() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, barcode }: { id: string; barcode: string }) =>
      unwrap(
        api.POST('/api/ingredients/{ingredient_id}/barcode', {
          params: { path: { ingredient_id: id } },
          body: { barcode },
        }),
      ),
    onSuccess: (ingredient) => {
      queryClient.setQueryData(detailKey(ingredient.id), ingredient);
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
      const params = { params: { path: { ingredient_id: id } } };
      return unwrap(
        action === 'apply'
          ? api.POST('/api/ingredients/{ingredient_id}/pending-update/apply', params)
          : api.POST('/api/ingredients/{ingredient_id}/pending-update/ignore', params),
      );
    },
    onSuccess: (ingredient) => {
      queryClient.setQueryData(detailKey(id), ingredient);
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
        api.GET('/api/ingredients/off-search', {
          params: { query: { q, page } },
          ...withLongTimeout(OFF_TIMEOUT_MS),
        }),
      ),
  });
}

/**
 * After a merge or delete: the lists reload, and the gone ingredient's own queries are only
 * marked stale (its screen is still open until the caller navigates away, so no refetch now).
 */
function forgetIngredient(queryClient: QueryClient, id: string) {
  invalidateSearches(queryClient);
  void queryClient.invalidateQueries({ queryKey: detailKey(id), refetchType: 'none' });
  void queryClient.invalidateQueries({ queryKey: ['admin', 'events'] });
}

/** ING-05 (admin): moves every reference of `id` to `intoId`, then deletes `id`. */
export function useMergeIngredient(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (intoId: string) =>
      unwrap(
        api.POST('/api/admin/ingredients/{ingredient_id}/merge', {
          params: { path: { ingredient_id: id } },
          body: { into_id: intoId },
        }),
      ),
    onSuccess: (target) => {
      forgetIngredient(queryClient, id);
      queryClient.setQueryData(detailKey(target.id), target);
    },
  });
}

/** ING-05 (admin): only while nothing references the ingredient (`ingredient.in_use`). */
export function useDeleteIngredient(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE('/api/admin/ingredients/{ingredient_id}', {
          params: { path: { ingredient_id: id } },
        }),
      ),
    onSuccess: () => forgetIngredient(queryClient, id),
  });
}
