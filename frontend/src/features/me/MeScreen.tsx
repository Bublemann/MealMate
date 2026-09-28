import { ChevronRight, LogOut } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { ExternalLink } from '@/components/ExternalLink';
import { Screen } from '@/components/Screen';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useLogout } from '@/features/auth/api';
import { useCurrentUser } from '@/features/auth/context';
import { CoupleSection } from '@/features/couple/CoupleSection';
import { OffAttribution } from '@/features/ingredients/OffAttribution';
import { useSyncEngine, useSyncStatus } from '@/features/sync/context';
import { errorMessage } from '@/i18n/errors';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import { useMeRefresh, useVersionInfo } from './api';
import { PrivacySection } from './PrivacySection';
import { ProfileSection } from './ProfileSection';
import { SecuritySection } from './SecuritySection';

export function MeScreen() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  useMeRefresh();

  return (
    <Screen title={t('me.title')} testId={testIds.screenMe}>
      <ProfileSection />
      <PrivacySection />
      <CoupleSection />
      <SecuritySection />
      {user.role === 'admin' && <AdminEntry />}
      <LogoutCard />
      <AboutCard diagnostics={user.role === 'admin'} />
    </Screen>
  );
}

const ADMIN_LINKS = [
  { to: '/me/admin/users', label: 'admin.users.title' },
  { to: '/me/admin/invites', label: 'admin.invites.title' },
  { to: '/me/admin/categories', label: 'admin.categories.title' },
  { to: '/me/admin/events', label: 'admin.events.title' },
  { to: '/me/admin/system', label: 'admin.system.title' },
] as const;

/** ADM-01: only shown to admins; the server checks the role on every admin request. */
function AdminEntry() {
  const { t } = useTranslation();

  return (
    <Card data-testid={testIds.adminEntry}>
      <CardHeader>
        <CardTitle>{t('admin.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-2">
          {ADMIN_LINKS.map(({ to, label }) => (
            <li key={to}>
              <Link
                to={to}
                className={cn(buttonVariants({ variant: 'outline' }), 'w-full justify-between')}
              >
                {t(label)}
                <ChevronRight aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

/**
 * Log out. With changes still waiting to be sent it asks first: logging out deletes them with the
 * local copy (SYNC-05, SYNC-10). The outbox is read before deciding, so a tap right after the
 * start can't skip the question.
 */
function LogoutCard() {
  const { t } = useTranslation();
  const logout = useLogout();
  const engine = useSyncEngine();
  const { pending } = useSyncStatus();
  const [confirming, setConfirming] = useState(false);

  async function onLogout() {
    if ((await engine.waitingCount()) > 0) setConfirming(true);
    else logout.mutate();
  }

  return (
    <div className="flex flex-col gap-2">
      <Button
        variant="outline"
        data-testid={testIds.logoutButton}
        disabled={logout.isPending}
        onClick={() => void onLogout()}
      >
        <LogOut aria-hidden="true" />
        {t('me.logout')}
      </Button>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('me.logoutPending.title', { count: pending })}
        description={t('me.logoutPending.text')}
        confirmLabel={t('me.logoutPending.confirm')}
        destructive
        onConfirm={() => logout.mutate()}
      />
      <ErrorAlert error={logout.error} />
    </div>
  );
}

/**
 * UI-06, LIC-02, BAR-09. `diagnostics`: the link to /diag, for admins only (the owner runs the
 * platform tests; nobody else needs a test screen in their app).
 */
function AboutCard({ diagnostics }: { diagnostics: boolean }) {
  const { t } = useTranslation();
  const version = useVersionInfo();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('me.about')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl className="flex items-baseline justify-between gap-4">
          <dt className="text-muted-foreground">{t('me.version')}</dt>
          {version.data ? (
            <dd data-testid={testIds.appVersion} className="font-medium break-all">
              {version.data.version}
            </dd>
          ) : (
            <dd className="text-muted-foreground">
              {version.isError ? errorMessage(t, version.error) : t('common.loading')}
            </dd>
          )}
        </dl>
        {version.data && (
          <ExternalLink
            href={version.data.source_url}
            data-testid={testIds.sourceLink}
            className="inline-flex min-h-(--tap-target) items-center self-start"
          >
            {t('me.sourceCode')}
          </ExternalLink>
        )}
        <OffAttribution />
        {/* A Home Screen app has no address bar: the way to /diag (M1 spike, removed in M9). */}
        {diagnostics && (
          <Link
            to="/diag"
            data-testid={testIds.diagnosticsLink}
            className="inline-flex min-h-(--tap-target) items-center self-start text-sm text-muted-foreground underline underline-offset-4"
          >
            {t('me.diagnostics')}
          </Link>
        )}
      </CardContent>
    </Card>
  );
}
