import { CloudOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { useAuthSession } from './context';

/** Shown while the start-up refresh runs (usually a fraction of a second). */
export function StartupScreen() {
  const { t } = useTranslation();

  return (
    <main className="flex min-h-dvh items-center justify-center px-4">
      <p role="status" className="text-muted-foreground">
        {t('common.loading')}
      </p>
    </main>
  );
}

/** The server couldn't be reached at start and nothing is cached yet (SYNC-09). */
export function UnreachableScreen() {
  const { t } = useTranslation();
  const session = useAuthSession();

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col items-center justify-center gap-4 px-4 text-center">
      <CloudOff aria-hidden="true" className="size-10 text-muted-foreground" />
      <h1 className="text-xl font-semibold">{t('auth.unreachable.title')}</h1>
      <p className="text-muted-foreground">{t('auth.unreachable.text')}</p>
      <Button onClick={() => void session.retry()}>{t('common.retry')}</Button>
    </main>
  );
}
