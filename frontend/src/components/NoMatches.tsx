import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';

/**
 * A search or filters that hide everything (UI-03): "Keine Treffer" and "Filter zurücksetzen",
 * which clears the search text and resets every filter group (`onReset`).
 */
export function NoMatches({ onReset }: { onReset: () => void }) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-start gap-3">
      <p role="status">{t('common.noMatches')}</p>
      {/* Wraps at the largest text sizes instead of widening the page. */}
      <Button variant="outline" className="max-w-full wrap-anywhere" onClick={onReset}>
        {t('common.resetFilters')}
      </Button>
    </div>
  );
}
