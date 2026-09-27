import { useId, useState, type FormEvent } from 'react';
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
import { useCategories } from '@/features/reference/api';
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
  type Ingredient,
  type IngredientCreate,
  type IngredientSummary,
  type IngredientUpdate,
  type NutrientValues,
} from './api';
import {
  NUTRIENT_KEYS,
  nutrientLabel,
  numberInputValue,
  parseOptionalAmount,
  type NutrientKey,
} from './nutrients';

const BASE_UNITS: readonly BaseUnit[] = ['g', 'ml'];
const NUMBER_FIELDS = ['piece_weight_g', 'density_g_per_ml'] as const;
type NumberField = (typeof NUMBER_FIELDS)[number];
/** The paths whose server errors are shown next to an input; others go to the alert. */
const SHOWN_FIELDS: ReadonlySet<string> = new Set([
  'name',
  'category_id',
  'base_unit',
  ...NUMBER_FIELDS,
  ...NUTRIENT_KEYS.map((key) => `manual.${key}`),
]);

interface IngredientFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Edit this ingredient; without it the dialog creates a new one. */
  ingredient?: Ingredient;
  /** Prefills the name of a new ingredient (e.g. from a search). */
  initialName?: string;
  /** Preselects the category of a new ingredient by key (e.g. guessed from a scanned product). */
  initialCategoryKey?: string | null;
  /** Preselects the base unit of a new ingredient (default g). */
  initialBaseUnit?: BaseUnit;
  /** Called with the saved ingredient; the dialog closes itself. */
  onSaved?: (ingredient: Ingredient) => void;
  /**
   * When given, the "similar ingredient exists" hint offers to use a match instead of linking to
   * it (the ingredient picker).
   */
  onPickExisting?: (ingredient: IngredientSummary) => void;
}

/** Creates or edits an ingredient (ING-01/02, NUT-02): name, category, units, manual nutrition. */
export function IngredientFormDialog({ open, onOpenChange, ...props }: IngredientFormDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {props.ingredient
              ? t('ingredients.form.editTitle', { name: props.ingredient.name })
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

type FormProps = Omit<IngredientFormDialogProps, 'open' | 'onOpenChange'> & {
  onClose: () => void;
};

function IngredientForm({
  ingredient,
  initialName = '',
  initialCategoryKey,
  initialBaseUnit = 'g',
  onSaved,
  onPickExisting,
  onClose,
}: FormProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const categories = useCategories();
  const create = useCreateIngredient();
  const update = useUpdateIngredient(ingredient?.id ?? '');
  const mutation = ingredient ? update : create;
  const baseUnitId = useId();

  const [name, setName] = useState(ingredient?.name ?? initialName);
  const [categoryId, setCategoryId] = useState<string | null>(ingredient?.category_id ?? null);
  const [baseUnit, setBaseUnit] = useState<BaseUnit>(ingredient?.base_unit ?? initialBaseUnit);
  // The number fields as the form opened with them. Only fields whose text was changed are
  // sent: a stored value with more decimals than shown would otherwise be cut on every save.
  const [initialNumbers] = useState<Record<NumberField, string>>(() => ({
    piece_weight_g: numberInputValue(ingredient?.piece_weight_g, language),
    density_g_per_ml: numberInputValue(ingredient?.density_g_per_ml, language),
  }));
  const [initialManual] = useState(
    () =>
      Object.fromEntries(
        NUTRIENT_KEYS.map((key) => [key, numberInputValue(ingredient?.manual[key], language)]),
      ) as Record<NutrientKey, string>,
  );
  const [numbers, setNumbers] = useState(initialNumbers);
  const [manual, setManual] = useState(initialManual);
  const [invalid, setInvalid] = useState<Set<string>>(new Set());

  const defaultCategory =
    categories.data?.find((category) => category.key === initialCategoryKey) ??
    categories.data?.find((category) => category.key === 'other');
  const selectedCategory = categoryId ?? defaultCategory?.id ?? '';
  const baseUnitLocked = (ingredient?.product_count ?? 0) > 0;
  const serverFields = fieldErrorMessagesByPath(t, mutation.error);
  const lockedError =
    isApiError(mutation.error) && mutation.error.code === 'ingredient.base_unit_locked';
  const showAlert = !lockedError && needsErrorAlert(serverFields, SHOWN_FIELDS);

  function fieldError(path: string): string | undefined {
    if (invalid.has(path)) return t('error.field.invalid_format');
    return serverFields[path];
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const problems = new Set<string>();
    const parsedNumbers = {} as Record<NumberField, number | null>;
    for (const field of NUMBER_FIELDS) {
      const parsed = parseOptionalAmount(numbers[field]);
      if (parsed.ok) parsedNumbers[field] = parsed.value;
      else problems.add(field);
    }
    const parsedManual = {} as Record<NutrientKey, number | null>;
    for (const key of NUTRIENT_KEYS) {
      const parsed = parseOptionalAmount(manual[key]);
      if (parsed.ok) parsedManual[key] = parsed.value;
      else problems.add(`manual.${key}`);
    }
    setInvalid(problems);
    if (problems.size > 0) return;

    const saved = (result: Ingredient) => {
      onClose();
      onSaved?.(result);
    };
    const trimmed = name.trim();

    if (!ingredient) {
      const body: IngredientCreate = { name: trimmed, base_unit: baseUnit };
      if (selectedCategory) body.category_id = selectedCategory;
      for (const field of NUMBER_FIELDS) {
        const value = parsedNumbers[field];
        if (value !== null) body[field] = value;
      }
      const values: Partial<NutrientValues> = {};
      for (const key of NUTRIENT_KEYS) {
        if (parsedManual[key] !== null) values[key] = parsedManual[key];
      }
      if (Object.keys(values).length > 0) body.manual = values;
      create.mutate(body, { onSuccess: saved });
      return;
    }

    // Only what changed is sent, so a concurrent edit of another field isn't overwritten.
    const body: IngredientUpdate = {};
    if (trimmed !== ingredient.name) body.name = trimmed;
    if (selectedCategory !== ingredient.category_id) body.category_id = selectedCategory;
    if (baseUnit !== ingredient.base_unit) body.base_unit = baseUnit;
    for (const field of NUMBER_FIELDS) {
      if (numbers[field].trim() !== initialNumbers[field]) body[field] = parsedNumbers[field];
    }
    const changedManual: Partial<NutrientValues> = {};
    for (const key of NUTRIENT_KEYS) {
      if (manual[key].trim() !== initialManual[key]) changedManual[key] = parsedManual[key];
    }
    if (Object.keys(changedManual).length > 0) body.manual = changedManual;
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
      <FormField label={t('ingredients.field.name')} error={fieldError('name')}>
        {(control) => (
          <Input
            {...control}
            name="name"
            autoComplete="off"
            required
            maxLength={60}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        )}
      </FormField>
      <SimilarHint
        name={name}
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
      <FormField label={t('ingredients.field.category')} error={fieldError('category_id')}>
        {(control) => (
          <NativeSelect
            {...control}
            name="category_id"
            value={selectedCategory}
            disabled={!categories.data}
            onChange={(event) => setCategoryId(event.target.value)}
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
      <fieldset
        className="flex flex-col gap-2"
        aria-describedby={`${baseUnitId}-hint`}
        disabled={baseUnitLocked}
      >
        <legend className="mb-2 text-sm leading-none font-medium">
          {t('ingredients.field.baseUnit')}
        </legend>
        <div className="flex flex-wrap gap-2">
          {BASE_UNITS.map((unit) => (
            <label
              key={unit}
              className="flex min-h-(--tap-target) flex-1 items-center gap-3 rounded-md border px-3 has-checked:border-primary has-checked:font-semibold has-disabled:opacity-60"
            >
              <input
                type="radio"
                name="base_unit"
                value={unit}
                checked={baseUnit === unit}
                onChange={() => setBaseUnit(unit)}
                className="size-5 accent-primary"
              />
              {t(`ingredients.baseUnit.${unit}`)}
            </label>
          ))}
        </div>
        <p id={`${baseUnitId}-hint`} className="text-sm text-muted-foreground">
          {baseUnitLocked
            ? t('ingredients.field.baseUnitLocked')
            : t('ingredients.field.baseUnitHint')}
        </p>
        {(lockedError || serverFields.base_unit) && (
          <p className="text-sm font-medium text-destructive">
            {lockedError ? t('error.ingredient.base_unit_locked') : serverFields.base_unit}
          </p>
        )}
      </fieldset>
      <FormField
        label={t('ingredients.field.pieceWeight')}
        hint={t('ingredients.field.pieceWeightHint')}
        error={fieldError('piece_weight_g')}
      >
        {(control) => (
          <Input
            {...control}
            name="piece_weight_g"
            inputMode="decimal"
            autoComplete="off"
            value={numbers.piece_weight_g}
            onChange={(event) =>
              setNumbers((current) => ({ ...current, piece_weight_g: event.target.value }))
            }
          />
        )}
      </FormField>
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
            value={numbers.density_g_per_ml}
            onChange={(event) =>
              setNumbers((current) => ({ ...current, density_g_per_ml: event.target.value }))
            }
          />
        )}
      </FormField>
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 font-semibold">
          {t('ingredients.form.nutritionTitle', { unit: unitLabel(t, baseUnit) })}
        </legend>
        <p className="text-sm text-muted-foreground">{t('ingredients.form.nutritionHint')}</p>
        <div className="grid grid-cols-2 gap-3">
          {NUTRIENT_KEYS.map((key) => (
            <FormField key={key} label={nutrientLabel(t, key)} error={fieldError(`manual.${key}`)}>
              {(control) => (
                <Input
                  {...control}
                  name={`manual.${key}`}
                  inputMode="decimal"
                  autoComplete="off"
                  value={manual[key]}
                  onChange={(event) =>
                    setManual((current) => ({ ...current, [key]: event.target.value }))
                  }
                />
              )}
            </FormField>
          ))}
        </div>
      </fieldset>
      {showAlert && <ErrorAlert error={mutation.error} />}
      <DialogFooter>
        <Button type="submit" disabled={mutation.isPending || name.trim() === ''}>
          {ingredient ? t('common.save') : t('ingredients.form.create')}
        </Button>
      </DialogFooter>
    </form>
  );
}

interface SimilarHintProps {
  name: string;
  ingredient?: Ingredient;
  onPickExisting?: (ingredient: IngredientSummary) => void;
  onNavigate: () => void;
}

/** ING-03: "Similar ingredients already exist", with links to them (or buttons in the picker). */
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
            {matches.map((match) => (
              <li key={match.id}>
                {onPickExisting ? (
                  <Button
                    type="button"
                    size="compact"
                    variant="outline"
                    onClick={() => onPickExisting(match)}
                  >
                    {t('ingredients.similar.use', { name: match.name })}
                  </Button>
                ) : (
                  <Link
                    to={`/ingredients/${match.id}`}
                    onClick={onNavigate}
                    className="inline-flex min-h-(--tap-target) items-center rounded-md px-2 font-medium text-primary underline underline-offset-4"
                  >
                    {match.name}
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
