import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { toSummary, useItems, type ItemSearchResult, type ItemSummary } from '@/features/items/api';
import { ItemCategoryUnit } from '@/features/items/ItemCategoryUnit';
import { ItemFormDialog } from '@/features/items/ItemFormDialog';
import { ItemName } from '@/features/items/ItemName';
import type { DueItem } from '@/features/recurring/api';
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
import { DueBox, type DueBoxHandle } from './DueBox';
import { shoppingOps, stampOp, useAddExtraItem, useHideDueItem, type ExtraItemCreate } from './api';
import { usePlus } from './usePlus';

/** Results shown under the field; typing more narrows them down. */
const MAX_RESULTS = 6;

/** What a pop-up opens with again when the server refused it: what was sent, and why. */
interface Retry {
  sent: ExtraItemCreate;
  error: Error;
}

/** The amount pop-up of an item. */
interface AmountRequest {
  kind: 'amount';
  item: ItemSummary;
  value: AmountValue;
  retry: Retry | null;
  /** Opened from the "Fällig" box: the focus goes back there, not into the field. */
  fromDue: boolean;
}

/** The open pop-up of the item field. */
type ItemRequest =
  | AmountRequest
  | { kind: 'freeText'; text: string; value: FreeTextValue | null; retry: Retry | null }
  | { kind: 'newItem'; name: string };

interface ItemFieldProps {
  listId: string;
  /** The due items of a draft, shown in the "Fällig" box below the field (LIST-16). */
  due?: readonly DueItem[];
  /** While shopping, free-text items go through the outbox and work offline (SHOP-02). */
  shopping?: boolean;
}

/**
 * The item field at the top of Artikel (LIST-06, D-41). It searches items, under
 * "„X“ als Artikel" and "„X“ als neue Zutat". An item, or ＋ with the only item of
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
 *
 * On a draft, `due` fills the "Fällig" box below the field (LIST-16): its ＋ opens the same amount
 * pop-up with the last amount, and the focus goes back to the box when the pop-up closes (to the
 * row in its place once the item is added, or to the field when the box is gone).
 */
export function ItemField({ listId, due = [], shopping = false }: ItemFieldProps) {
  const { t } = useTranslation();
  const connected = useConnected();
  const inputRef = useRef<HTMLInputElement>(null);
  const dueBox = useRef<DueBoxHandle>(null);
  /**
   * Where the focus goes when the open pop-up closes: the "Fällig" box it was opened from, or the
   * field. Set with the request (`show`); a ref because the pop-ups ask for it in
   * `onCloseAutoFocus`, after the request is already gone.
   */
  const focusBack = useRef<'field' | 'due'>('field');
  const [text, setText] = useState('');
  const [request, setRequest] = useState<ItemRequest | null>(null);
  const requestRef = useRef(request);
  const [addError, setAddError] = useState<Error | null>(null);
  /** The unit last chosen here: the next item starts with it while it fits (MEAL-02). */
  const [lastUnit, setLastUnit] = useState<Unit | ''>('');
  const add = useAddExtraItem(listId);
  const hideDue = useHideDueItem(listId);
  const queue = useQueueOp(listId);
  const units = useUnits();
  const categories = useCategories();
  const typed = text.trim();
  const debounced = useDebouncedValue(typed);
  const searching = connected && typed !== '';
  const results = useItems(debounced, { enabled: connected && debounced !== '' });
  // Only the answer for the text in the field (D-41). Offline, or when the search failed, there
  // is nothing to wait for: ＋ takes the text as free text.
  const current = searching && debounced === typed && !results.isPlaceholderData;
  const answer: ItemSearchResult[] | undefined = !connected
    ? []
    : current
      ? (results.data ?? (results.isError ? [] : undefined))
      : undefined;

  useEffect(() => {
    requestRef.current = request;
  });

  // A failed ✕ says why until the due items change after the reload that brought its row back,
  // or until the next action (`show`, another ✕). Compared by their items: a reload with
  // the same items is no change.
  const hideFailed = hideDue.isError;
  const dueIds = due.map((entry) => entry.item.id).join(' ');
  const rowBack = hideFailed && due.some((entry) => entry.item.id === hideDue.variables);
  const resetHide = hideDue.reset;
  const failedWith = useRef<string | null>(null);
  useEffect(() => {
    if (!hideFailed) {
      failedWith.current = null;
    } else if (failedWith.current === null) {
      if (rowBack) failedWith.current = dueIds;
    } else if (failedWith.current !== dueIds) {
      resetHide();
    }
  }, [hideFailed, rowBack, dueIds, resetHide]);

  function startUnit(item: ItemSummary): Unit {
    const kept = units.data ? keptUnit(units.data, item.base_unit, lastUnit) : '';
    return kept || item.base_unit;
  }

  /** Opens a pop-up; a new action also clears the error of a failed ✕. */
  function show(next: ItemRequest) {
    focusBack.current = next.kind === 'amount' && next.fromDue ? 'due' : 'field';
    hideDue.reset();
    setRequest(next);
  }

  /** The focus goes back where the pop-up was opened from (A11Y-01). */
  function focusBackThere() {
    if (focusBack.current === 'due' && dueBox.current?.restoreFocus()) return;
    inputRef.current?.focus();
  }

  const restoreFocus = (event: Event) => {
    event.preventDefault();
    focusBackThere();
  };

  function chooseItem(item: ItemSummary) {
    setAddError(null);
    show({
      kind: 'amount',
      item,
      value: { amount: null, unit: startUnit(item) },
      retry: null,
      fromDue: false,
    });
  }

  /** ＋ of a due item: its last amount filled in, when the server gives one that fits (D-42). */
  function chooseDue({ item, last_amount }: DueItem) {
    setAddError(null);
    show({
      kind: 'amount',
      item,
      value: last_amount
        ? { amount: last_amount.value, unit: last_amount.unit }
        : { amount: null, unit: startUnit(item) },
      retry: null,
      fromDue: true,
    });
  }

  function chooseFreeText() {
    setAddError(null);
    show({ kind: 'freeText', text: typed, value: null, retry: null });
  }

  const plus = usePlus(typed, answer, (found) => {
    const exact = found.filter((item) => item.exact);
    if (exact.length === 1 && exact[0]) chooseItem(exact[0]);
    else if (exact.length === 0) chooseFreeText();
    // Several brands of that name: the results stay for a tap.
  });

  /**
   * The pop-up closes and the emptied field gets the focus within this tap (iOS keyboard); after
   * an item of the "Fällig" box the box gets it, and what was typed in the field stays.
   */
  function closeAndFocus() {
    flushSync(() => {
      setRequest(null);
      if (focusBack.current === 'field') setText('');
    });
    focusBackThere();
  }

  /** After an error: the pop-up again, unless the user opened another one meanwhile. */
  function reopen(next: ItemRequest, error: Error | null) {
    if (requestRef.current === null) show(next);
    else if (error) setAddError(error);
  }

  /** The id to send: the same as last time for the very same extra item after an error. */
  function extraId(body: Omit<ExtraItemCreate, 'id'>, retry: Retry | null): string {
    if (retry) {
      const { id, ...sent } = retry.sent;
      if (id && JSON.stringify(sent) === JSON.stringify(body)) return id;
    }
    return uuidv7();
  }

  function addLinked({ item, retry, fromDue }: AmountRequest, value: AmountValue) {
    const body =
      value.amount === null
        ? { item_id: item.id }
        : { item_id: item.id, amount: value.amount, unit: value.unit };
    const extra = { id: extraId(body, retry), ...body };
    closeAndFocus();
    setLastUnit(value.unit);
    add.mutate(extra, {
      onError: (error) =>
        reopen({ kind: 'amount', item, value, retry: { sent: extra, error }, fromDue }, error),
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
    const extra = { id: extraId(body, retry), ...body };
    add.mutate(extra, {
      onError: (error) =>
        reopen({ kind: 'freeText', text: name, value, retry: { sent: extra, error } }, error),
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
          testId={testIds.itemNewItem}
          onSelect={() => {
            setAddError(null);
            show({ kind: 'newItem', name: typed });
          }}
        >
          {t('lists.itemField.newItem', { name: typed })}
        </FieldOption>
      )}
    </FieldOptions>
  );
  const resultList = (
    <>
      <ErrorAlert error={searching ? results.error : null} />
      {matches.length > 0 && (
        <ul aria-label={t('lists.itemField.results')} className={RESULT_LIST_CLASS}>
          {matches.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => chooseItem(item)}
                className={cn(RESULT_BUTTON_CLASS, 'flex-col items-start gap-0')}
              >
                <ItemName item={item} />
                <ItemCategoryUnit item={item} categories={categories.data ?? []} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );
  const amountRequest = request?.kind === 'amount' ? request : null;
  const freeTextRequest = request?.kind === 'freeText' ? request : null;

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
      <DueBox
        ref={dueBox}
        items={due}
        disabled={!connected}
        frozen={request !== null}
        onAdd={chooseDue}
        onHide={(entry) => hideDue.mutate(entry.item.id)}
        onEmpty={() => inputRef.current?.focus()}
      />
      <ErrorAlert error={hideDue.error} />
      <AmountDialog
        item={amountRequest?.item ?? null}
        initial={amountRequest?.value}
        error={amountRequest?.retry?.error}
        disabled={!connected}
        onAdd={(value) => {
          if (amountRequest) addLinked(amountRequest, value);
        }}
        onCancel={() => setRequest(null)}
        onCloseAutoFocus={restoreFocus}
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
        onCloseAutoFocus={restoreFocus}
      />
      {connected && (
        <ItemFormDialog
          open={request?.kind === 'newItem'}
          onOpenChange={(isOpen) => {
            if (!isOpen) setRequest((current) => (current?.kind === 'newItem' ? null : current));
          }}
          initialName={request?.kind === 'newItem' ? request.name : ''}
          onSaved={(item) => chooseItem(toSummary(item))}
          onPickExisting={chooseItem}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            // Saved: the amount pop-up has the focus; cancelled: back to the field.
            if (requestRef.current === null) focusBackThere();
          }}
        />
      )}
    </>
  );
}
