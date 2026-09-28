import { X } from 'lucide-react';
import { useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { useLanguage } from '@/i18n';
import { testIds } from '@/testIds';
import { useSyncEngine } from './context';

/**
 * Messages about sent changes the server didn't take (plan § 5.8): each is shown once and stays
 * until it is dismissed, so nothing is missed.
 */
export function SyncToasts() {
  const { t } = useTranslation();
  const language = useLanguage();
  const engine = useSyncEngine();
  const toasts = useSyncExternalStore(engine.toasts.subscribe, engine.toasts.get);

  return (
    <section
      aria-label={t('sync.notifications')}
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 top-[max(0.75rem,env(safe-area-inset-top))] z-30 flex flex-col items-center gap-2 px-4 empty:hidden"
    >
      {toasts.map((toast) => (
        <Card
          key={toast.id}
          data-testid={testIds.syncToast}
          className="pointer-events-auto w-full max-w-xl flex-row items-start gap-2 py-2 pr-2 pl-4 shadow-lg"
        >
          <p className="min-w-0 flex-1 py-2 text-sm">{toast.text(t, language)}</p>
          <Button
            variant="ghost"
            size="icon"
            aria-label={t('sync.dismiss')}
            onClick={() => engine.dismissToast(toast.id)}
          >
            <X aria-hidden="true" />
          </Button>
        </Card>
      ))}
    </section>
  );
}
