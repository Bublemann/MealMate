import { Share, Shield, X, type LucideIcon } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { writeStorage } from '@/features/auth/storage';
import { testIds, type TestId } from '@/testIds';
import { HINT_STORAGE_KEYS, initialHints, type Hint } from './hints';

const HINTS = {
  homeScreen: {
    icon: Share,
    title: 'hints.homeScreen.title',
    text: 'hints.homeScreen.text',
    testId: testIds.hintHomeScreen,
  },
  tailscale: {
    icon: Shield,
    title: 'hints.tailscale.title',
    text: 'hints.tailscale.text',
    testId: testIds.hintTailscale,
  },
} as const satisfies Record<
  Hint,
  { icon: LucideIcon; title: string; text: string; testId: TestId }
>;

/** One-time tips after the first login: add to Home Screen (iOS Safari), keep Tailscale on. */
export function FirstLoginHints() {
  const { t } = useTranslation();
  const [hints, setHints] = useState(initialHints);

  if (hints.length === 0) return null;

  function dismiss(hint: Hint) {
    writeStorage(HINT_STORAGE_KEYS[hint], '1');
    setHints((current) => current.filter((other) => other !== hint));
  }

  return (
    <ul className="flex flex-col gap-3" aria-label={t('hints.label')}>
      {hints.map((hint) => {
        const { icon: Icon, title, text, testId } = HINTS[hint];
        return (
          <li key={hint}>
            <Card data-testid={testId} className="flex-row items-start gap-3 py-3 pr-1 pl-4">
              <Icon aria-hidden="true" className="mt-2.5 size-5 shrink-0 text-primary" />
              <div className="flex min-w-0 flex-1 flex-col gap-1 py-2">
                <p className="font-semibold">{t(title)}</p>
                <p className="text-sm text-muted-foreground">{t(text)}</p>
              </div>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => dismiss(hint)}
                aria-label={t('hints.dismiss', { hint: t(title) })}
              >
                <X aria-hidden="true" />
              </Button>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}
