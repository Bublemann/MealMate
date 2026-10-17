import { Plus, X } from 'lucide-react';
import { useId, useState, type Ref } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { ingredientLabel } from '@/features/ingredients/label';
import { IngredientName } from '@/features/ingredients/IngredientName';
import type { DueItem } from '@/features/recurring/api';
import { dueLine } from '@/features/recurring/format';
import { useLanguage } from '@/i18n';
import { testIds } from '@/testIds';

interface DueBoxProps {
  /** The box, to take the focus back from the amount pop-up. */
  ref?: Ref<HTMLElement>;
  /** The due items as the list detail carries them, most overdue first (the server sorts). */
  items: readonly DueItem[];
  /** ＋: the item field's amount pop-up for it. */
  onAdd: (item: DueItem) => void;
  /** ✕: hide it on this list, for everyone who sees the list. */
  onHide: (item: DueItem) => void;
  /** Offline: ＋ and ✕ are inactive, not hidden (SYNC-03). */
  disabled: boolean;
  /** While a pop-up is open the rows stay as they are, so a load of the list doesn't move them. */
  frozen: boolean;
}

/**
 * The "Fällig" box below the item field of a draft (LIST-16, D-42): the due recurring items of the
 * viewer's set that aren't on the list, each with its name and "fällig seit 3 Tagen · zuletzt
 * 02.10.", worded from the server's values (MNT-02). Nothing shows when nothing is due. While a
 * pop-up is open the rows don't change: polling (SYNC-08) shows the new ones once it is closed.
 */
export function DueBox({ ref, items, onAdd, onHide, disabled, frozen }: DueBoxProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const headingId = useId();
  const [held, setHeld] = useState(items);
  if (!frozen && held !== items) setHeld(items);
  const rows = frozen ? held : items;

  if (rows.length === 0) return null;
  return (
    <section
      ref={ref}
      tabIndex={-1}
      aria-labelledby={headingId}
      data-testid={testIds.dueBox}
      className="flex flex-col rounded-xl border bg-card outline-none"
    >
      <h3
        id={headingId}
        className="px-4 pt-3 text-sm font-semibold tracking-wide text-muted-foreground uppercase"
      >
        {t('lists.due.title')}
      </h3>
      <ul aria-labelledby={headingId} className="flex flex-col divide-y">
        {rows.map((item) => {
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
                onClick={() => onAdd(item)}
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
                onClick={() => onHide(item)}
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
