import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { LoadError } from '@/components/LoadError';
import { Screen } from '@/components/Screen';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCategories } from '@/features/reference/api';
import { categoryName, unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { formatDate, formatNumber } from '@/i18n/format';
import { userLabel } from '@/i18n/users';
import { testIds } from '@/testIds';
import { useIngredient, type Ingredient } from './api';
import { IngredientMenu } from './IngredientMenu';
import { ingredientLabel } from './label';
import { formatNutrient, NUTRIENT_KEYS, nutrientLabel, nutritionUnit } from './nutrients';
import { OffAttribution } from './OffAttribution';
import { PendingUpdateHint } from './PendingUpdateHint';

/**
 * One ingredient: its details (brand, barcode, package, source, use), nutrition, newer values
 * from Open Food Facts (BAR-06), and who created and changed it; editing and the admin actions
 * are in the ⋯ menu (`IngredientMenu`), their errors below the title.
 */
export function IngredientDetailScreen() {
  const { id = '' } = useParams();
  // A fresh screen per ingredient, so an error of one ingredient's menu doesn't stay on the next.
  return <IngredientDetail key={id} id={id} />;
}

function IngredientDetail({ id }: { id: string }) {
  const { t } = useTranslation();
  const ingredient = useIngredient(id);
  const [actionError, setActionError] = useState<unknown>(null);

  return (
    <Screen
      title={
        ingredient.data
          ? ingredientLabel(ingredient.data.name, ingredient.data.brand)
          : t('nav.ingredients')
      }
      testId={testIds.screenIngredient}
      back={{ to: '/ingredients', label: t('ingredients.detail.back') }}
      action={
        ingredient.data && <IngredientMenu ingredient={ingredient.data} onError={setActionError} />
      }
    >
      <ErrorAlert error={actionError} />
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
        </>
      )}
    </Screen>
  );
}

function PropertiesCard({ ingredient }: { ingredient: Ingredient }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const categories = useCategories();
  const category = categories.data?.find(({ id }) => id === ingredient.category_id);
  const notSet = <span className="text-muted-foreground">{t('ingredients.detail.notSet')}</span>;

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
    // Only pieces have a weight (ING-02): they count towards the nutrition through it.
    ...(ingredient.base_unit === 'piece'
      ? [
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
        ]
      : []),
    { label: t('ingredients.detail.barcode'), value: ingredient.barcode ?? notSet },
    // The pack size is its text alone, as in the edit pop-up (D-47).
    { label: t('ingredients.detail.pack'), value: ingredient.quantity_text ?? notSet },
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
      <CardHeader>
        <CardTitle>{t('ingredients.detail.properties')}</CardTitle>
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
    </Card>
  );
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
          {t('ingredients.nutrition.title', {
            unit: unitLabel(t, nutritionUnit(ingredient.base_unit)),
          })}
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
