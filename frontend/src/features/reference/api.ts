import { useQuery } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';

export type Category = components['schemas']['Category'];
export type UnitInfo = components['schemas']['UnitInfo'];
export type Unit = UnitInfo['unit'];
export type Cuisine = components['schemas']['Cuisine'];

export const CATEGORIES_KEY = ['reference', 'categories'] as const;

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
    queryKey: ['reference', 'cuisines'],
    queryFn: ({ signal }) => unwrap(api.GET('/api/cuisines', { signal })),
    staleTime: REFERENCE_STALE_MS,
  });
}
