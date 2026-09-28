import { Check, CloudOff, RefreshCw, Upload } from 'lucide-react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import { useSyncStatus } from './context';
import { indicatorFor, type Indicator } from './status';

function indicatorText(t: TFunction, indicator: Indicator): string {
  switch (indicator.kind) {
    case 'offline':
      return indicator.waiting > 0
        ? t('lists.sync.offlineWaiting', { count: indicator.waiting })
        : t('lists.sync.offline');
    case 'unreachable':
      return indicator.waiting > 0
        ? `${t('lists.sync.unreachable')} · ${t('lists.sync.waiting', { count: indicator.waiting })}`
        : t('lists.sync.unreachable');
    case 'saving':
      return t('lists.sync.saving');
    case 'saved':
      return t('lists.sync.saved');
  }
}

const ICONS = { offline: CloudOff, unreachable: CloudOff, saving: Upload, saved: Check };

interface SyncIndicatorProps {
  /** Loads the list again (and sends what waits); without it there is no "Refresh" button. */
  onRefresh?: () => void;
  /** Only shown when there is something to say (not "Saved"), e.g. on the Lists home. */
  quiet?: boolean;
}

/**
 * The sync status indicator (SYNC-07, SHOP-03): "Saved", "Saving…", "Offline – N changes
 * waiting" or "Can't reach MealMate – no signal or Tailscale off?".
 */
export function SyncIndicator({ onRefresh, quiet = false }: SyncIndicatorProps) {
  const { t } = useTranslation();
  const indicator = indicatorFor(useSyncStatus());
  if (quiet && indicator.kind === 'saved') return null;
  const Icon = ICONS[indicator.kind];
  const problem = indicator.kind === 'offline' || indicator.kind === 'unreachable';

  return (
    <div className="-mt-2 flex items-center justify-between gap-3">
      <p
        role="status"
        data-testid={testIds.syncStatus}
        className={cn(
          'flex items-center gap-2 text-sm',
          problem ? 'font-medium text-destructive' : 'text-muted-foreground',
        )}
      >
        <Icon aria-hidden="true" className="size-4 shrink-0" />
        {indicatorText(t, indicator)}
      </p>
      {onRefresh && (
        <Button
          variant="ghost"
          size="compact"
          data-testid={testIds.refreshList}
          onClick={onRefresh}
        >
          <RefreshCw aria-hidden="true" />
          {t('lists.sync.refresh')}
        </Button>
      )}
    </div>
  );
}
