import { useTranslation } from 'react-i18next';
import { OfflineNotice } from '@/components/OfflineNotice';
import { testIds } from '@/testIds';
import { useConnected } from './context';

/**
 * SYNC-03: while offline, a list says what still works. While shopping that is checking off,
 * free-text items and finishing; on a draft (or a done list) nothing changes without a
 * connection. On a draft or a list being shopped with `leftovers` (LIST-17), ticking them works
 * too. The controls that need one are disabled, not hidden.
 */
export function ListOfflineBanner({
  shopping,
  leftovers,
}: {
  shopping: boolean;
  leftovers: boolean;
}) {
  const { t } = useTranslation();
  if (useConnected()) return null;
  const message = shopping
    ? t(leftovers ? 'sync.offline.shoppingLeftovers' : 'sync.offline.shopping')
    : t(leftovers ? 'sync.offline.listLeftovers' : 'sync.offline.list');
  return <OfflineNotice message={message} testId={testIds.offlineBanner} />;
}
