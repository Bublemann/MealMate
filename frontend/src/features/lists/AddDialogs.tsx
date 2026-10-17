import { useRef, useState, type FormEvent, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { IngredientSummary } from '@/features/ingredients/api';
import { ingredientLabel } from '@/features/ingredients/label';
import { useCategories, type Unit } from '@/features/reference/api';
import { useLanguage } from '@/i18n';
import { fieldErrorMessages } from '@/i18n/errors';
import { formatNumber, parseAmount } from '@/i18n/format';
import { testIds } from '@/testIds';
import { AmountFields, FreeTextFields } from './ExtraItemFields';
import { otherCategoryId } from './format';

/** What the amount pop-up adds: no amount, or an amount in a unit. */
export interface AmountValue {
  amount: number | null;
  unit: Unit;
}

interface AmountDialogProps {
  /** The ingredient to add; null closes the pop-up. */
  ingredient: IngredientSummary | null;
  /** The amount it opens with (none: empty), e.g. the last amount of a due item (D-42). */
  initialAmount?: number | null;
  /** The unit it opens with; without one, the ingredient's base unit (REF-02). */
  initialUnit?: Unit | null;
  /** Why the server refused it the last time: field errors show next to their field. */
  error?: Error | null;
  /** Offline: "Hinzufügen" is inactive (SYNC-03). */
  disabled?: boolean;
  onAdd: (value: AmountValue) => void;
  onCancel: () => void;
  onCloseAutoFocus?: (event: Event) => void;
}

/**
 * The amount pop-up of a linked item (LIST-06, D-41): the ingredient's name, the optional amount
 * and the units that fit it (D-32), "Hinzufügen". The cursor starts in the amount.
 */
export function AmountDialog({
  ingredient,
  initialAmount = null,
  initialUnit = null,
  error = null,
  disabled = false,
  onAdd,
  onCancel,
  onCloseAutoFocus,
}: AmountDialogProps) {
  const amountRef = useRef<HTMLInputElement>(null);

  return (
    <Dialog open={ingredient !== null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent
        data-testid={testIds.amountDialog}
        aria-describedby={undefined}
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          amountRef.current?.focus();
        }}
        onCloseAutoFocus={onCloseAutoFocus}
      >
        {ingredient && (
          <AmountForm
            key={ingredient.id}
            ingredient={ingredient}
            initialAmount={initialAmount}
            initialUnit={initialUnit ?? ingredient.base_unit}
            error={error}
            disabled={disabled}
            amountRef={amountRef}
            onAdd={onAdd}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

interface AmountFormProps {
  ingredient: IngredientSummary;
  initialAmount: number | null;
  initialUnit: Unit;
  error: Error | null;
  disabled: boolean;
  amountRef: RefObject<HTMLInputElement | null>;
  onAdd: (value: AmountValue) => void;
}

function AmountForm({
  ingredient,
  initialAmount,
  initialUnit,
  error,
  disabled,
  amountRef,
  onAdd,
}: AmountFormProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const name = ingredientLabel(ingredient.name, ingredient.brand);
  const [amount, setAmount] = useState(() =>
    initialAmount === null ? '' : formatNumber(initialAmount, language, { useGrouping: false }),
  );
  const [unit, setUnit] = useState<Unit>(initialUnit);
  const [invalid, setInvalid] = useState(false);
  const serverFields = fieldErrorMessages(t, error);
  const otherError =
    error !== null &&
    (Object.keys(serverFields).length === 0 ||
      Object.keys(serverFields).some((field) => field !== 'amount' && field !== 'unit'));

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled) return;
    const trimmed = amount.trim();
    if (trimmed === '') {
      onAdd({ amount: null, unit });
      return;
    }
    const value = parseAmount(trimmed);
    setInvalid(value === null);
    if (value !== null) onAdd({ amount: value, unit });
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-label={name} className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>{name}</DialogTitle>
      </DialogHeader>
      <AmountFields
        amountRef={amountRef}
        amount={amount}
        unit={unit}
        baseUnit={ingredient.base_unit}
        name={name}
        onAmountChange={(value) => {
          setInvalid(false);
          setAmount(value);
        }}
        onUnitChange={setUnit}
        amountError={invalid ? t('error.field.invalid_format') : serverFields.amount}
        unitError={serverFields.unit}
      />
      {otherError && <ErrorAlert error={error} />}
      <DialogFooter>
        <Button type="submit" disabled={disabled}>
          {t('lists.addField.add')}
        </Button>
      </DialogFooter>
    </form>
  );
}

/** What the free-text pop-up adds; empty texts are left out. */
export interface FreeTextValue {
  amountText: string;
  /** '' until the categories have loaded. */
  categoryId: string;
}

interface FreeTextDialogProps {
  /** The item's text; null closes the pop-up. */
  text: string | null;
  /** What it opens with again after an error. */
  initial?: FreeTextValue | null;
  error?: Error | null;
  disabled?: boolean;
  onAdd: (value: FreeTextValue) => void;
  onCancel: () => void;
  onCloseAutoFocus?: (event: Event) => void;
}

/**
 * The free-text pop-up (LIST-06, D-41): the text as its title, the optional free-text amount and
 * the category (*Other* by default; the pickable categories in walking order, REF-01),
 * "Hinzufügen". The cursor starts in the amount.
 */
export function FreeTextDialog({
  text,
  initial = null,
  error = null,
  disabled = false,
  onAdd,
  onCancel,
  onCloseAutoFocus,
}: FreeTextDialogProps) {
  const amountRef = useRef<HTMLInputElement>(null);

  return (
    <Dialog open={text !== null} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent
        data-testid={testIds.freeTextDialog}
        aria-describedby={undefined}
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          amountRef.current?.focus();
        }}
        onCloseAutoFocus={onCloseAutoFocus}
      >
        {text !== null && (
          <FreeTextForm
            text={text}
            initial={initial}
            error={error}
            disabled={disabled}
            amountRef={amountRef}
            onAdd={onAdd}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

interface FreeTextFormProps {
  text: string;
  initial: FreeTextValue | null;
  error: Error | null;
  disabled: boolean;
  amountRef: RefObject<HTMLInputElement | null>;
  onAdd: (value: FreeTextValue) => void;
}

function FreeTextForm({ text, initial, error, disabled, amountRef, onAdd }: FreeTextFormProps) {
  const { t } = useTranslation();
  const categories = useCategories();
  const [amountText, setAmountText] = useState(initial?.amountText ?? '');
  const [categoryId, setCategoryId] = useState(initial?.categoryId ?? '');
  const chosenCategory = categoryId || otherCategoryId(categories.data);
  const serverFields = fieldErrorMessages(t, error);
  const shown = ['amount_text', 'category_id'];
  const otherError =
    error !== null &&
    (Object.keys(serverFields).length === 0 ||
      Object.keys(serverFields).some((field) => !shown.includes(field)));

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (disabled) return;
    onAdd({ amountText: amountText.trim(), categoryId: chosenCategory });
  }

  return (
    <form onSubmit={onSubmit} noValidate aria-label={text} className="flex flex-col gap-4">
      <DialogHeader>
        <DialogTitle>{text}</DialogTitle>
      </DialogHeader>
      <FreeTextFields
        amountTextRef={amountRef}
        amountText={amountText}
        categoryId={chosenCategory}
        onAmountTextChange={setAmountText}
        onCategoryChange={setCategoryId}
        amountTextError={serverFields.amount_text}
        categoryError={serverFields.category_id}
      />
      {otherError && <ErrorAlert error={error} />}
      <DialogFooter>
        <Button type="submit" disabled={disabled}>
          {t('lists.addField.add')}
        </Button>
      </DialogFooter>
    </form>
  );
}
