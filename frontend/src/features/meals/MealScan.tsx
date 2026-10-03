import { CircleAlert, ScanBarcode } from 'lucide-react';
import { lazy, Suspense, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { fieldErrorCodes } from '@/api/errors';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Button } from '@/components/ui/button';
import { toSummary, type IngredientSummary } from '@/features/ingredients/api';
import { IngredientFormDialog } from '@/features/ingredients/IngredientFormDialog';
import { useBarcodeLookup } from '@/features/scanner/api';
import { testIds } from '@/testIds';

// The scanner and its decoder are a separate chunk, loaded on the first tap (PERF-03).
const BarcodeScanDialog = lazy(() =>
  import('@/features/scanner/BarcodeScanDialog').then((module) => ({
    default: module.BarcodeScanDialog,
  })),
);

interface MealScanProps {
  /** Called with the barcode's ingredient: the known one, or the one saved or taken in the pop-up. */
  onIngredient: (ingredient: IngredientSummary) => void;
}

/**
 * The meal form's "Scan barcode" (BAR-01, MEAL-03). A barcode one of our ingredients has adds its
 * row at once (BAR-02): our own ingredients answer that without waiting for Open Food Facts. Any
 * other barcode opens "New ingredient", which looks it up as after a scan with its own scan icon
 * (BAR-03); its "Save", or taking an ingredient there, adds the row.
 */
export function MealScan({ onIngredient }: MealScanProps) {
  const { t } = useTranslation();
  const lookup = useBarcodeLookup();
  const [scanning, setScanning] = useState(false);
  // The barcode no ingredient has, while "New ingredient" is open for it.
  const [unknown, setUnknown] = useState<string | null>(null);
  const barcode = lookup.variables?.barcode ?? '';
  const invalid = fieldErrorCodes(lookup.error).barcode !== undefined;

  function lookUp(code: string) {
    lookup.mutate(
      { barcode: code, ownOnly: true },
      {
        onSuccess: (result) => {
          if (result.found_in === 'db' && result.ingredient) {
            onIngredient(toSummary(result.ingredient));
          } else {
            setUnknown(result.barcode);
          }
        },
      },
    );
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        className="mt-3"
        data-testid={testIds.scanBarcode}
        onClick={() => {
          // A new scan replaces a lookup still running and its message.
          lookup.reset();
          setScanning(true);
        }}
      >
        <ScanBarcode aria-hidden="true" />
        {t('scanner.open')}
      </Button>
      {/* Without a message the live region stays for screen readers but takes no room. */}
      <div aria-live="polite" className="mt-3 text-sm empty:mt-0">
        {lookup.isPending && (
          <p className="text-muted-foreground">{t('scanner.lookingUp', { barcode })}</p>
        )}
        {invalid && (
          <p className="flex items-start gap-1.5 font-medium text-destructive">
            <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            {t('scanner.invalidBarcode', { barcode })}
          </p>
        )}
      </div>
      {lookup.isError && !invalid && (
        <div className="mt-3">
          <ErrorAlert error={lookup.error} />
        </div>
      )}
      {scanning && (
        <Suspense fallback={null}>
          <BarcodeScanDialog
            open
            onOpenChange={setScanning}
            onBarcode={lookUp}
            description={t('scanner.dialogText')}
          />
        </Suspense>
      )}
      <IngredientFormDialog
        open={unknown !== null}
        onOpenChange={(open) => {
          if (!open) setUnknown(null);
        }}
        initialScan={unknown ?? undefined}
        onSaved={(ingredient) => onIngredient(toSummary(ingredient))}
        onPickExisting={onIngredient}
      />
    </>
  );
}
