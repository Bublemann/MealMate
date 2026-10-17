import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import {
  toSummary,
  useIngredients,
  type IngredientSearchResult,
  type IngredientSummary,
} from '@/features/ingredients/api';
import { IngredientCategoryUnit } from '@/features/ingredients/IngredientCategoryUnit';
import { IngredientFormDialog } from '@/features/ingredients/IngredientFormDialog';
import { IngredientName } from '@/features/ingredients/IngredientName';
import { useCategories, useUnits, type Unit } from '@/features/reference/api';
import { keptUnit } from '@/features/reference/units';
import { useConnected, useQueueOp } from '@/features/sync/context';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { cn } from '@/lib/utils';
import { uuidv7 } from '@/lib/uuid';
import { testIds } from '@/testIds';
import {
  AddField,
  FieldOption,
  FieldOptions,
  RESULT_BUTTON_CLASS,
  RESULT_LIST_CLASS,
} from './AddField';
import { AmountDialog, FreeTextDialog, type AmountValue, type FreeTextValue } from './AddDialogs';
import { shoppingOps, stampOp, useAddExtraItem, type ExtraItemCreate } from './api';
import { usePlus } from './usePlus';

/** Results shown under the field; typing more narrows them down. */
const MAX_RESULTS = 6;

/** What a pop-up opens with again when the server refused it: what was sent, and why. */
interface Retry {
  sent: ExtraItemCreate;
  error: Error;
}

/** The open pop-up of the item field. */
type ItemRequest =
  | { kind: 'amount'; ingredient: IngredientSummary; value: AmountValue; retry: Retry | null }
  | { kind: 'freeText'; text: string; value: FreeTextValue | null; retry: Retry | null }
  | { kind: 'newIngredient'; name: string };

interface ItemFieldProps {
  listId: string;
  /** While shopping, free-text items go through the outbox and work offline (SHOP-02). */
  shopping?: boolean;
}

/**
 * The item field at the top of Artikel (LIST-06, D-41). It searches ingredients, under
 * "„X“ als Artikel" and "„X“ als neue Zutat". An ingredient, or ＋ with the only ingredient of
 * that name (whatever its brand), opens the amount pop-up with the units that fit it (REF-02);
 * "„X“ als Artikel", or ＋ without an exact match, the free-text pop-up; with several brands of
 * that name ＋ does nothing and the results stay for a tap. "„X“ als neue Zutat" opens "Neue
 * Zutat" (ING-04), then the amount pop-up for it.
 *
 * Offline a draft can't change (SYNC-03): the field is inactive. While shopping offline it
 * searches nothing and offers only free text, which goes into the outbox (SHOP-02).
 *
 * An item keeps its id when it is sent again unchanged after an error (e.g. a timeout whose
 * request did reach the server), so it isn't added twice.
 */
export function ItemField({ listId, shopping = false }: ItemFieldProps) {
  const { t } = useTranslation();
  const connected = useConnected();
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState('');
  const [request, setRequest] = useState<ItemRequest | null>(null);
  const requestRef = useRef(request);
  const [addError, setAddError] = useState<Error | null>(null);
  /** The unit last chosen here: the next ingredient starts with it while it fits (MEAL-02). */
  const [lastUnit, setLastUnit] = useState<Unit | ''>('');
  const add = useAddExtraItem(listId);
  const queue = useQueueOp(listId);
  const units = useUnits();
  const categories = useCategories();
  const typed = text.trim();
  const debounced = useDebouncedValue(typed);
  const searching = connected && typed !== '';
  const results = useIngredients(debounced, { enabled: connected && debounced !== '' });
  // Only the answer for the text in the field (D-41). Offline, or when the search failed, there
  // is nothing to wait for: ＋ takes the text as free text.
  const current = searching && debounced === typed && !results.isPlaceholderData;
  const answer: IngredientSearchResult[] | undefined = !connected
    ? []
    : current
      ? (results.data ?? (results.isError ? [] : undefined))
      : undefined;

  useEffect(() => {
    requestRef.current = request;
  });

  function startUnit(ingredient: IngredientSummary): Unit {
    const kept = units.data ? keptUnit(units.data, ingredient.base_unit, lastUnit) : '';
    return kept || ingredient.base_unit;
  }

  function chooseIngredient(ingredient: IngredientSummary) {
    setAddError(null);
    setRequest({
      kind: 'amount',
      ingredient,
      value: { amount: null, unit: startUnit(ingredient) },
      retry: null,
    });
  }

  function chooseFreeText() {
    setAddError(null);
    setRequest({ kind: 'freeText', text: typed, value: null, retry: null });
  }

  const plus = usePlus(typed, answer, (found) => {
    const exact = found.filter((ingredient) => ingredient.exact);
    if (exact.length === 1 && exact[0]) chooseIngredient(exact[0]);
    else if (exact.length === 0) chooseFreeText();
    // Several brands of that name: the results stay for a tap.
  });

  /** The pop-up closes and the emptied field gets the focus within this tap (iOS keyboard). */
  function closeAndFocus() {
    flushSync(() => {
      setRequest(null);
      setText('');
    });
    inputRef.current?.focus();
  }

  /** After an error: the pop-up again, unless the user opened another one meanwhile. */
  function reopen(next: ItemRequest, error: Error | null) {
    if (requestRef.current === null) setRequest(next);
    else if (error) setAddError(error);
  }

  /** The id to send: the same as last time for the very same item after an error. */
  function itemId(body: Omit<ExtraItemCreate, 'id'>, retry: Retry | null): string {
    if (retry) {
      const { id, ...sent } = retry.sent;
      if (id && JSON.stringify(sent) === JSON.stringify(body)) return id;
    }
    return uuidv7();
  }

  function addLinked(ingredient: IngredientSummary, value: AmountValue, retry: Retry | null) {
    const body =
      value.amount === null
        ? { ingredient_id: ingredient.id }
        : { ingredient_id: ingredient.id, amount: value.amount, unit: value.unit };
    const item = { id: itemId(body, retry), ...body };
    closeAndFocus();
    setLastUnit(value.unit);
    add.mutate(item, {
      onError: (error) =>
        reopen({ kind: 'amount', ingredient, value, retry: { sent: item, error } }, error),
    });
  }

  function addFreeText(name: string, value: FreeTextValue, retry: Retry | null) {
    const body = {
      text: name,
      ...(value.amountText ? { amount_text: value.amountText } : {}),
      ...(value.categoryId ? { category_id: value.categoryId } : {}),
    };
    closeAndFocus();
    if (shopping) {
      // SHOP-02: into the outbox, online or offline; it says so itself if it can't be stored.
      const payload = { extra_id: uuidv7(), ...body };
      void queue(shoppingOps.addExtra(payload, stampOp())).then((queued) => {
        if (!queued) reopen({ kind: 'freeText', text: name, value, retry: null }, null);
      });
      return;
    }
    const item = { id: itemId(body, retry), ...body };
    add.mutate(item, {
      onError: (error) =>
        reopen({ kind: 'freeText', text: name, value, retry: { sent: item, error } }, error),
    });
  }

  const matches = (answer ?? []).slice(0, MAX_RESULTS);
  const options = typed !== '' && (
    <FieldOptions>
      <FieldOption testId={testIds.itemFreeText} onSelect={chooseFreeText}>
        {t('lists.itemField.freeText', { name: typed })}
      </FieldOption>
      {connected && (
        <FieldOption
          testId={testIds.itemNewIngredient}
          onSelect={() => {
            setAddError(null);
            setRequest({ kind: 'newIngredient', name: typed });
          }}
        >
          {t('lists.itemField.newIngredient', { name: typed })}
        </FieldOption>
      )}
    </FieldOptions>
  );
  const resultList = (
    <>
      <ErrorAlert error={searching ? results.error : null} />
      {matches.length > 0 && (
        <ul aria-label={t('lists.itemField.results')} className={RESULT_LIST_CLASS}>
          {matches.map((ingredient) => (
            <li key={ingredient.id}>
              <button
                type="button"
                onClick={() => chooseIngredient(ingredient)}
                className={cn(RESULT_BUTTON_CLASS, 'flex-col items-start gap-0')}
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
    </>
  );
  const amountRequest = request?.kind === 'amount' ? request : null;
  const freeTextRequest = request?.kind === 'freeText' ? request : null;
  const focusField = (event: Event) => {
    event.preventDefault();
    inputRef.current?.focus();
  };

  return (
    <>
      <AddField
        inputRef={inputRef}
        inputTestId={testIds.extraItemInput}
        label={t('lists.itemField.label')}
        placeholder={t('lists.itemField.placeholder')}
        value={text}
        onValueChange={(value) => {
          setText(value);
          setAddError(null);
        }}
        // Offline a draft can't change (SYNC-03); while shopping free text still works.
        disabled={!connected && !shopping}
        onAdd={plus}
        // While text is typed its options always show (D-41).
        panelOpen={typed !== ''}
        options={options}
        results={resultList}
      >
        <ErrorAlert error={addError} />
      </AddField>
      <AmountDialog
        ingredient={amountRequest?.ingredient ?? null}
        initial={amountRequest?.value}
        error={amountRequest?.retry?.error}
        disabled={!connected}
        onAdd={(value) => {
          if (amountRequest) addLinked(amountRequest.ingredient, value, amountRequest.retry);
        }}
        onCancel={() => setRequest(null)}
        onCloseAutoFocus={focusField}
      />
      <FreeTextDialog
        text={freeTextRequest?.text ?? null}
        initial={freeTextRequest?.value}
        error={freeTextRequest?.retry?.error}
        disabled={!connected && !shopping}
        onAdd={(value) => {
          if (freeTextRequest) addFreeText(freeTextRequest.text, value, freeTextRequest.retry);
        }}
        onCancel={() => setRequest(null)}
        onCloseAutoFocus={focusField}
      />
      {connected && (
        <IngredientFormDialog
          open={request?.kind === 'newIngredient'}
          onOpenChange={(isOpen) => {
            if (!isOpen)
              setRequest((current) => (current?.kind === 'newIngredient' ? null : current));
          }}
          initialName={request?.kind === 'newIngredient' ? request.name : ''}
          onSaved={(ingredient) => chooseIngredient(toSummary(ingredient))}
          onPickExisting={chooseIngredient}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            // Saved: the amount pop-up has the focus; cancelled: back to the field.
            if (requestRef.current === null) inputRef.current?.focus();
          }}
        />
      )}
    </>
  );
}
