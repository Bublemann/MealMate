import { useTranslation } from 'react-i18next';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';
import { useDelayed } from '@/lib/useDelayed';
import { testIds } from '@/testIds';

interface LoadingStateProps {
  /**
   * What is being waited for, shown next to the spinner ("Suche bei Open Food Facts …"). Without
   * it, screen readers hear "Wird geladen …" and nothing shows besides the spinner.
   */
  label?: string;
  className?: string;
}

/**
 * The placeholder of a screen, a section or a pop-up whose data hasn't arrived yet (UI-08): the
 * shared spinner, centred, with its loading label. A screen shows only this until it knows what
 * it has, and then either its content or its empty state, so it never shows the controls of a
 * filled screen first and then swaps them for the empty state. The spinner appears only after
 * about 300 ms, so a quick load doesn't flash it.
 */
export function LoadingState({ label, className }: LoadingStateProps) {
  const { t } = useTranslation();
  const visible = useDelayed(true);

  return (
    <div
      role="status"
      data-testid={testIds.loadingState}
      className={cn('flex items-center justify-center gap-2 py-6 text-muted-foreground', className)}
    >
      {visible && (
        <>
          <Spinner />
          {label ? <span>{label}</span> : <span className="sr-only">{t('common.loading')}</span>}
        </>
      )}
    </div>
  );
}
