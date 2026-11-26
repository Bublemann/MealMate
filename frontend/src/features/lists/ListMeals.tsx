import type { TFunction } from 'i18next';
import { CookingPot, EllipsisVertical, ShoppingCart, Trash2, X } from 'lucide-react';
import { useEffect, useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { MoreMenu, MoreMenuItem } from '@/components/MoreMenu';
import { SwipeRow } from '@/components/SwipeRow';
import { useMoreMenuFocus } from '@/components/useMoreMenuFocus';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { TapCheckbox } from '@/components/ui/tap-checkbox';
import { useConnected, useQueueOp } from '@/features/sync/context';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import {
  shoppingOps,
  stampOp,
  useRemoveListMeal,
  useSetListMealEaten,
  useSetListMealServings,
  useShopLeftover,
  type ListDetail,
  type ListMealEntry,
} from './api';
import { ServingsStepper } from './ServingsStepper';

/** How long the undo toast of a ticked leftover stays (LIST-17). */
export const UNDO_TOAST_MS = 8000;

interface ListMealsProps {
  list: ListDetail;
  /** Servings can be changed and meals added or removed (editors of a draft or while shopping). */
  editable: boolean;
  /** Collapsed under "Meals (N)", as while shopping (LIST-12). */
  collapsible?: boolean;
  /** The meal field, at the top of the section (D-41). */
  field?: ReactNode;
  /**
   * Each meal has an eaten checkbox and the heading counts the eaten ones, as on a done list
   * (SHOP-07). The boxes only show the state for those who may not edit the list, and offline.
   */
  eatenBoxes?: boolean;
}

/**
 * The Gerichte section: the meal field (editors), then the meals with their servings
 * (LIST-04/05); its heading shows even without meals. A meal the viewer can't
 * see is only "Private meal (N servings)" (VIS-06); a detached one is marked "no longer
 * available" and can be removed (LIST-15). Changing meals needs a connection: offline the controls
 * are disabled (SYNC-03). On a done list, a meal is ticked eaten and then struck through (SHOP-07).
 *
 * A leftover (LIST-17) shows "übrig", "Zutaten nicht auf der Liste" and an eaten box on every
 * list, its servings without a stepper, and for editors of a draft or a list being shopped a ⋮
 * menu with "Doch einkaufen" and "Entfernen". Ticked there, it leaves the list and a toast offers
 * to undo it; that tick and its undo go through the outbox, so they work offline too (SYNC-03).
 */
export function ListMeals({
  list,
  editable,
  collapsible = false,
  field,
  eatenBoxes = false,
}: ListMealsProps) {
  const { t } = useTranslation();
  const headingId = useId();
  const setServings = useSetListMealServings(list.id);
  const remove = useRemoveListMeal(list.id);
  const setEaten = useSetListMealEaten(list.id);
  const queue = useQueueOp(list.id);
  const shopLeftover = useShopLeftover(list.id);
  // Kept here: the mutation's own `error` follows only the latest tap.
  const [eatenError, setEatenError] = useState<unknown>(null);
  // The leftover just ticked on a draft or a list being shopped, whose tick can be undone.
  const [undo, setUndo] = useState<{ id: string; sourceId: string; label: string } | null>(null);
  const offline = !useConnected();
  const eatenCount = list.meals.filter((meal) => meal.eaten).length;
  const leavesList = list.status !== 'done';

  useEffect(() => {
    if (!undo) return;
    const timer = setTimeout(() => setUndo(null), UNDO_TOAST_MS);
    return () => clearTimeout(timer);
  }, [undo]);

  /** A meal of a done list (SHOP-07), its leftovers too: sent at once, online only. */
  function sendEaten(listMealId: string, eaten: boolean, settled: () => void) {
    setEatenError(null);
    void setEaten
      .mutateAsync({ listMealId, eaten })
      .catch((error: unknown) => setEatenError(error))
      .finally(settled);
  }

  /** A leftover of a draft or a list being shopped: queued, online or offline (D-60). */
  function queueEaten(sourceId: string, eaten: boolean) {
    setEatenError(null);
    return queue(shoppingOps.eatLeftover(sourceId, eaten, stampOp()));
  }

  /** The box of a leftover that leaves the list when ticked; undefined for any other. */
  function queuedEatenBox(entry: ListMealEntry): MealEntryProps['eatenBox'] {
    const sourceId = entry.leftover_of;
    // `leftover_of` is set exactly on leftovers.
    if (sourceId === null || !leavesList) return undefined;
    return {
      disabled: !list.can_edit,
      onChange: (eaten, settled) => {
        if (eaten) setUndo({ id: entry.id, sourceId, label: mealLabel(t, entry) });
        void queueEaten(sourceId, eaten)
          .then((queued) => {
            if (!queued) setUndo((current) => (current?.id === entry.id ? null : current));
          })
          .finally(settled);
      },
    };
  }

  const content = (
    <>
      {field}
      {list.meals.length === 0 ? (
        <p className="text-muted-foreground">{t('lists.meals.empty')}</p>
      ) : (
        <ul
          data-testid={testIds.listMeals}
          aria-labelledby={headingId}
          className="flex flex-col divide-y overflow-hidden rounded-xl border bg-card"
        >
          {list.meals.map((entry) => (
            <MealEntry
              key={entry.id}
              entry={entry}
              editable={editable}
              offline={offline}
              onServings={(servings) => setServings.mutate({ listMealId: entry.id, servings })}
              onRemove={() => remove.mutate(entry.id)}
              onShop={() => shopLeftover.mutate(entry.id)}
              eatenBox={
                eatenBoxes || entry.leftover
                  ? (queuedEatenBox(entry) ?? {
                      disabled: !list.can_edit || offline,
                      // The promise settles for every tap; `mutate`'s own callbacks only for
                      // the latest, which would leave an earlier box as it was tapped.
                      onChange: (eaten, settled) => sendEaten(entry.id, eaten, settled),
                    })
                  : undefined
              }
            />
          ))}
        </ul>
      )}
      <ErrorAlert error={setServings.error ?? remove.error ?? shopLeftover.error ?? eatenError} />
      {undo && (
        <UndoToast
          text={t('lists.meals.eaten', { name: undo.label })}
          onUndo={() => {
            setUndo(null);
            void queueEaten(undo.sourceId, false);
          }}
          onDismiss={() => setUndo(null)}
        />
      )}
    </>
  );

  if (collapsible) {
    return (
      <details data-testid={testIds.shoppingMeals} className="rounded-xl border bg-card">
        <summary
          id={headingId}
          className="flex min-h-(--tap-target) cursor-pointer items-center px-4 text-lg font-semibold outline-none focus-visible:ring-[3px] focus-visible:ring-ring"
        >
          {t('lists.meals.titleCount', { count: list.meals.length })}
        </summary>
        <div className="flex flex-col gap-3 border-t p-3">{content}</div>
      </details>
    );
  }

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <h2 id={headingId} className="text-xl font-semibold">
        {t('lists.meals.title')}
        {eatenBoxes && list.meals.length > 0 && (
          <>
            {/* The space keeps the words apart in the heading's accessible name. */}{' '}
            <span className="ml-1 text-base font-normal text-muted-foreground">
              {t('lists.meals.eatenCount', { eaten: eatenCount, count: list.meals.length })}
            </span>
          </>
        )}
      </h2>
      {content}
    </section>
  );
}

/** What a meal is called on the list: its name, or "Private meal (N servings)" (VIS-06). */
function mealLabel(t: TFunction, entry: ListMealEntry): string {
  return !entry.private && entry.name !== null
    ? entry.name
    : t('lists.meals.privateServings', { count: entry.servings });
}

interface MealEntryProps {
  entry: ListMealEntry;
  editable: boolean;
  /** Without a connection: the controls are disabled. */
  offline: boolean;
  onServings: (servings: number) => void;
  onRemove: () => void;
  /** "Doch einkaufen" of a leftover (LIST-17). */
  onShop: () => void;
  /** The eaten checkbox of a done list (SHOP-07) or of a leftover (LIST-17). */
  eatenBox?: { disabled: boolean; onChange: (eaten: boolean, settled: () => void) => void };
}

/**
 * One meal in one line (D-40): thumbnail, name (a link when visible) and at the right the compact
 * stepper, or the servings for those who can't change them. "Remove" shows on focus and hover and
 * is always there for screen readers.
 */
function MealEntry({
  entry,
  editable,
  offline,
  onServings,
  onRemove,
  onShop,
  eatenBox,
}: MealEntryProps) {
  const { t } = useTranslation();
  const visible = !entry.private && entry.name !== null;
  const name = visible ? (entry.name ?? '') : t('lists.meals.private');
  const label = mealLabel(t, entry);
  const struck = eatenBox !== undefined && entry.eaten && 'text-muted-foreground line-through';
  // A leftover's servings are what was bought (LIST-17).
  const stepper = editable && !entry.leftover;

  return (
    <li data-testid={testIds.listMeal} aria-label={label}>
      <SwipeRow
        action={{
          label: t('lists.meals.removeAction'),
          icon: Trash2,
          tone: 'destructive',
          onAction: onRemove,
        }}
        disabled={!editable || offline}
      >
        <div className="group flex items-center gap-3 px-3 py-2">
          {eatenBox && (
            <EatenBox
              label={t('lists.meals.eaten', { name: label })}
              eaten={entry.eaten}
              disabled={eatenBox.disabled}
              onChange={eatenBox.onChange}
            />
          )}
          {entry.thumb_url ? (
            // The name next to it says what it shows, so the thumbnail is decorative.
            <img
              src={entry.thumb_url}
              alt=""
              loading="lazy"
              className="size-11 shrink-0 rounded-lg bg-muted object-cover"
            />
          ) : (
            <span className="flex size-11 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
              <CookingPot aria-hidden="true" className="size-6" />
            </span>
          )}
          <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
            {visible && entry.meal_id ? (
              <Link
                to={`/meals/${entry.meal_id}`}
                className={cn(
                  'inline-flex min-h-(--tap-target) min-w-0 items-center font-medium break-words text-primary underline-offset-4 hover:underline',
                  struck,
                )}
              >
                {name}
              </Link>
            ) : (
              <span className={cn('min-w-0 font-medium break-words', struck)}>{label}</span>
            )}
            {entry.leftover && <Badge variant="secondary">{t('lists.meals.leftover')}</Badge>}
            {entry.detached && <Badge variant="secondary">{t('lists.meals.detached')}</Badge>}
            {entry.leftover && (
              <span className="w-full text-sm text-muted-foreground">
                {t('lists.meals.leftoverHint')}
              </span>
            )}
          </span>
          {stepper && (
            // Visually hidden until the row has focus or the pointer is over it (D-40).
            <span className="sr-only group-focus-within:not-sr-only group-hover:not-sr-only">
              <Button
                variant="ghost"
                size="compact"
                data-testid={testIds.removeListMeal}
                aria-label={t('lists.meals.remove', { name })}
                disabled={offline}
                onClick={onRemove}
                className="text-destructive"
              >
                <Trash2 aria-hidden="true" />
                {t('lists.meals.removeAction')}
              </Button>
            </span>
          )}
          {stepper ? (
            <ServingsStepper
              value={entry.servings}
              name={name}
              onChange={onServings}
              disabled={offline}
            />
          ) : (
            visible && (
              <span className="shrink-0 text-sm text-muted-foreground">
                {t('lists.meals.servings', { count: entry.servings })}
              </span>
            )
          )}
          {editable && entry.leftover && (
            <LeftoverMenu
              label={label}
              // Not once the meal is gone or can't be seen (VIS-06, LIST-15).
              canShop={visible && entry.meal_id !== null}
              offline={offline}
              onShop={onShop}
              onRemove={onRemove}
            />
          )}
        </div>
      </SwipeRow>
    </li>
  );
}

interface EatenBoxProps {
  label: string;
  eaten: boolean;
  disabled: boolean;
  /** Sends the change; `settled` is called once it has its answer, or failed. */
  onChange: (eaten: boolean, settled: () => void) => void;
}

/**
 * The eaten checkbox of a meal on a done list (SHOP-07). A tap shows at once and stays until the
 * change has its answer: the list's change reaches the cache only after a tick, and a box bound
 * to the cache alone would jump back for a moment. Then the box shows the cached list again, which
 * is the server's answer, or the list loaded again after a failure.
 */
function EatenBox({ label, eaten, disabled, onChange }: EatenBoxProps) {
  const [tapped, setTapped] = useState<boolean | null>(null);
  const checked = tapped ?? eaten;

  return (
    <TapCheckbox
      aria-label={label}
      checked={checked}
      disabled={disabled}
      onChange={(event) => {
        const value = event.target.checked;
        setTapped(value);
        onChange(value, () => setTapped((current) => (current === value ? null : current)));
      }}
    />
  );
}

interface LeftoverMenuProps {
  label: string;
  canShop: boolean;
  /** Without a connection: the items are disabled, the button stays enabled (D-39). */
  offline: boolean;
  onShop: () => void;
  onRemove: () => void;
}

/** A leftover's ⋮ menu (LIST-17): "Doch einkaufen" and, red and last, "Entfernen". */
function LeftoverMenu({ label, canShop, offline, onShop, onRemove }: LeftoverMenuProps) {
  const { t } = useTranslation();
  const { trigger } = useMoreMenuFocus();

  return (
    <MoreMenu
      trigger={trigger}
      label={t('lists.meals.actions', { name: label })}
      testId={testIds.leftoverMenu}
      icon={<EllipsisVertical aria-hidden="true" />}
      danger={
        <MoreMenuItem
          testId={testIds.removeLeftover}
          icon={<Trash2 aria-hidden="true" />}
          disabled={offline}
          onSelect={onRemove}
        >
          {t('lists.meals.removeAction')}
        </MoreMenuItem>
      }
    >
      <MoreMenuItem
        testId={testIds.shopLeftover}
        icon={<ShoppingCart aria-hidden="true" />}
        disabled={offline || !canShop}
        onSelect={onShop}
      >
        {t('lists.meals.shopAfterAll')}
      </MoreMenuItem>
    </MoreMenu>
  );
}

interface UndoToastProps {
  text: string;
  onUndo: () => void;
  onDismiss: () => void;
}

/** "Chili gegessen · Rückgängig", above the tab bar until it is used, dismissed or times out. */
function UndoToast({ text, onUndo, onDismiss }: UndoToastProps) {
  const { t } = useTranslation();

  return (
    <div
      role="status"
      className="pointer-events-none fixed inset-x-0 bottom-[calc(var(--tab-bar-clearance)+0.5rem)] z-30 flex justify-center px-4"
    >
      <Card
        data-testid={testIds.leftoverToast}
        className="pointer-events-auto w-full max-w-xl flex-row items-center gap-2 py-2 pr-2 pl-4 shadow-lg"
      >
        <p className="min-w-0 flex-1 text-sm">{text}</p>
        <Button variant="ghost" onClick={onUndo} className="text-primary">
          {t('lists.meals.undo')}
        </Button>
        <Button variant="ghost" size="icon" aria-label={t('common.close')} onClick={onDismiss}>
          <X aria-hidden="true" />
        </Button>
      </Card>
    </div>
  );
}
