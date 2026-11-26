import type { Category } from './api';

/** *Other* (REF-01): the default of new items and free-text items; it can't be deleted. */
export const OTHER_KEY = 'other';
/**
 * *Uncategorized* (REF-01): it takes the items of a deleted category. It is in the walking
 * order like any other category, but is never picked by hand, renamed or deleted.
 */
export const UNCATEGORIZED_KEY = 'uncategorized';

type CategoryState = Pick<Category, 'key' | 'deleted'>;

/**
 * The walking order admins see and change: the categories that aren't deleted (D-30),
 * *Uncategorized* included.
 */
export function notDeletedCategories<C extends CategoryState>(categories: readonly C[]): C[] {
  return categories.filter((category) => !category.deleted);
}

/**
 * What an item or a free-text item can be put into, in walking order (ING-02, LIST-06):
 * neither a deleted category (D-30) nor *Uncategorized*, where nothing is put on purpose.
 */
export function pickableCategories<C extends CategoryState>(categories: readonly C[]): C[] {
  return notDeletedCategories(categories).filter((category) => category.key !== UNCATEGORIZED_KEY);
}

/**
 * What the Items tab's filter panel offers, in walking order (ING-03): what can be picked,
 * and *Uncategorized* at its place while it holds items, or while it is among `checked`, so
 * that it can be unticked. Never a deleted category (D-30).
 */
export function filterableCategories<C extends CategoryState & Pick<Category, 'id' | 'item_count'>>(
  categories: readonly C[],
  checked: readonly string[],
): C[] {
  return notDeletedCategories(categories).filter(
    (category) =>
      category.key !== UNCATEGORIZED_KEY ||
      category.item_count > 0 ||
      checked.includes(category.id),
  );
}
