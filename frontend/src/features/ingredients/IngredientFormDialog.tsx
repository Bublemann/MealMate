import { CircleAlert, RotateCcw, ScanBarcode, Search } from 'lucide-react';
import {
  lazy,
  Suspense,
  useEffect,
  useEffectEvent,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
  type Ref,
} from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { fieldErrorCodes, isApiError } from '@/api/errors';
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
import { isOffSlow, useBarcodeLookup } from '@/features/scanner/api';
import { useLanguage } from '@/i18n';
import { fieldErrorMessagesByPath, needsErrorAlert } from '@/i18n/errors';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import {
  toSummary,
  unitMismatch,
  useCreateIngredient,
  useLinkBarcode,
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
  typedValues,
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

// The plain scanner and its decoder are a chunk of their own (PERF-03), loaded when the scan
// icon is tapped. It only hands the digits back: the lookup and what follows are the form's, so
// the scanner never embeds the form (plan § 8).
const BarcodeScanDialog = lazy(() =>
  import('@/features/scanner/BarcodeScanDialog').then((module) => ({
    default: module.BarcodeScanDialog,
  })),
);

const BASE_UNITS: readonly BaseUnit[] = ['g', 'ml', 'piece'];
/** A link inside a hint or notice, as tall as a button. */
const INLINE_LINK =
  'inline-flex min-h-(--tap-target) items-center rounded-md px-2 font-medium text-primary underline underline-offset-4';
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
  /**
   * A barcode scanned before the pop-up opened (the meal form's scan, MEAL-03): it is looked up
   * at once, as a scan with the pop-up's own scan icon is.
   */
  initialScan?: string;
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

interface IngredientFormProps {
  /** Edit this ingredient; without it the form creates a new one. */
  ingredient?: Ingredient;
  /** Prefills the name of a new ingredient (e.g. from a search). */
  initialName?: string;
  /** A barcode to look up at once, as if it had just been scanned with the scan icon. */
  initialScan?: string;
  /** Called with the saved ingredient, after `onClose`. */
  onSaved?: (ingredient: Ingredient) => void;
  onPickExisting?: (ingredient: IngredientSummary) => void;
  /** Called after saving (or when there was nothing to save) and before leaving to a match. */
  onClose: () => void;
  /** The name field, e.g. for the dialog to put the cursor there. */
  nameRef?: Ref<HTMLInputElement>;
}

/** A base-unit change the server refused because amounts would stop fitting (D-33). */
interface Refused {
  body: IngredientUpdate;
  mismatch: UnitMismatch;
}

/** What the scan icon's lookup says, on the barcode's message line (BAR-02, BAR-03). */
type ScanNoticeState =
  | { kind: 'lookingUp'; barcode: string }
  | { kind: 'known'; ingredient: Ingredient }
  | { kind: 'notFound' }
  | { kind: 'slow'; barcode: string }
  | { kind: 'invalid'; barcode: string }
  | { kind: 'failed'; error: unknown };

/** The Open Food Facts proposal and its own values, to tell which ones the user changed. */
interface Proposed {
  prefill: Prefill;
  /** `proposalValues`: without what the form kept because the proposal lacks it. */
  values: FormValues;
}

/**
 * One form for every ingredient, new or existing, typed by hand, searched or scanned (ING-04,
 * D-35, D-36). Top to bottom: the Open Food Facts attribution while its values are shown; the
 * name with a magnifier (the Open Food Facts search, BAR-11; not when editing) and a scan icon;
 * the barcode with the scan's notice; the similar-ingredients hint; brand; category; base unit
 * (g, ml or pieces) with the piece weight for pieces only; the nutrition per 100 g/ml. "Save"
 * sits in a footer below the fields, which scroll on their own. A product chosen in the search
 * or scanned is saved in one request, with its pack size passed on and the fields the user
 * changed named as edited (BAR-04, D-38).
 *
 * The scan looks the barcode up (BAR-02/03): a barcode another ingredient has fills in nothing
 * and offers that one instead; one Open Food Facts knows fills the form like a chosen product;
 * any other one only the barcode. When editing, Open Food Facts isn't asked. The meal form's scan
 * opens the form with a barcode no ingredient has, looked up the same way (MEAL-03).
 */
function IngredientForm({
  ingredient,
  initialName = '',
  initialScan,
  onSaved,
  onPickExisting,
  onClose,
  nameRef,
}: IngredientFormProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const categories = useCategories();
  const create = useCreateIngredient();
  const update = useUpdateIngredient(ingredient?.id ?? '');
  const mutation = ingredient ? update : create;

  const [initial] = useState<FormValues>(() =>
    ingredient ? valuesFromIngredient(ingredient, language) : emptyValues(initialName, language),
  );
  const [values, setValues] = useState(initial);
  const [proposed, setProposed] = useState<Proposed | null>(null);
  const [invalid, setInvalid] = useState<Set<string>>(new Set());
  const [refused, setRefused] = useState<Refused | null>(null);
  const [searching, setSearching] = useState(false);
  const [scanning, setScanning] = useState(false);
  const lookup = useBarcodeLookup();
  // The last scanned barcode that no ingredient has: while it is in the field, the similar hint
  // can attach it to a match without one (BAR-03).
  const [scanned, setScanned] = useState<string | null>(null);

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
  const scanNotice = scanNoticeState(lookup, ingredient);
  const attachBarcode = !ingredient && scanned !== null && barcode === scanned ? scanned : null;

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

  /**
   * Fills the form with a product (BAR-03, BAR-11). Where it has no value, what the user typed
   * stays, but not the texts and nutrients of a product chosen before.
   */
  function fill(proposal: OffProposal) {
    const prefilled: Prefill = { barcode: proposal.barcode, proposal };
    const earlier = proposed?.values;
    setValues((current) =>
      valuesFromPrefill(prefilled, earlier ? typedValues(current, earlier) : current, language),
    );
    setProposed({ prefill: prefilled, values: proposalValues(prefilled, language) });
    setInvalid(new Set());
    create.reset();
  }

  function choose(proposal: OffProposal) {
    lookup.reset();
    fill(proposal);
  }

  /** Looks a scanned barcode up: our own ingredients first, then (not when editing) OFF. */
  function lookUp(code: string) {
    lookup.mutate(
      { barcode: code, ownOnly: ingredient !== undefined },
      {
        onSuccess: (result) => {
          if (result.found_in === 'db') {
            // Another ingredient's barcode is only named; the ingredient's own is filled in.
            if (ingredient && result.ingredient?.id === ingredient.id) {
              set('barcode', result.barcode);
            }
            return;
          }
          if (result.proposal && !ingredient) fill(result.proposal);
          else set('barcode', result.barcode);
          setScanned(result.barcode);
        },
        onError: (error) => {
          // Open Food Facts couldn't answer: the barcode is filled in, to try again or type the
          // values.
          if (ingredient || !isOffSlow(error)) return;
          set('barcode', code);
          setScanned(code);
        },
      },
    );
  }

  const lookUpInitialScan = useEffectEvent(() => {
    if (initialScan !== undefined) lookUp(initialScan);
  });
  // Once, also where development mode runs effects twice: a lookup may ask Open Food Facts.
  const lookedUpInitialScan = useRef(false);
  useEffect(() => {
    if (lookedUpInitialScan.current) return;
    lookedUpInitialScan.current = true;
    lookUpInitialScan();
  }, []);

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
                {!ingredient && (
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
              onChange={(event) => {
                // A barcode typed in is no scan: the scan's notice no longer applies.
                lookup.reset();
                set('barcode', event.target.value);
              }}
            />
          )}
        </FormField>
        {/* The barcode's message line for the scan. Without a notice it takes back the form's
            gap above it, as the similar hint does. */}
        <div aria-live="polite" className="empty:-mt-4">
          {scanNotice && (
            <ScanNotice
              state={scanNotice}
              onRetry={lookUp}
              onPickExisting={onPickExisting && pickExisting}
              onNavigate={onClose}
            />
          )}
        </div>
        <SimilarHint
          name={values.name}
          ingredient={ingredient}
          attachBarcode={attachBarcode}
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
          <BarcodeScanDialog open onOpenChange={setScanning} onBarcode={lookUp} />
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

/** The scan's notice, from the lookup's state; none when it filled the form or nothing ran. */
function scanNoticeState(
  lookup: ReturnType<typeof useBarcodeLookup>,
  edited: Ingredient | undefined,
): ScanNoticeState | null {
  const barcode = lookup.variables?.barcode ?? '';
  if (lookup.isPending) return { kind: 'lookingUp', barcode };
  if (lookup.isError) {
    if (fieldErrorCodes(lookup.error).barcode !== undefined) return { kind: 'invalid', barcode };
    if (!edited && isOffSlow(lookup.error)) return { kind: 'slow', barcode };
    return { kind: 'failed', error: lookup.error };
  }
  const result = lookup.data;
  if (!result) return null;
  if (result.found_in === 'db') {
    const owner = result.ingredient;
    return owner && owner.id !== edited?.id ? { kind: 'known', ingredient: owner } : null;
  }
  // When editing, the barcode is only filled in.
  if (edited) return null;
  if (result.off_unavailable) return { kind: 'slow', barcode: result.barcode };
  return result.found_in === 'none' ? { kind: 'notFound' } : null;
}

interface ScanNoticeProps {
  state: ScanNoticeState;
  /** Looks the barcode up again. */
  onRetry: (barcode: string) => void;
  /** Given in the picker: "use" takes the ingredient the barcode belongs to. */
  onPickExisting?: (ingredient: IngredientSummary) => void;
  /** Called before "open" leaves to the ingredient the barcode belongs to. */
  onNavigate: () => void;
}

/**
 * What a scan found, below the barcode (BAR-02, BAR-03): "Already belongs to Milch" with "open"
 * (or "use" in the picker), "Not at Open Food Facts", "Open Food Facts is slow" with "Try
 * again", or an invalid barcode.
 */
function ScanNotice({ state, onRetry, onPickExisting, onNavigate }: ScanNoticeProps) {
  const { t } = useTranslation();
  const textId = useId();
  if (state.kind === 'failed') return <ErrorAlert error={state.error} />;

  let text: string;
  let action: ReactNode = null;
  switch (state.kind) {
    case 'lookingUp':
      text = t('scanner.lookingUp', { barcode: state.barcode });
      break;
    case 'invalid':
      text = t('scanner.invalidBarcode', { barcode: state.barcode });
      break;
    case 'notFound':
      text = t('ingredients.scan.notFound');
      break;
    case 'slow':
      text = t('ingredients.scan.slow');
      action = (
        <Button
          type="button"
          size="compact"
          variant="outline"
          aria-describedby={textId}
          data-testid={testIds.ingredientScanRetry}
          onClick={() => onRetry(state.barcode)}
        >
          <RotateCcw aria-hidden="true" />
          {t('ingredients.scan.retry')}
        </Button>
      );
      break;
    case 'known': {
      const owner = state.ingredient;
      text = t('ingredients.scan.known', { name: ingredientLabel(owner.name, owner.brand) });
      action = onPickExisting ? (
        <Button
          type="button"
          size="compact"
          variant="outline"
          aria-describedby={textId}
          data-testid={testIds.ingredientScanTake}
          onClick={() => onPickExisting(toSummary(owner))}
        >
          {t('ingredients.scan.take')}
        </Button>
      ) : (
        <Link
          to={`/ingredients/${owner.id}`}
          aria-describedby={textId}
          data-testid={testIds.ingredientScanOpen}
          onClick={onNavigate}
          className={INLINE_LINK}
        >
          {t('ingredients.scan.open')}
        </Link>
      );
      break;
    }
  }

  return (
    <div
      data-testid={testIds.ingredientScanNotice}
      className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"
    >
      <p
        id={textId}
        className={cn(
          'flex items-start gap-1.5',
          state.kind === 'invalid' && 'font-medium text-destructive',
        )}
      >
        {state.kind !== 'lookingUp' && (
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        )}
        {text}
      </p>
      {action}
    </div>
  );
}

interface SimilarHintProps {
  name: string;
  ingredient?: Ingredient;
  /** A scanned barcode no ingredient has, while it is in the field (BAR-03). */
  attachBarcode: string | null;
  onPickExisting?: (ingredient: IngredientSummary) => void;
  onNavigate: () => void;
}

/**
 * ING-03: "Similar ingredients already exist", with links to them (or buttons in the picker). A
 * hint only: two brands of the same thing are different ingredients. After a scan, a match
 * without a barcode can get the scanned one (BAR-03): "Use Milch" in the picker gives it the
 * barcode before taking it, "Add the barcode to Milch" elsewhere before opening it. A match that
 * has a barcode is another package, so it is offered as it is (D-21).
 */
function SimilarHint({
  name,
  ingredient,
  attachBarcode,
  onPickExisting,
  onNavigate,
}: SimilarHintProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const link = useLinkBarcode();
  const debounced = useDebouncedValue(name.trim());
  // Editing without renaming needs no hint.
  const query = ingredient && debounced === ingredient.name ? '' : debounced;
  const similar = useSimilarIngredients(query);
  const matches = query ? (similar.data ?? []).filter((match) => match.id !== ingredient?.id) : [];

  function attach(match: IngredientSummary, barcode: string) {
    link.mutate(
      { id: match.id, barcode },
      {
        onSuccess: (linked) => {
          if (onPickExisting) {
            onPickExisting(toSummary(linked));
            return;
          }
          onNavigate();
          void navigate(`/ingredients/${linked.id}`);
        },
      },
    );
  }

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
              // A match with a barcode of its own is another package (D-21).
              const toAttach = match.barcode ? null : attachBarcode;
              return (
                <li key={match.id}>
                  {onPickExisting ? (
                    <Button
                      type="button"
                      size="compact"
                      variant="outline"
                      disabled={link.isPending}
                      onClick={() =>
                        toAttach === null ? onPickExisting(match) : attach(match, toAttach)
                      }
                    >
                      {t('ingredients.similar.use', { name: label })}
                    </Button>
                  ) : toAttach !== null ? (
                    <Button
                      type="button"
                      size="compact"
                      variant="outline"
                      disabled={link.isPending}
                      onClick={() => attach(match, toAttach)}
                    >
                      {t('ingredients.similar.attach', { name: label })}
                    </Button>
                  ) : (
                    <Link
                      to={`/ingredients/${match.id}`}
                      onClick={onNavigate}
                      className={INLINE_LINK}
                    >
                      {label}
                    </Link>
                  )}
                </li>
              );
            })}
          </ul>
          <ErrorAlert error={link.error} />
        </div>
      )}
    </div>
  );
}
