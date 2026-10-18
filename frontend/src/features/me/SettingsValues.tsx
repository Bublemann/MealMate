import { useTranslation } from 'react-i18next';
import { useCurrentUser } from '@/features/auth/context';
import { useCouple, waitingRequests } from '@/features/couple/api';
import { useLanguage } from '@/i18n';
import { formatDate, formatDateTime } from '@/i18n/format';
import { userLabel } from '@/i18n/users';
import { useSystemInfo, useVersionInfo } from './api';

// The values of the Settings rows (D-45), each loading on its own: nothing while it loads or
// when it fails, so the row shows at once and stays tappable.

/** Profil: the display name, which the Settings tab loads again as it opens. */
export function ProfileValue() {
  return useCurrentUser().display_name;
}

/** Paar: "1 Anfrage" while requests wait (D-51), else the partner, marked when deactivated. */
export function CoupleValue() {
  const { t } = useTranslation();
  const { data } = useCouple();
  if (!data) return null;
  const requests = waitingRequests(data);
  if (requests > 0) return t('couple.requests', { count: requests });
  return data.partner ? userLabel(t, data.partner) : null;
}

/** Über MealMate: the running version. */
export function VersionValue() {
  return useVersionInfo().data?.version ?? null;
}

/**
 * System, for admins: when the last backup ran; after a failed run "Fehlgeschlagen" in words
 * (A11Y-01) and the day of the last successful backup if the host knows it; nothing while the
 * host has written no backup status (ADM-01).
 */
export function SystemValue() {
  const { t } = useTranslation();
  const language = useLanguage();
  const backup = useSystemInfo().data?.backup;
  if (!backup) return null;
  if (backup.ok) {
    return (
      <time dateTime={backup.finished_at}>{formatDateTime(backup.finished_at, language)}</time>
    );
  }
  return (
    <>
      <span className="text-destructive">{t('admin.system.backupFailed')}</span>
      {backup.last_success_at && (
        <>
          {' · '}
          <time dateTime={backup.last_success_at}>
            {t('admin.system.backupLastSuccessOn', {
              date: formatDate(backup.last_success_at, language),
            })}
          </time>
        </>
      )}
    </>
  );
}
