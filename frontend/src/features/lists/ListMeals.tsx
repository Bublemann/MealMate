import { CookingPot, Plus, X } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { testIds } from '@/testIds';
import {
  useRemoveListMeal,
  useSetListMealServings,
  type ListDetail,
  type ListMealEntry,
} from './api';
import { ServingsStepper } from './ServingsStepper';

interface ListMealsProps {
  list: ListDetail;
  /** Servings can be changed and meals added or removed (editors of a draft). */
  editable: boolean;
  onAddMeals: () => void;
}

/**
 * The meals at the top of the list with their servings (LIST-04/05). A meal the viewer can't
 * see is only "Private meal (N servings)" (VIS-06); a detached one is marked "no longer
 * available" and can be removed (LIST-15).
 */
export function ListMeals({ list, editable, onAddMeals }: ListMealsProps) {
  const { t } = useTranslation();
  const headingId = useId();
  const setServings = useSetListMealServings(list.id);
  const remove = useRemoveListMeal(list.id);

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <h2 id={headingId} className="text-xl font-semibold">
        {t('lists.meals.title')}
      </h2>
      {list.meals.length === 0 ? (
        <p className="text-muted-foreground">{t('lists.meals.empty')}</p>
      ) : (
        <ul
          data-testid={testIds.listMeals}
          aria-labelledby={headingId}
          className="flex flex-col divide-y rounded-xl border bg-card"
        >
          {list.meals.map((entry) => (
            <MealEntry
              key={entry.id}
              entry={entry}
              editable={editable}
              busy={remove.isPending}
              onServings={(servings) => setServings.mutate({ listMealId: entry.id, servings })}
              onRemove={() => remove.mutate(entry.id)}
            />
          ))}
        </ul>
      )}
      <ErrorAlert error={setServings.error ?? remove.error} />
      {editable && (
        <Button
          variant="outline"
          data-testid={testIds.addMeals}
          onClick={onAddMeals}
          className="self-start"
        >
          <Plus aria-hidden="true" />
          {t('lists.meals.add')}
        </Button>
      )}
    </section>
  );
}

interface MealEntryProps {
  entry: ListMealEntry;
  editable: boolean;
  busy: boolean;
  onServings: (servings: number) => void;
  onRemove: () => void;
}

function MealEntry({ entry, editable, busy, onServings, onRemove }: MealEntryProps) {
  const { t } = useTranslation();
  const visible = !entry.private && entry.name !== null;
  const name = visible ? (entry.name ?? '') : t('lists.meals.private');
  const label = visible ? name : t('lists.meals.privateServings', { count: entry.servings });

  return (
    <li data-testid={testIds.listMeal} aria-label={label} className="flex flex-col gap-2 px-3 py-3">
      <div className="flex items-center gap-3">
        {entry.thumb_url ? (
          // The name next to it says what it shows, so the thumbnail is decorative.
          <img
            src={entry.thumb_url}
            alt=""
            loading="lazy"
            className="size-12 shrink-0 rounded-lg bg-muted object-cover"
          />
        ) : (
          <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <CookingPot aria-hidden="true" className="size-6" />
          </span>
        )}
        <span className="flex min-w-0 flex-1 flex-col items-start gap-1">
          {visible && entry.meal_id ? (
            <Link
              to={`/meals/${entry.meal_id}`}
              className="inline-flex min-h-(--tap-target) items-center font-medium break-words text-primary underline-offset-4 hover:underline"
            >
              {name}
            </Link>
          ) : (
            <span className="font-medium break-words">{label}</span>
          )}
          {entry.detached && <Badge variant="secondary">{t('lists.meals.detached')}</Badge>}
        </span>
        {editable && (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('lists.meals.remove', { name })}
            disabled={busy}
            onClick={onRemove}
          >
            <X aria-hidden="true" />
          </Button>
        )}
      </div>
      {editable ? (
        <ServingsStepper value={entry.servings} name={name} onChange={onServings} />
      ) : (
        visible && (
          <span className="text-sm text-muted-foreground">
            {t('lists.meals.servings', { count: entry.servings })}
          </span>
        )
      )}
    </li>
  );
}
