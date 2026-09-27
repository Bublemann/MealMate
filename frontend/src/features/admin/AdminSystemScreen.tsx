import { DatabaseBackup } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { ExternalLink } from '@/components/ExternalLink';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useLanguage } from '@/i18n';
import { formatBytes, formatDateTime, formatNumber } from '@/i18n/format';
import { testIds } from '@/testIds';
import { AdminScreen } from './AdminScreen';
import {
  useRequestBackup,
  useSystemInfo,
  type BackupStatus,
  type DiskStatus,
  type SystemInfo,
} from './api';

// The host's disk check alerts below this share of free space (plan § 11.4).
const LOW_DISK_PERCENT = 20;

const BACKUP_LABELS = {
  regular: 'admin.system.backupLabel.regular',
  'pre-update': 'admin.system.backupLabel.preUpdate',
  manual: 'admin.system.backupLabel.manual',
} as const;

/** ADM-01 / OPS-08: what is running, the last backup and free disk space, and "Back up now". */
export function AdminSystemScreen() {
  const { t } = useTranslation();
  const system = useSystemInfo();

  return (
    <AdminScreen title={t('admin.system.title')} testId={testIds.screenAdminSystem}>
      {system.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <ErrorAlert error={system.error} />
      {system.data && (
        <>
          <AppCard info={system.data} />
          <BackupCard backup={system.data.backup} />
          <DiskCard disk={system.data.disk} />
        </>
      )}
    </AdminScreen>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium break-all">{children}</dd>
    </div>
  );
}

function AppCard({ info }: { info: SystemInfo }) {
  const { t } = useTranslation();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('admin.system.appTitle')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl className="flex flex-col gap-2">
          <Row label={t('me.version')}>
            <span data-testid={testIds.systemVersion}>{info.version}</span>
          </Row>
          <Row label={t('admin.system.commit')}>{info.commit}</Row>
          {info.image_digest && <Row label={t('admin.system.image')}>{info.image_digest}</Row>}
        </dl>
        <ExternalLink
          href={info.source_url}
          className="inline-flex min-h-(--tap-target) items-center self-start"
        >
          {t('me.sourceCode')}
        </ExternalLink>
      </CardContent>
    </Card>
  );
}

function BackupCard({ backup }: { backup: BackupStatus | null }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const request = useRequestBackup();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('admin.system.backupTitle')}</CardTitle>
        <CardDescription>{t('admin.system.backupText')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div data-testid={testIds.backupStatus} className="flex flex-col gap-2">
          {backup ? (
            <>
              <p>
                <Badge variant={backup.ok ? 'default' : 'destructive'}>
                  {t(backup.ok ? 'admin.system.backupOk' : 'admin.system.backupFailed')}
                </Badge>
              </p>
              <dl className="flex flex-col gap-2">
                <Row label={t('admin.system.backupAt')}>
                  <time dateTime={backup.finished_at}>
                    {formatDateTime(backup.finished_at, language)}
                  </time>
                </Row>
                <Row label={t('admin.system.backupKind')}>{t(BACKUP_LABELS[backup.label])}</Row>
                {backup.size_bytes !== null && (
                  <Row label={t('admin.system.backupSize')}>
                    {formatBytes(backup.size_bytes, language)}
                  </Row>
                )}
              </dl>
              {/* The host's own short status line, shown as plain text. */}
              {backup.message && (
                <p className="text-sm break-words text-muted-foreground">{backup.message}</p>
              )}
            </>
          ) : (
            <p className="text-muted-foreground">{t('admin.system.backupNone')}</p>
          )}
        </div>
        <ErrorAlert error={request.error} />
        <Button
          data-testid={testIds.backupNow}
          disabled={request.isPending}
          onClick={() => request.mutate()}
          className="self-start"
        >
          <DatabaseBackup aria-hidden="true" />
          {t('admin.system.backupNow')}
        </Button>
        <p role="status" className="text-sm text-muted-foreground">
          {request.isSuccess && t('admin.system.backupRequested')}
        </p>
      </CardContent>
    </Card>
  );
}

function DiskCard({ disk }: { disk: DiskStatus | null }) {
  const { t } = useTranslation();
  const language = useLanguage();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('admin.system.diskTitle')}</CardTitle>
      </CardHeader>
      <CardContent data-testid={testIds.diskStatus} className="flex flex-col gap-2">
        {disk ? (
          <>
            <p className="font-medium">
              {t('admin.system.diskFree', {
                free: formatBytes(disk.free_bytes, language),
                total: formatBytes(disk.total_bytes, language),
                percent: formatNumber(disk.free_percent / 100, language, {
                  style: 'percent',
                  maximumFractionDigits: 0,
                }),
              })}
            </p>
            {disk.free_percent < LOW_DISK_PERCENT && (
              <p className="font-medium text-destructive">{t('admin.system.diskLow')}</p>
            )}
            <p className="text-sm text-muted-foreground">
              {t('admin.system.checkedAt', { date: formatDateTime(disk.checked_at, language) })}
            </p>
          </>
        ) : (
          <p className="text-muted-foreground">{t('admin.system.diskNone')}</p>
        )}
      </CardContent>
    </Card>
  );
}
