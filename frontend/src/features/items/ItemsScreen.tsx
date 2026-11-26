import { ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { EmptyLine } from '@/components/EmptyLine';
import { FilterPanel } from '@/components/FilterPanel';
import { LoadError } from '@/components/LoadError';
import { LoadingState } from '@/components/LoadingState';
import { NoMatches } from '@/components/NoMatches';
import { PinnedBlock } from '@/components/PinnedBlock';
import { Screen } from '@/components/Screen';
import { useCategories, type Category } from '@/features/reference/api';
import { filterableCategories } from '@/features/reference/categories';
import { categoryName } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { useTabMemory } from '@/lib/tabMemory';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import { useItems, type ItemSummary } from './api';
import { ItemCategoryUnit } from './ItemCategoryUnit';
import { ItemFormDialog } from './ItemFormDialog';
import { ItemName } from './ItemName';

/**
 * The Items tab (ING-01, ING-03, UI-01, UI-03): the pinned block with the search (name and
 * brand), the filter panel (several categories, any of them, and *Uncategorized* while it holds
 * items) and the "New item" tile, which offers to create what was searched for. Below
 * it one list in the server's order (dictionary order, best matches first when searching), one
 * line when there are no items yet, or "No matches". The scanner is not linked from here
 * (BAR-01).
 */
export function ItemsScreen() {
  const { t } = useTranslation();
  const language = useLanguage();
  const navigate = useNavigate();
  // The search and the categories stay when the user opens an item and comes back (UI-01).
  const [{ search, categoryIds }, remember] = useTabMemory('items');
  const [creating, setCreating] = useState(false);
  const searchText = search.trim();
  const debounced = useDebouncedValue(searchText);
  // The categories apply at once; only the typed search waits for a pause (UI-01).
  const items = useItems(debounced, { categoryIds });
  const filtered = debounced !== '' || categoryIds.length > 0;
  const categories = useCategories();
  // The rows name their category, so the list waits for the categories as well.
  const loaded =
    items.data && categories.data ? { items: items.data, categories: categories.data } : null;

  return (
    <Screen variant="pinned" title={t('nav.items')} testId={testIds.screenItems}>
      <PinnedBlock
        search={{
          label: t('items.search.label'),
          placeholder: t('items.search.placeholder'),
          value: search,
          onChange: (value) => remember({ search: value }),
          testId: testIds.itemSearch,
        }}
        filter={
          <FilterPanel
            groups={[
              {
                label: t('items.filter.categories'),
                options:
                  categories.data &&
                  filterableCategories(categories.data, categoryIds).map((category) => ({
                    id: category.id,
                    label: categoryName(category, language),
                  })),
                checked: categoryIds,
                active: categoryIds.length > 0,
                onChange: (checked) => remember({ categoryIds: checked }),
              },
            ]}
            onReset={() => remember({ categoryIds: [] })}
          />
        }
        newTile={{
          label: searchText ? t('items.createNamed', { name: searchText }) : t('items.new'),
          onClick: () => setCreating(true),
          testId: testIds.newItem,
        }}
      />
      {!loaded ? (
        // Until the first answer it is unknown whether there are items at all (UI-03).
        items.error || categories.error ? (
          <LoadError error={items.error ?? categories.error} />
        ) : (
          <LoadingState />
        )
      ) : (
        <>
          <LoadError error={items.error ?? categories.error} />
          {loaded.items.length > 0 ? (
            <ItemList {...loaded} />
          ) : !filtered ? (
            // An earlier search's or filter's empty answer, shown while the full list loads, says
            // nothing about whether there are items at all.
            items.isPlaceholderData ? (
              <LoadingState />
            ) : (
              <EmptyLine text={t('items.empty')} />
            )
          ) : (
            <NoMatches onReset={() => remember({ search: '', categoryIds: [] })} />
          )}
        </>
      )}
      <ItemFormDialog
        open={creating}
        onOpenChange={setCreating}
        initialName={searchText}
        onSaved={(item) => void navigate(`/ingredients/${item.id}`)}
      />
    </Screen>
  );
}

function ItemList({ items, categories }: { items: ItemSummary[]; categories: Category[] }) {
  const { t } = useTranslation();

  return (
    <ul
      data-testid={testIds.itemList}
      aria-label={t('items.listLabel')}
      className="flex flex-col divide-y rounded-xl border bg-card"
    >
      {items.map((item) => (
        <li key={item.id}>
          <Link
            to={`/ingredients/${item.id}`}
            data-testid={testIds.itemRow}
            className="flex min-h-(--tap-target) items-center gap-3 px-4 py-3 outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
          >
            <span className="flex min-w-0 flex-1 flex-col">
              <ItemName item={item} />
              <ItemCategoryUnit item={item} categories={categories} />
            </span>
            <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
          </Link>
        </li>
      ))}
    </ul>
  );
}
