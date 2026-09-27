import { useTranslation } from 'react-i18next';
import { OfflineNotice } from '@/components/OfflineNotice';
import { testIds } from '@/testIds';
import { useConnected } from './context';

/**
 * SYNC-03: while offline, a list says what still works. While shopping that is checking off,
 * free-text items and finishing; on a draft (or a done list) nothing changes without a
 * connection. The controls that need one are disabled, not hidden.
 */
export function ListOfflineBanner({ shopping }: { shopping: boolean }) {
  const { t } = useTranslation();
  if (useConnected()) return null;
  return (
    <OfflineNotice
      message={shopping ? t('sync.offline.shopping') : t('sync.offline.list')}
      testId={testIds.offlineBanner}
    />
  );
}
