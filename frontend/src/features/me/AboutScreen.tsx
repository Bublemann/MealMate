import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ExternalLink } from '@/components/ExternalLink';
import { useCurrentUser } from '@/features/auth/context';
import { OffAttribution } from '@/features/ingredients/OffAttribution';
import { errorMessage } from '@/i18n/errors';
import { testIds } from '@/testIds';
import { useVersionInfo } from './api';
import { SettingsPage } from './SettingsPage';

/**
 * Settings → Über MealMate (UI-06, LIC-02, BAR-09): the version, the link to its exact source
 * revision, the Open Food Facts credit and, for admins only, the link to /diag (the owner runs the
 * platform tests; nobody else needs a test screen in their app).
 */
export function AboutScreen() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const version = useVersionInfo();

  return (
    <SettingsPage title={t('me.about')} testId={testIds.screenAbout}>
      <div className="flex flex-col gap-3">
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
        {user.role === 'admin' && (
          <Link
            to="/diag"
            data-testid={testIds.diagnosticsLink}
            className="inline-flex min-h-(--tap-target) items-center self-start text-sm text-muted-foreground underline underline-offset-4"
          >
            {t('me.diagnostics')}
          </Link>
        )}
      </div>
    </SettingsPage>
  );
}
