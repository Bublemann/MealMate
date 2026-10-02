import { ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { EmptyLine } from '@/components/EmptyLine';
import { LoadError } from '@/components/LoadError';
import { LoadingState } from '@/components/LoadingState';
import { NoMatches } from '@/components/NoMatches';
import { PinnedBlock } from '@/components/PinnedBlock';
import { Screen } from '@/components/Screen';
import { useCategories, type Category } from '@/features/reference/api';
import { useTabMemory } from '@/lib/tabMemory';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import { useIngredients, type IngredientSummary } from './api';
import { IngredientCategoryUnit } from './IngredientCategoryUnit';
import { IngredientFormDialog } from './IngredientFormDialog';
import { IngredientName } from './IngredientName';

/**
 * The Ingredients tab (ING-01, ING-03, UI-01, UI-03): the pinned block with the search (name and
 * brand) and the "New ingredient" tile, which offers to create what was searched for. Below it one
 * list in the server's order (dictionary order, best matches first when searching), one line when
 * there are no ingredients yet, or "No matches". The scanner is not linked from here (BAR-01).
 */
export function IngredientsScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  // The search stays when the user opens an ingredient and comes back (UI-01).
  const [{ search }, remember] = useTabMemory('ingredients');
  const [creating, setCreating] = useState(false);
  const typed = search.trim();
  const debounced = useDebouncedValue(typed);
  const ingredients = useIngredients(debounced);
  const categories = useCategories();
  // The rows name their category, so the list waits for the categories as well.
  const loaded =
    ingredients.data && categories.data
      ? { ingredients: ingredients.data, categories: categories.data }
      : null;

  return (
    <Screen variant="tab" title={t('nav.ingredients')} testId={testIds.screenIngredients}>
      <PinnedBlock
        search={{
          label: t('ingredients.search.label'),
          placeholder: t('ingredients.search.placeholder'),
          value: search,
          onChange: (value) => remember({ search: value }),
          testId: testIds.ingredientSearch,
        }}
        newTile={{
          label: typed ? t('ingredients.createNamed', { name: typed }) : t('ingredients.new'),
          onClick: () => setCreating(true),
          testId: testIds.newIngredient,
        }}
      />
      {!loaded ? (
        // Until the first answer it is unknown whether there are ingredients at all (UI-03).
        ingredients.error || categories.error ? (
          <LoadError error={ingredients.error ?? categories.error} />
        ) : (
          <LoadingState />
        )
      ) : (
        <>
          <LoadError error={ingredients.error ?? categories.error} />
          {loaded.ingredients.length > 0 ? (
            <IngredientList {...loaded} />
          ) : debounced === '' ? (
            <EmptyLine text={t('ingredients.empty')} />
          ) : (
            <NoMatches onReset={() => remember({ search: '' })} />
          )}
        </>
      )}
      <IngredientFormDialog
        open={creating}
        onOpenChange={setCreating}
        initialName={typed}
        onSaved={(ingredient) => void navigate(`/ingredients/${ingredient.id}`)}
      />
    </Screen>
  );
}

function IngredientList({
  ingredients,
  categories,
}: {
  ingredients: IngredientSummary[];
  categories: Category[];
}) {
  const { t } = useTranslation();
  const categoryKeys = new Map(categories.map((category) => [category.id, category.key]));

  return (
    <ul
      data-testid={testIds.ingredientList}
      aria-label={t('ingredients.listLabel')}
      className="flex flex-col divide-y rounded-xl border bg-card"
    >
      {ingredients.map((ingredient) => (
        <li key={ingredient.id}>
          <Link
            to={`/ingredients/${ingredient.id}`}
            data-testid={testIds.ingredientRow}
            className="flex min-h-(--tap-target) items-center gap-3 px-4 py-3 outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
          >
            <span className="flex min-w-0 flex-1 flex-col">
              <IngredientName ingredient={ingredient} />
              <IngredientCategoryUnit ingredient={ingredient} categoryKeys={categoryKeys} />
            </span>
            <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
