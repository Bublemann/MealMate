import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';
import { api, unwrap, withLongTimeout } from '@/api/client';
import type { components, paths } from '@/api/generated/schema';
import { photoFormData, preparePhoto } from './photo';

export type Meal = components['schemas']['Meal'];
export type MealSummary = components['schemas']['MealSummary'];
export type MealCreate = components['schemas']['MealCreate'];
export type MealUpdate = components['schemas']['MealUpdate'];
export type MealIngredientRow = components['schemas']['MealIngredientRow'];
export type MealIngredientInput = components['schemas']['MealIngredientInput'];
export type MealNutrition = components['schemas']['MealNutrition'];
export type MealNutritionMissing = components['schemas']['MealNutritionMissing'];
export type Tag = components['schemas']['Tag'];

type PhotoUpload = NonNullable<
  paths['/api/meals/{meal_id}/photo']['put']['requestBody']
>['content']['multipart/form-data'];

/**
 * The Meals tab's search and filters (MEAL-09): a meal in any of `cuisineIds` that has every one
 * of `tagIds`; empty values mean "any".
 */
export interface MealFilters {
  q: string;
  cuisineIds: readonly string[];
  tagIds: readonly string[];
}

const MEALS_KEY = ['meals'] as const;
/** Every search of the meals: the user filter on Meals loads them again once it is saved. */
export const MEAL_SEARCH_KEY = [...MEALS_KEY, 'list'] as const;
const detailKey = (id: string) => [...MEALS_KEY, 'detail', id] as const;
const MEAL_TAGS_KEY = [...MEALS_KEY, 'tags'] as const;
const TAGS_KEY = ['reference', 'tags'] as const;

/** Photos can be large and phone uploads slow: more time than the default for writes. */
export const PHOTO_UPLOAD_TIMEOUT_MS = 60_000;

function invalidateLists(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: MEAL_SEARCH_KEY });
}

/** A meal was saved, copied or deleted: its tags may be new, or no longer used anywhere. */
function invalidateTags(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: MEAL_TAGS_KEY });
  void queryClient.invalidateQueries({ queryKey: TAGS_KEY });
}

/** A saved or copied meal: its detail is known now, and the lists show it after a reload. */
function remember(queryClient: QueryClient, meal: Meal) {
  queryClient.setQueryData(detailKey(meal.id), meal);
  invalidateLists(queryClient);
  invalidateTags(queryClient);
}

/**
 * The visible meals matching the filters, A–Z (MEAL-09). The server leaves out the owners the user
 * filter on Meals hides (MEAL-10). The previous result stays while the next one loads.
 */
export function useMeals({ q, cuisineIds, tagIds }: MealFilters) {
  const query = {
    ...(q.trim() ? { q: q.trim() } : {}),
    ...(cuisineIds.length ? { cuisine_id: [...cuisineIds] } : {}),
    ...(tagIds.length ? { tag_id: [...tagIds] } : {}),
  };
  return useQuery({
    queryKey: [...MEAL_SEARCH_KEY, query],
    queryFn: ({ signal }) => unwrap(api.GET('/api/meals', { params: { query }, signal })),
    placeholderData: keepPreviousData,
  });
}

/**
 * The tags of all meals the user can see, A–Z: the choices of the tag filter (MEAL-09). Unlike
 * the tag suggestions (`useTags`) it has no limit and leaves out tags only others can see.
 */
export function useMealTags() {
  return useQuery({
    queryKey: MEAL_TAGS_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/meals/tags', { signal })),
  });
}

export function useMeal(id: string) {
  return useQuery({
    queryKey: detailKey(id),
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/meals/{meal_id}', { params: { path: { meal_id: id } }, signal })),
  });
}

/** MEAL-01: only the name is required; the creator owns the meal. */
export function useCreateMeal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: MealCreate) => unwrap(api.POST('/api/meals', { body })),
    onSuccess: (meal) => remember(queryClient, meal),
  });
}

/** Owner only (MEAL-07). `ingredients` and `tags`, when sent, replace the whole list. */
export function useUpdateMeal(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: MealUpdate) =>
      unwrap(api.PATCH('/api/meals/{meal_id}', { params: { path: { meal_id: id } }, body })),
    onSuccess: (meal) => remember(queryClient, meal),
  });
}

/** Owner only (MEAL-07). The detail is only marked stale: its screen is left right away. */
export function useDeleteMeal(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE('/api/meals/{meal_id}', { params: { path: { meal_id: id } } })),
    onSuccess: () => {
      invalidateLists(queryClient);
      invalidateTags(queryClient);
      void queryClient.invalidateQueries({ queryKey: detailKey(id), refetchType: 'none' });
    },
  });
}

/** MEAL-08: any visible meal becomes an independent meal of the current user. */
export function useCopyMeal(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(api.POST('/api/meals/{meal_id}/copy', { params: { path: { meal_id: id } } })),
    onSuccess: (meal) => remember(queryClient, meal),
  });
}

/**
 * Shrinks the photo on the phone (MEAL-04), then uploads it as `multipart/form-data` through the
 * shared client, so the auth middleware (token, refresh and retry) applies, with a longer
 * timeout than other writes.
 */
export function useUploadMealPhoto() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ mealId, file }: { mealId: string; file: File }) => {
      const form = photoFormData(await preparePhoto(file));
      return unwrap(
        api.PUT('/api/meals/{meal_id}/photo', {
          params: { path: { meal_id: mealId } },
          // openapi-fetch passes FormData through untouched; the browser sets the boundary.
          body: form as unknown as PhotoUpload,
          ...withLongTimeout(PHOTO_UPLOAD_TIMEOUT_MS),
        }),
      );
    },
    onSuccess: (meal) => remember(queryClient, meal),
  });
}

export function useDeleteMealPhoto() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mealId: string) =>
      unwrap(api.DELETE('/api/meals/{meal_id}/photo', { params: { path: { meal_id: mealId } } })),
    onSuccess: (_, mealId) => {
      void queryClient.invalidateQueries({ queryKey: detailKey(mealId) });
      invalidateLists(queryClient);
    },
  });
}
