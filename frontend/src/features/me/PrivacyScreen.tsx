import { useTranslation } from 'react-i18next';
import { testIds } from '@/testIds';
import { SettingsPage } from './SettingsPage';
import { SettingSwitch } from './SettingSwitch';

/**
 * Settings → Privatsphäre: the two switches (VIS-02); the partner always sees everything
 * (CPL-04).
 */
export function PrivacyScreen() {
  const { t } = useTranslation();

  return (
    <SettingsPage title={t('me.privacy.title')} testId={testIds.screenPrivacy}>
      <p className="text-muted-foreground">{t('me.privacy.text')}</p>
      <SettingSwitch
        field="meals_public"
        label={t('me.privacy.mealsPublic')}
        hint={t('me.privacy.mealsPublicHint')}
        testId={testIds.mealsPublicSwitch}
      />
      <SettingSwitch
        field="lists_public"
        label={t('me.privacy.listsPublic')}
        hint={t('me.privacy.listsPublicHint')}
        testId={testIds.listsPublicSwitch}
      />
    </SettingsPage>
  );
}
