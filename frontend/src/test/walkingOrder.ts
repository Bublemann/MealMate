import type { components } from '@/api/generated/schema';
import { CATEGORIES_WITH_UNCATEGORIZED } from './ingredients';

type Schemas = components['schemas'];
type Category = Pick<Schemas['Category'], 'id' | 'key' | 'names'>;

interface WalkingOrderOptions {
  /** "Reihenfolge der Verwaltung übernehmen" (default on). */
  follows?: boolean;
  /** The ids of the categories an admin added since the own order was saved ("neu"). */
  fresh?: readonly string[];
}

/** `GET /api/walking-order`: the categories in this order. */
export function walkingOrder(
  categories: readonly Category[] = CATEGORIES_WITH_UNCATEGORIZED,
  { follows = true, fresh = [] }: WalkingOrderOptions = {},
): Schemas['WalkingOrder'] {
  return {
    follows_admin: follows,
    categories: categories.map(({ id, key, names }) => ({
      id,
      key,
      names,
      new: fresh.includes(id),
    })),
  };
}

/**
 * The server's answer to `PUT /api/walking-order`: the own order as sent, the moved category no
 * longer new, the others as `before` had them.
 */
export function savedOrder(before: Schemas['WalkingOrder']) {
  return async (request: Request): Promise<Schemas['WalkingOrder']> => {
    const { category_ids, moved_id } = (await request.json()) as Schemas['WalkingOrderSave'];
    const byId = new Map(before.categories.map((category) => [category.id, category]));
    return {
      follows_admin: false,
      categories: category_ids.map((id) => {
        const category = byId.get(id);
        if (!category) throw new Error(`unknown category ${id}`);
        return { ...category, new: category.new && id !== moved_id };
      }),
    };
  };
}
