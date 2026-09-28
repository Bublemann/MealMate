import { ChevronLeft, Copy, ExternalLink as ExternalLinkIcon, Pencil, Trash2 } from 'lucide-react';
import { Trans, useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate, useParams } from 'react-router';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { ExternalLink } from '@/components/ExternalLink';
import { LoadError } from '@/components/LoadError';
import { Screen } from '@/components/Screen';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button, buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ingredientLabel } from '@/features/ingredients/label';
import { cuisineName, unitLabel } from '@/features/reference/labels';
import { useLanguage } from '@/i18n';
import { formatNumber } from '@/i18n/format';
import { userLabel } from '@/i18n/users';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import { useCopyMeal, useDeleteMeal, useMeal, type Meal } from './api';
import { MealNutritionCard } from './MealNutritionCard';

/** Set by the meal form when the meal was saved but its photo upload failed. */
export interface MealDetailState {
  photoError?: string;
}

function photoError(state: unknown): string | undefined {
  if (typeof state !== 'object' || state === null || !('photoError' in state)) return undefined;
  return typeof state.photoError === 'string' ? state.photoError : undefined;
}

/**
 * One meal (MEAL-06): photo, owner and origin, facts, source, nutrition, ingredients and
 * instructions; Edit and Delete for the owner (MEAL-07), Copy for everyone (MEAL-08).
 */
export function MealDetailScreen() {
  const { t } = useTranslation();
  const { id = '' } = useParams();
  const location = useLocation();
  const meal = useMeal(id);
  const failedPhoto = photoError(location.state);

  return (
    <Screen title={meal.data?.name ?? t('nav.meals')} testId={testIds.screenMeal}>
      <Link
        to="/meals"
        className="-mt-3 inline-flex min-h-(--tap-target) items-center gap-1 self-start font-medium text-primary underline-offset-4 hover:underline"
      >
        <ChevronLeft aria-hidden="true" className="size-5" />
        {t('meals.detail.back')}
      </Link>
      {failedPhoto && (
        <Alert variant="destructive">
          <AlertDescription>
            {t('meals.detail.photoFailed', { error: failedPhoto })}
          </AlertDescription>
        </Alert>
      )}
      {meal.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <LoadError error={meal.error} />
      {meal.data && <MealContent key={meal.data.id} meal={meal.data} />}
    </Screen>
  );
}

function MealContent({ meal }: { meal: Meal }) {
  const { t } = useTranslation();

  return (
    <>
      {meal.photo && (
        <img
          src={meal.photo.url}
          alt={meal.name}
          data-testid={testIds.mealPhoto}
          className="aspect-[4/3] w-full rounded-xl bg-muted object-cover"
        />
      )}
      <Origin meal={meal} />
      {meal.source_url && (
        <ExternalLink
          href={meal.source_url}
          data-testid={testIds.mealSourceLink}
          className={cn(buttonVariants(), 'self-start text-primary-foreground no-underline')}
        >
          <ExternalLinkIcon aria-hidden="true" />
          {t('meals.detail.source')}
        </ExternalLink>
      )}
      <Facts meal={meal} />
      <Actions meal={meal} />
      <MealNutritionCard meal={meal} />
      <IngredientsCard meal={meal} />
      {meal.instructions && (
        <Card>
          <CardHeader>
            <CardTitle>{t('meals.instructions.title')}</CardTitle>
          </CardHeader>
          <CardContent>
            {/* Plain text with its line breaks, never HTML (SEC-13). */}
            <p data-testid={testIds.mealInstructions} className="break-words whitespace-pre-wrap">
              {meal.instructions}
            </p>
          </CardContent>
        </Card>
      )}
    </>
  );
}

/** "by X" for someone else's meal, and "Based on Y by Z" for a copy (MEAL-06, MEAL-08). */
function Origin({ meal }: { meal: Meal }) {
  const { t } = useTranslation();
  const basedOn = meal.based_on;
  if (meal.is_owner && !basedOn) return null;

  return (
    <div className="-mt-3 flex flex-col gap-1 text-muted-foreground">
      {!meal.is_owner && <p>{t('meals.detail.by', { name: userLabel(t, meal.owner) })}</p>}
      {basedOn && (
        <p data-testid={testIds.mealBasedOn}>
          {/* Names are passed as elements, so user text is never parsed as markup. */}
          <Trans
            i18nKey="meals.detail.basedOn"
            components={{
              mealLink: (
                <Link
                  to={`/meals/${basedOn.meal_id}`}
                  className="font-medium text-primary underline underline-offset-4"
                >
                  {basedOn.name}
                </Link>
              ),
              owner: <span>{userLabel(t, basedOn.owner)}</span>,
            }}
          />
        </p>
      )}
    </div>
  );
}

function Facts({ meal }: { meal: Meal }) {
  const { t } = useTranslation();

  const rows = [
    { label: t('meals.detail.servings'), value: meal.servings.toString() },
    ...(meal.cuisine
      ? [{ label: t('meals.detail.cuisine'), value: cuisineName(t, meal.cuisine) }]
      : []),
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('meals.detail.facts')}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl className="flex flex-col divide-y">
          {rows.map(({ label, value }) => (
            <div key={label} className="flex items-baseline justify-between gap-4 py-2">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="text-right font-medium">{value}</dd>
            </div>
          ))}
        </dl>
        {meal.tags.length > 0 && (
          <ul aria-label={t('meals.detail.tags')} className="flex flex-wrap gap-2">
            {meal.tags.map((tag) => (
              <li key={tag.id}>
                <Badge variant="secondary" className="text-sm">
                  {tag.name}
                </Badge>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function Actions({ meal }: { meal: Meal }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const copy = useCopyMeal(meal.id);
  const remove = useDeleteMeal(meal.id);
  const busy = copy.isPending || remove.isPending;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-2">
        <Button
          variant={meal.is_owner ? 'outline' : 'default'}
          data-testid={testIds.copyMeal}
          disabled={busy}
          onClick={() =>
            copy.mutate(undefined, {
              onSuccess: (created) => void navigate(`/meals/${created.id}`),
            })
          }
        >
          <Copy aria-hidden="true" />
          {t('meals.detail.copy')}
        </Button>
        {meal.is_owner && (
          <>
            <Button variant="outline" asChild>
              <Link
                to={`/meals/${meal.id}/edit`}
                data-testid={testIds.editMeal}
                aria-label={t('meals.detail.editLabel', { name: meal.name })}
              >
                <Pencil aria-hidden="true" />
                {t('meals.detail.edit')}
              </Link>
            </Button>
            <ConfirmDialog
              trigger={
                <Button
                  variant="outline"
                  data-testid={testIds.deleteMeal}
                  aria-label={t('meals.detail.deleteLabel', { name: meal.name })}
                  disabled={busy}
                >
                  <Trash2 aria-hidden="true" />
                  {t('meals.detail.delete')}
                </Button>
              }
              title={t('meals.detail.deleteTitle', { name: meal.name })}
              description={t('meals.detail.deleteText')}
              confirmLabel={t('meals.detail.deleteConfirm')}
              destructive
              onConfirm={() =>
                remove.mutate(undefined, {
                  onSuccess: () => void navigate('/meals', { replace: true }),
                })
              }
            />
          </>
        )}
      </div>
      <ErrorAlert error={copy.error ?? remove.error} />
    </div>
  );
}

function IngredientsCard({ meal }: { meal: Meal }) {
  const { t } = useTranslation();
  const language = useLanguage();

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t('meals.ingredients.title')}</CardTitle>
      </CardHeader>
      <CardContent>
        {meal.ingredients.length === 0 ? (
          <p className="text-muted-foreground">{t('meals.ingredients.empty')}</p>
        ) : (
          <ul data-testid={testIds.mealIngredients} className="flex flex-col divide-y">
            {meal.ingredients.map((row) => (
              <li key={row.id} className="flex items-baseline gap-3 py-2">
                <span className="w-24 shrink-0 text-right font-medium tabular-nums">
                  {row.amount !== null &&
                    t('common.amount', {
                      value: formatNumber(row.amount, language, { maximumFractionDigits: 2 }),
                      unit: row.unit ? unitLabel(t, row.unit) : '',
                    }).trim()}
                </span>
                <span className="min-w-0 flex-1 break-words">
                  <Link
                    to={`/ingredients/${row.ingredient.id}`}
                    className="inline-flex min-h-(--tap-target) items-center font-medium text-primary underline-offset-4 hover:underline"
                  >
                    {ingredientLabel(row.ingredient.name, row.ingredient.brand)}
                  </Link>
                  {row.note && <span className="text-muted-foreground"> · {row.note}</span>}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
