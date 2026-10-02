import { Check, CookingPot, Plus, Search } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCurrentUser } from '@/features/auth/context';
import { useMeals, type MealSummary } from '@/features/meals/api';
import { userLabel } from '@/i18n/users';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds, type TestId } from '@/testIds';
import { useAddListMeal, useRecentMeals } from './api';
import { ServingsStepper } from './ServingsStepper';

interface MealPickerProps {
  listId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Adds meals to a list (LIST-03/04): "Recently used" first (MEAL-09), then all visible meals or
 * the search results, each with its own servings. It stays open for adding several meals; a
 * missing meal can be created on the spot and comes back to the list.
 */
export function MealPicker({ listId, open, onOpenChange }: MealPickerProps) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={testIds.mealPicker}>
        <DialogHeader>
          <DialogTitle>{t('lists.picker.title')}</DialogTitle>
          <DialogDescription>{t('lists.picker.text')}</DialogDescription>
        </DialogHeader>
        {open && <PickerContent listId={listId} />}
        <DialogFooter>
          <Button variant="outline" asChild>
            <Link
              to={`/meals/new?addToList=${encodeURIComponent(listId)}`}
              data-testid={testIds.mealPickerCreate}
            >
              <Plus aria-hidden="true" />
              {t('lists.picker.create')}
            </Link>
          </Button>
          <DialogClose asChild>
            <Button>{t('lists.picker.done')}</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PickerContent({ listId }: { listId: string }) {
  const { t } = useTranslation();
  const searchId = useId();
  const [query, setQuery] = useState('');
  const debounced = useDebouncedValue(query.trim());
  const searching = debounced !== '';
  const recent = useRecentMeals({ enabled: !searching });
  const meals = useMeals({ q: debounced, cuisineIds: [], tagIds: [] });
  const recentIds = new Set(recent.data?.map((meal) => meal.id));
  // Without a search, the recently used meals come first and are not repeated below.
  const rest = searching ? meals.data : meals.data?.filter((meal) => !recentIds.has(meal.id));
  const nothingAtAll = !searching && meals.data?.length === 0 && recent.data?.length === 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label htmlFor={searchId}>{t('lists.picker.search')}</Label>
        <div className="relative">
          <Search
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3 size-5 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            id={searchId}
            type="search"
            enterKeyHint="search"
            autoComplete="off"
            className="pl-10"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      </div>
      {!searching && recent.data && recent.data.length > 0 && (
        <PickerSection
          title={t('lists.picker.recent')}
          meals={recent.data}
          listId={listId}
          testId={testIds.mealPickerRecent}
        />
      )}
      <ErrorAlert error={recent.error ?? meals.error} />
      {meals.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      {nothingAtAll && <p className="text-muted-foreground">{t('lists.picker.none')}</p>}
      {searching && meals.data?.length === 0 && (
        <p aria-live="polite" className="text-muted-foreground">
          {t('lists.picker.noResults')}
        </p>
      )}
      {rest && rest.length > 0 && (
        <PickerSection
          title={searching ? t('lists.picker.results') : t('lists.picker.all')}
          meals={rest}
          listId={listId}
          testId={testIds.mealPickerResults}
        />
      )}
    </div>
  );
}

interface PickerSectionProps {
  title: string;
  meals: MealSummary[];
  listId: string;
  testId: TestId;
}

function PickerSection({ title, meals, listId, testId }: PickerSectionProps) {
  const headingId = useId();

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h3 id={headingId} className="font-semibold">
        {title}
      </h3>
      <ul data-testid={testId} aria-labelledby={headingId} className="flex flex-col divide-y">
        {meals.map((meal) => (
          <PickerRow key={meal.id} meal={meal} listId={listId} />
        ))}
      </ul>
    </section>
  );
}

function PickerRow({ meal, listId }: { meal: MealSummary; listId: string }) {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const add = useAddListMeal(listId);
  const [servings, setServings] = useState(meal.servings);
  const [added, setAdded] = useState(false);

  function onAdd() {
    setAdded(false);
    add.mutate(
      { mealId: meal.id, servings },
      {
        onSuccess: () => {
          setAdded(true);
          setServings(meal.servings);
        },
      },
    );
  }

  return (
    <li aria-label={meal.name} className="flex flex-col gap-2 py-3">
      <div className="flex items-center gap-3">
        {meal.thumb_url ? (
          <img
            src={meal.thumb_url}
            alt=""
            loading="lazy"
            className="size-12 shrink-0 rounded-lg bg-muted object-cover"
          />
        ) : (
          <span className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
            <CookingPot aria-hidden="true" className="size-6" />
          </span>
        )}
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="font-medium break-words">{meal.name}</span>
          {meal.owner.id !== user.id && (
            <span className="text-sm text-muted-foreground">
              {t('meals.card.by', { name: userLabel(t, meal.owner) })}
            </span>
          )}
        </span>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ServingsStepper value={servings} name={meal.name} onChange={setServings} />
        <Button
          variant="outline"
          size="compact"
          aria-label={t('lists.picker.addLabel', { name: meal.name })}
          disabled={add.isPending}
          onClick={onAdd}
        >
          <Plus aria-hidden="true" />
          {t('lists.picker.add')}
        </Button>
      </div>
      <p aria-live="polite" className="text-sm text-muted-foreground empty:hidden">
        {added && (
          <>
            <Check aria-hidden="true" className="mr-1 inline size-4 text-primary" />
            {t('lists.picker.added', { name: meal.name })}
          </>
        )}
      </p>
      <ErrorAlert error={add.error} />
    </li>
  );
}
