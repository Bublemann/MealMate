import { Check, Circle, RotateCcw, ShoppingCart } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import type { Category } from '@/features/reference/api';
import { useConnected } from '@/features/sync/context';
import { useLanguage } from '@/i18n';
import { formatDayMonth } from '@/i18n/format';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import { useReopenList, useShopAgain, type ListDetail, type ListLine } from './api';
import { groupByCategory, lineAmount, lineLabel } from './format';
import { ListMeals } from './ListMeals';
import type { ListViewState } from './ListScreen';
import { Reminder } from './Reminder';

interface DoneViewProps {
  /** `pendingFinish`: finished here, not sent yet; reopening waits until it is. */
  list: ListDetail & { pendingFinish?: boolean };
  categories: readonly Category[];
}

/**
 * A finished list, read-only (LIST-10): checked lines count as bought, the others are greyed
 * (SHOP-05). "Shop again" starts a new draft from it, "Reopen" goes back to shopping (SHOP-06);
 * both need a connection (SYNC-03). A list finished here but not sent yet shows as done already.
 */
export function DoneView({ list, categories }: DoneViewProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const navigate = useNavigate();
  const headingId = useId();
  const shopAgain = useShopAgain(list.id);
  const reopen = useReopenList(list.id);
  const offline = !useConnected();
  const groups = groupByCategory(
    list.lines.filter((line) => !line.hidden),
    categories,
    language,
  );

  function onShopAgain() {
    shopAgain.mutate(undefined, {
      onSuccess: ({ list: created, left_out }) => {
        const state: ListViewState = { leftOut: left_out };
        void navigate(`/lists/${created.id}`, { state });
      },
    });
  }

  return (
    <>
      <Card data-testid={testIds.listDone} className="gap-3 px-5 py-4">
        {list.finished_at && (
          <p>{t('lists.done.note', { date: formatDayMonth(list.finished_at, language) })}</p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button
            data-testid={testIds.shopAgain}
            disabled={shopAgain.isPending || offline}
            onClick={onShopAgain}
          >
            <ShoppingCart aria-hidden="true" />
            {t('lists.done.shopAgain')}
          </Button>
          {list.can_edit && (
            <Button
              variant="outline"
              data-testid={testIds.reopenList}
              disabled={reopen.isPending || offline || list.pendingFinish === true}
              onClick={() => reopen.mutate()}
            >
              <RotateCcw aria-hidden="true" />
              {t('lists.done.reopen')}
            </Button>
          )}
        </div>
        <ErrorAlert error={shopAgain.error ?? reopen.error} />
      </Card>
      <ListMeals list={list} editable={false} onAddMeals={() => undefined} />
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
        <Reminder seed={list.reminder_seed} />
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
