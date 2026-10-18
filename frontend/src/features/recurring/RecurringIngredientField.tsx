import { useState, type RefObject } from 'react';
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

interface RecurringIngredientFieldProps {
  /** The typed text, kept by the page so it can empty the field once an item is added. */
  value: string;
  onValueChange: (value: string) => void;
  /** A picked ingredient, also one just created through "Neue Zutat". */
  onPick: (ingredient: IngredientSummary) => void;
  disabled: boolean;
  inputRef: RefObject<HTMLInputElement | null>;
}

/**
 * The ingredient field at the top of "Regelmäßige Artikel" (LIST-16): the item field's `AddField`
 * (D-41), a search input and a ＋, but it offers only ingredients, with "„X“ als neue Zutat"
 * (ING-04) first in the list so late results never move it. There is no free text: only
 * ingredients can be recognised on later lists. ＋ or Enter (`usePlus`, which waits for the
 * results of the typed text) takes the one ingredient the server marked `exact`, whatever its
 * brand; with several it leaves the choice to the results, and with none it opens "Neue Zutat".
 * When the search failed it does nothing; the error shows below the field.
 */
export function RecurringIngredientField({
  value,
  onValueChange,
  onPick,
  disabled,
  inputRef,
}: RecurringIngredientFieldProps) {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const typed = value.trim();
  const debounced = useDebouncedValue(typed);
  const searching = debounced !== '' && !disabled;
  const results = useIngredients(debounced, { enabled: searching });
  const categories = useCategories();
  // Only the answer for the text in the field: an earlier text's results would vanish under the
  // finger when the answer lands. A failed search answers null: ＋ has nothing to go by.
  const current = searching && debounced === typed && !results.isPlaceholderData;
  const answer: IngredientSearchResult[] | null | undefined = current
    ? (results.data ?? (results.isError ? null : undefined))
    : undefined;
  const matches = (answer ?? []).slice(0, MAX_RESULTS);

  const plus = usePlus(typed, answer, (found) => {
    if (found === null) return;
    const exact = found.filter((ingredient) => ingredient.exact);
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
            <FieldOption testId={testIds.recurringNewIngredient} onSelect={() => setCreating(true)}>
              {t('recurring.field.newIngredient', { name: typed })}
            </FieldOption>
            {matches.map((ingredient) => (
              <li key={ingredient.id}>
                <button
                  type="button"
                  onClick={() => onPick(ingredient)}
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
        }
      >
        <ErrorAlert error={searching ? results.error : null} />
      </AddField>
      {/* Outside the field's form: its own form's submit would bubble through the portal. */}
      <IngredientFormDialog
        open={creating}
        onOpenChange={setCreating}
        initialName={typed}
        onSaved={(ingredient) => onPick(toSummary(ingredient))}
        onPickExisting={onPick}
      />
    </>
  );
}
