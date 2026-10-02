import { useSyncExternalStore } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { testIds } from '@/testIds';
import { pwaUpdate } from './pwaUpdate';
import { useKeyboardOpen } from './viewport';

/**
 * Offers to reload when a new app version has been installed in the background. Like the tab bar,
 * it hides while the keyboard is open (UI-01).
 */
export function UpdatePrompt() {
  const { t } = useTranslation();
  const available = useSyncExternalStore(pwaUpdate.subscribe, pwaUpdate.isAvailable);
  const keyboardOpen = useKeyboardOpen();

  return (
    <div
      aria-live="polite"
      hidden={keyboardOpen}
      className="pointer-events-none fixed inset-x-0 bottom-[calc(var(--tab-bar-clearance)+0.5rem)] z-20 px-4"
    >
      {available && (
        <Card
          data-testid={testIds.updatePrompt}
          className="pointer-events-auto mx-auto max-w-xl flex-row flex-wrap items-center gap-2 px-4 py-2 shadow-lg"
        >
          <p className="min-w-0 flex-1 text-sm">{t('update.available')}</p>
          <div className="flex gap-2">
            <Button variant="ghost" size="compact" onClick={pwaUpdate.dismiss}>
              {t('update.dismiss')}
            </Button>
            <Button size="compact" onClick={() => void pwaUpdate.apply()}>
              {t('update.reload')}
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
