import { useTranslation } from 'react-i18next';
import { isApiError } from '@/api/errors';
import { testIds } from '@/testIds';
import { ErrorAlert } from './ErrorAlert';
import { OfflineNotice } from './OfflineNotice';

/**
 * The error of a failed load: when no answer came (offline, or a timeout on lie-fi), a friendly
 * "You're offline. This page needs a connection." (SYNC-09) instead of an error. An answer with an
 * error, including a server error, says what it says ("MealMate is unavailable right now").
 */
export function LoadError({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;
  if (isApiError(error) && error.status === 0) {
    return <OfflineNotice message={t('sync.offline.page')} testId={testIds.offlineNotice} />;
  }
  return <ErrorAlert error={error} />;
}
