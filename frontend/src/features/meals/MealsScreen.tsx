import { CookingPot } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { EmptyState } from '@/components/EmptyState';
import { Screen } from '@/components/Screen';
import { testIds } from '@/testIds';

export function MealsScreen() {
  const { t } = useTranslation();

  return (
    <Screen title={t('nav.meals')} testId={testIds.screenMeals}>
      <EmptyState
        icon={CookingPot}
        title={t('meals.empty.title')}
        text={t('meals.empty.text')}
        actionLabel={t('meals.empty.action')}
      />
    </Screen>
  );
}
