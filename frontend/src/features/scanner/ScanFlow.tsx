import { ChevronLeft, CircleAlert, Link2, RotateCcw, ScanBarcode } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { fieldErrorCodes, isApiError } from '@/api/errors';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { toSummary, useLinkBarcode, type IngredientSummary } from '@/features/ingredients/api';
import { IngredientForm } from '@/features/ingredients/IngredientFormDialog';
import { IngredientPicker } from '@/features/ingredients/IngredientPicker';
import { ingredientLabel } from '@/features/ingredients/label';
import { testIds } from '@/testIds';
import { useBarcodeLookup, type BarcodeLookup } from './api';
import { BarcodeScanner } from './BarcodeScanner';

type Step =
  | { kind: 'scan' }
  | { kind: 'form'; lookup: BarcodeLookup }
  | { kind: 'link'; lookup: BarcodeLookup };

interface ScanFlowProps {
  /**
   * Called with the ingredient the barcode belongs to: the known one (BAR-02), the one just
   * created from the scanned product (BAR-03), or an existing one the barcode was linked to.
   */
  onIngredient: (ingredient: IngredientSummary) => void;
}

/** When Open Food Facts can't answer in time: try again, or enter the values by hand. */
function isOffSlow(error: unknown): boolean {
  return isApiError(error) && (error.code === 'off.busy' || error.code === 'client.timeout');
}

/**
 * Scan or type a barcode and look it up (our ingredients first, then Open Food Facts). A known
 * barcode ends at once with its ingredient. Otherwise the ingredient form opens, filled with
 * Open Food Facts' proposal (or only the barcode), and one "Save" creates the ingredient.
 */
export function ScanFlow({ onIngredient }: ScanFlowProps) {
  const { t } = useTranslation();
  const lookup = useBarcodeLookup();
  const [step, setStep] = useState<Step>({ kind: 'scan' });
  const [barcode, setBarcode] = useState('');
  // A new lookup of the same barcode (retry) starts the form over with its answer.
  const [attempt, setAttempt] = useState(0);

  function lookUp(code: string) {
    setBarcode(code);
    lookup.mutate(code, {
      onSuccess: (result) => {
        if (result.found_in === 'db' && result.ingredient) {
          onIngredient(toSummary(result.ingredient));
          return;
        }
        setAttempt((current) => current + 1);
        setStep({ kind: 'form', lookup: result });
      },
    });
  }

  function restart() {
    lookup.reset();
    setStep({ kind: 'scan' });
  }

  if (step.kind === 'form') {
    return (
      <ScannedForm
        key={attempt}
        lookup={step.lookup}
        onRetry={() => lookUp(step.lookup.barcode)}
        retrying={lookup.isPending}
        retryError={lookup.error}
        onSaved={onIngredient}
        onLinkExisting={() => setStep({ kind: 'link', lookup: step.lookup })}
        onRestart={restart}
      />
    );
  }

  if (step.kind === 'link') {
    return (
      <LinkExisting
        barcode={step.lookup.barcode}
        onLinked={onIngredient}
        onBack={() => setStep({ kind: 'form', lookup: step.lookup })}
      />
    );
  }

  if (lookup.isPending) {
    return (
      <p aria-live="polite" className="text-muted-foreground">
        {t('scanner.lookingUp', { barcode })}
      </p>
    );
  }

  if (isOffSlow(lookup.error)) {
    return (
      <div className="flex flex-col gap-3">
        <Notice text={t('scanner.offUnavailable', { barcode })} />
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => lookUp(barcode)}>
            <RotateCcw aria-hidden="true" />
            {t('common.retry')}
          </Button>
          <Button
            variant="outline"
            data-testid={testIds.scanEnterManually}
            onClick={() => setStep({ kind: 'form', lookup: unavailableLookup(barcode) })}
          >
            {t('scanner.enterManually')}
          </Button>
          <ScanAgainButton onClick={restart} />
        </div>
      </div>
    );
  }

  const invalidBarcode = fieldErrorCodes(lookup.error).barcode !== undefined;
  return (
    <div className="flex flex-col gap-4">
      {invalidBarcode ? (
        <Alert variant="destructive">
          <CircleAlert aria-hidden="true" />
          <AlertDescription>{t('scanner.invalidBarcode', { barcode })}</AlertDescription>
        </Alert>
      ) : (
        <ErrorAlert error={lookup.error} />
      )}
      <BarcodeScanner onBarcode={lookUp} />
    </div>
  );
}

/** A lookup that couldn't ask Open Food Facts: the user enters the values. */
function unavailableLookup(barcode: string): BarcodeLookup {
  return { barcode, found_in: 'none', ingredient: null, proposal: null, off_unavailable: true };
}

/**
 * Back to the scanner, next to a notice that names the barcode: a misread code shows there, and
 * the next scan is one tap away.
 */
function ScanAgainButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation();

  return (
    <Button variant="outline" data-testid={testIds.scanAgain} onClick={onClick}>
      <ScanBarcode aria-hidden="true" />
      {t('scanner.scanAgain')}
    </Button>
  );
}

/** "Not found" or "Open Food Facts is slow", with the barcode looked up. */
function Notice({ text }: { text: string }) {
  return (
    <Alert data-testid={testIds.scanNotice}>
      <CircleAlert aria-hidden="true" />
      <AlertDescription>{text}</AlertDescription>
    </Alert>
  );
}

/** Moves the focus to a step's heading when the step appears, for screen readers. */
function useFocusOnMount<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => ref.current?.focus(), []);
  return ref;
}

interface ScannedFormProps {
  lookup: BarcodeLookup;
  onRetry: () => void;
  retrying: boolean;
  retryError: unknown;
  onSaved: (ingredient: IngredientSummary) => void;
  onLinkExisting: () => void;
  onRestart: () => void;
}

/**
 * BAR-03: the ingredient form for a new barcode, filled with Open Food Facts' values (or only the
 * barcode when it doesn't know it or couldn't be asked). Everything can be corrected before the
 * one "Save".
 */
function ScannedForm({
  lookup,
  onRetry,
  retrying,
  retryError,
  onSaved,
  onLinkExisting,
  onRestart,
}: ScannedFormProps) {
  const { t } = useTranslation();
  const headingId = useId();
  const headingRef = useFocusOnMount<HTMLHeadingElement>();
  const { proposal } = lookup;

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      {/* Compact like "Neue Zutat": no text below the headline (D-35). */}
      <h2 id={headingId} ref={headingRef} tabIndex={-1} className="text-xl font-semibold">
        {t(proposal ? 'scanner.form.titleFound' : 'scanner.form.titleNew')}
      </h2>
      {!proposal && (
        <div className="flex flex-col gap-3">
          <Notice
            text={t(lookup.off_unavailable ? 'scanner.offUnavailable' : 'scanner.notFound', {
              barcode: lookup.barcode,
            })}
          />
          <div className="flex flex-wrap gap-2">
            {lookup.off_unavailable && (
              <Button variant="outline" disabled={retrying} onClick={onRetry}>
                <RotateCcw aria-hidden="true" />
                {t('common.retry')}
              </Button>
            )}
            <ScanAgainButton onClick={onRestart} />
          </div>
          <ErrorAlert error={retryError} />
        </div>
      )}
      <IngredientForm
        prefill={{ barcode: lookup.barcode, proposal }}
        onClose={() => undefined}
        onSaved={(ingredient) => onSaved(toSummary(ingredient))}
        onPickExisting={onSaved}
      >
        <div className="mt-4 flex flex-col gap-2 border-t pt-4">
          <Button
            type="button"
            variant="outline"
            className="self-start"
            data-testid={testIds.scanLinkExisting}
            onClick={onLinkExisting}
          >
            <Link2 aria-hidden="true" />
            {t('scanner.link.open')}
          </Button>
          {/* Without a proposal, the notice at the top has "Scan again" already. */}
          {proposal && (
            <Button type="button" variant="ghost" className="self-start" onClick={onRestart}>
              <ScanBarcode aria-hidden="true" />
              {t('scanner.scanAnother')}
            </Button>
          )}
        </div>
      </IngredientForm>
    </section>
  );
}

interface LinkExistingProps {
  barcode: string;
  onLinked: (ingredient: IngredientSummary) => void;
  onBack: () => void;
}

/**
 * "This is already in MealMate": the scanned barcode goes to an ingredient typed by hand before,
 * so the next scan finds it (BAR-02). An ingredient that has a barcode keeps it: a package of
 * another brand is another ingredient.
 */
function LinkExisting({ barcode, onLinked, onBack }: LinkExistingProps) {
  const { t } = useTranslation();
  const headingId = useId();
  const headingRef = useFocusOnMount<HTMLHeadingElement>();
  const link = useLinkBarcode();
  const [refused, setRefused] = useState<string | null>(null);

  function onSelect(ingredient: IngredientSummary) {
    link.reset();
    if (ingredient.barcode) {
      setRefused(ingredientLabel(ingredient.name, ingredient.brand));
      return;
    }
    setRefused(null);
    link.mutate(
      { id: ingredient.id, barcode },
      { onSuccess: (linked) => onLinked(toSummary(linked)) },
    );
  }

  return (
    <section
      aria-labelledby={headingId}
      data-testid={testIds.scanLink}
      className="flex flex-col gap-4"
    >
      <div className="flex flex-col gap-1">
        <h2 id={headingId} ref={headingRef} tabIndex={-1} className="text-xl font-semibold">
          {t('scanner.link.title')}
        </h2>
        <p className="text-muted-foreground">{t('scanner.link.text', { barcode })}</p>
      </div>
      <IngredientPicker label={t('scanner.link.search')} allowCreate={false} onSelect={onSelect} />
      <div aria-live="polite">
        {refused && (
          <Alert variant="destructive">
            <CircleAlert aria-hidden="true" />
            <AlertDescription>{t('scanner.link.hasBarcode', { name: refused })}</AlertDescription>
          </Alert>
        )}
      </div>
      <ErrorAlert error={link.error} />
      <Button variant="outline" className="self-start" disabled={link.isPending} onClick={onBack}>
        <ChevronLeft aria-hidden="true" />
        {t('scanner.link.back')}
      </Button>
    </section>
  );
}
