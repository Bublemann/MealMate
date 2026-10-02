import { Plus } from 'lucide-react';
import { useId, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCategories } from '@/features/reference/api';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import { toSummary, useIngredients, type IngredientSummary } from './api';
import { IngredientCategoryUnit } from './IngredientCategoryUnit';
import { IngredientFormDialog } from './IngredientFormDialog';
import { IngredientName } from './IngredientName';

/** More matches than this are left out: the search narrows them down. */
const MAX_RESULTS = 50;

interface IngredientPickerProps {
  /** Called with the chosen ingredient, also with one just created here. */
  onSelect: (ingredient: IngredientSummary) => void;
  /** Ingredients that can't be chosen (e.g. the one being merged). */
  excludeIds?: readonly string[];
  /** The search field's label (default "Search ingredient"). */
  label?: string;
  /** Offers "Create “…”" for the typed name (default true). */
  allowCreate?: boolean;
}

/**
 * Search (name and brand) and pick an ingredient, or create it inline with the full ingredient
 * form, which can also fill it from Open Food Facts (ING-03). Reused by meals and lists. The
 * results are a list of buttons: Tab or the arrow keys move through them, Enter or Space picks.
 */
export function IngredientPicker({
  onSelect,
  excludeIds = [],
  label,
  allowCreate = true,
}: IngredientPickerProps) {
  const { t } = useTranslation();
  const inputId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const debounced = useDebouncedValue(query.trim());
  const searching = debounced !== '';
  const results = useIngredients(debounced, { enabled: searching });
  const categories = useCategories();
  const matches = searching
    ? (results.data ?? [])
        .filter((ingredient) => !excludeIds.includes(ingredient.id))
        .slice(0, MAX_RESULTS)
    : [];
  const typed = query.trim();

  function options(): HTMLButtonElement[] {
    return Array.from(listRef.current?.querySelectorAll('button') ?? []);
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== 'ArrowDown') return;
    event.preventDefault();
    options()[0]?.focus();
  }

  function onListKeyDown(event: KeyboardEvent<HTMLUListElement>) {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    const buttons = options();
    const index = buttons.findIndex((button) => button === document.activeElement);
    if (event.key === 'ArrowDown') buttons[Math.min(index + 1, buttons.length - 1)]?.focus();
    else if (index <= 0) document.getElementById(inputId)?.focus();
    else buttons[index - 1]?.focus();
  }

  return (
    <div data-testid={testIds.ingredientPicker} className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        <Label htmlFor={inputId}>{label ?? t('ingredients.picker.label')}</Label>
        <Input
          id={inputId}
          type="search"
          enterKeyHint="search"
          autoComplete="off"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={onInputKeyDown}
        />
      </div>
      <p aria-live="polite" className="text-sm text-muted-foreground">
        {!typed && t('ingredients.picker.typeToSearch')}
        {typed && searching && results.isSuccess && matches.length === 0 && (
          <>{t('ingredients.picker.noResults')}</>
        )}
      </p>
      <ErrorAlert error={results.error} />
      {typed && (matches.length > 0 || allowCreate) && (
        // The arrow keys only move the focus between the buttons inside.
        // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
        <ul
          ref={listRef}
          aria-label={t('ingredients.picker.results')}
          onKeyDown={onListKeyDown}
          className="flex flex-col divide-y rounded-lg border"
        >
          {matches.map((ingredient) => (
            <li key={ingredient.id}>
              <button
                type="button"
                onClick={() => onSelect(ingredient)}
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
          {allowCreate && (
            <li>
              <button
                type="button"
                data-testid={testIds.ingredientPickerCreate}
                onClick={() => setCreating(true)}
                className="flex min-h-(--tap-target) w-full items-center gap-2 px-3 py-2 text-left font-medium text-primary outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
              >
                <Plus aria-hidden="true" className="size-5 shrink-0" />
                {t('ingredients.createNamed', { name: typed })}
              </button>
            </li>
          )}
        </ul>
      )}
      {allowCreate && (
        <IngredientFormDialog
          open={creating}
          onOpenChange={setCreating}
          initialName={typed}
          onSaved={(ingredient) => onSelect(toSummary(ingredient))}
          onPickExisting={onSelect}
        />
      )}
    </div>
  );
}
