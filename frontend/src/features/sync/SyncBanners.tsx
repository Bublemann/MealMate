import { Clock, HardDrive } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { testIds } from '@/testIds';
import { useSyncStatus, useWaitingTooLong } from './context';

/**
 * App-wide notes about waiting changes: they have waited for more than an hour (SYNC-07), or
 * they can't be stored on this device (no IndexedDB, or it failed for good during this visit), so
 * they only last while the app is open.
 */
export function SyncBanners() {
  const { t } = useTranslation();
  const status = useSyncStatus();
  const tooLong = useWaitingTooLong();

  return (
    <>
      {tooLong && (
        <Alert data-testid={testIds.waitingBanner} className="mb-4">
          <Clock aria-hidden="true" />
          <AlertDescription>{t('sync.waitingTooLong')}</AlertDescription>
        </Alert>
      )}
      {!status.persistent && status.pending > 0 && (
        <Alert data-testid={testIds.noStorageBanner} className="mb-4">
          <HardDrive aria-hidden="true" />
          <AlertDescription>{t('sync.noStorage')}</AlertDescription>
        </Alert>
      )}
    </>
  );
}
