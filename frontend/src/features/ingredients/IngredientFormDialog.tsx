import { ScanBarcode, Search } from 'lucide-react';
import { lazy, Suspense, useRef, useState, type FormEvent, type ReactNode, type Ref } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { isApiError } from '@/api/errors';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { NativeSelect } from '@/components/ui/native-select';
import { useCategories } from '@/features/reference/api';
import { CategoryOptions } from '@/features/reference/CategoryOptions';
import { OTHER_KEY, pickableCategories } from '@/features/reference/categories';
import { unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { fieldErrorMessagesByPath, needsErrorAlert } from '@/i18n/errors';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import {
  unitMismatch,
  useCreateIngredient,
  useSimilarIngredients,
  useUpdateIngredient,
  type BaseUnit,
  type EditedField,
  type Ingredient,
  type IngredientCreate,
  type IngredientSummary,
  type IngredientUpdate,
  type NutrientValues,
  type OffProposal,
  type UnitMismatch,
} from './api';
import { BaseUnitConfirmDialog } from './BaseUnitConfirmDialog';
import {
  BRAND_MAX_LENGTH,
  editedFields,
  emptyValues,
  NAME_MAX_LENGTH,
  proposalValues,
  valuesFromIngredient,
  valuesFromPrefill,
  type FormValues,
  type Prefill,
} from './formValues';
import { ingredientLabel } from './label';
import {
  NUTRIENT_KEYS,
  nutrientLabel,
  nutritionUnit,
  parseOptionalAmount,
  type NutrientKey,
} from './nutrients';
import { OffAttribution } from './OffAttribution';
import { OffSearchDialog } from './OffSearchDialog';

// The scanner and its decoder are a chunk of their own (PERF-03), loaded when the scan icon is
// tapped.
const BarcodeScanDialog = lazy(() =>
  import('@/features/scanner/BarcodeScanDialog').then((module) => ({
    default: module.BarcodeScanDialog,
  })),
);

const BASE_UNITS: readonly BaseUnit[] = ['g', 'ml', 'piece'];
/** The paths whose server errors are shown next to an input; others go to the alert. */
const SHOWN_FIELDS: ReadonlySet<string> = new Set([
  'name',
  'brand',
  'category_id',
  'base_unit',
  'barcode',
  'piece_weight_g',
  ...NUTRIENT_KEYS.map((key) => `nutrients.${key}`),
]);

interface IngredientFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Edit this ingredient; without it the dialog creates a new one. */
  ingredient?: Ingredient;
  /** Prefills the name of a new ingredient (e.g. from a search). */
  initialName?: string;
  /** Called with the saved ingredient; the dialog closes itself. */
  onSaved?: (ingredient: Ingredient) => void;
  /**
   * When given, the "similar ingredient exists" hint and the Open Food Facts results that are
   * already in MealMate offer to use that ingredient instead of linking to it (the picker).
   */
  onPickExisting?: (ingredient: IngredientSummary) => void;
}

/**
 * Creates or edits an ingredient (ING-01/02/04, NUT-02) in the compact pop-up (D-35): the form
 * scrolls between the headline and its footer with "Save", which stays in the visible area
 * above the keyboard (UI-01).
 */
export function IngredientFormDialog({ open, onOpenChange, ...props }: IngredientFormDialogProps) {
  const { t } = useTranslation();
  const { ingredient } = props;
  const nameRef = useRef<HTMLInputElement>(null);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="gap-0 overflow-hidden"
        aria-describedby={undefined}
        onOpenAutoFocus={(event) => {
          // The cursor starts in the name only while it is empty (D-35): with a name, the
          // keyboard would cover the icons and the category, so the pop-up itself takes the focus.
          event.preventDefault();
          const name = nameRef.current;
          if (name && name.value === '') name.focus();
          else if (event.currentTarget instanceof HTMLElement) event.currentTarget.focus();
        }}
      >
        <DialogHeader>
          <DialogTitle>
            {ingredient
              ? t('ingredients.form.editTitle', {
                  name: ingredientLabel(ingredient.name, ingredient.brand),
                })
              : t('ingredients.form.createTitle')}
          </DialogTitle>
        </DialogHeader>
        {/* Mounted only while open, so every opening starts from the current values. */}
        {open && (
          <IngredientForm {...props} nameRef={nameRef} onClose={() => onOpenChange(false)} />
        )}
      </DialogContent>
    </Dialog>
  );
}

export interface IngredientFormProps {
  /** Edit this ingredient; without it the form creates a new one. */
  ingredient?: Ingredient;
  /** Prefills the name of a new ingredient (e.g. from a search). */
  initialName?: string;
  /**
   * Starts a new ingredient from a looked-up barcode (the scan flow, BAR-03): its barcode and,
   * if Open Food Facts knows it, the proposed values.
   */
  prefill?: Prefill;
  /** Called with the saved ingredient, after `onClose`. */
  onSaved?: (ingredient: Ingredient) => void;
  onPickExisting?: (ingredient: IngredientSummary) => void;
  /** Called after saving (or when there was nothing to save) and before leaving to a match. */
  onClose: () => void;
  /** The name field, e.g. for the dialog to put the cursor there. */
  nameRef?: Ref<HTMLInputElement>;
  /** More actions below the save button, e.g. the scan flow's "already in MealMate". */
  children?: ReactNode;
}

/** A base-unit change the server refused because amounts would stop fitting (D-33). */
interface Refused {
  body: IngredientUpdate;
  mismatch: UnitMismatch;
}

/** The Open Food Facts proposal and its own values, to tell which ones the user changed. */
interface Proposed {
  prefill: Prefill;
  /** `proposalValues`: without what the form kept because the proposal lacks it. */
  values: FormValues;
}

/**
 * One form for every ingredient, new or existing, typed by hand or from Open Food Facts (ING-04,
 * D-35). Top to bottom: the Open Food Facts attribution while its values are shown; the name with
 * a magnifier (the Open Food Facts search, BAR-11; not when editing) and a scan icon (fills in
 * the barcode); the barcode; the similar-ingredients hint; brand; category; base unit (g, ml or
 * pieces) with the piece weight for pieces only; the nutrition per 100 g/ml. "Save" sits in a
 * footer below the fields, which scroll on their own. A product chosen in the search is saved in
 * one request, with its pack size passed on and the fields the user changed named as edited
 * (BAR-04, D-38).
 */
export function IngredientForm({
  ingredient,
  initialName = '',
  prefill,
  onSaved,
  onPickExisting,
  onClose,
  nameRef,
  children,
}: IngredientFormProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const categories = useCategories();
  const create = useCreateIngredient();
  const update = useUpdateIngredient(ingredient?.id ?? '');
  const mutation = ingredient ? update : create;

  const [initial] = useState<FormValues>(() => {
    if (ingredient) return valuesFromIngredient(ingredient, language);
    const empty = emptyValues(initialName, language);
    return prefill ? valuesFromPrefill(prefill, empty, language) : empty;
  });
  const [values, setValues] = useState(initial);
  const [proposed, setProposed] = useState<Proposed | null>(
    prefill?.proposal ? { prefill, values: proposalValues(prefill, language) } : null,
  );
  const [invalid, setInvalid] = useState<Set<string>>(new Set());
  const [refused, setRefused] = useState<Refused | null>(null);
  const [searching, setSearching] = useState(false);
  const [scanning, setScanning] = useState(false);

  // Neither a deleted category nor *Uncategorized* can be picked (ING-02, D-30).
  const pickable = pickableCategories(categories.data ?? []);
  // Categories admins added have no key (REF-01), so a missing guess must not match them; a guess
  // of a deleted category falls back to *Other*, as no guess does.
  const guessed =
    values.categoryKey === null
      ? undefined
      : pickable.find((category) => category.key === values.categoryKey);
  const defaultCategory = guessed ?? pickable.find((category) => category.key === OTHER_KEY);
  const selectedCategory = values.categoryId ?? defaultCategory?.id ?? '';
  const serverFields = fieldErrorMessagesByPath(t, mutation.error);
  const barcodeTaken =
    isApiError(mutation.error) && mutation.error.code === 'ingredient.barcode_taken';
  // A refused base-unit change asks in its own dialog instead.
  const showAlert =
    !barcodeTaken &&
    unitMismatch(mutation.error) === null &&
    needsErrorAlert(serverFields, SHOWN_FIELDS);
  // A proposal belongs to its barcode: a scanned or chosen product keeps it.
  const barcodeFixed = proposed !== null;
  const fromOff = proposed !== null || ingredient?.source === 'off';
  const edited = new Set<string>(ingredient?.source === 'off' ? ingredient.user_edited_fields : []);
  const barcode = values.barcode.replace(/\s+/g, '');
  // A new barcode would bring another product's values, so the server ends the updates.
  const offBarcodeChanged = ingredient?.source === 'off' && barcode !== (ingredient.barcode ?? '');

  function set<K extends keyof FormValues>(field: K, value: FormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  function fieldError(path: string): string | undefined {
    if (invalid.has(path)) return t('error.field.invalid_format');
    return serverFields[path];
  }

  /** A mark for an Open Food Facts field a user changed: updates from there keep it (BAR-05). */
  function editedHint(field: EditedField): string | undefined {
    return edited.has(field) ? t('ingredients.form.userEdited') : undefined;
  }

  function choose(proposal: OffProposal) {
    const prefilled: Prefill = { barcode: proposal.barcode, proposal };
    setValues(valuesFromPrefill(prefilled, values, language));
    setProposed({ prefill: prefilled, values: proposalValues(prefilled, language) });
    setInvalid(new Set());
    create.reset();
  }

  function pickExisting(match: IngredientSummary) {
    onClose();
    onPickExisting?.(match);
  }

  function saved(result: Ingredient) {
    onClose();
    onSaved?.(result);
  }

  // The category was deleted meanwhile (REF-01): the categories load again to pick another.
  function failed(error: Error) {
    if ('category_id' in fieldErrorMessagesByPath(t, error)) void categories.refetch();
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Submit events of the dialogs opened from here (the Open Food Facts search, the barcode
    // input) bubble up through the React tree; only this form's own submit saves.
    if (event.target !== event.currentTarget) return;
    const problems = new Set<string>();
    // Only pieces have a weight (ING-02): its field shows, and is sent, only for Stück. Leaving
    // Stück clears it on the server.
    const inPieces = values.baseUnit === 'piece';
    let pieceWeight: number | null = null;
    if (inPieces) {
      const parsed = parseOptionalAmount(values.piece_weight_g);
      if (parsed.ok) pieceWeight = parsed.value;
      else problems.add('piece_weight_g');
    }
    const nutrients = {} as Record<NutrientKey, number | null>;
    for (const key of NUTRIENT_KEYS) {
      const parsed = parseOptionalAmount(values.nutrients[key]);
      if (parsed.ok) nutrients[key] = parsed.value;
      else problems.add(`nutrients.${key}`);
    }
    setInvalid(problems);
    if (problems.size > 0) return;

    const texts = {
      name: values.name.trim(),
      brand: values.brand.trim() || null,
      barcode: barcode || null,
    };

    if (!ingredient) {
      const body: IngredientCreate = { name: texts.name, base_unit: values.baseUnit };
      if (selectedCategory) body.category_id = selectedCategory;
      if (texts.brand !== null) body.brand = texts.brand;
      if (texts.barcode !== null) body.barcode = texts.barcode;
      if (pieceWeight !== null) body.piece_weight_g = pieceWeight;
      const given: Partial<NutrientValues> = {};
      for (const key of NUTRIENT_KEYS) {
        if (nutrients[key] !== null) given[key] = nutrients[key];
      }
      if (Object.keys(given).length > 0) body.nutrients = given;
      const proposal = proposed?.prefill.proposal;
      if (proposal) {
        // The pack size is Open Food Facts' alone, passed on as it came (D-38).
        if (proposal.quantity_text !== null) body.quantity_text = proposal.quantity_text;
        if (proposal.pack_quantity !== null) body.pack_quantity = proposal.pack_quantity;
        if (proposal.pack_unit !== null) body.pack_unit = proposal.pack_unit;
        // Saved with its Open Food Facts origin; only the corrected values count as edited.
        body.off = {
          off_last_modified_at: proposal.off_last_modified_at,
          edited_fields: editedFields(values, proposed.values),
        };
      }
      create.mutate(body, { onSuccess: saved, onError: failed });
      return;
    }

    // Only what changed is sent, so a concurrent edit of another field isn't overwritten, and
    // only a changed Open Food Facts value is marked as edited by a user (BAR-04).
    const body: IngredientUpdate = {};
    if (texts.name !== ingredient.name) body.name = texts.name;
    if (texts.brand !== ingredient.brand) body.brand = texts.brand;
    if (selectedCategory !== ingredient.category_id) body.category_id = selectedCategory;
    if (values.baseUnit !== ingredient.base_unit) body.base_unit = values.baseUnit;
    if (texts.barcode !== ingredient.barcode) body.barcode = texts.barcode;
    // A number field counts as changed when its text changed: a stored value with more decimals
    // than shown would otherwise be cut on every save.
    if (inPieces && values.piece_weight_g.trim() !== initial.piece_weight_g) {
      body.piece_weight_g = pieceWeight;
    }
    const changed: Partial<NutrientValues> = {};
    for (const key of NUTRIENT_KEYS) {
      if (values.nutrients[key].trim() !== initial.nutrients[key]) changed[key] = nutrients[key];
    }
    if (Object.keys(changed).length > 0) body.nutrients = changed;
    if (Object.keys(body).length === 0) {
      saved(ingredient);
      return;
    }
    // A base-unit change that leaves amounts not fitting asks first, then is sent again (D-33).
    update.mutate(body, {
      onSuccess: saved,
      onError: (error) => {
        const mismatch = unitMismatch(error);
        if (mismatch) setRefused({ body, mismatch });
        else failed(error);
      },
    });
  }

  function changeAnyway() {
    if (!refused) return;
    update.mutate(
      { ...refused.body, accept_unit_mismatch: true },
      { onSuccess: saved, onError: failed },
    );
  }

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      data-testid={testIds.ingredientForm}
      className="flex min-h-0 flex-col"
    >
      {/* The fields scroll above the footer; the side padding keeps their focus rings in view. */}
      <div className="-mx-2 flex min-h-0 flex-col gap-4 overflow-y-auto px-2 py-4">
        {fromOff && <OffAttribution />}
        <FormField
          label={t('ingredients.field.name')}
          hint={editedHint('name')}
          error={fieldError('name')}
        >
          {(control) => (
            // At large text sizes the icons wrap below the name.
            <div className="flex flex-wrap gap-2">
              <Input
                {...control}
                ref={nameRef}
                name="name"
                autoComplete="off"
                required
                maxLength={NAME_MAX_LENGTH}
                value={values.name}
                onChange={(event) => set('name', event.target.value)}
                className="flex-[1_1_12rem]"
              />
              <div className="flex gap-2">
                {!ingredient && !prefill && (
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    aria-label={t('ingredients.offSearch.open')}
                    data-testid={testIds.offSearchButton}
                    onClick={() => setSearching(true)}
                  >
                    <Search aria-hidden="true" />
                  </Button>
                )}
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  aria-label={t('ingredients.field.barcodeScan')}
                  data-testid={testIds.ingredientFormScan}
                  disabled={barcodeFixed}
                  onClick={() => setScanning(true)}
                >
                  <ScanBarcode aria-hidden="true" />
                </Button>
              </div>
            </div>
          )}
        </FormField>
        <FormField
          label={t('ingredients.field.barcode')}
          hint={offBarcodeChanged ? t('ingredients.field.barcodeOffHint') : undefined}
          error={barcodeTaken ? t('error.ingredient.barcode_taken') : fieldError('barcode')}
        >
          {(control) => (
            <Input
              {...control}
              name="barcode"
              inputMode="numeric"
              autoComplete="off"
              maxLength={20}
              placeholder={t('ingredients.field.barcodePlaceholder')}
              readOnly={barcodeFixed}
              value={values.barcode}
              onChange={(event) => set('barcode', event.target.value)}
            />
          )}
        </FormField>
        <SimilarHint
          name={values.name}
          ingredient={ingredient}
          onPickExisting={onPickExisting && pickExisting}
          onNavigate={onClose}
        />
        <FormField
          label={t('ingredients.field.brand')}
          hint={editedHint('brand')}
          error={fieldError('brand')}
        >
          {(control) => (
            <Input
              {...control}
              name="brand"
              autoComplete="off"
              maxLength={BRAND_MAX_LENGTH}
              placeholder={t('ingredients.field.brandPlaceholder')}
              value={values.brand}
              onChange={(event) => set('brand', event.target.value)}
            />
          )}
        </FormField>
        <FormField
          label={t('ingredients.field.category')}
          error={fieldError('category_id') && t('ingredients.field.categoryGone')}
        >
          {(control) => (
            <NativeSelect
              {...control}
              name="category_id"
              value={selectedCategory}
              disabled={!categories.data}
              onChange={(event) => set('categoryId', event.target.value)}
            >
              <CategoryOptions categories={categories.data ?? []} selected={selectedCategory} />
            </NativeSelect>
          )}
        </FormField>
        <ErrorAlert error={categories.error} />
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm leading-none font-medium">
            {t('ingredients.field.baseUnit')}
          </legend>
          <div className="flex flex-wrap gap-2">
            {BASE_UNITS.map((unit) => (
              <label
                key={unit}
                className="flex min-h-(--tap-target) flex-1 items-center gap-3 rounded-md border px-3 has-checked:border-primary has-checked:font-semibold"
              >
                <input
                  type="radio"
                  name="base_unit"
                  value={unit}
                  checked={values.baseUnit === unit}
                  onChange={() => set('baseUnit', unit)}
                  className="size-5 accent-primary"
                />
                {t(`ingredients.baseUnit.${unit}`)}
              </label>
            ))}
          </div>
          {serverFields.base_unit && (
            <p className="text-sm font-medium text-destructive">{serverFields.base_unit}</p>
          )}
        </fieldset>
        {values.baseUnit === 'piece' && (
          <FormField
            label={t('ingredients.field.weightPerPiece')}
            error={fieldError('piece_weight_g')}
          >
            {(control) => (
              <Input
                {...control}
                name="piece_weight_g"
                inputMode="decimal"
                autoComplete="off"
                value={values.piece_weight_g}
                onChange={(event) => set('piece_weight_g', event.target.value)}
              />
            )}
          </FormField>
        )}
        <fieldset className="flex flex-col gap-3">
          <legend className="mb-1 font-semibold">
            {t('ingredients.form.nutritionTitle', {
              unit: unitLabel(t, nutritionUnit(values.baseUnit)),
            })}
          </legend>
          <div className="grid grid-cols-2 gap-3">
            {NUTRIENT_KEYS.map((key) => (
              <FormField
                key={key}
                label={nutrientLabel(t, key)}
                hint={editedHint(`nutrients.${key}`)}
                error={fieldError(`nutrients.${key}`)}
              >
                {(control) => (
                  <Input
                    {...control}
                    name={`nutrients.${key}`}
                    inputMode="decimal"
                    autoComplete="off"
                    value={values.nutrients[key]}
                    onChange={(event) => {
                      const text = event.target.value;
                      setValues((current) => ({
                        ...current,
                        nutrients: { ...current.nutrients, [key]: text },
                      }));
                    }}
                  />
                )}
              </FormField>
            ))}
          </div>
        </fieldset>
      </div>
      <div data-testid={testIds.ingredientFormFooter} className="flex flex-col gap-3 border-t pt-4">
        {showAlert && <ErrorAlert error={mutation.error} />}
        <Button
          type="submit"
          className="w-full"
          disabled={mutation.isPending || values.name.trim() === ''}
        >
          {t('common.save')}
        </Button>
      </div>
      {children}
      {searching && (
        <OffSearchDialog
          open
          onOpenChange={setSearching}
          initialQuery={values.name.trim()}
          onChoose={choose}
          onPickExisting={onPickExisting && pickExisting}
          onNavigate={onClose}
        />
      )}
      {scanning && (
        <Suspense fallback={null}>
          <BarcodeScanDialog
            open
            onOpenChange={setScanning}
            onBarcode={(scanned) => set('barcode', scanned)}
          />
        </Suspense>
      )}
      {ingredient && (
        <BaseUnitConfirmDialog
          mismatch={refused?.mismatch ?? null}
          name={ingredientLabel(ingredient.name, ingredient.brand)}
          baseUnit={ingredient.base_unit}
          onConfirm={changeAnyway}
          onClose={() => setRefused(null)}
        />
      )}
    </form>
  );
}

interface SimilarHintProps {
  name: string;
  ingredient?: Ingredient;
  onPickExisting?: (ingredient: IngredientSummary) => void;
  onNavigate: () => void;
}

/**
 * ING-03: "Similar ingredients already exist", with links to them (or buttons in the picker). A
 * hint only: two brands of the same thing are different ingredients.
 */
function SimilarHint({ name, ingredient, onPickExisting, onNavigate }: SimilarHintProps) {
  const { t } = useTranslation();
  const debounced = useDebouncedValue(name.trim());
  // Editing without renaming needs no hint.
  const query = ingredient && debounced === ingredient.name ? '' : debounced;
  const similar = useSimilarIngredients(query);
  const matches = query ? (similar.data ?? []).filter((match) => match.id !== ingredient?.id) : [];

  return (
    // Without matches the live region stays for screen readers but takes back the form's gap
    // above it, so the brand follows the barcode as closely as any field follows another.
    <div aria-live="polite" className="empty:-mt-4">
      {matches.length > 0 && (
        <div
          data-testid={testIds.ingredientSimilar}
          className="flex flex-col gap-2 rounded-lg border bg-muted p-3"
        >
          <p className="text-sm font-medium">{t('ingredients.similar.title')}</p>
          <ul className="flex flex-wrap gap-2">
            {matches.map((match) => {
              const label = ingredientLabel(match.name, match.brand);
              return (
                <li key={match.id}>
                  {onPickExisting ? (
                    <Button
                      type="button"
                      size="compact"
                      variant="outline"
                      onClick={() => onPickExisting(match)}
                    >
                      {t('ingredients.similar.use', { name: label })}
                    </Button>
                  ) : (
                    <Link
                      to={`/ingredients/${match.id}`}
                      onClick={onNavigate}
                      className="inline-flex min-h-(--tap-target) items-center rounded-md px-2 font-medium text-primary underline underline-offset-4"
                    >
                      {label}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
