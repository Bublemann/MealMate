import { CircleAlert, Plus, RotateCcw, ScanBarcode } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { fieldErrorCodes, isApiError } from '@/api/errors';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { toSummary, type IngredientSummary } from '@/features/ingredients/api';
import { IngredientFormDialog } from '@/features/ingredients/IngredientFormDialog';
import { IngredientPicker } from '@/features/ingredients/IngredientPicker';
import { formatNutrient, NUTRIENT_KEYS, nutrientLabel } from '@/features/ingredients/nutrients';
import { OffAttribution } from '@/features/ingredients/OffAttribution';
import { ProductForm } from '@/features/ingredients/ProductFormDialog';
import { useCategories } from '@/features/reference/api';
import { categoryName, unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { testIds } from '@/testIds';
import { useProductLookup, type ProductLookup } from './api';
import { BarcodeScanner } from './BarcodeScanner';

/** The longest ingredient name the ingredient form accepts; a product name may be longer. */
const INGREDIENT_NAME_MAX = 60;

type Step =
  | { kind: 'scan' }
  | { kind: 'which'; lookup: ProductLookup }
  | { kind: 'product'; lookup: ProductLookup; ingredient: IngredientSummary };

interface ScanFlowProps {
  /**
   * Called with the ingredient the barcode belongs to: the known product's (BAR-02), or the one
   * chosen or created for a new product once that is saved (BAR-03).
   */
  onIngredient: (ingredient: IngredientSummary) => void;
}

/** When Open Food Facts can't answer in time: try again, or enter the values by hand. */
function isOffSlow(error: unknown): boolean {
  return isApiError(error) && (error.code === 'off.busy' || error.code === 'client.timeout');
}

/**
 * Scan or type a barcode, look it up (our products first, then Open Food Facts), and for a new
 * product ask "Which ingredient is this?" before saving it with its (corrected) values.
 */
export function ScanFlow({ onIngredient }: ScanFlowProps) {
  const { t } = useTranslation();
  const lookup = useProductLookup();
  const [step, setStep] = useState<Step>({ kind: 'scan' });
  const [barcode, setBarcode] = useState('');

  function lookUp(code: string) {
    setBarcode(code);
    lookup.mutate(code, {
      onSuccess: (result) => {
        if (result.found_in === 'db' && result.ingredient) onIngredient(result.ingredient);
        else setStep({ kind: 'which', lookup: result });
      },
    });
  }

  function restart() {
    lookup.reset();
    setStep({ kind: 'scan' });
  }

  if (step.kind === 'which') {
    return (
      <WhichIngredient
        lookup={step.lookup}
        onRetry={() => lookUp(step.lookup.barcode)}
        retrying={lookup.isPending}
        retryError={lookup.error}
        onChoose={(ingredient) => setStep({ kind: 'product', lookup: step.lookup, ingredient })}
        onRestart={restart}
      />
    );
  }

  if (step.kind === 'product') {
    return (
      <ProductStep
        lookup={step.lookup}
        ingredient={step.ingredient}
        onSaved={() => onIngredient(step.ingredient)}
        onBack={() => setStep({ kind: 'which', lookup: step.lookup })}
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
        <Notice text={t('scanner.offUnavailable')} />
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => lookUp(barcode)}>
            <RotateCcw aria-hidden="true" />
            {t('common.retry')}
          </Button>
          <Button
            variant="outline"
            data-testid={testIds.scanEnterManually}
            onClick={() => setStep({ kind: 'which', lookup: unavailableLookup(barcode) })}
          >
            {t('scanner.enterManually')}
          </Button>
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
function unavailableLookup(barcode: string): ProductLookup {
  return {
    barcode,
    found_in: 'none',
    product: null,
    ingredient: null,
    proposal: null,
    suggestions: [],
    off_unavailable: true,
  };
}

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

interface WhichIngredientProps {
  lookup: ProductLookup;
  onChoose: (ingredient: IngredientSummary) => void;
  onRetry: () => void;
  retrying: boolean;
  retryError: unknown;
  onRestart: () => void;
}

/** BAR-03: the proposal (or "not found"), then "Which ingredient is this?". */
function WhichIngredient({
  lookup,
  onChoose,
  onRetry,
  retrying,
  retryError,
  onRestart,
}: WhichIngredientProps) {
  const { t } = useTranslation();
  const headingId = useId();
  const headingRef = useFocusOnMount<HTMLHeadingElement>();
  const categories = useCategories();
  const [creating, setCreating] = useState(false);
  const { proposal, suggestions } = lookup;
  const categoryKeys = new Map(categories.data?.map((category) => [category.id, category.key]));

  return (
    <div className="flex flex-col gap-5">
      {proposal ? (
        <ProposalCard lookup={lookup} />
      ) : (
        <div className="flex flex-col gap-3">
          <Notice
            text={t(lookup.off_unavailable ? 'scanner.offUnavailable' : 'scanner.notFound')}
          />
          {lookup.off_unavailable && (
            <Button variant="outline" className="self-start" disabled={retrying} onClick={onRetry}>
              <RotateCcw aria-hidden="true" />
              {t('common.retry')}
            </Button>
          )}
          <ErrorAlert error={retryError} />
        </div>
      )}
      <section
        aria-labelledby={headingId}
        data-testid={testIds.scanWhich}
        className="flex flex-col gap-4"
      >
        <div className="flex flex-col gap-1">
          <h2 id={headingId} ref={headingRef} tabIndex={-1} className="text-xl font-semibold">
            {t('scanner.which.title')}
          </h2>
          <p className="text-muted-foreground">{t('scanner.which.text')}</p>
        </div>
        {suggestions.length > 0 && (
          <ul
            data-testid={testIds.scanSuggestions}
            aria-label={t('scanner.which.suggestions')}
            className="flex flex-col divide-y rounded-lg border"
          >
            {suggestions.map((ingredient) => {
              const key = categoryKeys.get(ingredient.category_id);
              return (
                <li key={ingredient.id}>
                  <button
                    type="button"
                    onClick={() => onChoose(ingredient)}
                    className="flex min-h-(--tap-target) w-full flex-col items-start px-3 py-2 text-left outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
                  >
                    <span className="font-medium break-words">{ingredient.name}</span>
                    <span className="text-sm text-muted-foreground">
                      {key ? `${categoryName(t, key)} · ` : ''}
                      {unitLabel(t, ingredient.base_unit)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <IngredientPicker
          label={t('scanner.which.search')}
          allowCreate={false}
          onSelect={onChoose}
        />
        <Button
          variant="outline"
          className="self-start"
          data-testid={testIds.scanCreateIngredient}
          onClick={() => setCreating(true)}
        >
          <Plus aria-hidden="true" />
          {t('scanner.which.create')}
        </Button>
      </section>
      <Button variant="ghost" className="self-start" onClick={onRestart}>
        <ScanBarcode aria-hidden="true" />
        {t('scanner.scanAnother')}
      </Button>
      <IngredientFormDialog
        open={creating}
        onOpenChange={setCreating}
        initialName={proposal?.name?.slice(0, INGREDIENT_NAME_MAX) ?? ''}
        initialCategoryKey={proposal?.category_key}
        initialBaseUnit={proposal?.nutrition_basis ?? undefined}
        onSaved={(ingredient) => onChoose(toSummary(ingredient))}
        onPickExisting={onChoose}
      />
    </div>
  );
}

/** What Open Food Facts knows about the product, as text only (BAR-10, SEC-13). */
function ProposalCard({ lookup }: { lookup: ProductLookup }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const proposal = lookup.proposal;
  if (!proposal) return null;
  const basis = proposal.nutrition_basis;
  const values = NUTRIENT_KEYS.flatMap((key) => {
    const value = proposal.nutrients[key];
    return value === null || value === undefined
      ? []
      : [{ key, text: formatNutrient(t, language, key, value) }];
  });

  return (
    <Card data-testid={testIds.scanProposal}>
      <CardHeader>
        <CardTitle className="break-words">
          {proposal.name ?? t('ingredients.products.unnamed')}
        </CardTitle>
        <CardDescription>{t('scanner.proposal.found')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl className="flex flex-col divide-y">
          {proposal.brand && <Row label={t('ingredients.product.brand')} value={proposal.brand} />}
          {proposal.quantity_text && (
            <Row label={t('scanner.proposal.quantity')} value={proposal.quantity_text} />
          )}
          <Row label={t('ingredients.product.barcode')} value={lookup.barcode} />
        </dl>
        <div className="flex flex-col gap-2">
          <h3 className="font-semibold">
            {basis
              ? t('ingredients.product.nutritionTitle', { unit: unitLabel(t, basis) })
              : t('scanner.proposal.nutritionUnknownBasis')}
          </h3>
          {values.length > 0 ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
              {values.map(({ key, text }) => (
                <div key={key} className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">{nutrientLabel(t, key)}</dt>
                  <dd className="font-medium tabular-nums">{text}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-muted-foreground">{t('ingredients.products.noValues')}</p>
          )}
        </div>
        <OffAttribution />
      </CardContent>
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium break-words">{value}</dd>
    </div>
  );
}

interface ProductStepProps {
  lookup: ProductLookup;
  ingredient: IngredientSummary;
  onSaved: () => void;
  onBack: () => void;
}

/** The product's values, prefilled from Open Food Facts and correctable, saved to `ingredient`. */
function ProductStep({ lookup, ingredient, onSaved, onBack }: ProductStepProps) {
  const { t } = useTranslation();
  const headingId = useId();
  const headingRef = useFocusOnMount<HTMLHeadingElement>();
  const proposal = lookup.proposal;

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h2
          id={headingId}
          ref={headingRef}
          tabIndex={-1}
          className="text-xl font-semibold break-words"
        >
          {t('scanner.product.title', { name: ingredient.name })}
        </h2>
        <p className="text-muted-foreground">
          {t(proposal ? 'scanner.product.textProposal' : 'scanner.product.textManual')}
        </p>
      </div>
      {proposal && <OffAttribution />}
      <ProductForm
        ingredient={ingredient}
        lookedUp={{ barcode: lookup.barcode, proposal }}
        onClose={onSaved}
      />
      <Button variant="outline" className="self-start" onClick={onBack}>
        {t('scanner.product.otherIngredient')}
      </Button>
    </section>
  );
}
