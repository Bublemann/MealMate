import { Carrot, ChevronRight, Plus, ScanBarcode, Search } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { EmptyState } from '@/components/EmptyState';
import { LoadError } from '@/components/LoadError';
import { LoadingState } from '@/components/LoadingState';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCategories, type Category } from '@/features/reference/api';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import { useIngredients, type IngredientSummary } from './api';
import { IngredientDetails } from './IngredientDetails';
import { IngredientFormDialog } from './IngredientFormDialog';
import { IngredientName } from './IngredientName';

/**
 * The Ingredients tab: search (name and brand), one list in the server's order (dictionary order,
 * best matches first when searching), "New ingredient" and "Scan" (ING-01, ING-03, BAR-01).
 */
export function IngredientsScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const searchId = useId();
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const debounced = useDebouncedValue(query.trim());
  const ingredients = useIngredients(debounced);
  const categories = useCategories();
  // The rows name their category, so the list waits for the categories as well.
  const loaded =
    ingredients.data && categories.data
      ? { ingredients: ingredients.data, categories: categories.data }
      : null;
  const noIngredientsAtAll = debounced === '' && ingredients.data?.length === 0;

  return (
    <Screen title={t('nav.ingredients')} testId={testIds.screenIngredients}>
      {!loaded ? (
        // Until the first answer it is unknown whether there are ingredients at all (UI-03).
        ingredients.error || categories.error ? (
          <LoadError error={ingredients.error ?? categories.error} />
        ) : (
          <LoadingState />
        )
      ) : noIngredientsAtAll ? (
        <EmptyState
          icon={Carrot}
          title={t('ingredients.empty.title')}
          text={t('ingredients.empty.text')}
          actionLabel={t('ingredients.empty.action')}
          onAction={() => setCreating(true)}
        >
          <ScanLink />
        </EmptyState>
      ) : (
        <>
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              <Button data-testid={testIds.newIngredient} onClick={() => setCreating(true)}>
                <Plus aria-hidden="true" />
                {t('ingredients.new')}
              </Button>
              <ScanLink />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor={searchId}>{t('ingredients.search.label')}</Label>
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
                  data-testid={testIds.ingredientSearch}
                  placeholder={t('ingredients.search.placeholder')}
                  className="pl-10"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </div>
            </div>
          </div>
          <LoadError error={ingredients.error ?? categories.error} />
          {loaded.ingredients.length === 0 && debounced !== '' && (
            <Card className="items-start gap-3 px-5">
              <p aria-live="polite">{t('ingredients.noResults', { query: debounced })}</p>
              <Button variant="outline" onClick={() => setCreating(true)}>
                <Plus aria-hidden="true" />
                {t('ingredients.createNamed', { name: debounced })}
              </Button>
            </Card>
          )}
          {loaded.ingredients.length > 0 && <IngredientList {...loaded} />}
        </>
      )}
      <IngredientFormDialog
        open={creating}
        onOpenChange={setCreating}
        initialName={query.trim()}
        onSaved={(ingredient) => void navigate(`/ingredients/${ingredient.id}`)}
      />
    </Screen>
  );
}

/** BAR-01: opens the scanner, which ends on the barcode's ingredient. */
function ScanLink() {
  const { t } = useTranslation();

  return (
    <Button asChild variant="outline">
      <Link to="/scan" data-testid={testIds.scanBarcode}>
        <ScanBarcode aria-hidden="true" />
        {t('scanner.open')}
      </Link>
    </Button>
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
              <IngredientDetails ingredient={ingredient} categoryKeys={categoryKeys} />
            </span>
            <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
