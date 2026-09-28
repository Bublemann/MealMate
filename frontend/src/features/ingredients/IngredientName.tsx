import { ScanBarcode } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { IngredientSummary } from './api';

/**
 * An ingredient's name as the lists and pickers show it: the brand muted in brackets after it and
 * a small barcode icon for one with a barcode, so two brands of the same thing are told apart at a
 * glance. Plain inline text, so it reads (and is named) "Milch (Weidehof), with barcode".
 */
export function IngredientName({
  ingredient,
}: {
  ingredient: Pick<IngredientSummary, 'name' | 'brand' | 'barcode'>;
}) {
  const { t } = useTranslation();

  return (
    <span className="break-words">
      <span className="font-medium">{ingredient.name}</span>
      {ingredient.brand && (
        <>
          {' '}
          <span className="text-muted-foreground">({ingredient.brand})</span>
        </>
      )}
      {ingredient.barcode && (
        <>
          {' '}
          <ScanBarcode
            aria-hidden="true"
            className="inline size-4 align-[-0.125em] text-muted-foreground"
          />
          <span className="sr-only">{t('ingredients.hasBarcode')}</span>
        </>
      )}
    </span>
  );
}
