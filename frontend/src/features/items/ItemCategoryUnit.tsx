import { useTranslation } from 'react-i18next';
import type { Category } from '@/features/reference/api';
import { categoryName, unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import type { ItemSummary } from './api';

/**
 * The grey line under an item's name in the lists and pickers: its category and base unit,
 * "Milchprodukte & Eier · ml" (ING-03), so it shows where the item sorts on a shopping
 * list. While its category is unknown (not loaded yet), only the unit shows.
 */
export function ItemCategoryUnit({
  item,
  categories,
}: {
  item: Pick<ItemSummary, 'category_id' | 'base_unit'>;
  categories: readonly Category[];
}) {
  const { t } = useTranslation();
  const language = useLanguage();
  const category = categories.find(({ id }) => id === item.category_id);

  return (
    <span className="text-sm text-muted-foreground">
      {category ? `${categoryName(category, language)} · ` : ''}
      {unitLabel(t, item.base_unit)}
    </span>
  );
}
