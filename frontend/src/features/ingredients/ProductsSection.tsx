import { Pencil, Plus } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { testIds } from '@/testIds';
import { useIngredientProducts, type Ingredient, type Product } from './api';
import { formatNutrient, NUTRIENT_KEYS, nutrientLabel } from './nutrients';
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
    <div
      data-testid={testIds.productRow}
      className="flex items-start justify-between gap-3 rounded-lg border p-3"
    >
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
            {t('ingredients.products.basis', { unit: unitLabel(t, product.nutrition_basis) })}{' '}
          </span>
          {values.length > 0 ? values.join(' · ') : t('ingredients.products.noValues')}
        </p>
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
      <ProductFormDialog
        open={editing}
        onOpenChange={setEditing}
        ingredient={ingredient}
        product={product}
      />
    </div>
  );
}
