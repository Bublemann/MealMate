import { ChevronRight, LogOut } from 'lucide-react';
import { Trans, useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { ExternalLink } from '@/components/ExternalLink';
import { Screen } from '@/components/Screen';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useLogout } from '@/features/auth/api';
import { useCurrentUser } from '@/features/auth/context';
import { CoupleSection } from '@/features/couple/CoupleSection';
import { errorMessage } from '@/i18n/errors';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import { useMeRefresh, useVersionInfo } from './api';
import { PrivacySection } from './PrivacySection';
import { ProfileSection } from './ProfileSection';
import { SecuritySection } from './SecuritySection';

const OPEN_FOOD_FACTS_URL = 'https://world.openfoodfacts.org';

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
      <AboutCard />
    </Screen>
  );
}

const ADMIN_LINKS = [
  { to: '/me/admin/users', label: 'admin.users.title' },
  { to: '/me/admin/invites', label: 'admin.invites.title' },
  { to: '/me/admin/categories', label: 'admin.categories.title' },
  { to: '/me/admin/events', label: 'admin.events.title' },
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

function LogoutCard() {
  const { t } = useTranslation();
  const logout = useLogout();

  return (
    <div className="flex flex-col gap-2">
      <Button
        variant="outline"
        data-testid={testIds.logoutButton}
        disabled={logout.isPending}
        onClick={() => logout.mutate()}
      >
        <LogOut aria-hidden="true" />
        {t('me.logout')}
      </Button>
      <ErrorAlert error={logout.error} />
    </div>
  );
}

/** UI-06, LIC-02, BAR-09 */
function AboutCard() {
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
        <p className="text-sm text-muted-foreground">
          <Trans
            i18nKey="me.offAttribution"
            components={{ offLink: <ExternalLink href={OPEN_FOOD_FACTS_URL} /> }}
          />
        </p>
      </CardContent>
    </Card>
  );
}
