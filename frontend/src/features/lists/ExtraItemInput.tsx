import { Plus } from 'lucide-react';
import { useId, useRef, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Button } from '@/components/ui/button';
import { RemovableChip } from '@/components/ui/chip';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useIngredients, type IngredientSummary } from '@/features/ingredients/api';
import { IngredientCategoryUnit } from '@/features/ingredients/IngredientCategoryUnit';
import { IngredientName } from '@/features/ingredients/IngredientName';
import { ingredientLabel } from '@/features/ingredients/label';
import { useCategories, useUnits, type Unit } from '@/features/reference/api';
import { useConnected, useQueueOp } from '@/features/sync/context';
import { categoryName } from '@/features/reference/labels';
import { keptUnit } from '@/features/reference/units';
import { useLanguage } from '@/i18n';
import { fieldErrorMessages } from '@/i18n/errors';
import { parseAmount } from '@/i18n/format';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { uuidv7 } from '@/lib/uuid';
import { testIds } from '@/testIds';
import { shoppingOps, stampOp, useAddExtraItem, type ExtraItemCreate } from './api';
import { AmountFields, FreeTextFields } from './ExtraItemFields';
import { otherCategoryId } from './format';

/** Suggestions shown under the input; typing more narrows them down. */
const MAX_SUGGESTIONS = 6;
/** The longest free-text item the server takes (LIST-06). */
const MAX_TEXT_LENGTH = 80;

/**
 * LIST-06: one input with autocomplete over the ingredients. Picking one adds a linked item
 * (optional amount and unit) that merges with the same ingredient from the meals; Enter or "Add"
 * without a pick adds what was typed as a free-text item (optional amount text, category Other
 * unless another is chosen).
 *
 * The item keeps its id until it is added or changed, so sending it again after an error (e.g. a
 * timeout whose request did reach the server) doesn't add it twice. While shopping (SHOP-02) a
 * free-text item is an op of the outbox with its category's key, which works offline too
 * (SYNC-03); linked items need a connection, so the suggestions are off while offline. On a draft
 * nothing can be added offline: the form is disabled.
 */
export function ExtraItemInput({
  listId,
  shopping = false,
}: {
  listId: string;
  shopping?: boolean;
}) {
  const { t } = useTranslation();
  const language = useLanguage();
  const inputId = useId();
  const hintId = `${inputId}-hint`;
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState('');
  const [picked, setPicked] = useState<IngredientSummary | null>(null);
  const [amount, setAmount] = useState('');
  const [unit, setUnit] = useState<Unit>('g');
  const [amountText, setAmountText] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [amountInvalid, setAmountInvalid] = useState(false);
  /** The id of the item as it is typed; null until it is first sent. */
  const pendingId = useRef<string | null>(null);
  /** A free-text item is being stored in the outbox (SHOP-02). */
  const queuing = useRef(false);
  const add = useAddExtraItem(listId);
  const queue = useQueueOp(listId);
  const connected = useConnected();
  const categories = useCategories();
  const units = useUnits();
  const debounced = useDebouncedValue(text.trim());
  const searching = debounced !== '' && !picked && connected;
  const suggestions = useIngredients(debounced, { enabled: searching });
  const matches = searching ? (suggestions.data ?? []).slice(0, MAX_SUGGESTIONS) : [];
  const typed = text.trim();
  const pickedLabel = picked ? ingredientLabel(picked.name, picked.brand) : null;
  const pickedCategory = picked
    ? categories.data?.find(({ id }) => id === picked.category_id)
    : undefined;
  const chosenCategory = categoryId || otherCategoryId(categories.data);
  const serverFields = fieldErrorMessages(t, add.error);
  const shownFields = picked ? ['amount', 'unit'] : ['text', 'amount_text', 'category_id'];
  const showAlert =
    add.error !== null &&
    (Object.keys(serverFields).length === 0 ||
      Object.keys(serverFields).some((field) => !shownFields.includes(field)));

  /** The item changed: a new id the next time it is sent. */
  function edited() {
    pendingId.current = null;
  }

  function pick(ingredient: IngredientSummary) {
    add.reset();
    edited();
    setPicked(ingredient);
    // Another ingredient keeps the unit while it fits, else it starts with its base unit (REF-02).
    const kept = units.data ? keptUnit(units.data, ingredient.base_unit, unit) : '';
    setUnit(kept || ingredient.base_unit);
    setAmount('');
    setAmountInvalid(false);
  }

  function unpick() {
    add.reset();
    edited();
    setPicked(null);
    setAmountInvalid(false);
    inputRef.current?.focus();
  }

  function clear() {
    edited();
    setText('');
    setPicked(null);
    setAmount('');
    setAmountText('');
    setCategoryId('');
    setAmountInvalid(false);
    inputRef.current?.focus();
  }

  function itemId(): string {
    pendingId.current ??= uuidv7();
    return pendingId.current;
  }

  function body(): ExtraItemCreate | null {
    if (picked) {
      const trimmed = amount.trim();
      if (trimmed === '') return { id: itemId(), ingredient_id: picked.id };
      const value = parseAmount(trimmed);
      if (value === null) return null;
      return { id: itemId(), ingredient_id: picked.id, amount: value, unit };
    }
    return {
      id: itemId(),
      text: typed,
      ...(amountText.trim() ? { amount_text: amountText.trim() } : {}),
      ...(chosenCategory ? { category_id: chosenCategory } : {}),
    };
  }

  /**
   * SHOP-02: stored in the outbox at once, sent when there is a connection. What was typed is
   * cleared only once the item is queued, so nothing is lost if it can't be (a message says so).
   */
  async function queueFreeText() {
    // A second Enter while the first is being stored must not add the item twice.
    if (queuing.current) return;
    queuing.current = true;
    const payload = {
      extra_id: uuidv7(),
      text: typed,
      ...(amountText.trim() ? { amount_text: amountText.trim() } : {}),
      ...(chosenCategory ? { category_id: chosenCategory } : {}),
    };
    try {
      if (await queue(shoppingOps.addExtra(payload, stampOp()))) clear();
    } finally {
      queuing.current = false;
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (add.isPending || (!picked && !typed)) return;
    if (shopping && !picked) {
      void queueFreeText();
      return;
    }
    if (!connected) return;
    const item = body();
    setAmountInvalid(item === null);
    if (item) add.mutate(item, { onSuccess: clear });
  }

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      aria-label={t('lists.extra.label')}
      className="rounded-xl border bg-card p-4"
    >
      {/* Offline, a draft can't change (SYNC-03): everything is disabled, nothing hidden. */}
      <fieldset
        disabled={!shopping && !connected}
        className="m-0 flex min-w-0 flex-col gap-3 border-0 p-0"
      >
        <div className="flex flex-col gap-2">
          {picked ? (
            <div className="flex flex-wrap items-center gap-2">
              <RemovableChip
                removeLabel={t('lists.extra.unpick', { name: pickedLabel })}
                onRemove={unpick}
              >
                {pickedLabel}
              </RemovableChip>
              {pickedCategory && (
                <span className="text-sm text-muted-foreground">
                  {categoryName(pickedCategory, language)}
                </span>
              )}
            </div>
          ) : (
            <>
              <Label htmlFor={inputId}>{t('lists.extra.label')}</Label>
              <Input
                ref={inputRef}
                id={inputId}
                data-testid={testIds.extraItemInput}
                autoComplete="off"
                enterKeyHint="done"
                maxLength={MAX_TEXT_LENGTH}
                aria-describedby={hintId}
                aria-invalid={serverFields.text ? true : undefined}
                value={text}
                onChange={(event) => {
                  add.reset();
                  edited();
                  setText(event.target.value);
                }}
              />
              <p id={hintId} className="text-sm text-muted-foreground">
                {serverFields.text ?? t('lists.extra.hint')}
              </p>
            </>
          )}
        </div>
        {matches.length > 0 && (
          <ul
            aria-label={t('lists.extra.suggestions')}
            className="flex flex-col divide-y rounded-lg border"
          >
            {matches.map((ingredient) => (
              <li key={ingredient.id}>
                <button
                  type="button"
                  onClick={() => pick(ingredient)}
                  className="flex min-h-(--tap-target) w-full flex-col items-start px-3 py-2 text-left outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
                >
                  <IngredientName ingredient={ingredient} />
                  <IngredientCategoryUnit
                    ingredient={ingredient}
                    categories={categories.data ?? []}
                  />
                </button>
              </li>
            ))}
          </ul>
        )}
        <ErrorAlert error={suggestions.error} />
        {picked && (
          <AmountFields
            amount={amount}
            unit={unit}
            baseUnit={picked.base_unit}
            name={pickedLabel ?? ''}
            onAmountChange={(value) => {
              edited();
              setAmountInvalid(false);
              setAmount(value);
            }}
            onUnitChange={(value) => {
              edited();
              setUnit(value);
            }}
            amountError={amountInvalid ? t('error.field.invalid_format') : serverFields.amount}
            unitError={serverFields.unit}
          />
        )}
        {!picked && typed && (
          <FreeTextFields
            amountText={amountText}
            categoryId={chosenCategory}
            onAmountTextChange={(value) => {
              edited();
              setAmountText(value);
            }}
            onCategoryChange={(value) => {
              edited();
              setCategoryId(value);
            }}
            amountTextError={serverFields.amount_text}
            categoryError={serverFields.category_id}
          />
        )}
        {showAlert && <ErrorAlert error={add.error} />}
        <Button
          type="submit"
          className="self-start"
          disabled={add.isPending || (!picked && !typed) || (picked !== null && !connected)}
          aria-label={
            picked || typed ? t('lists.extra.addLabel', { name: pickedLabel ?? typed }) : undefined
          }
        >
          <Plus aria-hidden="true" />
          {t('lists.extra.add')}
        </Button>
      </fieldset>
    </form>
  );
}
