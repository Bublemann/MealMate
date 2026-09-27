import { Trans } from 'react-i18next';
import { ExternalLink } from '@/components/ExternalLink';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';

const OPEN_FOOD_FACTS_URL = 'https://world.openfoodfacts.org';

/**
 * "Nutrition data: Open Food Facts (ODbL)" with a link (BAR-09): wherever Open Food Facts data
 * is shown, and on the Me tab's About section.
 */
export function OffAttribution({ className }: { className?: string }) {
  return (
    <p
      data-testid={testIds.offAttribution}
      className={cn('text-sm text-muted-foreground', className)}
    >
      <Trans
        i18nKey="off.attribution"
        components={{ offLink: <ExternalLink href={OPEN_FOOD_FACTS_URL} /> }}
      />
    </p>
  );
}
