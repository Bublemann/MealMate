import { Check, CircleCheck, CloudOff, Pencil, RefreshCw, ShoppingBasket } from 'lucide-react';
import { useEffect, useId, useRef, useState, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
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
import { useLanguage } from '@/i18n';
import { userLabel } from '@/i18n/users';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import {
  stampOp,
  useCheckLine,
  useFinishList,
  type ListDetail,
  type ListLine,
  type OpStamp,
} from './api';
import { ExtraItemDialog } from './ExtraItemDialog';
import { ExtraItemInput } from './ExtraItemInput';
import { groupByCategory, initialOf, lineAmount, needsMoreTexts, reminderText } from './format';
import { ListMeals } from './ListMeals';
import { Reminder } from './Reminder';

interface ShoppingViewProps {
  list: ListDetail;
  categoryKeys: ReadonlyMap<string, string>;
  /** The last load of the list failed for want of a connection (SYNC-07). */
  unreachable: boolean;
  onRefresh: () => void;
  onAddMeals: () => void;
}

/** Where the focus goes once a line has moved: a line to buy (by key), or the cart. */
const CART = Symbol('cart');

/**
 * The list while shopping (SHOP): big check boxes by category, checked lines in the collapsed
 * "In the cart" section with who checked them, quick add (SHOP-02), extra items editable from
 * their line, the meals still editable but collapsed (LIST-12), and "Finish shopping" (SHOP-04).
 * Checking the last line offers to finish, once per visit.
 *
 * A checked line leaves the list, so the focus moves on to the next line to buy (the cart once
 * there is none), and an unchecked one keeps it in its new place; a polite live region says where
 * the line went.
 */
export function ShoppingView({
  list,
  categoryKeys,
  unreachable,
  onRefresh,
  onAddMeals,
}: ShoppingViewProps) {
  const { t } = useTranslation();
  const headingId = useId();
  const check = useCheckLine(list.id);
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
  const groups = groupByCategory(open, categoryKeys, t);
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

  function onCheck(line: ListLine, checked: boolean) {
    check.mutate(
      { key: line.key, checked, ...stampOp() },
      {
        onError: () => {
          focusNext.current = null;
        },
      },
    );
    setAnnouncement(
      t(checked ? 'lists.shop.inCart' : 'lists.shop.backOnList', { name: line.name }),
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
      <SyncStatus unreachable={unreachable} onRefresh={onRefresh} />
      <section aria-labelledby={headingId} className="flex flex-col gap-4">
        <h2 id={headingId} className="text-xl font-semibold">
          {t('lists.lines.title')}
        </h2>
        {!editable && <p className="text-muted-foreground">{t('lists.shop.readOnly')}</p>}
        <ErrorAlert error={check.error} />
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
        {editable && (
          <Button
            data-testid={testIds.finishShopping}
            onClick={() => setFinishOpen(true)}
            className="self-start"
          >
            <ShoppingBasket aria-hidden="true" />
            {t('lists.shop.finish')}
          </Button>
        )}
        <Reminder seed={list.reminder_seed} />
      </section>
      {editable && <ExtraItemInput listId={list.id} shopping />}
      <ListMeals list={list} editable={editable} collapsible onAddMeals={onAddMeals} />
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

/** SYNC-07 in short (M6 adds the offline states): did the last request reach the server? */
function SyncStatus({ unreachable, onRefresh }: { unreachable: boolean; onRefresh: () => void }) {
  const { t } = useTranslation();

  return (
    <div className="-mt-2 flex items-center justify-between gap-3">
      <p
        role="status"
        data-testid={testIds.syncStatus}
        className={cn(
          'flex items-center gap-2 text-sm',
          unreachable ? 'font-medium text-destructive' : 'text-muted-foreground',
        )}
      >
        {unreachable ? (
          <CloudOff aria-hidden="true" className="size-4 shrink-0" />
        ) : (
          <Check aria-hidden="true" className="size-4 shrink-0" />
        )}
        {unreachable ? t('lists.sync.unreachable') : t('lists.sync.saved')}
      </p>
      <Button variant="ghost" size="compact" data-testid={testIds.refreshList} onClick={onRefresh}>
        <RefreshCw aria-hidden="true" />
        {t('lists.sync.refresh')}
      </Button>
    </div>
  );
}

/** What every row needs from the view. */
interface RowProps {
  editable: boolean;
  onCheck: (line: ListLine, checked: boolean) => void;
  /** Keeps track of each line's check box, to move the focus to it. */
  box: (key: string) => (element: HTMLInputElement | null) => void;
  /** Opens the dialog of an extra item (editors). */
  onEdit?: (extraId: string) => void;
}

interface CategoryCheckLinesProps {
  name: string;
  lines: ListLine[];
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
  lines: ListLine[];
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
  line: ListLine;
}

/**
 * One line with a big check box (SHOP-01). The whole row is its label, and the box itself is at
 * least 44 × 44 px. Badges say what is new or needs more (LIST-12); a checked line is struck
 * through and shows who checked it. A line with an extra item has a button to change or remove
 * the item (editors, LIST-12).
 */
function CheckRow({ line, editable, onCheck, box, onEdit }: CheckRowProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const amount = lineAmount(t, language, line);
  const more = line.needs_more ? needsMoreTexts(t, language, line.needs_more) : [];
  const checkedBy = line.checked ? line.checked_by : null;
  const extraId = line.sources.find((source) => source.kind === 'extra')?.extra_id ?? null;

  return (
    <li data-testid={testIds.shoppingLine} className="flex items-center">
      <label
        className={cn(
          'flex min-h-14 min-w-0 flex-1 items-center gap-3 py-1.5 pr-4 pl-1.5',
          editable && 'cursor-pointer hover:bg-accent/50',
        )}
      >
        <span className="relative flex size-(--tap-target) shrink-0 items-center justify-center">
          <input
            ref={box(line.key)}
            type="checkbox"
            aria-label={t(line.checked ? 'lists.shop.uncheck' : 'lists.shop.check', {
              name: line.name,
            })}
            checked={line.checked}
            disabled={!editable}
            onChange={(event) => onCheck(line, event.target.checked)}
            className="peer absolute inset-0 size-full cursor-pointer appearance-none rounded-md opacity-0 disabled:cursor-default"
          />
          <span
            aria-hidden="true"
            className="flex size-8 items-center justify-center rounded-md border-2 border-input bg-background text-primary-foreground peer-checked:border-primary peer-checked:bg-primary peer-focus-visible:ring-[3px] peer-focus-visible:ring-ring peer-disabled:opacity-60"
          >
            {line.checked && <Check className="size-6" strokeWidth={3} />}
          </span>
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex items-baseline justify-between gap-3">
            <span
              className={cn(
                'min-w-0 break-words',
                line.checked && 'text-muted-foreground line-through',
              )}
            >
              {line.name}
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
          {(line.new || more.length > 0) && (
            <span className="flex flex-wrap gap-1">
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
        </span>
        {checkedBy && (
          <>
            <span
              data-testid={testIds.lineCheckedBy}
              aria-hidden="true"
              title={userLabel(t, checkedBy)}
              className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent text-sm font-semibold text-accent-foreground"
            >
              {initialOf(checkedBy.display_name)}
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
          aria-label={t('lists.sources.editLabel', { name: line.name })}
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
  list: ListDetail;
  /** Visible lines not checked off. */
  unchecked: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Where the focus goes when the dialog closes (default: back to what opened it). */
  onCloseAutoFocus?: (event: Event) => void;
}

/**
 * SHOP-04: the reminder, how many items aren't checked, then *Finish* or *Keep shopping*. The tap
 * on *Finish* is stamped once per opening, so trying again after an error is the same op.
 */
function FinishDialog({
  list,
  unchecked,
  open,
  onOpenChange,
  onCloseAutoFocus,
}: FinishDialogProps) {
  const { t } = useTranslation();
  const finish = useFinishList(list.id);
  const stamp = useRef<OpStamp | null>(null);

  function onOpen(next: boolean) {
    if (next) {
      finish.reset();
      stamp.current = null;
    }
    onOpenChange(next);
  }

  function onFinish() {
    stamp.current ??= stampOp();
    finish.mutate(stamp.current, { onSuccess: () => onOpenChange(false) });
  }

  return (
    <Dialog open={open} onOpenChange={onOpen}>
      <DialogContent data-testid={testIds.finishDialog} onCloseAutoFocus={onCloseAutoFocus}>
        <DialogHeader>
          <DialogTitle>{t('lists.shop.finishTitle')}</DialogTitle>
          <DialogDescription>{t('lists.shop.finishText')}</DialogDescription>
        </DialogHeader>
        {unchecked > 0 && (
          <p className="font-semibold">{t('lists.shop.unchecked', { count: unchecked })}</p>
        )}
        <p className="rounded-xl bg-accent px-4 py-3 text-accent-foreground">
          <span className="sr-only">{t('lists.reminderLabel')}: </span>
          {reminderText(t, list.reminder_seed)}
        </p>
        <ErrorAlert error={finish.error} />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpen(false)}>
            {t('lists.shop.keepShopping')}
          </Button>
          <Button disabled={finish.isPending} onClick={onFinish}>
            {t('lists.shop.finishConfirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
