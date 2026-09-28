import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Button } from '@/components/ui/button';
import { unitLabel } from '@/features/reference/labels';
import { useLanguage, type Language } from '@/i18n';
import { formatNumber } from '@/i18n/format';
import { testIds } from '@/testIds';
import { usePendingUpdate, type Ingredient, type PendingUpdateField } from './api';
import { ingredientLabel } from './label';
import { formatNutrient, NUTRIENT_KEYS, nutrientLabel, type NutrientKey } from './nutrients';

const TEXT_FIELD_LABELS = {
  name: 'ingredients.field.name',
  brand: 'ingredients.field.brand',
  quantity_text: 'ingredients.field.quantityText',
  pack_quantity: 'ingredients.field.packQuantity',
  pack_unit: 'ingredients.field.packUnit',
} as const;

function nutrientKeyOf(field: string): NutrientKey | null {
  const key = field.startsWith('nutrients.') ? field.slice('nutrients.'.length) : '';
  return (NUTRIENT_KEYS as readonly string[]).includes(key) ? (key as NutrientKey) : null;
}

/** "Calories: 165 kcal → 158 kcal": a field of a pending update with its units. */
function describeChange(t: TFunction, language: Language, change: PendingUpdateField): string {
  const nutrient = nutrientKeyOf(change.field);
  const format = (value: string | number | null): string => {
    if (value === null) return t('ingredients.pending.none');
    if (typeof value === 'string') {
      return change.field === 'pack_unit' ? unitLabel(t, value) : value;
    }
    return nutrient
      ? formatNutrient(t, language, nutrient, value)
      : formatNumber(value, language, { maximumFractionDigits: 3 });
  };
  const label = nutrient
    ? nutrientLabel(t, nutrient)
    : change.field in TEXT_FIELD_LABELS
      ? t(TEXT_FIELD_LABELS[change.field as keyof typeof TEXT_FIELD_LABELS])
      : change.field;
  return t('ingredients.pending.change', {
    field: label,
    current: format(change.current),
    proposed: format(change.proposed),
  });
}

interface PendingUpdateHintProps {
  ingredient: Ingredient;
  fields: PendingUpdateField[];
}

/**
 * BAR-06: Open Food Facts has other values for fields a user changed. They are only taken on
 * "Apply"; "Ignore" keeps the user's values until Open Food Facts changes the product again.
 */
export function PendingUpdateHint({ ingredient, fields }: PendingUpdateHintProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const apply = usePendingUpdate(ingredient.id, 'apply');
  const ignore = usePendingUpdate(ingredient.id, 'ignore');
  const name = ingredientLabel(ingredient.name, ingredient.brand);
  const busy = apply.isPending || ignore.isPending;

  return (
    <div
      data-testid={testIds.pendingUpdate}
      className="flex flex-col gap-2 rounded-lg border bg-muted p-3"
    >
      <p className="text-sm font-medium">{t('ingredients.pending.title')}</p>
      <ul className="flex flex-col gap-1 text-sm">
        {fields.map((change) => (
          <li key={change.field} className="break-words">
            {describeChange(t, language, change)}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button
          size="compact"
          data-testid={testIds.applyPendingUpdate}
          aria-label={t('ingredients.pending.applyLabel', { name })}
          disabled={busy}
          onClick={() => apply.mutate()}
        >
          {t('ingredients.pending.apply')}
        </Button>
        <Button
          size="compact"
          variant="outline"
          data-testid={testIds.ignorePendingUpdate}
          aria-label={t('ingredients.pending.ignoreLabel', { name })}
          disabled={busy}
          onClick={() => ignore.mutate()}
        >
          {t('ingredients.pending.ignore')}
        </Button>
      </div>
      <ErrorAlert error={apply.error ?? ignore.error} />
    </div>
  );
}
