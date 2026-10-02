import type { TFunction } from 'i18next';
import i18n, { type Language } from '@/i18n';
import type { Category } from './api';

// Units and seeded cuisines are translated through keys (I18N-04). The keys come from the server
// as plain strings, so a key this app version doesn't know yet is shown as it is.
function translated(t: TFunction, key: string, fallback: string): string {
  // The key is checked at runtime; the cast only satisfies the typed `t`.
  return i18n.exists(key) ? t(key as 'unit.g') : fallback;
}

/**
 * A category's name in the UI language, else in English (I18N-01): category names are data from
 * the server, not translations (I18N-04, D-31), so admins can add and rename categories.
 */
export function categoryName(category: Pick<Category, 'names'>, language: Language): string {
  // Widened: a UI language added later has no names until admins fill them in.
  const names: Partial<Record<string, string | null>> = category.names;
  return names[language] || category.names.en;
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
