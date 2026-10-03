import { NativeSelectOption } from '@/components/ui/native-select';
import { useLanguage } from '@/i18n';
import type { Category } from './api';
import { pickableCategories } from './categories';
import { categoryName } from './labels';

interface CategoryOptionsProps {
  categories: readonly Category[];
  /** The category the select shows. */
  selected: string;
}

/**
 * The options of a category select (ING-02, LIST-06): the categories that can be picked, in
 * walking order. A selected category that can't be picked (*Uncategorized*, or one deleted
 * meanwhile) comes first, disabled, so it shows as the current value without being offered.
 */
export function CategoryOptions({ categories, selected }: CategoryOptionsProps) {
  const language = useLanguage();
  const pickable = pickableCategories(categories);
  const current = categories.find(
    (category) => category.id === selected && !pickable.includes(category),
  );

  return (
    <>
      {current && (
        <NativeSelectOption value={current.id} disabled>
          {categoryName(current, language)}
        </NativeSelectOption>
      )}
      {pickable.map((category) => (
        <NativeSelectOption key={category.id} value={category.id}>
          {categoryName(category, language)}
        </NativeSelectOption>
      ))}
    </>
  );
}
