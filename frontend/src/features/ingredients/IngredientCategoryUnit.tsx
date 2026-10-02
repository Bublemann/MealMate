import { useTranslation } from 'react-i18next';
import type { Category } from '@/features/reference/api';
import { categoryName, unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import type { IngredientSummary } from './api';

/**
 * The grey line under an ingredient's name in the lists and pickers: its category and base unit,
 * "Milchprodukte & Eier · ml" (ING-03), so it shows where the ingredient sorts on a shopping
 * list. `categories` holds the categories by id; while a category is unknown, only the unit shows.
 */
export function IngredientCategoryUnit({
  ingredient,
  categories,
}: {
  ingredient: Pick<IngredientSummary, 'category_id' | 'base_unit'>;
  categories: ReadonlyMap<string, Category>;
}) {
  const { t } = useTranslation();
  const language = useLanguage();
  const category = categories.get(ingredient.category_id);

  return (
    <span className="text-sm text-muted-foreground">
      {category ? `${categoryName(category, language)} · ` : ''}
      {unitLabel(t, ingredient.base_unit)}
    </span>
  );
}
