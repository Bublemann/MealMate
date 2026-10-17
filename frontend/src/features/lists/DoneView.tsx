import { Check, Circle } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { Card } from '@/components/ui/card';
import type { Category } from '@/features/reference/api';
import { useLanguage } from '@/i18n';
import { formatDayMonth } from '@/i18n/format';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import type { ListDetail, ListLine } from './api';
import { groupByCategory, lineAmount, lineLabel } from './format';
import { ListMeals } from './ListMeals';

interface DoneViewProps {
  list: ListDetail;
  categories: readonly Category[];
}

/**
 * A finished list, read-only (LIST-10): the note when it was bought, then its meals and lines;
 * checked lines count as bought, the others are greyed (SHOP-05). "Shop again" and "Reopen"
 * (SHOP-06) are in the ⋯ menu (`ListMenu`). A list finished here but not sent yet shows as done
 * already.
 */
export function DoneView({ list, categories }: DoneViewProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const headingId = useId();
  const groups = groupByCategory(
    list.lines.filter((line) => !line.hidden),
    categories,
    language,
  );

  return (
    <>
      {list.finished_at && (
        <Card data-testid={testIds.listDone} className="px-5 py-4">
          <p>{t('lists.done.note', { date: formatDayMonth(list.finished_at, language) })}</p>
        </Card>
      )}
      <ListMeals list={list} editable={false} />
      <section aria-labelledby={headingId} className="flex flex-col gap-4">
        <h2 id={headingId} className="text-xl font-semibold">
          {t('lists.lines.title')}
        </h2>
        {groups.length === 0 && <p className="text-muted-foreground">{t('lists.lines.empty')}</p>}
        {groups.length > 0 && (
          <div data-testid={testIds.doneLines} className="flex flex-col gap-4">
            {groups.map((group) => (
              <DoneCategory key={group.categoryId} name={group.name} lines={group.lines} />
            ))}
          </div>
        )}
      </section>
    </>
  );
}

function DoneCategory({ name, lines }: { name: string; lines: ListLine[] }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const headingId = useId();

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h3
        id={headingId}
        className="text-sm font-semibold tracking-wide text-muted-foreground uppercase"
      >
        {name}
      </h3>
      <ul aria-labelledby={headingId} className="flex flex-col divide-y rounded-xl border bg-card">
        {lines.map((line) => {
          const amount = lineAmount(t, language, line);
          const Icon = line.checked ? Check : Circle;
          return (
            <li
              key={line.key}
              className={cn(
                'flex min-h-(--tap-target) items-center gap-3 px-4 py-2',
                !line.checked && 'text-muted-foreground',
              )}
            >
              <Icon
                aria-hidden="true"
                className={cn('size-5 shrink-0', line.checked && 'text-primary')}
              />
              <span className="min-w-0 flex-1 break-words">
                {lineLabel(line)}
                <span className="sr-only">
                  {' '}
                  ({line.checked ? t('lists.done.bought') : t('lists.done.notBought')})
                </span>
              </span>
              {amount && <span className="shrink-0 text-right tabular-nums">{amount}</span>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
