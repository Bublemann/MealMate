import { Carrot, ChevronRight, Plus, ScanBarcode, Search } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { EmptyState } from '@/components/EmptyState';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCategories, type Category } from '@/features/reference/api';
import { categoryName, unitLabel } from '@/features/reference/labels';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import { useIngredients, type IngredientSummary } from './api';
import { IngredientFormDialog } from './IngredientFormDialog';

interface Group {
  category: Category;
  ingredients: IngredientSummary[];
}

/**
 * The server's results under their category headings, in the categories' walking order; within
 * a category they keep the server's order (best matches first when searching).
 */
function groupByCategory(ingredients: IngredientSummary[], categories: Category[]): Group[] {
  const byCategory = new Map<string, IngredientSummary[]>();
  for (const ingredient of ingredients) {
    const group = byCategory.get(ingredient.category_id) ?? [];
    group.push(ingredient);
    byCategory.set(ingredient.category_id, group);
  }
  return categories.flatMap((category) => {
    const members = byCategory.get(category.id);
    return members ? [{ category, ingredients: members }] : [];
  });
}

/** The Ingredients tab: search, grouped by category, and "New ingredient" (ING-01, ING-03). */
export function IngredientsScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const searchId = useId();
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);
  const debounced = useDebouncedValue(query.trim());
  const ingredients = useIngredients(debounced);
  const categories = useCategories();
  const groups =
    ingredients.data && categories.data ? groupByCategory(ingredients.data, categories.data) : null;
  const noIngredientsAtAll = debounced === '' && ingredients.data?.length === 0;

  return (
    <Screen title={t('nav.ingredients')} testId={testIds.screenIngredients}>
      {noIngredientsAtAll ? (
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
          {(ingredients.isPending || categories.isPending) && (
            <p className="text-muted-foreground">{t('common.loading')}</p>
          )}
          <ErrorAlert error={ingredients.error ?? categories.error} />
          {groups && groups.length === 0 && debounced !== '' && (
            <Card className="items-start gap-3 px-5">
              <p aria-live="polite">{t('ingredients.noResults', { query: debounced })}</p>
              <Button variant="outline" onClick={() => setCreating(true)}>
                <Plus aria-hidden="true" />
                {t('ingredients.createNamed', { name: debounced })}
              </Button>
            </Card>
          )}
          {groups && groups.length > 0 && <IngredientGroups groups={groups} />}
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

function IngredientGroups({ groups }: { groups: Group[] }) {
  const { t } = useTranslation();

  return (
    <section
      data-testid={testIds.ingredientList}
      aria-label={t('ingredients.listLabel')}
      className="flex flex-col gap-6"
    >
      {groups.map(({ category, ingredients }) => (
        <CategoryGroup key={category.id} category={category} ingredients={ingredients} />
      ))}
    </section>
  );
}

function CategoryGroup({ category, ingredients }: Group) {
  const { t } = useTranslation();
  const headingId = useId();

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-lg font-semibold">
        {categoryName(t, category.key)}
      </h2>
      <ul className="flex flex-col divide-y rounded-xl border bg-card">
        {ingredients.map((ingredient) => (
          <li key={ingredient.id}>
            <Link
              to={`/ingredients/${ingredient.id}`}
              data-testid={testIds.ingredientRow}
              className="flex min-h-(--tap-target) items-center gap-3 px-4 py-3 outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
            >
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="font-medium break-words">{ingredient.name}</span>
                <span className="text-sm text-muted-foreground">
                  {unitLabel(t, ingredient.base_unit)}
                  {' · '}
                  {t('ingredients.productCount', { count: ingredient.product_count })}
                </span>
              </span>
              <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
