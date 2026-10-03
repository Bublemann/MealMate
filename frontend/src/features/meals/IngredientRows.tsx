import { ArrowDown, ArrowUp, CircleAlert, X } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import type { IngredientSummary } from '@/features/ingredients/api';
import { IngredientPicker } from '@/features/ingredients/IngredientPicker';
import { ingredientLabel } from '@/features/ingredients/label';
import type { Unit } from '@/features/reference/api';
import { unitLabel } from '@/features/reference/labels';
import { useUnitChoice } from '@/features/reference/units';
import { testIds } from '@/testIds';
import { moved, newRow, withAmountText, type RowState } from './form';
import { MealScan } from './MealScan';

interface IngredientRowsProps {
  rows: RowState[];
  onChange: (rows: RowState[]) => void;
  /** The error for a path such as `ingredients.0.amount`. */
  fieldError: (path: string) => string | undefined;
}

/**
 * The meal's ingredient rows (MEAL-02): amount, unit and note per row, in an order the user
 * sets. A row offers only the units that fit its ingredient's base unit (REF-02); an older amount
 * that doesn't fit stays as it is, marked, until the user picks one that fits. New rows come from
 * the ingredient picker, which can also create an ingredient, and from the scan (MEAL-03).
 */
export function IngredientRows({ rows, onChange, fieldError }: IngredientRowsProps) {
  const { t } = useTranslation();
  // A new picker after each pick starts with an empty search.
  const [pickerKey, setPickerKey] = useState(0);

  function update(index: number, row: RowState) {
    onChange(rows.map((current, i) => (i === index ? row : current)));
  }

  function onPick(ingredient: IngredientSummary) {
    onChange([...rows, newRow(ingredient)]);
    setPickerKey((key) => key + 1);
  }

  return (
    <fieldset className="flex flex-col gap-3">
      <legend className="mb-2 text-lg font-semibold">{t('meals.field.ingredients')}</legend>
      {fieldError('ingredients') && <RowError message={fieldError('ingredients')} />}
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('meals.field.ingredientsEmpty')}</p>
      ) : (
        <ol className="flex flex-col gap-3">
          {rows.map((row, index) => (
            <IngredientRow
              key={row.key}
              row={row}
              first={index === 0}
              last={index === rows.length - 1}
              path={`ingredients.${index}`}
              fieldError={fieldError}
              onChange={(next) => update(index, next)}
              onMove={(offset) => onChange(moved(rows, index, offset))}
              onRemove={() => onChange(rows.filter((_, i) => i !== index))}
            />
          ))}
        </ol>
      )}
      {/* Enter in the search field picks nothing and must not save the whole meal. Dialogs
          opened from the picker and the scan (the ingredient form, the Open Food Facts search,
          the scanner) are portals: their key events bubble through here in React, but their
          Enter must still submit. */}
      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
      <div
        className="rounded-xl border border-dashed p-3"
        onKeyDown={(event) => {
          if (
            event.key === 'Enter' &&
            event.target instanceof HTMLInputElement &&
            event.currentTarget.contains(event.target)
          ) {
            event.preventDefault();
          }
        }}
      >
        <IngredientPicker
          key={pickerKey}
          label={t('meals.field.addIngredient')}
          onSelect={onPick}
        />
        <MealScan onIngredient={onPick} />
      </div>
    </fieldset>
  );
}

interface IngredientRowProps {
  row: RowState;
  first: boolean;
  last: boolean;
  path: string;
  fieldError: (path: string) => string | undefined;
  onChange: (row: RowState) => void;
  onMove: (offset: -1 | 1) => void;
  onRemove: () => void;
}

function IngredientRow({
  row,
  first,
  last,
  path,
  fieldError,
  onChange,
  onMove,
  onRemove,
}: IngredientRowProps) {
  const { t } = useTranslation();
  const name = ingredientLabel(row.ingredient.name, row.ingredient.brand);
  const rowError = fieldError(`${path}.ingredient_id`) ?? fieldError(path);
  const unitChoice = useUnitChoice(
    row.ingredient.base_unit,
    row.unit,
    row.amountText.trim() !== '',
  );

  return (
    <li
      data-testid={testIds.mealIngredientRow}
      aria-label={t('meals.row.label', { name })}
      className="flex flex-col gap-3 rounded-xl border bg-card p-3"
    >
      <div className="flex items-center gap-1">
        <span className="min-w-0 flex-1 font-medium break-words">{name}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={t('meals.row.moveUp', { name })}
          disabled={first}
          onClick={() => onMove(-1)}
        >
          <ArrowUp aria-hidden="true" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={t('meals.row.moveDown', { name })}
          disabled={last}
          onClick={() => onMove(1)}
        >
          <ArrowDown aria-hidden="true" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          aria-label={t('meals.row.remove', { name })}
          onClick={onRemove}
        >
          <X aria-hidden="true" />
        </Button>
      </div>
      {rowError && <RowError message={rowError} />}
      <div className="grid grid-cols-2 gap-3">
        <FormField label={t('meals.row.amount')} error={fieldError(`${path}.amount`)}>
          {(control) => (
            <Input
              {...control}
              inputMode="decimal"
              autoComplete="off"
              value={row.amountText}
              onChange={(event) => onChange(withAmountText(row, event.target.value))}
            />
          )}
        </FormField>
        <FormField
          label={t('meals.row.unit')}
          error={
            unitChoice.fits ? fieldError(`${path}.unit`) : t('meals.row.unitMismatch', { name })
          }
        >
          {(control) => (
            <NativeSelect
              {...control}
              value={row.unit}
              onChange={(event) =>
                onChange({ ...row, unit: event.target.value as Unit | '', unitChosen: true })
              }
            >
              <NativeSelectOption value="" disabled={!unitChoice.withoutUnitFits}>
                {t('meals.row.unitNone')}
              </NativeSelectOption>
              {unitChoice.options.map(({ unit, disabled }) => (
                <NativeSelectOption key={unit} value={unit} disabled={disabled}>
                  {unitLabel(t, unit)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          )}
        </FormField>
      </div>
      <FormField label={t('meals.row.note')} error={fieldError(`${path}.note`)}>
        {(control) => (
          <Input
            {...control}
            autoComplete="off"
            maxLength={80}
            placeholder={t('meals.row.notePlaceholder')}
            value={row.note}
            onChange={(event) => onChange({ ...row, note: event.target.value })}
          />
        )}
      </FormField>
    </li>
  );
}

function RowError({ message }: { message?: string }) {
  return (
    <p className="flex items-start gap-1.5 text-sm font-medium text-destructive">
      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
      {message}
    </p>
  );
}
