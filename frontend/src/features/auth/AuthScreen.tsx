import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Screen } from '@/components/Screen';
import type { TestId } from '@/testIds';

interface AuthScreenProps {
  title: string;
  testId: TestId;
  children: ReactNode;
}

/** The frame of the screens without the tab bar: login, join, reset. */
export function AuthScreen({ title, testId, children }: AuthScreenProps) {
  const { t } = useTranslation();

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center gap-6 px-4 pt-[max(1.5rem,env(safe-area-inset-top))] pb-[max(1.5rem,env(safe-area-inset-bottom))]">
      <p className="flex items-center gap-2 text-lg font-semibold">
        <img src="/favicon.svg" alt="" className="size-8" />
        {t('app.name')}
      </p>
      <Screen title={title} testId={testId}>
        {children}
      </Screen>
    </main>
  );
}
