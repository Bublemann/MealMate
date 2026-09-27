import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';

export type Category = components['schemas']['Category'];
export type UnitInfo = components['schemas']['UnitInfo'];
export type Unit = UnitInfo['unit'];
export type Cuisine = components['schemas']['Cuisine'];
export type Tag = components['schemas']['Tag'];

export const CATEGORIES_KEY = ['reference', 'categories'] as const;
const CUISINES_KEY = ['reference', 'cuisines'] as const;

// Reference data changes rarely (someone adds a cuisine), so it is kept for a long time; the
// admin screens update the cache themselves.
const REFERENCE_STALE_MS = 60 * 60 * 1000;
// A new category order from an admin should reach everyone else soon: kept for 5 minutes, then
// loaded again when a screen using it mounts or the app regains focus.
export const CATEGORIES_STALE_MS = 5 * 60 * 1000;

/** The categories in the store's walking order (REF-01, ADM-01). */
export function useCategories() {
  return useQuery({
    queryKey: CATEGORIES_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/categories', { signal })),
    staleTime: CATEGORIES_STALE_MS,
    refetchOnMount: true,
    refetchOnWindowFocus: true,
  });
}

/** The fixed units in display order (REF-02). */
export function useUnits() {
  return useQuery({
    queryKey: ['reference', 'units'],
    queryFn: ({ signal }) => unwrap(api.GET('/api/units', { signal })),
    staleTime: Infinity,
  });
}

/** Seeded cuisines first, then the ones users added (REF-03). */
export function useCuisines() {
  return useQuery({
    queryKey: CUISINES_KEY,
    queryFn: ({ signal }) => unwrap(api.GET('/api/cuisines', { signal })),
    staleTime: REFERENCE_STALE_MS,
  });
}

/**
 * Adds a cuisine as plain text (REF-03); an existing one with that name is returned instead. The
 * cached list gets it at once, so a select can show it right away.
 */
export function useCreateCuisine() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => unwrap(api.POST('/api/cuisines', { body: { name } })),
    onSuccess: (cuisine) => {
      queryClient.setQueryData<Cuisine[]>(CUISINES_KEY, (cuisines) =>
        cuisines && !cuisines.some(({ id }) => id === cuisine.id)
          ? [...cuisines, cuisine]
          : cuisines,
      );
      void queryClient.invalidateQueries({ queryKey: CUISINES_KEY });
    },
  });
}

/**
 * Tags for suggestions and filters (REF-04): the server returns at most 20, those starting with
 * `query` first. The previous result stays while the next one loads.
 */
export function useTags(query = '') {
  const q = query.trim();
  return useQuery({
    queryKey: ['reference', 'tags', q],
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/tags', { params: { query: q ? { q } : {} }, signal })),
    placeholderData: keepPreviousData,
  });
}
