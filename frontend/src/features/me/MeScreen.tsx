import { useId } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { ExternalLink } from '@/components/ExternalLink';
import { Screen } from '@/components/Screen';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { changeLanguage, isLanguage, LANGUAGE_NAMES, LANGUAGES, useLanguage } from '@/i18n';
import { errorMessage } from '@/i18n/errors';
import { testIds } from '@/testIds';
import { useVersionInfo } from './api';

const OPEN_FOOD_FACTS_URL = 'https://world.openfoodfacts.org';

export function MeScreen() {
  const { t } = useTranslation();
  const language = useLanguage();
  const languageSelectId = useId();
  const version = useVersionInfo();

  return (
    <Screen title={t('me.title')} testId={testIds.screenMe}>
      <Card>
        <CardHeader>
          <CardTitle>{t('me.settings')}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-2">
          <Label htmlFor={languageSelectId}>{t('me.language')}</Label>
          <NativeSelect
            id={languageSelectId}
            data-testid={testIds.languageSelect}
            value={language}
            onChange={(event) => {
              const selected = event.target.value;
              if (isLanguage(selected)) void changeLanguage(selected);
            }}
          >
            {LANGUAGES.map((code) => (
              <NativeSelectOption key={code} value={code} lang={code}>
                {LANGUAGE_NAMES[code]}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        </CardContent>
      </Card>

      {/* UI-06, LIC-02, BAR-09 */}
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
    </Screen>
  );
}
