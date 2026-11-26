import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { LoadError } from '@/components/LoadError';
import { LoadingState } from '@/components/LoadingState';
import { Screen } from '@/components/Screen';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCategories } from '@/features/reference/api';
import { categoryName, unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { formatDate, formatNumber } from '@/i18n/format';
import { userLabel } from '@/i18n/users';
import { testIds } from '@/testIds';
import { useItem, type Item } from './api';
import { ItemMenu } from './ItemMenu';
import { itemLabel } from './label';
import { formatNutrient, NUTRIENT_KEYS, nutrientLabel, nutritionUnit } from './nutrients';
import { OffAttribution } from './OffAttribution';
import { PendingUpdateHint } from './PendingUpdateHint';

/**
 * One item: its details (kind, brand, barcode, package, source, use), nutrition (none for a
 * supply, D-55), newer values
 * from Open Food Facts (BAR-06), and who created and changed it; editing and the admin actions
 * are in the ⋯ menu (`ItemMenu`), their errors below the title.
 */
export function ItemDetailScreen() {
  const { id = '' } = useParams();
  // A fresh screen per item, so an error of one item's menu doesn't stay on the next.
  return <ItemDetail key={id} id={id} />;
}

function ItemDetail({ id }: { id: string }) {
  const { t } = useTranslation();
  const item = useItem(id);
  const [actionError, setActionError] = useState<unknown>(null);

  return (
    <Screen
      title={item.data ? itemLabel(item.data.name, item.data.brand) : t('nav.items')}
      testId={testIds.screenItem}
      back={{ to: '/items', label: t('items.detail.back') }}
      action={item.data && <ItemMenu item={item.data} onError={setActionError} />}
    >
      <ErrorAlert error={actionError} />
      {item.isPending && <LoadingState />}
      <LoadError error={item.error} />
      {item.data && (
        <>
          {item.data.pending_update && item.data.pending_update.fields.length > 0 && (
            <PendingUpdateHint item={item.data} fields={item.data.pending_update.fields} />
          )}
          <PropertiesCard item={item.data} />
          {item.data.kind === 'food' && <NutritionCard item={item.data} />}
        </>
      )}
    </Screen>
  );
}

function PropertiesCard({ item }: { item: Item }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const categories = useCategories();
  const category = categories.data?.find(({ id }) => id === item.category_id);
  const notSet = <span className="text-muted-foreground">{t('items.detail.notSet')}</span>;

  const rows = [
    { label: t('items.detail.kind'), value: t(`items.kind.${item.kind}`) },
    { label: t('items.detail.brand'), value: item.brand ?? notSet },
    {
      label: t('items.detail.category'),
      value: category ? categoryName(category, language) : '…',
    },
    {
      label: t('items.detail.baseUnit'),
      value: t(`items.baseUnit.${item.base_unit}`),
    },
    // Only pieces of food have a weight (ING-02, D-55): they count towards the nutrition
    // through it.
    ...(item.base_unit === 'piece' && item.kind === 'food'
      ? [
          {
            label: t('items.detail.pieceWeight'),
            value:
              item.piece_weight_g === null
                ? notSet
                : t('common.amount', {
                    value: formatNumber(item.piece_weight_g, language, {
                      maximumFractionDigits: 1,
                    }),
                    unit: unitLabel(t, 'g'),
                  }),
          },
        ]
      : []),
    { label: t('items.detail.barcode'), value: item.barcode ?? notSet },
    {
      label: t('items.detail.source'),
      value: t(`items.detail.source.${item.source}`),
    },
    {
      label: t('items.detail.usedIn'),
      value: t('items.detail.meals', { count: item.usage.meals }),
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('items.detail.properties')}</CardTitle>
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
        {item.source === 'off' && <OffAttribution />}
        <div className="flex flex-col gap-1 text-sm text-muted-foreground">
          <p>
            {t('items.detail.createdBy', {
              name: userLabel(t, item.created_by),
              date: formatDate(item.created_at, language),
            })}
          </p>
          <p>
            {t('items.detail.updatedBy', {
              name: userLabel(t, item.updated_by),
              date: formatDate(item.updated_at, language),
            })}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * NUT-02: the item's own value per nutrient; an unknown one shows "–" and makes a meal's
 * total incomplete. Values a user changed on an Open Food Facts item are marked, because
 * updates from there leave them alone (BAR-05).
 */
function NutritionCard({ item }: { item: Item }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const edited = new Set<string>(item.source === 'off' ? item.user_edited_fields : []);

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {t('items.nutrition.title', {
            unit: unitLabel(t, nutritionUnit(item.base_unit)),
          })}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <table data-testid={testIds.itemNutrition} className="w-full text-left">
          <thead className="sr-only">
            <tr>
              <th scope="col">{t('items.nutrition.nutrient')}</th>
              <th scope="col">{t('items.nutrition.value')}</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {NUTRIENT_KEYS.map((key) => {
              const value = item.nutrients[key];
              return (
                <tr key={key} className="align-top">
                  <th scope="row" className="py-2 pr-3 font-medium">
                    {nutrientLabel(t, key)}
                    {edited.has(`nutrients.${key}`) && (
                      <span className="block text-sm font-normal text-muted-foreground">
                        {t('items.form.userEdited')}
                      </span>
                    )}
                  </th>
                  <td className="py-2 text-right whitespace-nowrap tabular-nums">
                    {value === null || value === undefined
                      ? t('items.nutrition.noValue')
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
