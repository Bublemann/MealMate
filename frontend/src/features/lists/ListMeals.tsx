import { Check, CookingPot, Trash2 } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { SwipeRow } from '@/components/SwipeRow';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useConnected } from '@/features/sync/context';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import {
  useRemoveListMeal,
  useSetListMealEaten,
  useSetListMealServings,
  type ListDetail,
  type ListMealEntry,
} from './api';
import { ServingsStepper } from './ServingsStepper';

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
  const offline = !useConnected();
  const eatenCount = list.meals.filter((meal) => meal.eaten).length;

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
              eatenBox={
                eatenBoxes
                  ? {
                      disabled: !list.can_edit || offline,
                      onChange: (eaten, settled) =>
                        setEaten.mutate({ listMealId: entry.id, eaten }, { onSettled: settled }),
                    }
                  : undefined
              }
            />
          ))}
        </ul>
      )}
      <ErrorAlert error={setServings.error ?? remove.error ?? setEaten.error} />
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
        {eatenBoxes && list.meals.length > 0 && ' '}
        {eatenBoxes && list.meals.length > 0 && (
          <span className="ml-2 text-base font-normal text-muted-foreground">
            {t('lists.meals.eatenCount', { eaten: eatenCount, count: list.meals.length })}
          </span>
        )}
      </h2>
      {content}
    </section>
  );
}

interface MealEntryProps {
  entry: ListMealEntry;
  editable: boolean;
  /** Without a connection: the controls are disabled. */
  offline: boolean;
  onServings: (servings: number) => void;
  onRemove: () => void;
  /** The eaten checkbox of a done list (SHOP-07). */
  eatenBox?: { disabled: boolean; onChange: (eaten: boolean, settled: () => void) => void };
}

/**
 * One meal in one line (D-40): thumbnail, name (a link when visible) and at the right the compact
 * stepper, or the servings for those who can't change them. "Remove" shows on focus and hover and
 * is always there for screen readers.
 */
function MealEntry({ entry, editable, offline, onServings, onRemove, eatenBox }: MealEntryProps) {
  const { t } = useTranslation();
  const visible = !entry.private && entry.name !== null;
  const name = visible ? (entry.name ?? '') : t('lists.meals.private');
  const label = visible ? name : t('lists.meals.privateServings', { count: entry.servings });
  const struck = eatenBox !== undefined && entry.eaten && 'text-muted-foreground line-through';

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
              label={t('lists.meals.eaten', { name })}
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
            {entry.detached && <Badge variant="secondary">{t('lists.meals.detached')}</Badge>}
          </span>
          {editable && (
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
          {editable ? (
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
    <span className="relative flex size-(--tap-target) shrink-0 items-center justify-center">
      <input
        type="checkbox"
        aria-label={label}
        checked={checked}
        disabled={disabled}
        onChange={(event) => {
          const value = event.target.checked;
          setTapped(value);
          onChange(value, () => setTapped((current) => (current === value ? null : current)));
        }}
        className="peer absolute inset-0 size-full cursor-pointer appearance-none rounded-md opacity-0 disabled:cursor-default"
      />
      <span
        aria-hidden="true"
        className="flex size-8 items-center justify-center rounded-md border-2 border-input bg-background text-primary-foreground peer-checked:border-primary peer-checked:bg-primary peer-focus-visible:ring-[3px] peer-focus-visible:ring-ring peer-disabled:opacity-60"
      >
        {checked && <Check className="size-6" strokeWidth={3} />}
      </span>
    </span>
  );
}
