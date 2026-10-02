import type { TFunction } from 'i18next';
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
import { useLanguage, type Language } from '@/i18n';
import { formatDate, formatNumber } from '@/i18n/format';
import { userLabel } from '@/i18n/users';
import { testIds } from '@/testIds';
import { useIngredient, type Ingredient } from './api';
import { IngredientAdminActions } from './IngredientAdminActions';
import { IngredientFormDialog } from './IngredientFormDialog';
import { ingredientLabel } from './label';
import { formatNutrient, NUTRIENT_KEYS, nutrientLabel } from './nutrients';
import { OffAttribution } from './OffAttribution';
import { PendingUpdateHint } from './PendingUpdateHint';

/**
 * One ingredient: its details (brand, barcode, package, source, use), nutrition, newer values
 * from Open Food Facts (BAR-06), who created and changed it, and the admin actions.
 */
export function IngredientDetailScreen() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const ingredient = useIngredient(id);
  const user = useCurrentUser();

  return (
    <Screen
      title={
        ingredient.data
          ? ingredientLabel(ingredient.data.name, ingredient.data.brand)
          : t('nav.ingredients')
      }
      testId={testIds.screenIngredient}
    >
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
          {ingredient.data.pending_update && ingredient.data.pending_update.fields.length > 0 && (
            <PendingUpdateHint
              ingredient={ingredient.data}
              fields={ingredient.data.pending_update.fields}
            />
          )}
          <PropertiesCard ingredient={ingredient.data} />
          <NutritionCard ingredient={ingredient.data} />
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

  const label = ingredientLabel(ingredient.name, ingredient.brand);
  const pack = packText(t, language, ingredient);

  const rows = [
    { label: t('ingredients.detail.brand'), value: ingredient.brand ?? notSet },
    {
      label: t('ingredients.detail.category'),
      value: category ? categoryName(category, language) : '…',
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
    { label: t('ingredients.detail.barcode'), value: ingredient.barcode ?? notSet },
    { label: t('ingredients.detail.pack'), value: pack ?? notSet },
    {
      label: t('ingredients.detail.source'),
      value: t(`ingredients.detail.source.${ingredient.source}`),
    },
    {
      label: t('ingredients.detail.usedIn'),
      value: t('ingredients.detail.meals', { count: ingredient.usage.meals }),
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
          aria-label={t('ingredients.detail.editLabel', { name: label })}
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
              <dd className="min-w-0 text-right font-medium wrap-anywhere">{value}</dd>
            </div>
          ))}
        </dl>
        <ErrorAlert error={categories.error} />
        {ingredient.source === 'off' && <OffAttribution />}
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

/**
 * The package as Open Food Facts or the user gave it: the printed text ("6 × 1,5 l"), else the
 * contents with their unit; null when neither is known. Information only (nothing is computed
 * from it).
 */
function packText(t: TFunction, language: Language, ingredient: Ingredient): string | null {
  if (ingredient.quantity_text) return ingredient.quantity_text;
  if (ingredient.pack_quantity === null) return null;
  const value = formatNumber(ingredient.pack_quantity, language, { maximumFractionDigits: 3 });
  return ingredient.pack_unit
    ? t('common.amount', { value, unit: unitLabel(t, ingredient.pack_unit) })
    : value;
}

/**
 * NUT-02: the ingredient's own value per nutrient; an unknown one shows "–" and makes a meal's
 * total incomplete. Values a user changed on an Open Food Facts ingredient are marked, because
 * updates from there leave them alone (BAR-05).
 */
function NutritionCard({ ingredient }: { ingredient: Ingredient }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const edited = new Set<string>(ingredient.source === 'off' ? ingredient.user_edited_fields : []);

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
            </tr>
          </thead>
          <tbody className="divide-y">
            {NUTRIENT_KEYS.map((key) => {
              const value = ingredient.nutrients[key];
              return (
                <tr key={key} className="align-top">
                  <th scope="row" className="py-2 pr-3 font-medium">
                    {nutrientLabel(t, key)}
                    {edited.has(`nutrients.${key}`) && (
                      <span className="block text-sm font-normal text-muted-foreground">
                        {t('ingredients.form.userEdited')}
                      </span>
                    )}
                  </th>
                  <td className="py-2 text-right whitespace-nowrap tabular-nums">
                    {value === null || value === undefined
                      ? t('ingredients.nutrition.noValue')
                      : formatNutrient(t, language, key, value)}
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
