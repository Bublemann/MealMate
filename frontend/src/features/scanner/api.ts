import { useMutation } from '@tanstack/react-query';
import { api, unwrap, withLongTimeout } from '@/api/client';
import type { components } from '@/api/generated/schema';
import { OFF_TIMEOUT_MS } from '@/features/ingredients/api';

export type BarcodeLookup = components['schemas']['BarcodeLookup'];

/**
 * A lookup may wait for Open Food Facts (up to about 15 s on the server, plan § 5.9), so it gets
 * more time than other reads (plan § 8). Running out of it means "Open Food Facts is slow".
 */
export const LOOKUP_TIMEOUT_MS = OFF_TIMEOUT_MS;

/** BAR-02/03: our own ingredients first, then Open Food Facts; nothing is saved. */
export function useBarcodeLookup() {
  return useMutation({
    mutationFn: (barcode: string) =>
      unwrap(
        api.GET('/api/ingredients/lookup', {
          params: { query: { barcode } },
          ...withLongTimeout(LOOKUP_TIMEOUT_MS),
        }),
      ),
  });
}
