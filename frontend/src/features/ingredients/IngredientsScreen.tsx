import { Carrot } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { EmptyState } from '@/components/EmptyState';
import { Screen } from '@/components/Screen';
import { testIds } from '@/testIds';

export function IngredientsScreen() {
  const { t } = useTranslation();

  return (
    <Screen title={t('nav.ingredients')} testId={testIds.screenIngredients}>
      <EmptyState
        icon={Carrot}
        title={t('ingredients.empty.title')}
        text={t('ingredients.empty.text')}
        actionLabel={t('ingredients.empty.action')}
      />
    </Screen>
  );
}
