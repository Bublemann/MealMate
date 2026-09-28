import { ChevronLeft, Pencil } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { LoadError } from '@/components/LoadError';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCurrentUser } from '@/features/auth/context';
import { useCategories } from '@/features/reference/api';
import { categoryName, unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { formatDate, formatNumber } from '@/i18n/format';
import { userLabel } from '@/i18n/users';
import { testIds } from '@/testIds';
import { useIngredient, type Ingredient } from './api';
import { IngredientAdminActions } from './IngredientAdminActions';
import { IngredientFormDialog } from './IngredientFormDialog';
import { formatNutrient, NUTRIENT_KEYS, nutrientLabel } from './nutrients';
import { ProductsSection } from './ProductsSection';

/** One ingredient: its properties, nutrition with sources, products and admin actions. */
export function IngredientDetailScreen() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const ingredient = useIngredient(id);
  const user = useCurrentUser();

  return (
    <Screen title={ingredient.data?.name ?? t('nav.ingredients')} testId={testIds.screenIngredient}>
      <Link
        to="/ingredients"
        className="-mt-3 inline-flex min-h-(--tap-target) items-center gap-1 self-start font-medium text-primary underline-offset-4 hover:underline"
      >
        <ChevronLeft aria-hidden="true" className="size-5" />
        {t('ingredients.detail.back')}
      </Link>
      {ingredient.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <LoadError error={ingredient.error} />
      {ingredient.data && (
        <>
          <PropertiesCard ingredient={ingredient.data} />
          <NutritionCard ingredient={ingredient.data} />
          <ProductsSection ingredient={ingredient.data} />
          {user.role === 'admin' && <IngredientAdminActions ingredient={ingredient.data} />}
        </>
      )}
    </Screen>
  );
}

function PropertiesCard({ ingredient }: { ingredient: Ingredient }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const categories = useCategories();
  const [editing, setEditing] = useState(false);
  const category = categories.data?.find(({ id }) => id === ingredient.category_id);
  const notSet = <span className="text-muted-foreground">{t('ingredients.detail.notSet')}</span>;

  const rows = [
    {
      label: t('ingredients.detail.category'),
      value: category ? categoryName(t, category.key) : '…',
    },
    {
      label: t('ingredients.detail.baseUnit'),
      value: t(`ingredients.baseUnit.${ingredient.base_unit}`),
    },
    {
      label: t('ingredients.detail.pieceWeight'),
      value:
        ingredient.piece_weight_g === null
          ? notSet
          : t('common.amount', {
              value: formatNumber(ingredient.piece_weight_g, language, {
                maximumFractionDigits: 1,
              }),
              unit: unitLabel(t, 'g'),
            }),
    },
    {
      label: t('ingredients.detail.density'),
      value:
        ingredient.density_g_per_ml === null
          ? notSet
          : t('common.amount', {
              value: formatNumber(ingredient.density_g_per_ml, language, {
                maximumFractionDigits: 3,
              }),
              unit: t('ingredients.densityUnit'),
            }),
    },
  ];

  return (
    <Card>
      <CardHeader className="flex items-center justify-between gap-3">
        <CardTitle>{t('ingredients.detail.properties')}</CardTitle>
        <Button
          size="compact"
          variant="outline"
          data-testid={testIds.editIngredient}
          aria-label={t('ingredients.detail.editLabel', { name: ingredient.name })}
          onClick={() => setEditing(true)}
        >
          <Pencil aria-hidden="true" />
          {t('ingredients.detail.edit')}
        </Button>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl className="flex flex-col divide-y">
          {rows.map(({ label, value }) => (
            <div key={label} className="flex items-baseline justify-between gap-4 py-2">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="text-right font-medium">{value}</dd>
            </div>
          ))}
        </dl>
        <ErrorAlert error={categories.error} />
        <div className="flex flex-col gap-1 text-sm text-muted-foreground">
          <p>
            {t('ingredients.detail.createdBy', {
              name: userLabel(t, ingredient.created_by),
              date: formatDate(ingredient.created_at, language),
            })}
          </p>
          <p>
            {t('ingredients.detail.updatedBy', {
              name: userLabel(t, ingredient.updated_by),
              date: formatDate(ingredient.updated_at, language),
            })}
          </p>
        </div>
      </CardContent>
      <IngredientFormDialog open={editing} onOpenChange={setEditing} ingredient={ingredient} />
    </Card>
  );
}

/** NUT-02: per nutrient the value, where it comes from, and the product average as a hint. */
function NutritionCard({ ingredient }: { ingredient: Ingredient }) {
  const { t } = useTranslation();
  const language = useLanguage();

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {t('ingredients.nutrition.title', { unit: unitLabel(t, ingredient.base_unit) })}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <table data-testid={testIds.ingredientNutrition} className="w-full text-left">
          <thead className="sr-only">
            <tr>
              <th scope="col">{t('ingredients.nutrition.nutrient')}</th>
              <th scope="col">{t('ingredients.nutrition.value')}</th>
              <th scope="col">{t('ingredients.nutrition.source')}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {NUTRIENT_KEYS.map((key) => {
              const info = ingredient.nutrition[key];
              const showHint =
                info.source === 'manual' && info.products_count > 0 && info.products_mean !== null;
              return (
                <tr key={key} className="align-top">
                  <th scope="row" className="py-2 pr-3 font-medium">
                    {nutrientLabel(t, key)}
                  </th>
                  <td className="py-2 pr-3 text-right whitespace-nowrap tabular-nums">
                    {info.value === null
                      ? t('ingredients.nutrition.noValue')
                      : formatNutrient(t, language, key, info.value)}
                  </td>
                  <td className="py-2 text-sm text-muted-foreground">
                    <span className="block">
                      {info.source === 'products'
                        ? t('ingredients.nutrition.source.products', {
                            count: info.products_count,
                          })
                        : t(`ingredients.nutrition.source.${info.source}`)}
                    </span>
                    {showHint && info.products_mean !== null && (
                      <span className="block">
                        {t('ingredients.nutrition.productsHint', {
                          value: formatNutrient(t, language, key, info.products_mean),
                        })}
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
