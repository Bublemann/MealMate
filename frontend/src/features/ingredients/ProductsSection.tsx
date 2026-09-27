import type { TFunction } from 'i18next';
import { Pencil, Plus } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { unitLabel } from '@/features/reference/labels';
import { useLanguage, type Language } from '@/i18n';
import { formatNumber } from '@/i18n/format';
import { testIds } from '@/testIds';
import {
  useIngredientProducts,
  usePendingUpdate,
  type Ingredient,
  type PendingUpdateField,
  type Product,
} from './api';
import { formatNutrient, NUTRIENT_KEYS, nutrientLabel, type NutrientKey } from './nutrients';
import { OffAttribution } from './OffAttribution';
import { ProductFormDialog } from './ProductFormDialog';

/** The products linked to an ingredient (ING-04), with "Add product" (manual entry). */
export function ProductsSection({ ingredient }: { ingredient: Ingredient }) {
  const { t } = useTranslation();
  const products = useIngredientProducts(ingredient.id);
  const [adding, setAdding] = useState(false);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('ingredients.products.title')}</CardTitle>
        <CardDescription>{t('ingredients.products.text')}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {products.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
        <ErrorAlert error={products.error} />
        {products.data?.length === 0 && (
          <p className="text-muted-foreground">{t('ingredients.products.empty')}</p>
        )}
        {products.data && products.data.length > 0 && (
          <ul data-testid={testIds.productList} className="flex flex-col gap-3">
            {products.data.map((product) => (
              <li key={product.id}>
                <ProductRow product={product} ingredient={ingredient} />
              </li>
            ))}
          </ul>
        )}
        <Button
          variant="outline"
          className="self-start"
          data-testid={testIds.addProduct}
          onClick={() => setAdding(true)}
        >
          <Plus aria-hidden="true" />
          {t('ingredients.products.add')}
        </Button>
      </CardContent>
      <ProductFormDialog open={adding} onOpenChange={setAdding} ingredient={ingredient} />
    </Card>
  );
}

function ProductRow({ product, ingredient }: { product: Product; ingredient: Ingredient }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const [editing, setEditing] = useState(false);
  const name = product.name ?? t('ingredients.products.unnamed');
  const values = NUTRIENT_KEYS.flatMap((key) => {
    const value = product.nutrients[key];
    return value === null || value === undefined
      ? []
      : [`${nutrientLabel(t, key)} ${formatNutrient(t, language, key, value)}`];
  });

  return (
    <div data-testid={testIds.productRow} className="flex flex-col gap-3 rounded-lg border p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="font-medium break-words">
            {name}
            {product.brand && <span className="text-muted-foreground"> · {product.brand}</span>}
          </p>
          <p className="text-sm text-muted-foreground">
            {t('ingredients.products.barcode', { barcode: product.barcode })}
            {product.quantity_text && ` · ${product.quantity_text}`}
          </p>
          <p className="text-sm">
            <span className="text-muted-foreground">
              {t('ingredients.products.basis', {
                unit: unitLabel(t, product.nutrition_basis),
              })}{' '}
            </span>
            {values.length > 0 ? values.join(' · ') : t('ingredients.products.noValues')}
          </p>
          {product.source === 'off' && <OffAttribution />}
        </div>
        <Button
          size="compact"
          variant="outline"
          aria-label={t('ingredients.products.editLabel', { name })}
          onClick={() => setEditing(true)}
        >
          <Pencil aria-hidden="true" />
          {t('ingredients.products.edit')}
        </Button>
      </div>
      {product.pending_update && product.pending_update.fields.length > 0 && (
        <PendingUpdateHint product={product} fields={product.pending_update.fields} name={name} />
      )}
      <ProductFormDialog
        open={editing}
        onOpenChange={setEditing}
        ingredient={ingredient}
        product={product}
      />
    </div>
  );
}

const TEXT_FIELD_LABELS = {
  name: 'ingredients.product.name',
  brand: 'ingredients.product.brand',
  quantity_text: 'ingredients.product.quantityText',
  pack_quantity: 'ingredients.product.packQuantity',
  pack_unit: 'ingredients.product.packUnit',
  nutrition_basis: 'ingredients.pending.basis',
} as const;

function nutrientKeyOf(field: string): NutrientKey | null {
  const key = field.startsWith('nutrients.') ? field.slice('nutrients.'.length) : '';
  return (NUTRIENT_KEYS as readonly string[]).includes(key) ? (key as NutrientKey) : null;
}

/** "Calories: 165 kcal → 158 kcal": a field of a pending update with its units. */
function describeChange(t: TFunction, language: Language, change: PendingUpdateField): string {
  const nutrient = nutrientKeyOf(change.field);
  const format = (value: string | number | null): string => {
    if (value === null) return t('ingredients.pending.none');
    if (typeof value === 'string') {
      return change.field === 'pack_unit' || change.field === 'nutrition_basis'
        ? unitLabel(t, value)
        : value;
    }
    return nutrient
      ? formatNutrient(t, language, nutrient, value)
      : formatNumber(value, language, { maximumFractionDigits: 3 });
  };
  const label = nutrient
    ? nutrientLabel(t, nutrient)
    : change.field in TEXT_FIELD_LABELS
      ? t(TEXT_FIELD_LABELS[change.field as keyof typeof TEXT_FIELD_LABELS])
      : change.field;
  return t('ingredients.pending.change', {
    field: label,
    current: format(change.current),
    proposed: format(change.proposed),
  });
}

interface PendingUpdateHintProps {
  product: Product;
  fields: PendingUpdateField[];
  name: string;
}

/**
 * BAR-06: Open Food Facts has other values for fields a user changed. They are only taken on
 * "Apply"; "Ignore" keeps the user's values until Open Food Facts changes the product again.
 */
function PendingUpdateHint({ product, fields, name }: PendingUpdateHintProps) {
  const { t } = useTranslation();
  const language = useLanguage();
  const apply = usePendingUpdate(product.id, 'apply');
  const ignore = usePendingUpdate(product.id, 'ignore');
  const busy = apply.isPending || ignore.isPending;

  return (
    <div
      data-testid={testIds.pendingUpdate}
      className="flex flex-col gap-2 rounded-lg border bg-muted p-3"
    >
      <p className="text-sm font-medium">{t('ingredients.pending.title')}</p>
      <ul className="flex flex-col gap-1 text-sm">
        {fields.map((change) => (
          <li key={change.field} className="break-words">
            {describeChange(t, language, change)}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button
          size="compact"
          data-testid={testIds.applyPendingUpdate}
          aria-label={t('ingredients.pending.applyLabel', { name })}
          disabled={busy}
          onClick={() => apply.mutate()}
        >
          {t('ingredients.pending.apply')}
        </Button>
        <Button
          size="compact"
          variant="outline"
          data-testid={testIds.ignorePendingUpdate}
          aria-label={t('ingredients.pending.ignoreLabel', { name })}
          disabled={busy}
          onClick={() => ignore.mutate()}
        >
          {t('ingredients.pending.ignore')}
        </Button>
      </div>
      <ErrorAlert error={apply.error ?? ignore.error} />
    </div>
  );
}
