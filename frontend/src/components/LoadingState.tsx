import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { testIds } from '@/testIds';

/** How long a load may take before the placeholder shows: shorter loads show nothing at all. */
export const LOADING_DELAY_MS = 300;

/**
 * The placeholder of a screen whose first load hasn't answered yet. A screen shows only this
 * until it knows what it has, and then either its content or its empty state, so it never
 * shows the controls of a filled screen first and then swaps them for the empty state. The text
 * appears only after a short delay, so a quick load doesn't flash it either.
 */
export function LoadingState() {
  const { t } = useTranslation();
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), LOADING_DELAY_MS);
    return () => clearTimeout(timer);
  }, []);

  return (
    <p role="status" data-testid={testIds.loadingState} className="text-muted-foreground">
      {visible ? t('common.loading') : null}
    </p>
  );
}
