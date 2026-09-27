import { ChevronRight, CookingPot, Plus, Search } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { EmptyState } from '@/components/EmptyState';
import { ErrorAlert } from '@/components/ErrorAlert';
import { LoadError } from '@/components/LoadError';
import { Screen } from '@/components/Screen';
import { UserFilterChips } from '@/components/UserFilterChips';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { useCurrentUser } from '@/features/auth/context';
import { useCuisines } from '@/features/reference/api';
import { cuisineName } from '@/features/reference/labels';
import { userLabel } from '@/i18n/users';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import { useMealTags, useMealUsers, useMeals, useToggleMealChip, type MealSummary } from './api';

/**
 * The Meals tab: search, cuisine and tag filters, one chip per user whose meals are visible
 * (MEAL-09, MEAL-10), and the meals A–Z. Without any meal to show, an empty state replaces
 * search and filters, but the chips stay while others' meals could be visible (UI-03).
 */
export function MealsScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const user = useCurrentUser();
  const searchId = useId();
  const [query, setQuery] = useState('');
  const [cuisineId, setCuisineId] = useState('');
  const [tagId, setTagId] = useState('');
  const debounced = useDebouncedValue(query.trim());
  const meals = useMeals({ q: debounced, cuisineId, tagId });
  const hidden = new Set(user.filter_hidden.meals);
  // The server leaves out hidden owners; a chip switched off just now hides them right away.
  const shown = meals.data?.filter((meal) => !hidden.has(meal.owner.id));
  const filtered = debounced !== '' || cuisineId !== '' || tagId !== '';
  const noMealsAtAll = !filtered && hidden.size === 0 && meals.data?.length === 0;
  const createMeal = () => void navigate('/meals/new');

  function clearFilters() {
    setQuery('');
    setCuisineId('');
    setTagId('');
  }

  return (
    <Screen title={t('nav.meals')} testId={testIds.screenMeals}>
      {noMealsAtAll ? (
        <>
          <UserChips onlyWithOthers />
          <EmptyState
            icon={CookingPot}
            title={t('meals.empty.title')}
            text={t('meals.empty.text')}
            actionLabel={t('meals.empty.action')}
            onAction={createMeal}
          />
        </>
      ) : (
        <>
          <div className="flex flex-col gap-4">
            <Button data-testid={testIds.newMeal} onClick={createMeal} className="self-start">
              <Plus aria-hidden="true" />
              {t('meals.new')}
            </Button>
            <div className="flex flex-col gap-2">
              <Label htmlFor={searchId}>{t('meals.search.label')}</Label>
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
                  data-testid={testIds.mealSearch}
                  placeholder={t('meals.search.placeholder')}
                  className="pl-10"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
            </div>
            <Filters
              cuisineId={cuisineId}
              tagId={tagId}
              onCuisineChange={setCuisineId}
              onTagChange={setTagId}
            />
            <UserChips />
          </div>
          {meals.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
          <LoadError error={meals.error} />
          {shown && shown.length === 0 && (
            <Card className="items-start gap-3 px-5" aria-live="polite">
              <div className="flex flex-col gap-1">
                <h2 className="text-lg font-semibold">{t('meals.noResults')}</h2>
                <p className="text-muted-foreground">{t('meals.noResults.text')}</p>
              </div>
              {filtered && (
                <Button variant="outline" onClick={clearFilters}>
                  {t('meals.noResults.action')}
                </Button>
              )}
            </Card>
          )}
          {shown && shown.length > 0 && <MealList meals={shown} />}
        </>
      )}
    </Screen>
  );
}

interface FiltersProps {
  cuisineId: string;
  tagId: string;
  onCuisineChange: (id: string) => void;
  onTagChange: (id: string) => void;
}

function Filters({ cuisineId, tagId, onCuisineChange, onTagChange }: FiltersProps) {
  const { t } = useTranslation();
  const cuisineSelectId = useId();
  const tagSelectId = useId();
  const cuisines = useCuisines();
  const tags = useMealTags();

  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-3">
        <div className="flex min-w-0 flex-col gap-2">
          <Label htmlFor={cuisineSelectId}>{t('meals.filter.cuisine')}</Label>
          <NativeSelect
            id={cuisineSelectId}
            value={cuisineId}
            onChange={(event) => onCuisineChange(event.target.value)}
          >
            <NativeSelectOption value="">{t('meals.filter.allCuisines')}</NativeSelectOption>
            {cuisines.data?.map((cuisine) => (
              <NativeSelectOption key={cuisine.id} value={cuisine.id}>
                {cuisineName(t, cuisine)}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <Label htmlFor={tagSelectId}>{t('meals.filter.tag')}</Label>
          <NativeSelect
            id={tagSelectId}
            value={tagId}
            onChange={(event) => onTagChange(event.target.value)}
          >
            <NativeSelectOption value="">{t('meals.filter.allTags')}</NativeSelectOption>
            {tags.data?.map((tag) => (
              <NativeSelectOption key={tag.id} value={tag.id}>
                {tag.name}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
      </div>
      <ErrorAlert error={cuisines.error ?? tags.error} />
    </div>
  );
}

/**
 * MEAL-10: one chip per user whose meals are visible, the user first ("Me"). With
 * `onlyWithOthers`, nothing is shown while the user is the only one.
 */
function UserChips({ onlyWithOthers = false }: { onlyWithOthers?: boolean }) {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const users = useMealUsers();
  const toggle = useToggleMealChip();
  const hidden = user.filter_hidden.meals;

  if (!users.data) return <LoadError error={users.error} />;
  if (onlyWithOthers && users.data.every((person) => person.id === user.id)) return null;
  return (
    <div className="flex flex-col gap-2">
      <UserFilterChips
        users={users.data}
        hidden={hidden}
        meId={user.id}
        meLabel={t('meals.chips.me')}
        label={t('meals.chips.label')}
        testId={testIds.mealUserChips}
        onChange={(next) => toggle.mutate(next)}
      />
      <ErrorAlert error={toggle.error} />
    </div>
  );
}

function MealList({ meals }: { meals: MealSummary[] }) {
  const { t } = useTranslation();

  return (
    <ul
      data-testid={testIds.mealList}
      aria-label={t('meals.listLabel')}
      className="flex flex-col divide-y rounded-xl border bg-card"
    >
      {meals.map((meal) => (
        <li key={meal.id}>
          <MealCard meal={meal} />
        </li>
      ))}
    </ul>
  );
}

function MealCard({ meal }: { meal: MealSummary }) {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const details = [
    meal.owner.id === user.id ? null : t('meals.card.by', { name: userLabel(t, meal.owner) }),
    meal.cuisine ? cuisineName(t, meal.cuisine) : null,
  ].filter((detail) => detail !== null);

  return (
    <Link
      to={`/meals/${meal.id}`}
      data-testid={testIds.mealCard}
      className="flex min-h-(--tap-target) items-center gap-3 px-3 py-3 outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
    >
      {meal.thumb_url ? (
        // The name next to it says what it shows, so the thumbnail is decorative.
        <img
          src={meal.thumb_url}
          alt=""
          loading="lazy"
          className="size-16 shrink-0 rounded-lg bg-muted object-cover"
        />
      ) : (
        <span className="flex size-16 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground">
          <CookingPot aria-hidden="true" className="size-7" />
        </span>
      )}
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="font-medium break-words">{meal.name}</span>
        {details.length > 0 && (
          <span className="text-sm text-muted-foreground">{details.join(' · ')}</span>
        )}
      </span>
      <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
    </Link>
  );
}
