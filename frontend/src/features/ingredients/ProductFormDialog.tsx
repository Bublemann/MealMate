import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
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
import { useUnits, type Unit } from '@/features/reference/api';
import { unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { fieldErrorMessagesByPath, needsErrorAlert } from '@/i18n/errors';
import { testIds } from '@/testIds';
import {
  useCreateProduct,
  useUpdateProduct,
  type Ingredient,
  type NutrientValues,
  type Product,
  type ProductCreate,
  type ProductUpdate,
} from './api';
import {
  NUTRIENT_KEYS,
  nutrientLabel,
  numberInputValue,
  parseOptionalAmount,
  type NutrientKey,
} from './nutrients';

const TEXT_FIELDS = ['name', 'brand', 'quantity_text'] as const;
type TextField = (typeof TEXT_FIELDS)[number];
const TEXT_LIMITS: Record<TextField, number> = { name: 120, brand: 80, quantity_text: 40 };
const TEXT_LABELS = {
  name: 'ingredients.product.name',
  brand: 'ingredients.product.brand',
  quantity_text: 'ingredients.product.quantityText',
} as const;
/**
 * The paths whose server errors are shown next to an input; others (`ingredient_id`,
 * `nutrition_basis`) go to the alert.
 */
const SHOWN_FIELDS: ReadonlySet<string> = new Set([
  'barcode',
  ...TEXT_FIELDS,
  'pack_quantity',
  'pack_unit',
  ...NUTRIENT_KEYS.map((key) => `nutrients.${key}`),
]);

interface ProductFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ingredient: Ingredient;
  /** Edit this product; without it the dialog adds a new one to `ingredient`. */
  product?: Product;
}

/** Adds a product by hand or edits one (ING-04); its values are per 100 g/ml of the base unit. */
export function ProductFormDialog({ open, onOpenChange, ...props }: ProductFormDialogProps) {
  const { t } = useTranslation();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {props.product
              ? t('ingredients.product.editTitle')
              : t('ingredients.product.createTitle')}
          </DialogTitle>
          <DialogDescription>
            {t('ingredients.product.text', {
              unit: unitLabel(t, props.product?.nutrition_basis ?? props.ingredient.base_unit),
            })}
          </DialogDescription>
        </DialogHeader>
        {open && <ProductForm {...props} onClose={() => onOpenChange(false)} />}
      </DialogContent>
    </Dialog>
  );
}

type FormProps = Omit<ProductFormDialogProps, 'open' | 'onOpenChange'> & { onClose: () => void };

function ProductForm({ ingredient, product, onClose }: FormProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const units = useUnits();
  const create = useCreateProduct();
  const update = useUpdateProduct(product?.id ?? '');
  const mutation = product ? update : create;
  const basis = product?.nutrition_basis ?? ingredient.base_unit;

  const [barcode, setBarcode] = useState(product?.barcode ?? '');
  const [texts, setTexts] = useState<Record<TextField, string>>({
    name: product?.name ?? '',
    brand: product?.brand ?? '',
    quantity_text: product?.quantity_text ?? '',
  });
  // The number fields as the form opened with them. Only fields whose text was changed are
  // sent: a stored value with more decimals than shown would otherwise be cut and marked as
  // edited by a user (BAR-04) on every save.
  const [initialPackQuantity] = useState(() => numberInputValue(product?.pack_quantity, language));
  const [initialNutrients] = useState(
    () =>
      Object.fromEntries(
        NUTRIENT_KEYS.map((key) => [key, numberInputValue(product?.nutrients[key], language)]),
      ) as Record<NutrientKey, string>,
  );
  const [packQuantity, setPackQuantity] = useState(initialPackQuantity);
  const [packUnit, setPackUnit] = useState<Unit | ''>(product?.pack_unit ?? '');
  const [nutrients, setNutrients] = useState(initialNutrients);
  const [invalid, setInvalid] = useState<Set<string>>(new Set());
  const serverFields = fieldErrorMessagesByPath(t, mutation.error);

  function fieldError(path: string): string | undefined {
    if (invalid.has(path)) return t('error.field.invalid_format');
    return serverFields[path];
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const problems = new Set<string>();
    const quantity = parseOptionalAmount(packQuantity);
    if (!quantity.ok) problems.add('pack_quantity');
    const values = {} as Record<NutrientKey, number | null>;
    for (const key of NUTRIENT_KEYS) {
      const parsed = parseOptionalAmount(nutrients[key]);
      if (parsed.ok) values[key] = parsed.value;
      else problems.add(`nutrients.${key}`);
    }
    setInvalid(problems);
    if (problems.size > 0 || !quantity.ok) return;

    const trimmedTexts = Object.fromEntries(
      TEXT_FIELDS.map((field) => [field, texts[field].trim() || null]),
    ) as Record<TextField, string | null>;
    const unit = packUnit === '' ? null : packUnit;

    if (!product) {
      // Only what was filled in: the server records every given field as entered by a user.
      const body: ProductCreate = { barcode: barcode.trim(), ingredient_id: ingredient.id };
      for (const field of TEXT_FIELDS) {
        const text = trimmedTexts[field];
        if (text !== null) body[field] = text;
      }
      if (quantity.value !== null) body.pack_quantity = quantity.value;
      if (unit !== null) body.pack_unit = unit;
      const given: Partial<NutrientValues> = {};
      for (const key of NUTRIENT_KEYS) {
        if (values[key] !== null) given[key] = values[key];
      }
      if (Object.keys(given).length > 0) body.nutrients = given;
      create.mutate(body, { onSuccess: onClose });
      return;
    }

    // Only the changed fields: each one sent is marked as edited by a user (BAR-04).
    const body: ProductUpdate = {};
    if (barcode.trim() !== product.barcode) body.barcode = barcode.trim();
    for (const field of TEXT_FIELDS) {
      if (trimmedTexts[field] !== product[field]) body[field] = trimmedTexts[field];
    }
    if (packQuantity.trim() !== initialPackQuantity) body.pack_quantity = quantity.value;
    if (unit !== product.pack_unit) body.pack_unit = unit;
    const changed: Partial<NutrientValues> = {};
    for (const key of NUTRIENT_KEYS) {
      if (nutrients[key].trim() !== initialNutrients[key]) changed[key] = values[key];
    }
    if (Object.keys(changed).length > 0) body.nutrients = changed;
    if (Object.keys(body).length === 0) {
      onClose();
      return;
    }
    update.mutate(body, { onSuccess: onClose });
  }

  const showAlert = needsErrorAlert(serverFields, SHOWN_FIELDS);

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      data-testid={testIds.productForm}
      className="flex flex-col gap-4"
    >
      <FormField
        label={t('ingredients.product.barcode')}
        hint={t('ingredients.product.barcodeHint')}
        error={fieldError('barcode')}
      >
        {(control) => (
          <Input
            {...control}
            name="barcode"
            inputMode="numeric"
            autoComplete="off"
            required
            maxLength={20}
            value={barcode}
            onChange={(event) => setBarcode(event.target.value)}
          />
        )}
      </FormField>
      {TEXT_FIELDS.map((field) => (
        <FormField
          key={field}
          label={t(TEXT_LABELS[field])}
          hint={field === 'quantity_text' ? t('ingredients.product.quantityTextHint') : undefined}
          error={fieldError(field)}
        >
          {(control) => (
            <Input
              {...control}
              name={field}
              autoComplete="off"
              maxLength={TEXT_LIMITS[field]}
              value={texts[field]}
              onChange={(event) =>
                setTexts((current) => ({ ...current, [field]: event.target.value }))
              }
            />
          )}
        </FormField>
      ))}
      <div className="grid grid-cols-2 gap-3">
        <FormField
          label={t('ingredients.product.packQuantity')}
          error={fieldError('pack_quantity')}
        >
          {(control) => (
            <Input
              {...control}
              name="pack_quantity"
              inputMode="decimal"
              autoComplete="off"
              value={packQuantity}
              onChange={(event) => setPackQuantity(event.target.value)}
            />
          )}
        </FormField>
        <FormField label={t('ingredients.product.packUnit')} error={fieldError('pack_unit')}>
          {(control) => (
            <NativeSelect
              {...control}
              name="pack_unit"
              value={packUnit}
              disabled={!units.data}
              onChange={(event) => setPackUnit(event.target.value as Unit | '')}
            >
              <NativeSelectOption value="">
                {t('ingredients.product.packUnitNone')}
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
      <fieldset className="flex flex-col gap-3">
        <legend className="mb-1 font-semibold">
          {t('ingredients.product.nutritionTitle', { unit: unitLabel(t, basis) })}
        </legend>
        <div className="grid grid-cols-2 gap-3">
          {NUTRIENT_KEYS.map((key) => (
            <FormField
              key={key}
              label={nutrientLabel(t, key)}
              error={fieldError(`nutrients.${key}`)}
            >
              {(control) => (
                <Input
                  {...control}
                  name={`nutrients.${key}`}
                  inputMode="decimal"
                  autoComplete="off"
                  value={nutrients[key]}
                  onChange={(event) =>
                    setNutrients((current) => ({ ...current, [key]: event.target.value }))
                  }
                />
              )}
            </FormField>
          ))}
        </div>
      </fieldset>
      <ErrorAlert error={units.error} />
      {showAlert && <ErrorAlert error={mutation.error} />}
      <DialogFooter>
        <Button type="submit" disabled={mutation.isPending || barcode.trim() === ''}>
          {product ? t('common.save') : t('ingredients.product.create')}
        </Button>
      </DialogFooter>
    </form>
  );
}
