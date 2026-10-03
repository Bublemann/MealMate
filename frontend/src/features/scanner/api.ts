import { useMutation } from '@tanstack/react-query';
import { api, unwrap, withLongTimeout } from '@/api/client';
import { isApiError } from '@/api/errors';
import type { components } from '@/api/generated/schema';
import { OFF_TIMEOUT_MS } from '@/features/ingredients/api';

export type BarcodeLookup = components['schemas']['BarcodeLookup'];

export interface LookupRequest {
  barcode: string;
  /**
   * Only our own ingredients, without asking Open Food Facts: the edit pop-up's scan only needs
   * to know whether another ingredient has the barcode (BAR-03).
   */
  ownOnly?: boolean;
}

/**
 * A lookup may wait for Open Food Facts (up to about 15 s on the server, plan § 5.9), so it gets
 * more time than other reads (plan § 8). Running out of it means "Open Food Facts is slow".
 */
export const LOOKUP_TIMEOUT_MS = OFF_TIMEOUT_MS;

/** BAR-02/03: our own ingredients first, then Open Food Facts; nothing is saved. */
export function useBarcodeLookup() {
  return useMutation({
    mutationFn: ({ barcode, ownOnly = false }: LookupRequest) =>
      unwrap(
        api.GET('/api/ingredients/lookup', {
          params: { query: ownOnly ? { barcode, own_only: true } : { barcode } },
          // Our own ingredients alone answer as fast as any other read.
          ...(ownOnly ? {} : withLongTimeout(LOOKUP_TIMEOUT_MS)),
        }),
      ),
  });
}

/** When Open Food Facts can't answer in time: try again, or enter the values by hand. */
export function isOffSlow(error: unknown): boolean {
  return isApiError(error) && (error.code === 'off.busy' || error.code === 'client.timeout');
}
