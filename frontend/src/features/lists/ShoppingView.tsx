import { Check, CircleCheck, Pencil, ShoppingBasket } from 'lucide-react';
import { useEffect, useId, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { FloatingBar, FloatingBarButton } from '@/components/FloatingBar';
import { InitialMarker } from '@/components/InitialMarker';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { Category } from '@/features/reference/api';
import type { PendingLine, PendingList } from '@/features/sync/applyPending';
import { useConnected, useQueueOp } from '@/features/sync/context';
import { useLanguage } from '@/i18n';
import { userLabel } from '@/i18n/users';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import { shoppingOps, stampOp } from './api';
import { ExtraItemDialog } from './ExtraItemDialog';
import { groupByCategory, lineAmount, lineLabel, needsMoreTexts } from './format';
import { ItemField } from './ItemField';
import { ListMeals } from './ListMeals';
import { MealField } from './MealField';

interface ShoppingViewProps {
  /** The list with the user's waiting changes applied. */
  list: PendingList;
  categories: readonly Category[];
}

/** Where the focus goes once a line has moved: a line to buy (by key), or the cart. */
const CART = Symbol('cart');

/**
 * The list while shopping (SHOP): Artikel first, with the item field (SHOP-02, D-41), big check
 * boxes by category and the checked lines in the collapsed "In the cart" section with who checked
 * them; extra items editable from their line; then the meals, still editable but collapsed under
 * "Gerichte (N)" with the meal field inside (LIST-12); and "Finish shopping" (SHOP-04)
 * in the floating bar above the tab bar (D-39). Checking the last line offers to finish, once per
 * visit.
 *
 * Checking off, free-text items and *Finish* go through the outbox, online or offline (SYNC-03):
 * stored, shown at once, then sent; what hasn't been sent yet looks faded (SYNC-07).
 *
 * A checked line leaves the list, so the focus moves on to the next line to buy (the cart once
 * there is none), and an unchecked one keeps it in its new place; a polite live region says where
 * the line went.
 */
export function ShoppingView({ list, categories }: ShoppingViewProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const headingId = useId();
  const queue = useQueueOp(list.id);
  const connected = useConnected();
  const [finishOpen, setFinishOpen] = useState(false);
  const [announcement, setAnnouncement] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const offered = useRef(false);
  const boxes = useRef(new Map<string, HTMLInputElement>());
  const cartSummary = useRef<HTMLElement>(null);
  const focusNext = useRef<string | typeof CART | null>(null);
  const editable = list.can_edit;
  const shown = list.lines.filter((line) => !line.hidden);
  const open = shown.filter((line) => !line.checked);
  const inCart = shown.filter((line) => line.checked);
  const groups = groupByCategory(open, categories, language);
  // In the order they are shown, across the categories.
  const openInOrder = groups.flatMap((group) => group.lines);
  const editing = list.extra_items.find((item) => item.id === editingId) ?? null;
  const editingName =
    list.lines.find((line) => line.sources.some((source) => source.extra_id === editingId))?.name ??
    '';

  // Moves the focus once its target is on screen: the cart appears with its first line, and an
  // unchecked line's box among the lines to buy replaces the one in the cart. Not away from the
  // finish dialog, which leaves the focus here when it closes.
  useEffect(() => {
    const target = focusNext.current;
    if (target === null || finishOpen) return;
    const element = target === CART ? cartSummary.current : boxes.current.get(target);
    if (element && !(element instanceof HTMLInputElement && element.checked)) {
      focusNext.current = null;
      element.focus();
    }
  });

  function onCheck(line: PendingLine, checked: boolean) {
    void queue(shoppingOps.check(line.key, checked, stampOp()));
    setAnnouncement(
      t(checked ? 'lists.shop.inCart' : 'lists.shop.backOnList', { name: lineLabel(line) }),
    );
    if (checked) {
      const index = openInOrder.findIndex((other) => other.key === line.key);
      const next = openInOrder[index + 1] ?? openInOrder[index - 1];
      focusNext.current = next ? next.key : CART;
    } else {
      focusNext.current = line.key;
    }
    const last = open.length === 1 && open[0]?.key === line.key;
    if (checked && last && !offered.current) {
      offered.current = true;
      setFinishOpen(true);
    }
  }

  function box(key: string) {
    return (element: HTMLInputElement | null) => {
      if (element) boxes.current.set(key, element);
      else boxes.current.delete(key);
    };
  }

  const rowProps = {
    editable,
    onCheck,
    box,
    onEdit: editable ? (extraId: string) => setEditingId(extraId) : undefined,
  };

  return (
    <>
      <section aria-labelledby={headingId} className="flex flex-col gap-4">
        <h2 id={headingId} className="text-xl font-semibold">
          {t('lists.lines.title')}
        </h2>
        {editable && <ItemField listId={list.id} shopping />}
        {!editable && <p className="text-muted-foreground">{t('lists.shop.readOnly')}</p>}
        {shown.length === 0 && <p className="text-muted-foreground">{t('lists.lines.empty')}</p>}
        {shown.length > 0 && open.length === 0 && (
          <p className="flex items-center gap-2 font-medium">
            <CircleCheck aria-hidden="true" className="size-5 text-primary" />
            {t('lists.shop.allChecked')}
          </p>
        )}
        {groups.length > 0 && (
          <div data-testid={testIds.shoppingLines} className="flex flex-col gap-4">
            {groups.map((group) => (
              <CategoryCheckLines
                key={group.categoryId}
                name={group.name}
                lines={group.lines}
                rowProps={rowProps}
              />
            ))}
          </div>
        )}
        {inCart.length > 0 && (
          <InTheCart lines={inCart} summaryRef={cartSummary} rowProps={rowProps} />
        )}
        <p data-testid={testIds.shoppingAnnouncement} aria-live="polite" className="sr-only">
          {announcement}
        </p>
      </section>
      <ListMeals
        list={list}
        editable={editable}
        collapsible
        // Changing meals needs a connection (LIST-12, SYNC-03).
        field={editable && <MealField listId={list.id} disabled={!connected} />}
      />
      {editable && (
        <ExtraItemDialog
          listId={list.id}
          item={editing}
          name={editingName}
          shopping
          onClose={() => setEditingId(null)}
        />
      )}
      {editable && (
        // Above the tab bar, under the thumb (D-39); finishing works offline too.
        <FloatingBar>
          <FloatingBarButton
            data-testid={testIds.finishShopping}
            onClick={() => setFinishOpen(true)}
          >
            <ShoppingBasket aria-hidden="true" />
            {t('lists.shop.finish')}
          </FloatingBarButton>
        </FloatingBar>
      )}
      {editable && (
        <FinishDialog
          list={list}
          unchecked={open.length}
          open={finishOpen}
          onOpenChange={setFinishOpen}
          onCloseAutoFocus={(event) => {
            // Offered after the last line: the focus goes on as after any check-off.
            if (focusNext.current !== null) event.preventDefault();
          }}
        />
      )}
    </>
  );
}

/** What every row needs from the view. */
interface RowProps {
  editable: boolean;
  onCheck: (line: PendingLine, checked: boolean) => void;
  /** Keeps track of each line's check box, to move the focus to it. */
  box: (key: string) => (element: HTMLInputElement | null) => void;
  /** Opens the dialog of an extra item (editors). */
  onEdit?: (extraId: string) => void;
}

interface CategoryCheckLinesProps {
  name: string;
  lines: PendingLine[];
  rowProps: RowProps;
}

function CategoryCheckLines({ name, lines, rowProps }: CategoryCheckLinesProps) {
  const headingId = useId();

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h3
        id={headingId}
        className="text-sm font-semibold tracking-wide text-muted-foreground uppercase"
      >
        {name}
      </h3>
      <ul aria-labelledby={headingId} className="flex flex-col divide-y rounded-xl border bg-card">
        {lines.map((line) => (
          <CheckRow key={line.key} line={line} {...rowProps} />
        ))}
      </ul>
    </section>
  );
}

interface InTheCartProps {
  lines: PendingLine[];
  summaryRef: RefObject<HTMLElement | null>;
  rowProps: RowProps;
}

/** SHOP-01: the checked lines, collapsed at the bottom; each can be unchecked again. */
function InTheCart({ lines, summaryRef, rowProps }: InTheCartProps) {
  const { t } = useTranslation();
  const summaryId = useId();

  return (
    <details data-testid={testIds.inTheCart} className="rounded-xl border bg-card">
      <summary
        ref={summaryRef}
        id={summaryId}
        className="flex min-h-(--tap-target) cursor-pointer items-center px-4 font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring"
      >
        {t('lists.shop.cart', { count: lines.length })}
      </summary>
      <ul aria-labelledby={summaryId} className="flex flex-col divide-y border-t">
        {lines.map((line) => (
          <CheckRow key={line.key} line={line} {...rowProps} />
        ))}
      </ul>
    </details>
  );
}

interface CheckRowProps extends RowProps {
  line: PendingLine;
}

/**
 * One line with a big check box (SHOP-01). The whole row is its label, and the box itself is at
 * least 44 × 44 px. Badges say what is new or needs more (LIST-12); a checked line is struck
 * through and shows who checked it. A line with an extra item has a button to change or remove
 * the item (editors, LIST-12). A line whose change hasn't been sent yet is faded and says so
 * (SYNC-07).
 *
 * The box and the marker are centred on the name, with or without badges and the pending note
 * stacked under it. On such a stacked row the edit button lines up with the name's first line.
 */
function CheckRow({ line, editable, onCheck, box, onEdit }: CheckRowProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const amount = lineAmount(t, language, line);
  const more = line.needs_more ? needsMoreTexts(t, language, line.needs_more) : [];
  const checkedBy = line.checked ? line.checked_by : null;
  const extraId = line.sources.find((source) => source.kind === 'extra')?.extra_id ?? null;
  const hasBadges = line.new || more.length > 0;
  const stacked = line.pending || hasBadges;

  return (
    <li
      data-testid={testIds.shoppingLine}
      className={cn(
        'flex',
        stacked ? 'items-start' : 'items-center',
        line.pending && 'bg-muted/50',
      )}
    >
      {/*
       * The first grid row holds the box, the name and the marker, centred on each other; the
       * pending note and the badges go in the rows below, under the name. The box and the marker
       * count as one line high and overflow it, so what is stacked follows right under the name;
       * a stacked row's top padding makes room for the box. The minimum height keeps the box's
       * own height plus padding, as for a row with nothing stacked.
       */}
      <label
        className={cn(
          'grid min-h-[calc(var(--tap-target)+0.75rem)] min-w-0 flex-1 items-center gap-x-3 gap-y-1 py-1.5 pr-4 pl-1.5',
          checkedBy ? 'grid-cols-[auto_minmax(0,1fr)_auto]' : 'grid-cols-[auto_minmax(0,1fr)]',
          stacked && 'pt-[calc((var(--tap-target)-1lh)/2)]',
          editable && 'cursor-pointer hover:bg-accent/50',
        )}
      >
        <span className="flex h-[1lh] items-center">
          <span className="relative flex size-(--tap-target) items-center justify-center">
            <input
              ref={box(line.key)}
              type="checkbox"
              aria-label={t(line.checked ? 'lists.shop.uncheck' : 'lists.shop.check', {
                name: lineLabel(line),
              })}
              checked={line.checked}
              disabled={!editable}
              onChange={(event) => onCheck(line, event.target.checked)}
              className="peer absolute inset-0 size-full cursor-pointer appearance-none rounded-md opacity-0 disabled:cursor-default"
            />
            <span
              aria-hidden="true"
              className={cn(
                'flex size-8 items-center justify-center rounded-md border-2 border-input bg-background text-primary-foreground peer-checked:border-primary peer-checked:bg-primary peer-focus-visible:ring-[3px] peer-focus-visible:ring-ring peer-disabled:opacity-60',
                // Faded while not sent (SYNC-07); the text keeps its contrast and says so.
                line.pending && 'opacity-50 peer-checked:opacity-50',
              )}
            >
              {line.checked && <Check className="size-6" strokeWidth={3} />}
            </span>
          </span>
        </span>
        <span className="flex items-baseline justify-between gap-3">
          <span
            className={cn(
              'min-w-0 break-words',
              line.checked && 'text-muted-foreground line-through',
            )}
          >
            {lineLabel(line)}
          </span>
          {amount && (
            <span
              className={cn(
                'shrink-0 text-right font-medium tabular-nums',
                line.checked && 'text-muted-foreground line-through',
              )}
            >
              {amount}
            </span>
          )}
        </span>
        {line.pending && (
          <span
            data-testid={testIds.linePending}
            className="col-start-2 text-sm text-muted-foreground"
          >
            {t('lists.sync.pending')}
          </span>
        )}
        {hasBadges && (
          <span className="col-start-2 flex flex-wrap gap-1">
            {line.new && (
              <Badge data-testid={testIds.lineNew} variant="secondary">
                {t('lists.shop.new')}
              </Badge>
            )}
            {more.length > 0 && (
              <span data-testid={testIds.lineNeedsMore} className="flex flex-wrap gap-1">
                <span className="sr-only">{t('lists.shop.needsMore')}</span>
                {more.map((text) => (
                  <Badge key={text} variant="outline">
                    {text}
                  </Badge>
                ))}
              </span>
            )}
          </span>
        )}
        {checkedBy && (
          <>
            {/* In the first row, one line high like the box. */}
            <span className="col-start-3 row-start-1 flex h-[1lh] items-center">
              <InitialMarker user={checkedBy} decorative testId={testIds.lineCheckedBy} />
            </span>
            <span className="sr-only">
              {t('lists.shop.checkedBy', { name: userLabel(t, checkedBy) })}
            </span>
          </>
        )}
      </label>
      {onEdit && extraId && (
        <Button
          variant="ghost"
          size="icon"
          data-testid={testIds.editShoppingItem}
          aria-label={t('lists.sources.editLabel', { name: lineLabel(line) })}
          onClick={() => onEdit(extraId)}
          className="mr-1 shrink-0"
        >
          <Pencil aria-hidden="true" />
        </Button>
      )}
    </li>
  );
}

interface FinishDialogProps {
  list: PendingList;
  /** Visible lines not checked off. */
  unchecked: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Where the focus goes when the dialog closes (default: back to what opened it). */
  onCloseAutoFocus?: (event: Event) => void;
}

/**
 * SHOP-04: how many items aren't checked, then *Finish* or *Keep shopping*. *Finish* is an op of
 * the outbox, stamped at the tap (the list counts as finished then), so it works offline too
 * (SYNC-03); the view shows the done list at once.
 */
function FinishDialog({
  list,
  unchecked,
  open,
  onOpenChange,
  onCloseAutoFocus,
}: FinishDialogProps) {
  const { t } = useTranslation();
  const queue = useQueueOp(list.id);
  const [finishing, setFinishing] = useState(false);

  function onFinish() {
    if (finishing) return;
    setFinishing(true);
    void queue(shoppingOps.finish(stampOp())).finally(() => {
      setFinishing(false);
      onOpenChange(false);
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={testIds.finishDialog} onCloseAutoFocus={onCloseAutoFocus}>
        <DialogHeader>
          <DialogTitle>{t('lists.shop.finishTitle')}</DialogTitle>
          <DialogDescription>{t('lists.shop.finishText')}</DialogDescription>
        </DialogHeader>
        {unchecked > 0 && (
          <p className="font-semibold">{t('lists.shop.unchecked', { count: unchecked })}</p>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('lists.shop.keepShopping')}
          </Button>
          <Button disabled={finishing} onClick={onFinish}>
            {t('lists.shop.finishConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
