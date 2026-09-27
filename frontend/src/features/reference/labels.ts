import type { TFunction } from 'i18next';
import i18n from '@/i18n';

// Seeded reference data is translated through keys (I18N-04). The keys come from the server as
// plain strings, so a key this app version doesn't know yet is shown as it is.
function translated(t: TFunction, key: string, fallback: string): string {
  // The key is checked at runtime; the cast only satisfies the typed `t`.
  return i18n.exists(key) ? t(key as 'category.other') : fallback;
}

/** "Obst & Gemüse" for `fruit_vegetables` (REF-01). */
export function categoryName(t: TFunction, key: string): string {
  return translated(t, `category.${key}`, key);
}

/** "Stk." / "pcs" for `piece` (REF-02). */
export function unitLabel(t: TFunction, unit: string): string {
  return translated(t, `unit.${unit}`, unit);
}

/** A seeded cuisine by its key, a user-added one by its name (REF-03). */
export function cuisineName(
  t: TFunction,
  cuisine: { key?: string | null; name?: string | null },
): string {
  if (cuisine.key) return translated(t, `cuisine.${cuisine.key}`, cuisine.key);
  return cuisine.name ?? '';
}
