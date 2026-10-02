import { useTranslation } from 'react-i18next';
import { categoryName, unitLabel } from '@/features/reference/labels';
import type { IngredientSummary } from './api';

/**
 * The grey line under an ingredient's name in the lists and pickers: its category and base unit,
 * "Milchprodukte & Eier · ml" (ING-03), so it shows where the ingredient sorts on a shopping
 * list. `categoryKeys` maps category ids to keys; while a category is unknown, only the unit shows.
 */
export function IngredientCategoryUnit({
  ingredient,
  categoryKeys,
}: {
  ingredient: Pick<IngredientSummary, 'category_id' | 'base_unit'>;
  categoryKeys: ReadonlyMap<string, string>;
}) {
  const { t } = useTranslation();
  const key = categoryKeys.get(ingredient.category_id);

  return (
    <span className="text-sm text-muted-foreground">
      {key ? `${categoryName(t, key)} · ` : ''}
      {unitLabel(t, ingredient.base_unit)}
    </span>
  );
}
