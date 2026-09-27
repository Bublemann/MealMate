import { ListChecks } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { EmptyState } from '@/components/EmptyState';
import { Screen } from '@/components/Screen';
import { FirstLoginHints } from '@/features/hints/FirstLoginHints';
import { testIds } from '@/testIds';

export function ListsScreen() {
  const { t } = useTranslation();

  return (
    <Screen title={t('nav.lists')} testId={testIds.screenLists}>
      <FirstLoginHints />
      <EmptyState
        icon={ListChecks}
        title={t('lists.empty.title')}
        text={t('lists.empty.text')}
        actionLabel={t('lists.empty.action')}
      />
    </Screen>
  );
}
