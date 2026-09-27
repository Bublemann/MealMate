import { ShieldAlert } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useLanguage } from '@/i18n';
import { formatDate, formatDateTime } from '@/i18n/format';
import { userLabel } from '@/i18n/users';
import { describeUserAgent } from '@/lib/userAgent';
import { testIds } from '@/testIds';
import {
  useLogoutAll,
  useRevokeSession,
  useSecurityInfo,
  useSessions,
  type SessionInfo,
} from './api';
import { PasswordDialog } from './PasswordDialog';

/** Security notice, password change, sessions and "log out on all devices" (ACC-09, ACC-10). */
export function SecuritySection() {
  const { t } = useTranslation();
  const [passwordChanged, setPasswordChanged] = useState(false);
  const logoutAll = useLogoutAll();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('me.security.title')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <SecurityNotice />
        <div className="flex flex-col gap-2">
          <PasswordDialog onChanged={() => setPasswordChanged(true)} />
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {passwordChanged && t('me.password.changed')}
          </p>
        </div>
        <SessionList />
        <ConfirmDialog
          trigger={
            <Button
              variant="outline"
              data-testid={testIds.logoutAllButton}
              disabled={logoutAll.isPending}
            >
              {t('me.sessions.logoutAll')}
            </Button>
          }
          title={t('me.sessions.logoutAllTitle')}
          description={t('me.sessions.logoutAllText')}
          confirmLabel={t('me.sessions.logoutAllConfirm')}
          onConfirm={() => logoutAll.mutate()}
          destructive
        />
        <ErrorAlert error={logoutAll.error} />
      </CardContent>
    </Card>
  );
}

function SecurityNotice() {
  const { t } = useTranslation();
  const language = useLanguage();
  const security = useSecurityInfo();

  if (!security.data) return <ErrorAlert error={security.error} />;
  const { password_reset_at: resetAt, password_reset_by: resetBy } = security.data;
  const changedAt = security.data.password_changed_at;

  return (
    <>
      {resetAt && (
        <Alert data-testid={testIds.securityNotice}>
          <ShieldAlert aria-hidden="true" />
          <AlertDescription>
            {resetBy
              ? t('me.security.resetBy', {
                  name: userLabel(t, resetBy),
                  date: formatDateTime(resetAt, language),
                })
              : t('me.security.resetByLink', { date: formatDateTime(resetAt, language) })}
          </AlertDescription>
        </Alert>
      )}
      {changedAt && (
        <p className="text-sm text-muted-foreground">
          {t('me.security.changedAt', { date: formatDate(changedAt, language) })}
        </p>
      )}
    </>
  );
}

function SessionList() {
  const { t } = useTranslation();
  const sessions = useSessions();
  const revoke = useRevokeSession();
  const headingId = useId();

  return (
    <section className="flex flex-col gap-3" aria-labelledby={headingId}>
      <h3 id={headingId} className="font-semibold">
        {t('me.sessions.title')}
      </h3>
      {sessions.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <ErrorAlert error={sessions.error} />
      {sessions.data && (
        <ul data-testid={testIds.sessionList} className="flex flex-col divide-y">
          {sessions.data.map((session) => (
            <SessionRow
              key={session.id}
              session={session}
              onRevoke={() => revoke.mutate(session.id)}
              revoking={revoke.isPending && revoke.variables === session.id}
            />
          ))}
        </ul>
      )}
      <ErrorAlert error={revoke.error} />
    </section>
  );
}

interface SessionRowProps {
  session: SessionInfo;
  onRevoke: () => void;
  revoking: boolean;
}

function SessionRow({ session, onRevoke, revoking }: SessionRowProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const device = describeUserAgent(session.user_agent) ?? t('me.sessions.unknownDevice');

  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <div className="flex min-w-0 flex-col gap-1">
        <p className="flex flex-wrap items-center gap-2 font-medium">
          {device}
          {session.current && <Badge variant="secondary">{t('me.sessions.current')}</Badge>}
        </p>
        <p className="text-sm text-muted-foreground">
          {t('me.sessions.lastUsed', { date: formatDateTime(session.last_used_at, language) })}
        </p>
      </div>
      {!session.current && (
        <Button
          variant="outline"
          size="compact"
          onClick={onRevoke}
          disabled={revoking}
          aria-label={t('me.sessions.revokeLabel', { device })}
        >
          {t('me.sessions.revoke')}
        </Button>
      )}
    </li>
  );
}
