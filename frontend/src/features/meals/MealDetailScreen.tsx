import { Copy, ExternalLink as ExternalLinkIcon, Pencil, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Trans, useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate, useParams } from 'react-router';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { ExternalLink } from '@/components/ExternalLink';
import { LoadError } from '@/components/LoadError';
import { MoreMenu, MoreMenuItem, useMoreMenuFocus } from '@/components/MoreMenu';
import { Screen } from '@/components/Screen';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { buttonVariants } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ingredientLabel } from '@/features/ingredients/label';
import { cuisineName, unitLabel } from '@/features/reference/labels';
import { useConnected } from '@/features/sync/context';
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
 * instructions; its actions are in the ⋯ menu (`MealMenu`), their errors below the title.
 */
export function MealDetailScreen() {
  const { id = '' } = useParams();
  // A fresh screen per meal, so an error of one meal's menu doesn't stay on the next.
  return <MealDetail key={id} id={id} />;
}

function MealDetail({ id }: { id: string }) {
  const { t } = useTranslation();
  const location = useLocation();
  const meal = useMeal(id);
  const failedPhoto = photoError(location.state);
  const [actionError, setActionError] = useState<unknown>(null);

  return (
    <Screen
      title={meal.data?.name ?? t('nav.meals')}
      testId={testIds.screenMeal}
      back={{ to: '/meals', label: t('meals.detail.back') }}
      action={meal.data && <MealMenu meal={meal.data} onError={setActionError} />}
    >
      <ErrorAlert error={actionError} />
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

interface MealMenuProps {
  meal: Meal;
  /** Shows an error of an action below the title; `null` clears it when the next one starts. */
  onError: (error: unknown) => void;
}

/**
 * The meal's ⋯ menu (D-39): "Edit", "Copy" and, red and last, "Delete" for the owner (MEAL-07);
 * only "Copy" on someone else's meal (MEAL-08). Each needs a connection (SYNC-03).
 */
function MealMenu({ meal, onError }: MealMenuProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const offline = !useConnected();
  const copy = useCopyMeal(meal.id);
  const remove = useDeleteMeal(meal.id);
  const [deleting, setDeleting] = useState(false);
  const { trigger, focusMenu } = useMoreMenuFocus();
  const busy = copy.isPending || remove.isPending || offline;

  return (
    <>
      <MoreMenu
        trigger={trigger}
        danger={
          meal.is_owner && (
            <MoreMenuItem
              testId={testIds.deleteMeal}
              icon={<Trash2 aria-hidden="true" />}
              destructive
              dialog
              disabled={busy}
              onSelect={() => setDeleting(true)}
            >
              {t('meals.detail.delete')}
            </MoreMenuItem>
          )
        }
      >
        {meal.is_owner && (
          <MoreMenuItem
            testId={testIds.editMeal}
            icon={<Pencil aria-hidden="true" />}
            disabled={offline}
            onSelect={() => void navigate(`/meals/${meal.id}/edit`)}
          >
            {t('meals.detail.edit')}
          </MoreMenuItem>
        )}
        <MoreMenuItem
          testId={testIds.copyMeal}
          icon={<Copy aria-hidden="true" />}
          disabled={busy}
          onSelect={() => {
            onError(null);
            copy.mutate(undefined, {
              onSuccess: (created) => void navigate(`/meals/${created.id}`),
              onError,
            });
          }}
        >
          {t('meals.detail.copy')}
        </MoreMenuItem>
      </MoreMenu>
      {meal.is_owner && (
        <ConfirmDialog
          open={deleting}
          onOpenChange={setDeleting}
          onCloseAutoFocus={focusMenu}
          title={t('meals.detail.deleteTitle', { name: meal.name })}
          description={t('meals.detail.deleteText')}
          confirmLabel={t('meals.detail.deleteConfirm')}
          destructive
          onConfirm={() => {
            onError(null);
            remove.mutate(undefined, {
              onSuccess: () => void navigate('/meals', { replace: true }),
              onError,
            });
          }}
        />
      )}
    </>
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
