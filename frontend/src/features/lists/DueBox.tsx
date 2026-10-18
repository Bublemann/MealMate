import { Plus, X } from 'lucide-react';
import { useId, useImperativeHandle, useLayoutEffect, useRef, useState, type Ref } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { ingredientLabel } from '@/features/ingredients/label';
import { IngredientName } from '@/features/ingredients/IngredientName';
import type { DueItem } from '@/features/recurring/api';
import { dueLine } from '@/features/recurring/format';
import { useLanguage } from '@/i18n';
import { testIds } from '@/testIds';

/** What a row's button does. */
type DueAction = 'add' | 'hide';

export interface DueBoxHandle {
  /**
   * Focuses the button last tapped in the box, or, when its row has left, the same button of the
   * row in its place, else of the row above. Returns false when there is no row to focus.
   */
  restoreFocus: () => boolean;
}

interface DueBoxProps {
  ref?: Ref<DueBoxHandle>;
  /** The due items as the list detail carries them, longest due first (the server sorts). */
  items: readonly DueItem[];
  /** ＋: the item field's amount pop-up for it. */
  onAdd: (item: DueItem) => void;
  /** ✕: hide it on this list, for everyone who sees the list. */
  onHide: (item: DueItem) => void;
  /** Offline: ＋ and ✕ are inactive, not hidden (SYNC-03). */
  disabled: boolean;
  /** While a pop-up is open the rows stay as they are, so a load of the list doesn't move them. */
  frozen: boolean;
  /** The last row left while its button had the focus: the item field takes it (A11Y-01). */
  onEmpty: () => void;
}

/**
 * The "Fällig" box below the item field of a draft (LIST-16, D-42): the due recurring items of the
 * viewer's set that aren't on the list, each with its name and "fällig seit 3 Tagen · zuletzt
 * 02.10.", worded from the server's values (MNT-02). Nothing shows when nothing is due. While a
 * pop-up is open the rows don't change: polling (SYNC-08) shows the new ones once it is closed.
 * When the row whose button had the focus leaves (added, hidden), the focus moves to the same
 * button of the next row, or of the one above, or to the item field when none is left.
 */
export function DueBox({ ref, items, onAdd, onHide, disabled, frozen, onEmpty }: DueBoxProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const headingId = useId();
  const [shownRows, setShownRows] = useState(items);
  if (!frozen && shownRows !== items) setShownRows(items);
  const rows = frozen ? shownRows : items;
  /** The row and button last tapped, and where that row was. */
  const acted = useRef<{ id: string; index: number; action: DueAction } | null>(null);
  const buttons = useRef(new Map<string, HTMLButtonElement>());

  function focusActed(): boolean {
    const last = acted.current;
    if (!last) return false;
    const index = rows.findIndex((row) => row.ingredient.id === last.id);
    const at = index >= 0 ? index : Math.min(last.index, rows.length - 1);
    const row = rows[at];
    if (!row) {
      acted.current = null;
      return false;
    }
    acted.current = { id: row.ingredient.id, index: at, action: last.action };
    buttons.current.get(`${last.action}:${row.ingredient.id}`)?.focus();
    return true;
  }

  useImperativeHandle(ref, () => ({ restoreFocus: focusActed }));

  // The row that had the focus left: its button went, and the focus with it (to the page).
  useLayoutEffect(() => {
    const last = acted.current;
    if (!last || rows.some((row) => row.ingredient.id === last.id)) return;
    const active = document.activeElement;
    if (active !== null && active !== document.body) {
      acted.current = null;
      return;
    }
    if (!focusActed()) onEmpty();
  });

  function act(item: DueItem, index: number, action: DueAction) {
    acted.current = { id: item.ingredient.id, index, action };
    if (action === 'add') onAdd(item);
    else onHide(item);
  }

  function buttonRef(action: DueAction, id: string) {
    return (button: HTMLButtonElement | null) => {
      if (button) buttons.current.set(`${action}:${id}`, button);
      else buttons.current.delete(`${action}:${id}`);
    };
  }

  if (rows.length === 0) return null;
  return (
    <section
      aria-labelledby={headingId}
      data-testid={testIds.dueBox}
      className="flex flex-col rounded-xl border bg-card"
    >
      <h3
        id={headingId}
        className="px-4 pt-3 text-sm font-semibold tracking-wide text-muted-foreground uppercase"
      >
        {t('lists.due.title')}
      </h3>
      <ul aria-labelledby={headingId} className="flex flex-col divide-y">
        {rows.map((item, index) => {
          const name = ingredientLabel(item.ingredient.name, item.ingredient.brand);
          return (
            <li
              key={item.ingredient.id}
              data-testid={testIds.dueItem}
              className="flex min-h-(--tap-target) items-center gap-2 py-2 pr-2 pl-4"
            >
              <div className="flex min-w-0 flex-1 flex-col">
                <IngredientName ingredient={item.ingredient} />
                <span className="text-sm text-muted-foreground">{dueLine(t, language, item)}</span>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="text-primary"
                disabled={disabled}
                aria-label={t('lists.due.add', { name })}
                ref={buttonRef('add', item.ingredient.id)}
                onClick={() => act(item, index, 'add')}
              >
                <Plus aria-hidden="true" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="text-muted-foreground"
                disabled={disabled}
                aria-label={t('lists.due.hide', { name })}
                ref={buttonRef('hide', item.ingredient.id)}
                onClick={() => act(item, index, 'hide')}
              >
                <X aria-hidden="true" />
              </Button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
