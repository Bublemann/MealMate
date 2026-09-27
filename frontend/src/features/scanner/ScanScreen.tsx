import { ChevronLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { Screen } from '@/components/Screen';
import { testIds } from '@/testIds';
import { ScanFlow } from './ScanFlow';

/**
 * `/scan` (BAR-01), opened from the Ingredients tab; a lazy-loaded chunk with the decoder
 * (PERF-03). It ends on the barcode's ingredient.
 */
export function ScanScreen() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Screen title={t('scanner.title')} testId={testIds.screenScan}>
      <Link
        to="/ingredients"
        className="-mt-3 inline-flex min-h-(--tap-target) items-center gap-1 self-start font-medium text-primary underline-offset-4 hover:underline"
      >
        <ChevronLeft aria-hidden="true" className="size-5" />
        {t('ingredients.detail.back')}
      </Link>
      <ScanFlow
        onIngredient={(ingredient) =>
          void navigate(`/ingredients/${ingredient.id}`, { replace: true })
        }
      />
    </Screen>
  );
}
