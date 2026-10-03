import { useTranslation } from 'react-i18next';
import { FormField } from '@/components/FormField';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { useCategories, useUnits, type Unit } from '@/features/reference/api';
import { pickableCategories } from '@/features/reference/categories';
import { categoryName, unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';

/** The longest free-text amount the server takes (LIST-06). */
export const MAX_AMOUNT_TEXT_LENGTH = 30;

interface AmountFieldsProps {
  amount: string;
  unit: Unit;
  onAmountChange: (amount: string) => void;
  onUnitChange: (unit: Unit) => void;
  amountError?: string;
  unitError?: string;
}

/** Optional amount and unit of an extra item linked to an ingredient (LIST-06). */
export function AmountFields({
  amount,
  unit,
  onAmountChange,
  onUnitChange,
  amountError,
  unitError,
}: AmountFieldsProps) {
  const { t } = useTranslation();
  const units = useUnits();

  return (
    <div className="grid grid-cols-2 gap-3">
      <FormField label={t('lists.extra.amount')} error={amountError}>
        {(control) => (
          <Input
            {...control}
            name="amount"
            inputMode="decimal"
            autoComplete="off"
            maxLength={12}
            value={amount}
            onChange={(event) => onAmountChange(event.target.value)}
          />
        )}
      </FormField>
      <FormField label={t('lists.extra.unit')} error={unitError}>
        {(control) => (
          <NativeSelect
            {...control}
            name="unit"
            value={unit}
            onChange={(event) => onUnitChange(event.target.value as Unit)}
          >
            {units.data?.map((info) => (
              <NativeSelectOption key={info.unit} value={info.unit}>
                {unitLabel(t, info.unit)}
              </NativeSelectOption>
            ))}
            {/* The chosen unit before the units have loaded. */}
            {!units.data && (
              <NativeSelectOption value={unit}>{unitLabel(t, unit)}</NativeSelectOption>
            )}
          </NativeSelect>
        )}
      </FormField>
    </div>
  );
}

interface FreeTextFieldsProps {
  amountText: string;
  /** '' until the categories have loaded. */
  categoryId: string;
  onAmountTextChange: (amountText: string) => void;
  onCategoryChange: (categoryId: string) => void;
  amountTextError?: string;
  categoryError?: string;
  /** Without the category (an item changed while shopping keeps its category). */
  withoutCategory?: boolean;
}

/**
 * Optional free-text amount and the category of a free-text extra item (LIST-06). Neither a
 * deleted category nor *Uncategorized* is offered; an item already in a deleted one shows it.
 */
export function FreeTextFields({
  amountText,
  categoryId,
  onAmountTextChange,
  onCategoryChange,
  amountTextError,
  categoryError,
  withoutCategory = false,
}: FreeTextFieldsProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const categories = useCategories();
  const pickable = pickableCategories(categories.data ?? []);
  const unpickable = categories.data?.find(
    (category) => category.id === categoryId && !pickable.includes(category),
  );

  return (
    <div className="grid grid-cols-2 gap-3">
      <FormField label={t('lists.extra.amountText')} error={amountTextError}>
        {(control) => (
          <Input
            {...control}
            name="amount_text"
            autoComplete="off"
            maxLength={MAX_AMOUNT_TEXT_LENGTH}
            placeholder={t('lists.extra.amountTextPlaceholder')}
            value={amountText}
            onChange={(event) => onAmountTextChange(event.target.value)}
          />
        )}
      </FormField>
      {!withoutCategory && (
        <FormField label={t('lists.extra.category')} error={categoryError}>
          {(control) => (
            <NativeSelect
              {...control}
              name="category_id"
              value={categoryId}
              onChange={(event) => onCategoryChange(event.target.value)}
            >
              {!categories.data && (
                <NativeSelectOption value="">{t('common.loading')}</NativeSelectOption>
              )}
              {unpickable && (
                <NativeSelectOption value={unpickable.id} disabled>
                  {categoryName(unpickable, language)}
                </NativeSelectOption>
              )}
              {pickable.map((category) => (
                <NativeSelectOption key={category.id} value={category.id}>
                  {categoryName(category, language)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          )}
        </FormField>
      )}
    </div>
  );
}
