import { useMutation } from '@tanstack/react-query';
import { api, unwrap, withLongTimeout } from '@/api/client';
import type { components } from '@/api/generated/schema';

export type ProductLookup = components['schemas']['ProductLookup'];

/**
 * A lookup may wait for Open Food Facts (up to about 15 s on the server, plan § 5.9), so it gets
 * more time than other reads (plan § 8). Running out of it means "Open Food Facts is slow".
 */
export const LOOKUP_TIMEOUT_MS = 25_000;

/** BAR-02/03: our own products first, then Open Food Facts; nothing is saved. */
export function useProductLookup() {
  return useMutation({
    mutationFn: (barcode: string) =>
      unwrap(
        api.GET('/api/products/lookup', {
          params: { query: { barcode } },
          ...withLongTimeout(LOOKUP_TIMEOUT_MS),
        }),
      ),
  });
}
