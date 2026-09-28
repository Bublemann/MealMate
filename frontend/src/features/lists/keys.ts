/**
 * Query keys of the lists, shared by `api.ts` and the sync module (which seeds them from the
 * local copy and stores what the outbox sends back), so neither imports the other's hooks.
 */

/** `mine`: my drafts and my partner's shared ones; `others`: other lists I may look at (UI-02). */
export type ListScope = 'mine' | 'others';

export const LISTS_KEY = ['lists'] as const;
export const SUMMARIES_KEY = [...LISTS_KEY, 'summaries'] as const;
export const summariesKey = (scope: ListScope) => [...SUMMARIES_KEY, scope] as const;
export const detailKey = (id: string) => [...LISTS_KEY, 'detail', id] as const;
// Below ['meals'], so everything that reloads the meals reloads these too.
export const HISTORY_KEY = [...SUMMARIES_KEY, 'history'] as const;
