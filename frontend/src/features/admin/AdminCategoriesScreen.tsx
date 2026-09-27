import { ArrowDown, ArrowUp } from 'lucide-react';
import { useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Button } from '@/components/ui/button';
import { useCategories, type Category } from '@/features/reference/api';
import { categoryName } from '@/features/reference/labels';
import { testIds } from '@/testIds';
import { AdminScreen } from './AdminScreen';
import { useReorderCategories } from './api';

type Direction = 'up' | 'down';

/** REF-01 / ADM-01: the categories in the store's walking order, moved with up/down buttons. */
export function AdminCategoriesScreen() {
  const { t } = useTranslation();
  const categories = useCategories();

  return (
    <AdminScreen title={t('admin.categories.title')} testId={testIds.screenAdminCategories}>
      <p className="text-muted-foreground">{t('admin.categories.text')}</p>
      {categories.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <ErrorAlert error={categories.error} />
      {categories.data && <CategoryOrder categories={categories.data} />}
    </AdminScreen>
  );
}

function CategoryOrder({ categories }: { categories: Category[] }) {
  const { t } = useTranslation();
  const reorder = useReorderCategories();
  const [order, setOrder] = useState(() => categories.map(({ id }) => id));
  const [saved, setSaved] = useState(false);
  // After a move the focus follows the moved category (its button may have become disabled).
  const [focus, setFocus] = useState<{ id: string; direction: Direction } | null>(null);
  const baseId = useId();
  const buttonId = (id: string, direction: Direction) => `${baseId}-${id}-${direction}`;
  const byId = new Map(categories.map((category) => [category.id, category]));
  const unchanged = order.every((id, index) => categories[index]?.id === id);

  useEffect(() => {
    if (!focus) return;
    const index = order.indexOf(focus.id);
    const atEdge = focus.direction === 'up' ? index === 0 : index === order.length - 1;
    const direction = atEdge ? (focus.direction === 'up' ? 'down' : 'up') : focus.direction;
    document.getElementById(`${baseId}-${focus.id}-${direction}`)?.focus();
  }, [focus, order, baseId]);

  function move(id: string, direction: Direction) {
    setSaved(false);
    reorder.reset();
    setOrder((current) => {
      const index = current.indexOf(id);
      const other = direction === 'up' ? index - 1 : index + 1;
      if (index < 0 || other < 0 || other >= current.length) return current;
      const next = [...current];
      [next[index], next[other]] = [next[other] as string, next[index] as string];
      return next;
    });
    setFocus({ id, direction });
  }

  function onSave() {
    reorder.mutate(order, {
      onSuccess: (result) => {
        setOrder(result.map(({ id }) => id));
        setSaved(true);
      },
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <ol
        data-testid={testIds.adminCategoryList}
        aria-label={t('admin.categories.listLabel')}
        className="flex flex-col divide-y rounded-xl border bg-card"
      >
        {order.map((id, index) => {
          const category = byId.get(id);
          if (!category) return null;
          const name = categoryName(t, category.key);
          return (
            <li key={id} className="flex items-center gap-2 py-1 pr-2 pl-4">
              <span
                aria-hidden="true"
                className="w-6 text-right text-muted-foreground tabular-nums"
              >
                {index + 1}
              </span>
              <span className="flex-1 font-medium">{name}</span>
              <Button
                id={buttonId(id, 'up')}
                size="icon"
                variant="ghost"
                aria-label={t('admin.categories.moveUp', { name })}
                disabled={index === 0 || reorder.isPending}
                onClick={() => move(id, 'up')}
              >
                <ArrowUp aria-hidden="true" />
              </Button>
              <Button
                id={buttonId(id, 'down')}
                size="icon"
                variant="ghost"
                aria-label={t('admin.categories.moveDown', { name })}
                disabled={index === order.length - 1 || reorder.isPending}
                onClick={() => move(id, 'down')}
              >
                <ArrowDown aria-hidden="true" />
              </Button>
            </li>
          );
        })}
      </ol>
      <ErrorAlert error={reorder.error} />
      <div className="flex items-center gap-3">
        <Button
          data-testid={testIds.saveCategoryOrder}
          disabled={unchanged || reorder.isPending}
          onClick={onSave}
        >
          {t('admin.categories.save')}
        </Button>
        <p role="status" className="text-sm text-muted-foreground">
          {saved && unchanged && t('admin.categories.saved')}
        </p>
      </div>
    </div>
  );
}
