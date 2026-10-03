import { useTranslation } from 'react-i18next';
import { FormField } from '@/components/FormField';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import type { BaseUnit } from '@/features/ingredients/api';
import { useCategories, useUnits, type Unit } from '@/features/reference/api';
import { categoryName, unitLabel } from '@/features/reference/labels';
import { fittingUnits, unitFits } from '@/features/reference/units';
import { useLanguage } from '@/i18n';

/** The longest free-text amount the server takes (LIST-06). */
export const MAX_AMOUNT_TEXT_LENGTH = 30;

interface AmountFieldsProps {
  amount: string;
  unit: Unit;
  /**
   * The base unit the item is calculated with: only the units that fit it are offered (REF-02).
   * Null when it isn't known (a copy kept offline by an older app version): every unit then.
   */
  baseUnit: BaseUnit | null;
  /** The ingredient's name, for the mark of a unit that doesn't fit. */
  name: string;
  onAmountChange: (amount: string) => void;
  onUnitChange: (unit: Unit) => void;
  amountError?: string;
  unitError?: string;
}

/**
 * Optional amount and unit of an extra item linked to an ingredient (LIST-06). An older amount
 * whose unit doesn't fit is marked, and stays as it is until the user picks one that fits.
 */
export function AmountFields({
  amount,
  unit,
  baseUnit,
  name,
  onAmountChange,
  onUnitChange,
  amountError,
  unitError,
}: AmountFieldsProps) {
  const { t } = useTranslation();
  const units = useUnits();
  const fitting =
    units.data &&
    (baseUnit ? fittingUnits(units.data, baseUnit) : units.data.map((info) => info.unit));
  const fits =
    !units.data || !baseUnit || unitFits(units.data, baseUnit, unit, amount.trim() !== '');

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
      <FormField
        label={t('lists.extra.unit')}
        error={fits ? unitError : t('lists.extra.unitMismatch', { name })}
      >
        {(control) => (
          <NativeSelect
            {...control}
            name="unit"
            value={unit}
            onChange={(event) => onUnitChange(event.target.value as Unit)}
          >
            {fitting?.map((option) => (
              <NativeSelectOption key={option} value={option}>
                {unitLabel(t, option)}
              </NativeSelectOption>
            ))}
            {/* The chosen unit before the units have loaded, or one that doesn't fit: shown, but
                once changed it can't be chosen again. */}
            {!fitting?.includes(unit) && (
              <NativeSelectOption value={unit} disabled={fitting !== undefined}>
                {unitLabel(t, unit)}
              </NativeSelectOption>
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

/** Optional free-text amount and the category of a free-text extra item (LIST-06). */
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
              {categories.data?.map((category) => (
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
