import { CircleAlert, Info } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  formatNutrient,
  NUTRIENT_KEYS,
  nutrientLabel,
  type NutrientKey,
} from '@/features/ingredients/nutrients';
import { useLanguage } from '@/i18n';
import { testIds } from '@/testIds';
import type { Meal } from './api';
import { missingLines } from './nutrition';

/**
 * NUT-03/04/05: the server's totals per meal and per serving, only formatted here (MNT-02), with
 * the "incomplete" and "estimate" markers.
 */
export function MealNutritionCard({ meal }: { meal: Meal }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const { per_meal, per_serving, incomplete, estimate, missing } = meal.nutrition;
  const value = (key: NutrientKey, amount: number | null | undefined) =>
    amount === null || amount === undefined
      ? t('meals.nutrition.noValue')
      : formatNutrient(t, language, key, amount);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('meals.nutrition.title')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {meal.ingredients.length === 0 ? (
          <p className="text-muted-foreground">{t('meals.nutrition.empty')}</p>
        ) : (
          <table data-testid={testIds.mealNutrition} className="w-full text-left">
            <thead>
              <tr className="text-sm text-muted-foreground">
                <th scope="col" className="pb-2 font-medium">
                  <span className="sr-only">{t('meals.nutrition.nutrient')}</span>
                </th>
                <th scope="col" className="pb-2 pl-3 text-right font-medium">
                  {t('meals.nutrition.perMeal')}
                </th>
                <th scope="col" className="pb-2 pl-3 text-right font-medium">
                  {t('meals.nutrition.perServing')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {NUTRIENT_KEYS.map((key) => (
                <tr key={key}>
                  <th scope="row" className="py-2 pr-3 font-medium">
                    {nutrientLabel(t, key)}
                  </th>
                  <td className="py-2 pl-3 text-right whitespace-nowrap tabular-nums">
                    {value(key, per_meal[key])}
                  </td>
                  <td className="py-2 pl-3 text-right whitespace-nowrap tabular-nums">
                    {value(key, per_serving[key])}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {incomplete && (
          <div
            data-testid={testIds.mealIncomplete}
            className="flex gap-3 rounded-lg border bg-muted p-3 text-sm"
          >
            <CircleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
            <div className="flex flex-col gap-1">
              <p className="font-semibold">{t('meals.nutrition.incomplete')}</p>
              <ul className="list-disc pl-5">
                {missingLines(t, language, missing).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
        {estimate && (
          <p
            data-testid={testIds.mealEstimate}
            className="flex gap-3 rounded-lg border bg-muted p-3 text-sm"
          >
            <Info aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
            {t('meals.nutrition.estimate')}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
