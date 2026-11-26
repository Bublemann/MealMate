import { useTranslation } from 'react-i18next';
import { testIds } from '@/testIds';
import { SettingsPage } from './SettingsPage';
import { SettingSwitch } from './SettingSwitch';

/**
 * Settings → Übrige Gerichte: whether new drafts bring along the uneaten meals of the last done
 * list (LIST-17, D-59). The setting is the user's own and kept on the server, so it follows them
 * across devices; the Settings tab loads the profile again as it opens.
 */
export function LeftoversScreen() {
  const { t } = useTranslation();

  return (
    <SettingsPage title={t('me.leftovers.title')} testId={testIds.screenLeftovers}>
      <SettingSwitch
        field="carry_over_leftovers"
        label={t('me.leftovers.carryOver')}
        hint={t('me.leftovers.carryOverHint')}
        testId={testIds.carryOverSwitch}
      />
    </SettingsPage>
  );
}
