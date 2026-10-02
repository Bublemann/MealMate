import type { TFunction } from 'i18next';
import { EyeOff, Pencil, RotateCcw, Trash2 } from 'lucide-react';
import { useId, useRef, useState, type PointerEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
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
import { cn } from '@/lib/utils';
import type { Category } from '@/features/reference/api';
import { useConnected } from '@/features/sync/context';
import { testIds } from '@/testIds';
import {
  useRemoveExtraItem,
  useSetLineHidden,
  type LineSource,
  type ListDetail,
  type ListLine,
} from './api';
import { ExtraItemDialog } from './ExtraItemDialog';
import { groupByCategory, lineAmount, lineLabel, sourceAmount } from './format';
import { Reminder } from './Reminder';

/** How far (px) a line has to be swiped to the left to be removed for this list (LIST-07). */
const SWIPE_DISTANCE = 96;

interface ListLinesProps {
  list: ListDetail;
  /** The categories, for the headings. */
  categories: readonly Category[];
  /** Lines can be removed and restored, and extra items changed (editors of a draft). */
  editable: boolean;
}

/**
 * The aggregated lines under their category headings, in the order the server sorted them
 * (LIST-05, AGG). Tapping a line shows where it comes from (LIST-08); a line can be removed for
 * this list by swiping it to the left or with the button in that dialog, and comes back from the
 * collapsed "Removed" section (LIST-07). The reminder is the last row (LIST-14). Offline these
 * changes are disabled (SYNC-03).
 */
export function ListLines({ list, categories, editable }: ListLinesProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const offline = !useConnected();
  const headingId = useId();
  const setHidden = useSetLineHidden(list.id);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const shown = list.lines.filter((line) => !line.hidden);
  const hidden = list.lines.filter((line) => line.hidden);
  const groups = groupByCategory(shown, categories, language);
  const open = list.lines.find((line) => line.key === openKey) ?? null;
  const editing = list.extra_items.find((item) => item.id === editingId) ?? null;
  const editingName =
    list.lines.find((line) => line.sources.some((source) => source.extra_id === editingId))?.name ??
    '';

  function hide(line: ListLine, value: boolean) {
    setHidden.mutate({ key: line.key, hidden: value });
  }

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      <h2 id={headingId} className="text-xl font-semibold">
        {t('lists.lines.title')}
      </h2>
      <ErrorAlert error={setHidden.error} />
      {shown.length === 0 && hidden.length === 0 && (
        <p className="text-muted-foreground">{t('lists.lines.empty')}</p>
      )}
      {groups.length > 0 && (
        <div data-testid={testIds.listLines} className="flex flex-col gap-4">
          {groups.map((group) => (
            <CategoryLines
              key={group.categoryId}
              name={group.name}
              lines={group.lines}
              editable={editable && !offline}
              onOpen={(line) => setOpenKey(line.key)}
              onHide={(line) => hide(line, true)}
            />
          ))}
        </div>
      )}
      {hidden.length > 0 && (
        <HiddenLines
          lines={hidden}
          editable={editable}
          offline={offline}
          onRestore={(line) => hide(line, false)}
        />
      )}
      <Reminder seed={list.reminder_seed} />
      <SourcesDialog
        listId={list.id}
        line={open}
        editable={editable}
        offline={offline}
        onClose={() => setOpenKey(null)}
        onHide={(line, value) => {
          hide(line, value);
          setOpenKey(null);
        }}
        onEdit={(extraId) => {
          setOpenKey(null);
          setEditingId(extraId);
        }}
      />
      <ExtraItemDialog
        listId={list.id}
        item={editing}
        name={editingName}
        onClose={() => setEditingId(null)}
      />
    </section>
  );
}

interface CategoryLinesProps {
  name: string;
  lines: ListLine[];
  editable: boolean;
  onOpen: (line: ListLine) => void;
  onHide: (line: ListLine) => void;
}

function CategoryLines({ name, lines, editable, onOpen, onHide }: CategoryLinesProps) {
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
          <LineRow
            key={line.key}
            line={line}
            swipeable={editable}
            onOpen={() => onOpen(line)}
            onHide={() => onHide(line)}
          />
        ))}
      </ul>
    </section>
  );
}

interface LineRowProps {
  line: ListLine;
  swipeable: boolean;
  onOpen: () => void;
  onHide: () => void;
}

/** One line; on touch screens it can be swiped to the left to remove it for this list. */
function LineRow({ line, swipeable, onOpen, onHide }: LineRowProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const amount = lineAmount(t, language, line);
  const start = useRef<{ x: number; y: number; pointer: number } | null>(null);
  // A swipe must not also count as a tap on the line.
  const moved = useRef(false);
  const [offset, setOffset] = useState(0);

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (!swipeable || event.pointerType === 'mouse') return;
    start.current = { x: event.clientX, y: event.clientY, pointer: event.pointerId };
    moved.current = false;
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const origin = start.current;
    if (!origin || origin.pointer !== event.pointerId) return;
    const dx = event.clientX - origin.x;
    const dy = event.clientY - origin.y;
    if (!moved.current && Math.abs(dy) > Math.abs(dx)) {
      // Scrolling the page, not swiping the line.
      start.current = null;
      return;
    }
    if (Math.abs(dx) > 8) moved.current = true;
    setOffset(Math.min(0, dx));
  }

  function onPointerEnd() {
    if (!start.current) return;
    start.current = null;
    if (offset <= -SWIPE_DISTANCE) onHide();
    setOffset(0);
  }

  return (
    <li
      data-testid={testIds.listLine}
      className="relative overflow-hidden first:rounded-t-xl last:rounded-b-xl"
    >
      {offset < 0 && (
        <span
          aria-hidden="true"
          className="absolute inset-0 flex items-center justify-end gap-2 bg-destructive px-4 text-sm font-medium text-destructive-foreground"
        >
          <EyeOff className="size-5" />
          {t('lists.lines.hide')}
        </span>
      )}
      <div
        className={cn(
          'relative touch-pan-y bg-card',
          // Follows the finger while swiping, slides back when let go.
          offset === 0 && 'transition-transform motion-reduce:transition-none',
        )}
        style={offset < 0 ? { transform: `translateX(${offset}px)` } : undefined}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerEnd}
        onPointerCancel={() => {
          start.current = null;
          setOffset(0);
        }}
        onClickCapture={(event) => {
          if (!moved.current) return;
          moved.current = false;
          event.preventDefault();
          event.stopPropagation();
        }}
      >
        <button
          type="button"
          onClick={onOpen}
          className="flex min-h-(--tap-target) w-full items-baseline justify-between gap-3 px-4 py-2.5 text-left outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
        >
          <span className="min-w-0 break-words">{lineLabel(line)}</span>
          {amount && <span className="shrink-0 text-right font-medium tabular-nums">{amount}</span>}
        </button>
      </div>
    </li>
  );
}

interface HiddenLinesProps {
  lines: ListLine[];
  editable: boolean;
  offline: boolean;
  onRestore: (line: ListLine) => void;
}

/** LIST-07: lines removed for this list, collapsed; each can be restored. */
function HiddenLines({ lines, editable, offline, onRestore }: HiddenLinesProps) {
  const { t } = useTranslation();
  const language = useLanguage();

  return (
    <details data-testid={testIds.hiddenLines} className="group rounded-xl border bg-card">
      <summary className="flex min-h-(--tap-target) cursor-pointer items-center px-4 font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring">
        {t('lists.lines.hidden', { count: lines.length })}
      </summary>
      <div className="flex flex-col gap-2 border-t px-4 py-3">
        <p className="text-sm text-muted-foreground">{t('lists.lines.hiddenText')}</p>
        <ul className="flex flex-col divide-y">
          {lines.map((line) => {
            const amount = lineAmount(t, language, line);
            return (
              <li key={line.key} className="flex items-center justify-between gap-3 py-2">
                <span className="min-w-0 break-words text-muted-foreground">
                  {lineLabel(line)}
                  {amount && <span className="ml-2 tabular-nums">{amount}</span>}
                </span>
                {editable && (
                  <Button
                    variant="outline"
                    size="compact"
                    aria-label={t('lists.lines.restoreLabel', { name: lineLabel(line) })}
                    disabled={offline}
                    onClick={() => onRestore(line)}
                  >
                    <RotateCcw aria-hidden="true" />
                    {t('lists.lines.restore')}
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </details>
  );
}

interface SourcesDialogProps {
  listId: string;
  /** The line whose sources are shown; null closes the dialog. */
  line: ListLine | null;
  editable: boolean;
  /** Without a connection: the buttons are disabled. */
  offline: boolean;
  onClose: () => void;
  onHide: (line: ListLine, hidden: boolean) => void;
  onEdit: (extraId: string) => void;
}

/** LIST-08: where a line comes from; meals the viewer can't see are "Private meal" (VIS-06). */
function SourcesDialog({
  listId,
  line,
  editable,
  offline,
  onClose,
  onHide,
  onEdit,
}: SourcesDialogProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const removeItem = useRemoveExtraItem(listId);
  const amount = line ? lineAmount(t, language, line) : '';

  return (
    <Dialog open={line !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid={testIds.lineSources}>
        {line && (
          <>
            <DialogHeader>
              <DialogTitle className="break-words">{lineLabel(line)}</DialogTitle>
              {amount && <p className="text-lg font-medium tabular-nums">{amount}</p>}
            </DialogHeader>
            <DialogDescription className="font-medium text-foreground">
              {t('lists.sources.text')}
            </DialogDescription>
            <ul className="flex flex-col divide-y">
              {line.sources.map((source) => (
                <li
                  key={`${source.kind}:${source.list_meal_id ?? source.extra_id ?? ''}`}
                  className="flex flex-col gap-2 py-2"
                >
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="min-w-0 break-words">{sourceLabel(t, source)}</span>
                    <span className="shrink-0 font-medium tabular-nums">
                      {sourceAmount(t, language, source)}
                    </span>
                  </div>
                  {editable && source.kind === 'extra' && source.extra_id && (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        size="compact"
                        aria-label={t('lists.sources.editLabel', { name: lineLabel(line) })}
                        disabled={offline}
                        onClick={() => source.extra_id && onEdit(source.extra_id)}
                      >
                        <Pencil aria-hidden="true" />
                        {t('lists.sources.edit')}
                      </Button>
                      <Button
                        variant="outline"
                        size="compact"
                        aria-label={t('lists.item.removeLabel', { name: lineLabel(line) })}
                        disabled={removeItem.isPending || offline}
                        onClick={() => source.extra_id && removeItem.mutate(source.extra_id)}
                      >
                        <Trash2 aria-hidden="true" />
                        {t('lists.item.remove')}
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
            <ErrorAlert error={removeItem.error} />
            {editable && (
              <DialogFooter>
                {line.hidden ? (
                  <Button variant="outline" disabled={offline} onClick={() => onHide(line, false)}>
                    <RotateCcw aria-hidden="true" />
                    {t('lists.lines.restore')}
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    aria-label={t('lists.lines.hideLabel', { name: lineLabel(line) })}
                    disabled={offline}
                    onClick={() => onHide(line, true)}
                  >
                    <EyeOff aria-hidden="true" />
                    {t('lists.lines.hide')}
                  </Button>
                )}
              </DialogFooter>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function sourceLabel(t: TFunction, source: LineSource): string {
  if (source.kind === 'extra') return t('lists.sources.extra');
  const count = source.servings ?? 0;
  if (source.private || source.meal_name === null) {
    return t('lists.meals.privateServings', { count });
  }
  return t('lists.sources.meal', { name: source.meal_name, count });
}
