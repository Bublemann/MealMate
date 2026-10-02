import { ChevronRight, CookingPot } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { EmptyLine } from '@/components/EmptyLine';
import { FilterPanel } from '@/components/FilterPanel';
import { InitialMarker } from '@/components/InitialMarker';
import { LoadError } from '@/components/LoadError';
import { LoadingState } from '@/components/LoadingState';
import { NoMatches } from '@/components/NoMatches';
import { PinnedBlock } from '@/components/PinnedBlock';
import { Screen } from '@/components/Screen';
import { useCuisines } from '@/features/reference/api';
import { cuisineName } from '@/features/reference/labels';
import { useUserFilterGroup } from '@/features/savedFilters/useUserFilterGroup';
import { useTabMemory } from '@/lib/tabMemory';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import { MEAL_SEARCH_KEY, useMealTags, useMeals, type MealSummary } from './api';

/**
 * The Meals tab (MEAL-09, MEAL-10, UI-01, UI-03): the pinned block with the search (name, tag,
 * cuisine), the filter panel (the user filter; several cuisines, any of them; several tags, all of
 * them) and the "New meal" tile, which offers to create what was searched for. Below it the
 * meals A–Z with their owner's marker, one line when there are no meals yet, or "No matches".
 */
export function MealsScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  // The search, cuisines and tags stay when the user opens a meal and comes back (UI-01).
  const [{ search, cuisineIds, tagIds }, remember] = useTabMemory('meals');
  const searchText = search.trim();
  const debounced = useDebouncedValue(searchText);
  const cuisines = useCuisines();
  const tags = useMealTags();
  // A ticked cuisine or tag that is no longer offered (its last meal lost the tag) doesn't count.
  const cuisineFilter = stillOffered(cuisineIds, cuisines.data);
  const tagFilter = stillOffered(tagIds, tags.data);
  // The filters apply at once; only the typed search waits for a pause (UI-01).
  const meals = useMeals({ q: debounced, cuisineIds: cuisineFilter, tagIds: tagFilter });
  const userFilter = useUserFilterGroup('meals', {
    label: t('meals.filter.users'),
    reloadKey: MEAL_SEARCH_KEY,
  });
  // The server leaves out unticked users; one unticked just now is hidden right away.
  const shown = meals.data?.filter((meal) => !userFilter.hidden.has(meal.owner.id));
  const filtered =
    debounced !== '' || cuisineFilter.length > 0 || tagFilter.length > 0 || userFilter.group.active;

  function resetFilters() {
    remember({ cuisineIds: [], tagIds: [] });
    userFilter.reset();
  }

  return (
    <Screen variant="tab" title={t('nav.meals')} testId={testIds.screenMeals}>
      <PinnedBlock
        search={{
          label: t('meals.search.label'),
          placeholder: t('meals.search.placeholder'),
          value: search,
          onChange: (value) => remember({ search: value }),
          testId: testIds.mealSearch,
        }}
        filter={
          <FilterPanel
            groups={[
              // First: it is short, and the tags can be many.
              userFilter.group,
              {
                label: t('meals.filter.cuisines'),
                options: cuisines.data?.map((cuisine) => ({
                  id: cuisine.id,
                  label: cuisineName(t, cuisine),
                })),
                checked: cuisineFilter,
                active: cuisineFilter.length > 0,
                onChange: (checked) => remember({ cuisineIds: checked }),
                error: cuisines.error,
              },
              {
                label: t('meals.filter.tags'),
                options: tags.data?.map((tag) => ({ id: tag.id, label: tag.name })),
                checked: tagFilter,
                active: tagFilter.length > 0,
                onChange: (checked) => remember({ tagIds: checked }),
                error: tags.error,
              },
            ]}
            onReset={resetFilters}
          />
        }
        newTile={{
          label: searchText ? t('meals.createNamed', { name: searchText }) : t('meals.new'),
          // The meal form fills in the searched name (MEAL-09).
          onClick: () =>
            void navigate(
              searchText ? `/meals/new?${new URLSearchParams({ name: searchText })}` : '/meals/new',
            ),
          testId: testIds.newMeal,
        }}
      />
      {!shown ? (
        // Until the first answer it is unknown whether there are meals at all (UI-03).
        meals.error ? (
          <LoadError error={meals.error} />
        ) : (
          <LoadingState />
        )
      ) : (
        <>
          <LoadError error={meals.error} />
          {shown.length > 0 ? (
            <MealList meals={shown} />
          ) : !filtered ? (
            // An earlier search's or filter's empty answer, shown while all meals load, says
            // nothing about whether there are meals at all; nor does the answer from before users
            // were ticked again.
            meals.isPlaceholderData || userFilter.saving ? (
              <LoadingState />
            ) : (
              <EmptyLine text={t('meals.empty')} />
            )
          ) : (
            <NoMatches
              onReset={() => {
                remember({ search: '' });
                resetFilters();
              }}
            />
          )}
        </>
      )}
    </Screen>
  );
}

/** The ticked ids that are among the options, once these have loaded. */
function stillOffered(ids: string[], options: readonly { id: string }[] | undefined): string[] {
  return options ? ids.filter((id) => options.some((option) => option.id === id)) : ids;
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

/** A meal's row: thumbnail, name, the cuisine in the grey line and the owner's marker (MEAL-09). */
function MealCard({ meal }: { meal: MealSummary }) {
  const { t } = useTranslation();

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
        {meal.cuisine && (
          <span className="text-sm text-muted-foreground">{cuisineName(t, meal.cuisine)}</span>
        )}
      </span>
      {/* After the name, so screen readers read the meal first and then whose it is. */}
      <InitialMarker user={meal.owner} />
      <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
    </Link>
  );
}
