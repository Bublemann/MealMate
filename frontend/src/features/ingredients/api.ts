import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';

export type Ingredient = components['schemas']['Ingredient'];
export type IngredientSummary = components['schemas']['IngredientSummary'];
export type IngredientCreate = components['schemas']['IngredientCreate'];
export type IngredientUpdate = components['schemas']['IngredientUpdate'];
export type BaseUnit = Ingredient['base_unit'];
export type NutrientValues = components['schemas']['NutrientValues'];
export type NutrientInfo = components['schemas']['NutrientInfo'];
export type Product = components['schemas']['Product'];
export type ProductCreate = components['schemas']['ProductCreate'];
export type ProductUpdate = components['schemas']['ProductUpdate'];

const INGREDIENTS_KEY = ['ingredients'] as const;
const listKey = (query: string) => [...INGREDIENTS_KEY, 'list', query] as const;
const detailKey = (id: string) => [...INGREDIENTS_KEY, 'detail', id] as const;
const productsKey = (id: string) => [...INGREDIENTS_KEY, 'products', id] as const;

/** Lists and similarity hints show names, categories and counts, which may have changed. */
function invalidateSearches(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: [...INGREDIENTS_KEY, 'list'] });
  void queryClient.invalidateQueries({ queryKey: [...INGREDIENTS_KEY, 'similar'] });
}

/** A summary as the lists show it, from a full ingredient (e.g. one just created). */
export function toSummary(ingredient: Ingredient): IngredientSummary {
  const { id, name, category_id, base_unit, product_count } = ingredient;
  return { id, name, category_id, base_unit, product_count };
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

/** ING-01/02: anyone can edit any ingredient; the base unit is locked while products exist. */
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

/** The products linked to an ingredient (ING-04). */
export function useIngredientProducts(id: string) {
  return useQuery({
    queryKey: productsKey(id),
    queryFn: ({ signal }) =>
      unwrap(
        api.GET('/api/ingredients/{ingredient_id}/products', {
          params: { path: { ingredient_id: id } },
          signal,
        }),
      ),
  });
}

/** A product entered by hand (ING-04); the nutrition average of its ingredient changes. */
export function useCreateProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ProductCreate) => unwrap(api.POST('/api/products', { body })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: INGREDIENTS_KEY }),
  });
}

/** Only the fields in `body` are sent: the server marks them as edited by a user (BAR-04). */
export function useUpdateProduct(productId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ProductUpdate) =>
      unwrap(
        api.PATCH('/api/products/{product_id}', {
          params: { path: { product_id: productId } },
          body,
        }),
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: INGREDIENTS_KEY }),
  });
}

/**
 * After a merge or delete: the lists reload, and the gone ingredient's own queries are only
 * marked stale (its screen is still open until the caller navigates away, so no refetch now).
 */
function forgetIngredient(queryClient: QueryClient, id: string) {
  invalidateSearches(queryClient);
  void queryClient.invalidateQueries({ queryKey: detailKey(id), refetchType: 'none' });
  void queryClient.invalidateQueries({ queryKey: productsKey(id), refetchType: 'none' });
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
      void queryClient.invalidateQueries({ queryKey: productsKey(target.id) });
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
