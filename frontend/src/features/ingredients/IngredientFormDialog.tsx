import { ScanBarcode, Search } from 'lucide-react';
import { lazy, Suspense, useId, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { isApiError } from '@/api/errors';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { useCategories, useUnits, type Unit } from '@/features/reference/api';
import { categoryName, unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { fieldErrorMessagesByPath, needsErrorAlert } from '@/i18n/errors';
import { useDebouncedValue } from '@/lib/useDebouncedValue';
import { testIds } from '@/testIds';
import {
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
} from './api';
import {
  BRAND_MAX_LENGTH,
  editedFields,
  emptyValues,
  NAME_MAX_LENGTH,
  NUMBER_FIELDS,
  proposalValues,
  QUANTITY_TEXT_MAX_LENGTH,
  valuesFromIngredient,
  valuesFromPrefill,
  type FormValues,
  type NumberField,
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

// The scanner and its decoder are a chunk of their own (PERF-03), loaded when the field's "Scan"
// is tapped.
const BarcodeScanDialog = lazy(() =>
  import('@/features/scanner/BarcodeScanDialog').then((module) => ({
    default: module.BarcodeScanDialog,
  })),
);

const BASE_UNITS: readonly BaseUnit[] = ['g', 'ml', 'piece'];
const PACK_FIELDS = ['quantity_text', 'pack_quantity', 'pack_unit'] as const;
/** The paths whose server errors are shown next to an input; others go to the alert. */
const SHOWN_FIELDS: ReadonlySet<string> = new Set([
  'name',
  'brand',
  'category_id',
  'base_unit',
  'barcode',
  ...NUMBER_FIELDS,
  ...PACK_FIELDS,
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

/** Creates or edits an ingredient (ING-01/02, NUT-02) in a dialog. */
export function IngredientFormDialog({ open, onOpenChange, ...props }: IngredientFormDialogProps) {
  const { t } = useTranslation();
  const { ingredient } = props;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {ingredient
              ? t('ingredients.form.editTitle', {
                  name: ingredientLabel(ingredient.name, ingredient.brand),
                })
              : t('ingredients.form.createTitle')}
          </DialogTitle>
          <DialogDescription>{t('ingredients.form.text')}</DialogDescription>
        </DialogHeader>
        {/* Mounted only while open, so every opening starts from the current values. */}
        {open && <IngredientForm {...props} onClose={() => onOpenChange(false)} />}
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
  /** More actions below the save button, e.g. the scan flow's "already in MealMate". */
  children?: ReactNode;
}

/** The Open Food Facts proposal and its own values, to tell which ones the user changed. */
interface Proposed {
  prefill: Prefill;
  /** `proposalValues`: without what the form kept because the proposal lacks it. */
  values: FormValues;
}

/**
 * One form for every ingredient, new or existing, typed by hand or from Open Food Facts: name,
 * brand, category, base unit (g, ml or pieces), piece weight, density (not for pieces),
 * nutrition per 100 g/ml, barcode (with a scan button) and package details under "More". A new
 * ingredient can be filled from an Open Food Facts search by name; its values are then saved in
 * one request with the fields the user changed named as edited (BAR-04).
 */
export function IngredientForm({
  ingredient,
  initialName = '',
  prefill,
  onSaved,
  onPickExisting,
  onClose,
  children,
}: IngredientFormProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const categories = useCategories();
  const units = useUnits();
  const create = useCreateIngredient();
  const update = useUpdateIngredient(ingredient?.id ?? '');
  const mutation = ingredient ? update : create;
  const baseUnitId = useId();

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
  const [searching, setSearching] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [moreOpen, setMoreOpen] = useState(
    () => initial.quantity_text !== '' || initial.pack_quantity !== '',
  );

  const defaultCategory =
    categories.data?.find((category) => category.key === values.categoryKey) ??
    categories.data?.find((category) => category.key === 'other');
  const selectedCategory = values.categoryId ?? defaultCategory?.id ?? '';
  const serverFields = fieldErrorMessagesByPath(t, mutation.error);
  const barcodeTaken =
    isApiError(mutation.error) && mutation.error.code === 'ingredient.barcode_taken';
  const showAlert = !barcodeTaken && needsErrorAlert(serverFields, SHOWN_FIELDS);
  // A proposal belongs to its barcode: a scanned or chosen product keeps it.
  const barcodeFixed = proposed !== null;
  const fromOff = proposed !== null || ingredient?.source === 'off';
  const edited = new Set<string>(ingredient?.source === 'off' ? ingredient.user_edited_fields : []);
  const moreErrors = PACK_FIELDS.some((field) => fieldError(field) !== undefined);

  function set<K extends keyof FormValues>(field: K, value: FormValues[K]) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  /**
   * Leaving Stück clears its piece weight, as the server does (ING-02); grams and millilitres
   * get back the piece weight the ingredient has.
   */
  function chooseBaseUnit(unit: BaseUnit) {
    setValues((current) => {
      const leavingPieces = current.baseUnit === 'piece' && unit !== 'piece';
      const ownPieceWeight = initial.baseUnit === 'piece' ? '' : initial.piece_weight_g;
      return {
        ...current,
        baseUnit: unit,
        piece_weight_g: leavingPieces ? ownPieceWeight : current.piece_weight_g,
      };
    });
  }

  function fieldError(path: string): string | undefined {
    if (invalid.has(path)) return t('error.field.invalid_format');
    return serverFields[path];
  }

  /** A mark for an Open Food Facts field a user changed: updates from there keep it (BAR-05). */
  function editedHint(field: EditedField): string | undefined {
    return edited.has(field) ? t('ingredients.form.userEdited') : undefined;
  }

  /** The piece weight's field: for pieces with a label of its own and no hint (ING-02). */
  function pieceWeightField(label: string, hint?: string) {
    return (
      <FormField label={label} hint={hint} error={fieldError('piece_weight_g')}>
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
    );
  }

  function choose(proposal: OffProposal) {
    const prefilled: Prefill = { barcode: proposal.barcode, proposal };
    const next = valuesFromPrefill(prefilled, values, language);
    setValues(next);
    setProposed({ prefill: prefilled, values: proposalValues(prefilled, language) });
    setMoreOpen(next.quantity_text !== '' || next.pack_quantity !== '');
    setInvalid(new Set());
    create.reset();
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Submit events of the dialogs opened from here (the Open Food Facts search, the barcode
    // input) bubble up through the React tree; only this form's own submit saves.
    if (event.target !== event.currentTarget) return;
    const problems = new Set<string>();
    // A density means nothing for pieces: its field is hidden then, and left as it is.
    const numberFields: readonly NumberField[] =
      values.baseUnit === 'piece' ? ['piece_weight_g'] : NUMBER_FIELDS;
    const numbers = {} as Record<NumberField | 'pack_quantity', number | null>;
    for (const field of [...numberFields, 'pack_quantity'] as const) {
      const parsed = parseOptionalAmount(values[field]);
      if (parsed.ok) numbers[field] = parsed.value;
      else problems.add(field);
    }
    const nutrients = {} as Record<NutrientKey, number | null>;
    for (const key of NUTRIENT_KEYS) {
      const parsed = parseOptionalAmount(values.nutrients[key]);
      if (parsed.ok) nutrients[key] = parsed.value;
      else problems.add(`nutrients.${key}`);
    }
    setInvalid(problems);
    if (problems.has('pack_quantity')) setMoreOpen(true);
    if (problems.size > 0) return;

    const saved = (result: Ingredient) => {
      onClose();
      onSaved?.(result);
    };
    const texts = {
      name: values.name.trim(),
      brand: values.brand.trim() || null,
      barcode: values.barcode.replace(/\s+/g, '') || null,
      quantity_text: values.quantity_text.trim() || null,
    };
    const packUnit: Unit | null = values.pack_unit === '' ? null : values.pack_unit;

    if (!ingredient) {
      const body: IngredientCreate = { name: texts.name, base_unit: values.baseUnit };
      if (selectedCategory) body.category_id = selectedCategory;
      if (texts.brand !== null) body.brand = texts.brand;
      if (texts.barcode !== null) body.barcode = texts.barcode;
      if (texts.quantity_text !== null) body.quantity_text = texts.quantity_text;
      if (numbers.pack_quantity !== null) body.pack_quantity = numbers.pack_quantity;
      if (packUnit !== null) body.pack_unit = packUnit;
      for (const field of numberFields) {
        const value = numbers[field];
        if (value !== null) body[field] = value;
      }
      const given: Partial<NutrientValues> = {};
      for (const key of NUTRIENT_KEYS) {
        if (nutrients[key] !== null) given[key] = nutrients[key];
      }
      if (Object.keys(given).length > 0) body.nutrients = given;
      if (proposed?.prefill.proposal) {
        // Saved with its Open Food Facts origin; only the corrected values count as edited.
        body.off = {
          off_last_modified_at: proposed.prefill.proposal.off_last_modified_at,
          edited_fields: editedFields(values, proposed.values),
        };
      }
      create.mutate(body, { onSuccess: saved });
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
    if (texts.quantity_text !== ingredient.quantity_text) body.quantity_text = texts.quantity_text;
    if (packUnit !== ingredient.pack_unit) body.pack_unit = packUnit;
    // A number field counts as changed when its text changed: a stored value with more decimals
    // than shown would otherwise be cut on every save.
    for (const field of [...numberFields, 'pack_quantity'] as const) {
      if (values[field].trim() !== initial[field]) body[field] = numbers[field];
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
    update.mutate(body, { onSuccess: saved });
  }

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      data-testid={testIds.ingredientForm}
      className="flex flex-col gap-4"
    >
      {fromOff && <OffAttribution />}
      <FormField label={t('ingredients.field.name')} error={fieldError('name')}>
        {(control) => (
          <Input
            {...control}
            name="name"
            autoComplete="off"
            required
            maxLength={NAME_MAX_LENGTH}
            value={values.name}
            onChange={(event) => set('name', event.target.value)}
          />
        )}
      </FormField>
      {!ingredient && !prefill && (
        <Button
          type="button"
          variant="outline"
          className="self-start"
          data-testid={testIds.offSearchButton}
          onClick={() => setSearching(true)}
        >
          <Search aria-hidden="true" />
          {t('ingredients.offSearch.open')}
        </Button>
      )}
      <SimilarHint
        name={values.name}
        ingredient={ingredient}
        onPickExisting={
          onPickExisting &&
          ((match) => {
            onClose();
            onPickExisting(match);
          })
        }
        onNavigate={onClose}
      />
      <FormField
        label={t('ingredients.field.brand')}
        hint={editedHint('brand') ?? t('ingredients.field.brandHint')}
        error={fieldError('brand')}
      >
        {(control) => (
          <Input
            {...control}
            name="brand"
            autoComplete="off"
            maxLength={BRAND_MAX_LENGTH}
            value={values.brand}
            onChange={(event) => set('brand', event.target.value)}
          />
        )}
      </FormField>
      <FormField label={t('ingredients.field.category')} error={fieldError('category_id')}>
        {(control) => (
          <NativeSelect
            {...control}
            name="category_id"
            value={selectedCategory}
            disabled={!categories.data}
            onChange={(event) => set('categoryId', event.target.value)}
          >
            {categories.data?.map((category) => (
              <NativeSelectOption key={category.id} value={category.id}>
                {categoryName(t, category.key)}
              </NativeSelectOption>
            ))}
          </NativeSelect>
        )}
      </FormField>
      <ErrorAlert error={categories.error} />
      <fieldset className="flex flex-col gap-2" aria-describedby={`${baseUnitId}-hint`}>
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
                onChange={() => chooseBaseUnit(unit)}
                className="size-5 accent-primary"
              />
              {t(`ingredients.baseUnit.${unit}`)}
            </label>
          ))}
        </div>
        <p id={`${baseUnitId}-hint`} className="text-sm text-muted-foreground">
          {ingredient
            ? t('ingredients.field.baseUnitEditHint')
            : t('ingredients.field.baseUnitHint')}
        </p>
        {serverFields.base_unit && (
          <p className="text-sm font-medium text-destructive">{serverFields.base_unit}</p>
        )}
      </fieldset>
      {values.baseUnit === 'piece' ? (
        pieceWeightField(t('ingredients.field.weightPerPiece'))
      ) : (
        <>
          {pieceWeightField(
            t('ingredients.field.pieceWeight'),
            t('ingredients.field.pieceWeightHint'),
          )}
          <FormField
            label={t('ingredients.field.density')}
            hint={t('ingredients.field.densityHint')}
            error={fieldError('density_g_per_ml')}
          >
            {(control) => (
              <Input
                {...control}
                name="density_g_per_ml"
                inputMode="decimal"
                autoComplete="off"
                value={values.density_g_per_ml}
                onChange={(event) => set('density_g_per_ml', event.target.value)}
              />
            )}
          </FormField>
        </>
      )}
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 font-semibold">
          {t('ingredients.form.nutritionTitle', {
            unit: unitLabel(t, nutritionUnit(values.baseUnit)),
          })}
        </legend>
        <p className="text-sm text-muted-foreground">{t('ingredients.form.nutritionHint')}</p>
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
      <div className="flex flex-col gap-2">
        <FormField
          label={t('ingredients.field.barcode')}
          hint={t(
            barcodeFixed
              ? 'ingredients.field.barcodeFixed'
              : ingredient?.source === 'off'
                ? 'ingredients.field.barcodeOffHint'
                : 'ingredients.field.barcodeHint',
          )}
          error={barcodeTaken ? t('error.ingredient.barcode_taken') : fieldError('barcode')}
        >
          {(control) => (
            <Input
              {...control}
              name="barcode"
              inputMode="numeric"
              autoComplete="off"
              maxLength={20}
              readOnly={barcodeFixed}
              value={values.barcode}
              onChange={(event) => set('barcode', event.target.value)}
            />
          )}
        </FormField>
        {!barcodeFixed && (
          <Button
            type="button"
            variant="outline"
            className="self-start"
            data-testid={testIds.barcodeFieldScan}
            onClick={() => setScanning(true)}
          >
            <ScanBarcode aria-hidden="true" />
            {t('ingredients.field.barcodeScan')}
          </Button>
        )}
      </div>
      <details
        open={moreOpen || moreErrors}
        onToggle={(event) => setMoreOpen(event.currentTarget.open)}
        className="rounded-lg border px-3"
      >
        <summary className="flex min-h-(--tap-target) cursor-pointer items-center font-medium outline-none focus-visible:ring-[3px] focus-visible:ring-ring">
          {t('ingredients.form.more')}
        </summary>
        <div className="flex flex-col gap-4 pb-3">
          <FormField
            label={t('ingredients.field.quantityText')}
            hint={editedHint('quantity_text') ?? t('ingredients.field.quantityTextHint')}
            error={fieldError('quantity_text')}
          >
            {(control) => (
              <Input
                {...control}
                name="quantity_text"
                autoComplete="off"
                maxLength={QUANTITY_TEXT_MAX_LENGTH}
                value={values.quantity_text}
                onChange={(event) => set('quantity_text', event.target.value)}
              />
            )}
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField
              label={t('ingredients.field.packQuantity')}
              hint={editedHint('pack_quantity')}
              error={fieldError('pack_quantity')}
            >
              {(control) => (
                <Input
                  {...control}
                  name="pack_quantity"
                  inputMode="decimal"
                  autoComplete="off"
                  value={values.pack_quantity}
                  onChange={(event) => set('pack_quantity', event.target.value)}
                />
              )}
            </FormField>
            <FormField
              label={t('ingredients.field.packUnit')}
              hint={editedHint('pack_unit')}
              error={fieldError('pack_unit')}
            >
              {(control) => (
                <NativeSelect
                  {...control}
                  name="pack_unit"
                  value={values.pack_unit}
                  disabled={!units.data}
                  onChange={(event) => set('pack_unit', event.target.value as Unit | '')}
                >
                  <NativeSelectOption value="">
                    {t('ingredients.field.packUnitNone')}
                  </NativeSelectOption>
                  {units.data?.map(({ unit }) => (
                    <NativeSelectOption key={unit} value={unit}>
                      {unitLabel(t, unit)}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              )}
            </FormField>
          </div>
          <ErrorAlert error={units.error} />
        </div>
      </details>
      {showAlert && <ErrorAlert error={mutation.error} />}
      <DialogFooter>
        <Button type="submit" disabled={mutation.isPending || values.name.trim() === ''}>
          {t('common.save')}
        </Button>
      </DialogFooter>
      {children}
      {searching && (
        <OffSearchDialog
          open
          onOpenChange={setSearching}
          initialQuery={values.name.trim()}
          onChoose={choose}
          onPickExisting={
            onPickExisting &&
            ((match) => {
              onClose();
              onPickExisting(match);
            })
          }
          onNavigate={onClose}
        />
      )}
      {scanning && (
        <Suspense fallback={null}>
          <BarcodeScanDialog
            open
            onOpenChange={setScanning}
            onBarcode={(barcode) => set('barcode', barcode)}
          />
        </Suspense>
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
    <div aria-live="polite">
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
