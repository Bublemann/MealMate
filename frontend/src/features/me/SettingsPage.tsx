import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Screen } from '@/components/Screen';
import type { TestId } from '@/testIds';

interface SettingsPageProps {
  title: string;
  testId: TestId;
  children: ReactNode;
}

/**
 * A page that a row of the Settings tab opens (D-45): a detail screen with the strip back to
 * the tab, "‹ Einstellungen", and no ⋯ menu, since none of these pages has actions (D-46).
 */
export function SettingsPage({ title, testId, children }: SettingsPageProps) {
  const { t } = useTranslation();

  return (
    <Screen title={title} testId={testId} back={{ to: '/me', label: t('nav.me') }}>
      {children}
    </Screen>
  );
}
