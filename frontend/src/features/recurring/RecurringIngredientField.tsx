import { Plus } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { useId, useRef, useState, type FormEvent, type Ref } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  ingredientsQuery,
  toSummary,
  useIngredients,
  type IngredientSummary,
} from '@/features/ingredients/api';
import { IngredientCategoryUnit } from '@/features/ingredients/IngredientCategoryUnit';
import { IngredientFormDialog } from '@/features/ingredients/IngredientFormDialog';
import { IngredientName } from '@/features/ingredients/IngredientName';
import { useCategories } from '@/features/reference/api';
import { useLanguage, type Language } from '@/i18n';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';

/** More matches than this are left out: typing more narrows them down. */
const MAX_RESULTS = 20;
const OPTION =
  'flex min-h-(--tap-target) w-full px-3 py-2 text-left outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset';

/**
 * Whether a result has the typed name, ignoring case and accents, as the search does (ING-03).
 * The search marks no exact results yet; the item field (D-41) will, and this can follow it.
 */
function sameName(name: string, typed: string, language: Language): boolean {
  return name.localeCompare(typed, language, { sensitivity: 'base' }) === 0;
}

interface RecurringIngredientFieldProps {
  /** The typed text, kept by the page so it can empty the field once an item is added. */
  value: string;
  onValueChange: (value: string) => void;
  /** A picked ingredient, also one just created through "Neue Zutat". */
  onPick: (ingredient: IngredientSummary) => void;
  disabled: boolean;
  inputRef: Ref<HTMLInputElement>;
}

/**
 * The ingredient field at the top of "Regelmäßige Artikel" (LIST-16): it looks like the item field
 * of a list (D-41), a search input and a ＋, but offers only ingredients, with "„X“ als neue
 * Zutat" (ING-04) directly under the field so late results never move it. There is no free text:
 * only ingredients can be recognised on later lists. ＋ or Enter takes the one ingredient with
 * exactly the typed name, whatever its brand; with several it leaves the choice to the results,
 * and with none it opens "Neue Zutat". While the typed text's results load, ＋ waits for them.
 */
export function RecurringIngredientField({
  value,
  onValueChange,
  onPick,
  disabled,
  inputRef,
}: RecurringIngredientFieldProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const inputId = useId();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const [submitError, setSubmitError] = useState<unknown>(null);
  /** The text as last typed, to drop a ＋ whose results arrive after the text changed. */
  const latest = useRef(value.trim());
  const typed = value.trim();
  const debounced = useDebouncedValue(typed);
  const searching = debounced !== '' && !disabled;
  const results = useIngredients(debounced, { enabled: searching });
  const categories = useCategories();
  // Only the answer for the text in the field: an earlier text's results would vanish under the
  // finger when the answer lands.
  const answer =
    searching && debounced === typed && !results.isPlaceholderData ? results.data : undefined;
  const matches = (answer ?? []).slice(0, MAX_RESULTS);

  /** ＋ or Enter: the results of the typed text decide, once they are there. */
  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const text = typed;
    if (!text || disabled) return;
    setSubmitError(null);
    let found: readonly IngredientSummary[];
    try {
      found = answer ?? (await queryClient.fetchQuery(ingredientsQuery(text)));
    } catch (error) {
      setSubmitError(error);
      return;
    }
    if (latest.current !== text) return;
    const exact = found.filter((ingredient) => sameName(ingredient.name, text, language));
    if (exact.length === 1 && exact[0]) onPick(exact[0]);
    else if (exact.length === 0) setCreating(true);
    // Several brands of that name: the results stay for a tap.
  }

  return (
    <>
      <form
        onSubmit={(event) => void onSubmit(event)}
        noValidate
        role="search"
        aria-label={t('recurring.field.label')}
      >
        <fieldset disabled={disabled} className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
          <div className="flex items-center gap-2">
            <label htmlFor={inputId} className="sr-only">
              {t('recurring.field.label')}
            </label>
            <Input
              ref={inputRef}
              id={inputId}
              type="search"
              data-testid={testIds.recurringInput}
              enterKeyHint="go"
              autoComplete="off"
              placeholder={t('recurring.field.placeholder')}
              value={value}
              onChange={(event) => {
                latest.current = event.target.value.trim();
                onValueChange(event.target.value);
              }}
            />
            <Button
              type="submit"
              size="icon"
              className="size-(--tap-target) shrink-0"
              disabled={!typed}
              aria-label={
                typed ? t('recurring.field.addNamed', { name: typed }) : t('recurring.field.add')
              }
            >
              <Plus aria-hidden="true" />
            </Button>
          </div>
          {typed && (
            <ul
              aria-label={t('recurring.field.results')}
              className="flex flex-col divide-y rounded-lg border bg-card"
            >
              <li>
                <button
                  type="button"
                  data-testid={testIds.recurringNewIngredient}
                  onClick={() => setCreating(true)}
                  className={`${OPTION} items-center gap-2 font-medium text-primary`}
                >
                  <Plus aria-hidden="true" className="size-5 shrink-0" />
                  {t('recurring.field.newIngredient', { name: typed })}
                </button>
              </li>
              {matches.map((ingredient) => (
                <li key={ingredient.id}>
                  <button
                    type="button"
                    onClick={() => onPick(ingredient)}
                    className={`${OPTION} flex-col items-start`}
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
          <ErrorAlert error={results.error ?? submitError} />
        </fieldset>
      </form>
      {/* Outside the form: its own form's submit would bubble through the portal into this one. */}
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
