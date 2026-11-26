import { Plus } from 'lucide-react';
import { useId, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCategories } from '@/features/reference/api';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import { toSummary, useItems, type ItemKind, type ItemSummary } from './api';
import { ItemCategoryUnit } from './ItemCategoryUnit';
import { ItemFormDialog } from './ItemFormDialog';
import { ItemName } from './ItemName';

/** More matches than this are left out: the search narrows them down. */
const MAX_RESULTS = 50;

interface ItemPickerProps {
  /** Called with the chosen item, also with one just created here. */
  onSelect: (item: ItemSummary) => void;
  /** Items that can't be chosen (e.g. the one being merged). */
  excludeIds?: readonly string[];
  /** The search field's label (default "Search item"). */
  label?: string;
  /** Offers "Create “…”" for the typed name (default true). */
  allowCreate?: boolean;
  /**
   * Only items of this kind: a meal's ingredients are food (D-54), so supplies are neither found
   * nor offered, and an item created here is food.
   */
  kind?: ItemKind;
}

/**
 * Search (name and brand) and pick an item, or create it inline with the full item
 * form, which can also fill it from Open Food Facts (ING-03). Reused by meals and lists. The
 * results are a list of buttons: Tab or the arrow keys move through them, Enter or Space picks.
 */
export function ItemPicker({
  onSelect,
  excludeIds = [],
  label,
  allowCreate = true,
  kind,
}: ItemPickerProps) {
  const { t } = useTranslation();
  const inputId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const typed = query.trim();
  const debounced = useDebouncedValue(typed);
  const searching = debounced !== '';
  const results = useItems(debounced, { enabled: searching, kind });
  const categories = useCategories();
  // Only the answer for the text in the field: an earlier text's results, kept while the debounce
  // runs or the search loads, would vanish under the finger when the answer lands (MEAL-03).
  const answer =
    searching && debounced === typed && !results.isPlaceholderData ? results.data : undefined;
  const matches = (answer ?? [])
    .filter((item) => !excludeIds.includes(item.id))
    .slice(0, MAX_RESULTS);

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
    <div data-testid={testIds.itemPicker} className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        <Label htmlFor={inputId}>{label ?? t('items.picker.label')}</Label>
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
      {/* "Create" comes first, right under the field, so results arriving below never move it. */}
      {typed && (matches.length > 0 || allowCreate) && (
        // The arrow keys only move the focus between the buttons inside.
        // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
        <ul
          ref={listRef}
          aria-label={t('items.picker.results')}
          onKeyDown={onListKeyDown}
          className="flex flex-col divide-y rounded-lg border"
        >
          {allowCreate && (
            <li>
              <button
                type="button"
                data-testid={testIds.itemPickerCreate}
                onClick={() => setCreating(true)}
                className="flex min-h-(--tap-target) w-full items-center gap-2 px-3 py-2 text-left font-medium text-primary outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
              >
                <Plus aria-hidden="true" className="size-5 shrink-0" />
                {t('items.createNamed', { name: typed })}
              </button>
            </li>
          )}
          {matches.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => onSelect(item)}
                className="flex min-h-(--tap-target) w-full flex-col items-start px-3 py-2 text-left outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
              >
                <ItemName item={item} />
                <ItemCategoryUnit item={item} categories={categories.data ?? []} />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p aria-live="polite" className="text-sm text-muted-foreground">
        {!typed && t('items.picker.typeToSearch')}
        {answer && matches.length === 0 && t('items.picker.noResults')}
      </p>
      <ErrorAlert error={results.error} />
      {allowCreate && (
        <ItemFormDialog
          open={creating}
          onOpenChange={setCreating}
          initialName={typed}
          onSaved={(item) => onSelect(toSummary(item))}
          onPickExisting={onSelect}
          foodOnly={kind === 'food'}
        />
      )}
    </div>
  );
}
