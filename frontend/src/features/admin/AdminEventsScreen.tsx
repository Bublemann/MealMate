import { useTranslation } from 'react-i18next';
import { useLanguage } from '@/i18n';
import { formatDateTime } from '@/i18n/format';
import { testIds } from '@/testIds';
import { AdminScreen } from './AdminScreen';
import { useAdminEvents } from './api';
import { describeEvent } from './events';
import { LoadError } from '@/components/LoadError';

/** The admin activity log (ADM-01), newest first. */
export function AdminEventsScreen() {
  const { t } = useTranslation();
  const language = useLanguage();
  const events = useAdminEvents();

  return (
    <AdminScreen title={t('admin.events.title')} testId={testIds.screenAdminEvents}>
      {events.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <LoadError error={events.error} />
      {events.data?.length === 0 && (
        <p className="text-muted-foreground">{t('admin.events.empty')}</p>
      )}
      {events.data && events.data.length > 0 && (
        <ol data-testid={testIds.eventList} className="flex flex-col divide-y rounded-xl border">
          {events.data.map((event) => (
            <li key={event.id} className="flex flex-col gap-1 px-4 py-3">
              <p>{describeEvent(t, event)}</p>
              <p className="text-sm text-muted-foreground">
                <time dateTime={event.created_at}>
                  {formatDateTime(event.created_at, language)}
                </time>
              </p>
            </li>
          ))}
        </ol>
      )}
    </AdminScreen>
  );
}
