import type { InfiniteData } from '@tanstack/react-query';
import type { components } from '@/api/generated/schema';

/**
 * Query keys of the lists, shared by `api.ts` and the sync module (which seeds them from the
 * local copy and stores what the outbox sends back), so neither imports the other's hooks.
 */

export const LISTS_KEY = ['lists'] as const;
/** The list feed on the Lists tab (UI-02), loaded page by page. */
export const FEED_KEY = [...LISTS_KEY, 'feed'] as const;
export const detailKey = (id: string) => [...LISTS_KEY, 'detail', id] as const;

/**
 * When the local copy in the feed's cache counts as loaded: never, so the feed is asked for anyway
 * (the copy lacks read-only and done lists), and it can be told apart from the server's pages.
 */
export const COPY_UPDATED_AT = 0;

/** The pages of the list feed loaded so far, each asked for with the cursor beside it. */
export type FeedData = InfiniteData<components['schemas']['ListFeedPage'], string | null>;
