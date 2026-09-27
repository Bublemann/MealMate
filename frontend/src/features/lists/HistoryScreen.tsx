import { ChevronLeft, History, ListChecks } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { EmptyState } from '@/components/EmptyState';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Screen } from '@/components/Screen';
import { useLanguage } from '@/i18n';
import { formatDayMonth } from '@/i18n/format';
import { testIds } from '@/testIds';
import { useListHistory, type ListSummary } from './api';
import { groupByWeek, type WeekGroup } from './history';
import { ListCards } from './ListsScreen';

/**
 * `/lists/history` (SHOP-05): done lists, mine and my partner's shared ones, grouped by the week
 * they were finished in, newest first; each says when it was bought.
 */
export function HistoryScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const history = useListHistory();
  const weeks = history.data ? groupByWeek(history.data) : [];

  return (
    <Screen title={t('lists.history.title')} testId={testIds.screenHistory}>
      <Link
        to="/lists"
        className="-mt-3 inline-flex min-h-(--tap-target) items-center gap-1 self-start font-medium text-primary underline-offset-4 hover:underline"
      >
        <ChevronLeft aria-hidden="true" className="size-5" />
        {t('lists.detail.back')}
      </Link>
      {history.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <ErrorAlert error={history.error} />
      {history.data && weeks.length === 0 && (
        <EmptyState
          icon={History}
          title={t('lists.history.emptyTitle')}
          text={t('lists.history.emptyText')}
          actionLabel={t('lists.history.emptyAction')}
          actionIcon={ListChecks}
          onAction={() => void navigate('/lists')}
        />
      )}
      {weeks.map((week) => (
        <Week key={week.monday} week={week} />
      ))}
    </Screen>
  );
}

function Week({ week }: { week: WeekGroup<ListSummary> }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const headingId = useId();

  return (
    <section
      aria-labelledby={headingId}
      data-testid={testIds.historyWeek}
      className="flex flex-col gap-3"
    >
      <h2 id={headingId} className="text-xl font-semibold">
        {/* The Monday is a calendar date, read as midnight UTC. */}
        {t('lists.history.week', { date: formatDayMonth(week.monday, language, 'UTC') })}
      </h2>
      <ListCards lists={week.lists} />
    </section>
  );
}
