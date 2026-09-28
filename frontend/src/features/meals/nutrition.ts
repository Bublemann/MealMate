import type { TFunction } from 'i18next';
import { ingredientLabel } from '@/features/ingredients/label';
import { NUTRIENT_KEYS, nutrientLabel, type NutrientKey } from '@/features/ingredients/nutrients';
import type { Language } from '@/i18n';
import { formatList } from '@/i18n/format';
import type { MealNutritionMissing } from './api';

function isNutrientKey(key: string | null): key is NutrientKey {
  return (NUTRIENT_KEYS as readonly string[]).includes(key ?? '');
}

/**
 * What is missing, one line per ingredient and reason (NUT-04): "Salt: no amount", "Flour:
 * Calories and Fat unknown", each ingredient named with its brand. The lines keep the server's
 * order.
 */
export function missingLines(
  t: TFunction,
  language: Language,
  missing: readonly MealNutritionMissing[],
): string[] {
  const groups = new Map<string, { name: string; reason: string; nutrients: string[] }>();
  for (const entry of missing) {
    const key = `${entry.ingredient_id}:${entry.reason}`;
    const group = groups.get(key) ?? {
      name: ingredientLabel(entry.ingredient_name, entry.ingredient_brand),
      reason: entry.reason,
      nutrients: [],
    };
    if (isNutrientKey(entry.nutrient)) group.nutrients.push(nutrientLabel(t, entry.nutrient));
    groups.set(key, group);
  }
  return [...groups.values()].map(({ name, reason, nutrients }) => {
    if (reason === 'no_amount') return t('meals.nutrition.reason.no_amount', { name });
    if (reason === 'not_convertible') return t('meals.nutrition.reason.not_convertible', { name });
    return nutrients.length > 0
      ? t('meals.nutrition.reason.unknown_value', {
          name,
          nutrients: formatList(nutrients, language),
        })
      : t('meals.nutrition.reason.unknown_values', { name });
  });
}
