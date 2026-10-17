import type { TFunction } from 'i18next';
import { EyeOff, Pencil, RotateCcw, Trash2 } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { SwipeRow } from '@/components/SwipeRow';
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

interface ListLinesProps {
  list: ListDetail;
  /** The categories, for the headings. */
  categories: readonly Category[];
  /** Lines can be removed and restored, and extra items changed (editors of a draft). */
  editable: boolean;
  /** What comes first under the heading: the item field (D-41). */
  top?: ReactNode;
}

/**
 * The Artikel section of a draft or a read-only list: what `top` holds (the item field), then
 * the aggregated lines under their category headings, in the order the server sorted them
 * (LIST-05, AGG). Tapping a line shows where it comes from (LIST-08); a line can be hidden for
 * this list by swiping it to the left (D-40) or with the button in that dialog, and comes back
 * from the collapsed "Hidden" section (LIST-07). Offline these changes are disabled (SYNC-03).
 */
export function ListLines({ list, categories, editable, top }: ListLinesProps) {
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
      {top}
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
      <ul
        aria-labelledby={headingId}
        className="flex flex-col divide-y overflow-hidden rounded-xl border bg-card"
      >
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

/** One line; on touch screens a swipe to the left reveals "Hide" (LIST-07, D-40). */
function LineRow({ line, swipeable, onOpen, onHide }: LineRowProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const amount = lineAmount(t, language, line);

  return (
    <li data-testid={testIds.listLine}>
      <SwipeRow
        action={{ label: t('lists.lines.hide'), icon: EyeOff, tone: 'neutral', onAction: onHide }}
        disabled={!swipeable}
      >
        {/* Centred in the tap target, while name and amount share a baseline. */}
        <button
          type="button"
          onClick={onOpen}
          className="flex min-h-(--tap-target) w-full items-center px-4 py-2.5 text-left outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
        >
          <span className="flex min-w-0 flex-1 items-baseline justify-between gap-3">
            <span className="min-w-0 break-words">{lineLabel(line)}</span>
            {amount && (
              <span className="shrink-0 text-right font-medium tabular-nums">{amount}</span>
            )}
          </span>
        </button>
      </SwipeRow>
    </li>
  );
}

interface HiddenLinesProps {
  lines: ListLine[];
  editable: boolean;
  offline: boolean;
  onRestore: (line: ListLine) => void;
}

/** LIST-07: lines hidden for this list, collapsed under "Hidden (N)"; each can be restored. */
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
