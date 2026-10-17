import { notifyManager } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, GripVertical } from 'lucide-react';
import { useEffect, useId, useMemo, useRef, useState, type PointerEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { LoadError } from '@/components/LoadError';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { SettingsPage } from '@/features/me/SettingsPage';
import { categoryName } from '@/features/reference/labels';
import { useConnected } from '@/features/sync/context';
import { useLanguage } from '@/i18n';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import {
  useFollowAdminOrder,
  useSaveWalkingOrder,
  useWalkingOrder,
  type WalkingOrder,
} from './api';

type Direction = 'up' | 'down';

/** A drag by a row's handle, from the pointer going down until it is let go or cancelled. */
interface Drag {
  pointer: number;
  id: string;
  /** The order when it started, and the order shown before (null: the saved one). */
  start: string[];
  before: string[] | null;
  /** Where each row was when it started (px from the top): the places it can be dropped in. */
  slots: { top: number; bottom: number }[];
}

/** The place a pointer at `y` drops into: the row it is over, else the first or the last. */
function slotAt(slots: Drag['slots'], y: number): number {
  const index = slots.findIndex((slot) => y < slot.bottom);
  return index < 0 ? slots.length - 1 : index;
}

function movedTo(ids: readonly string[], id: string, index: number): string[] {
  const rest = ids.filter((each) => each !== id);
  return [...rest.slice(0, index), id, ...rest.slice(index)];
}

/**
 * Settings → Reihenfolge im Laden (UI-07, REF-01, D-48): the order the lists of the user, or of
 * their couple, are grouped in. "Reihenfolge der Verwaltung übernehmen" follows the admins' order
 * while it is on. Moving a category, by its up and down buttons or by dragging its handle, keeps
 * the order as the own one and turns the switch off; turning it back on asks first. A category an
 * admin added since is last and marked "neu" until it is moved. The page needs a connection
 * (SYNC-09).
 */
export function WalkingOrderScreen() {
  const { t } = useTranslation();
  const order = useWalkingOrder();

  return (
    <SettingsPage title={t('walkingOrder.title')} testId={testIds.screenWalkingOrder}>
      <p className="text-muted-foreground">{t('walkingOrder.text')}</p>
      {order.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <LoadError error={order.error} />
      {order.data && <OrderEditor order={order.data} />}
    </SettingsPage>
  );
}

function OrderEditor({ order }: { order: WalkingOrder }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const connected = useConnected();
  const save = useSaveWalkingOrder();
  const follow = useFollowAdminOrder();
  // The order on screen while moves wait for the server; null shows the saved one.
  const [moved, setMoved] = useState<string[] | null>(null);
  const ids = useMemo(
    () => moved ?? order.categories.map(({ id }) => id),
    [moved, order.categories],
  );
  const byId = new Map(order.categories.map((category) => [category.id, category]));
  // The switch shows what was asked for while it is being saved.
  const switchedOn = follow.isPending || (!save.isPending && moved === null && order.follows_admin);
  const [confirming, setConfirming] = useState(false);
  // After a move by its buttons the focus follows the category (its button may be disabled now).
  const [focus, setFocus] = useState<{ id: string; direction: Direction } | null>(null);
  const list = useRef<HTMLOListElement>(null);
  // Ends the drag under way, if there is one: it stops listening and forgets it.
  const endDrag = useRef<(() => void) | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const baseId = useId();
  const switchId = `${baseId}-follow`;
  const hintId = `${baseId}-hint`;
  const buttonId = (id: string, direction: Direction) => `${baseId}-${id}-${direction}`;
  // The order as text, so the focus moves when the order does, not when the server confirms it.
  const orderKey = ids.join(' ');

  useEffect(() => () => endDrag.current?.(), []);

  useEffect(() => {
    if (!focus) return;
    const shown = orderKey.split(' ');
    const index = shown.indexOf(focus.id);
    const atEdge = focus.direction === 'up' ? index === 0 : index === shown.length - 1;
    const direction = atEdge ? (focus.direction === 'up' ? 'down' : 'up') : focus.direction;
    document.getElementById(`${baseId}-${focus.id}-${direction}`)?.focus();
  }, [focus, orderKey, baseId]);

  /**
   * Each move is saved at once, the saves one after another (`api.ts`). Only the latest move's
   * callback runs: once its save is in, or has failed, the screen shows the cached order again,
   * which is then the server's, after React Query has passed it on, so an older order never
   * flashes up in between.
   */
  function saveMove(next: string[], movedId: string) {
    setMoved(next);
    save.mutate(
      { categoryIds: next, movedId },
      { onSettled: () => notifyManager.schedule(() => setMoved(null)) },
    );
  }

  function move(id: string, direction: Direction) {
    const index = ids.indexOf(id);
    const other = direction === 'up' ? index - 1 : index + 1;
    if (index < 0 || other < 0 || other >= ids.length) return;
    setFocus({ id, direction });
    saveMove(movedTo(ids, id, other), id);
  }

  function onSwitch(value: boolean) {
    // Off keeps the admins' order as it is as the own one; on drops the own one, after asking.
    if (value) setConfirming(true);
    else save.mutate({ categoryIds: ids });
  }

  /**
   * A drag by a row's handle. The pointer's moves and its letting go are followed on the window:
   * while the order changes, React moves the rows, the dragged one too, and a moved element may
   * lose the pointer capture.
   */
  function onHandleDown(event: PointerEvent<HTMLElement>, id: string) {
    if (!connected || !event.isPrimary || endDrag.current) return;
    const rows = [...(list.current?.children ?? [])];
    const drag: Drag = {
      pointer: event.pointerId,
      id,
      start: ids,
      before: moved,
      slots: rows.map((row) => {
        const { top, bottom } = row.getBoundingClientRect();
        return { top, bottom };
      }),
    };
    const onMove = (move: globalThis.PointerEvent) => {
      if (move.pointerId !== drag.pointer) return;
      setMoved(movedTo(drag.start, drag.id, slotAt(drag.slots, move.clientY)));
    };
    const onEnd = (end: globalThis.PointerEvent) => {
      if (end.pointerId !== drag.pointer) return;
      stop();
      const index = slotAt(drag.slots, end.clientY);
      if (end.type === 'pointercancel' || index === drag.start.indexOf(drag.id)) {
        setMoved(drag.before);
      } else {
        saveMove(movedTo(drag.start, drag.id, index), drag.id);
      }
    };
    function stop() {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onEnd);
      window.removeEventListener('pointercancel', onEnd);
      endDrag.current = null;
      setDragging(null);
    }
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onEnd);
    window.addEventListener('pointercancel', onEnd);
    endDrag.current = stop;
    setDragging(id);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <Label htmlFor={switchId} className="min-h-7">
            {t('walkingOrder.follow')}
          </Label>
          <p id={hintId} className="text-sm text-muted-foreground">
            {t('walkingOrder.followHint')}
          </p>
        </div>
        <Switch
          id={switchId}
          data-testid={testIds.walkingOrderSwitch}
          aria-describedby={hintId}
          checked={switchedOn}
          disabled={!connected || follow.isPending}
          onCheckedChange={onSwitch}
        />
      </div>
      <ol
        ref={list}
        data-testid={testIds.walkingOrderList}
        aria-label={t('walkingOrder.listLabel')}
        className="flex flex-col divide-y rounded-xl border bg-card"
      >
        {ids.map((id, index) => {
          const category = byId.get(id);
          if (!category) return null;
          const name = categoryName(category, language);
          return (
            // At the largest text sizes the name and the arrows wrap onto lines of their own
            // (UI-01).
            <li
              key={id}
              className={cn(
                'flex flex-wrap items-center gap-x-1 py-1 pr-2',
                dragging === id && 'bg-accent',
              )}
            >
              {/* Dragging is for touch and the mouse; screen readers and keyboards use the
                  buttons. The handle doesn't scroll the page. */}
              <span
                aria-hidden="true"
                data-testid={testIds.walkingOrderHandle}
                className={cn(
                  'flex size-(--tap-target) shrink-0 touch-none items-center justify-center text-muted-foreground select-none',
                  connected ? 'cursor-grab' : 'opacity-50',
                )}
                onPointerDown={(event) => onHandleDown(event, id)}
              >
                <GripVertical className="size-5" />
              </span>
              <span className="min-w-0 flex-[1_1_8rem] py-2 wrap-anywhere">
                {name}
                {category.new && (
                  <>
                    {' '}
                    <Badge variant="secondary">{t('walkingOrder.new')}</Badge>
                  </>
                )}
              </span>
              <div className="ml-auto flex flex-wrap justify-end">
                <Button
                  id={buttonId(id, 'up')}
                  size="icon"
                  variant="ghost"
                  aria-label={t('walkingOrder.moveUp', { name })}
                  disabled={!connected || index === 0}
                  onClick={() => move(id, 'up')}
                >
                  <ArrowUp aria-hidden="true" />
                </Button>
                <Button
                  id={buttonId(id, 'down')}
                  size="icon"
                  variant="ghost"
                  aria-label={t('walkingOrder.moveDown', { name })}
                  disabled={!connected || index === ids.length - 1}
                  onClick={() => move(id, 'down')}
                >
                  <ArrowDown aria-hidden="true" />
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      <ErrorAlert error={save.error ?? follow.error} />
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('walkingOrder.followTitle')}
        description={t('walkingOrder.followText')}
        confirmLabel={t('walkingOrder.followConfirm')}
        onConfirm={() => follow.mutate()}
      />
    </div>
  );
}
