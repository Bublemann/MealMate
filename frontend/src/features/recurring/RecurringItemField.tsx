import { useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { toSummary, useItems, type ItemSearchResult, type ItemSummary } from '@/features/items/api';
import { ItemCategoryUnit } from '@/features/items/ItemCategoryUnit';
import { ItemFormDialog } from '@/features/items/ItemFormDialog';
import { ItemName } from '@/features/items/ItemName';
import {
  AddField,
  FieldOption,
  RESULT_BUTTON_CLASS,
  RESULT_LIST_CLASS,
} from '@/features/lists/AddField';
import { usePlus } from '@/features/lists/usePlus';
import { useCategories } from '@/features/reference/api';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';

/** More matches than this are left out: typing more narrows them down. */
const MAX_RESULTS = 20;

interface RecurringItemFieldProps {
  /** The typed text, kept by the page so it can empty the field once an item is added. */
  value: string;
  onValueChange: (value: string) => void;
  /** A picked item, also one just created through "Neue Zutat". */
  onPick: (item: ItemSummary) => void;
  disabled: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
}

/**
 * The item field at the top of "Regelmäßige Artikel" (LIST-16): the item field's `AddField`
 * (D-41), a search input and a ＋, but it offers only items, with "„X“ als neue Zutat"
 * (ING-04) first in the list so late results never move it. There is no free text: only
 * items can be recognised on later lists. ＋ or Enter (`usePlus`, which waits for the
 * results of the typed text) takes the one item the server marked `exact`, whatever its
 * brand; with several it leaves the choice to the results, and with none it opens "Neue Zutat".
 * When the search failed it does nothing; the error shows below the field.
 */
export function RecurringItemField({
  value,
  onValueChange,
  onPick,
  disabled,
  inputRef,
}: RecurringItemFieldProps) {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const typed = value.trim();
  const debounced = useDebouncedValue(typed);
  const searching = debounced !== '' && !disabled;
  const results = useItems(debounced, { enabled: searching });
  const categories = useCategories();
  // Only the answer for the text in the field: an earlier text's results would vanish under the
  // finger when the answer lands. A failed search answers null: ＋ has nothing to go by.
  const current = searching && debounced === typed && !results.isPlaceholderData;
  const answer: ItemSearchResult[] | null | undefined = current
    ? (results.data ?? (results.isError ? null : undefined))
    : undefined;
  const matches = (answer ?? []).slice(0, MAX_RESULTS);

  const plus = usePlus(typed, answer, (found) => {
    if (found === null) return;
    const exact = found.filter((item) => item.exact);
    if (exact.length === 1 && exact[0]) onPick(exact[0]);
    else if (exact.length === 0) setCreating(true);
    // Several brands of that name: the results stay for a tap.
  });

  return (
    <>
      <AddField
        inputRef={inputRef}
        inputTestId={testIds.recurringInput}
        label={t('recurring.field.label')}
        placeholder={t('recurring.field.placeholder')}
        value={value}
        onValueChange={onValueChange}
        disabled={disabled}
        onAdd={plus}
        panelOpen={typed !== ''}
        results={
          <ul aria-label={t('recurring.field.results')} className={RESULT_LIST_CLASS}>
            <FieldOption testId={testIds.recurringNewItem} onSelect={() => setCreating(true)}>
              {t('recurring.field.newItem', { name: typed })}
            </FieldOption>
            {matches.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onPick(item)}
                  className={cn(RESULT_BUTTON_CLASS, 'flex-col items-start gap-0')}
                >
                  <ItemName item={item} />
                  <ItemCategoryUnit item={item} categories={categories.data ?? []} />
                </button>
              </li>
            ))}
          </ul>
        }
      >
        <ErrorAlert error={searching ? results.error : null} />
      </AddField>
      {/* Outside the field's form: its own form's submit would bubble through the portal. */}
      <ItemFormDialog
        open={creating}
        onOpenChange={setCreating}
        initialName={typed}
        onSaved={(item) => onPick(toSummary(item))}
        onPickExisting={onPick}
      />
    </>
  );
}
