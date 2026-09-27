import { ChevronLeft } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';
import { ApiError } from '@/api/errors';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FormField } from '@/components/FormField';
import { LoadError } from '@/components/LoadError';
import { Screen } from '@/components/Screen';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAddListMeal } from '@/features/lists/api';
import type { ListViewState } from '@/features/lists/ListScreen';
import { useLanguage } from '@/i18n';
import { errorMessage, fieldErrorMessagesByPath, needsErrorAlert } from '@/i18n/errors';
import { isUuid } from '@/lib/uuid';
import { testIds } from '@/testIds';
import {
  useCreateMeal,
  useDeleteMealPhoto,
  useMeal,
  useUpdateMeal,
  useUploadMealPhoto,
  type Meal,
} from './api';
import {
  checkValues,
  createBody,
  initialValues,
  isShownPath,
  updateBody,
  withoutRowProblems,
  type FormValues,
} from './form';
import { CuisineField, PhotoField, ServingsField, TagsField, type PhotoChange } from './MealFields';
import type { MealDetailState } from './MealDetailScreen';
import { IngredientRows } from './IngredientRows';

/** `/meals/new` and `/meals/:id/edit`: a screen of its own, not a dialog (plan § 8). */
export function MealFormScreen() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const addToList = params.get('addToList');
  if (id) return <EditMeal key={id} id={id} />;
  // From the meal picker (LIST-03): the new meal goes onto that list, and back there. Only a list
  // id goes into the paths; anything else in the URL is ignored.
  return addToList && isUuid(addToList) ? <MealFormView addToList={addToList} /> : <MealFormView />;
}

function EditMeal({ id }: { id: string }) {
  const { t } = useTranslation();
  const meal = useMeal(id);
  // Only the owner can edit (MEAL-07); the server checks it anyway.
  const forbidden =
    meal.data && !meal.data.is_owner
      ? new ApiError({ status: 403, code: 'common.forbidden' })
      : null;

  if (!meal.data || forbidden) {
    return (
      <Screen
        title={t('meals.form.editTitle', { name: meal.data?.name ?? '' })}
        testId={testIds.screenMealForm}
      >
        {meal.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
        <LoadError error={meal.error ?? forbidden} />
      </Screen>
    );
  }
  return <MealFormView meal={meal.data} />;
}

function MealFormView({ meal, addToList = '' }: { meal?: Meal; addToList?: string }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const navigate = useNavigate();
  const create = useCreateMeal();
  const update = useUpdateMeal(meal?.id ?? '');
  const upload = useUploadMealPhoto();
  const deletePhoto = useDeleteMealPhoto();
  const addToListMeal = useAddListMeal(addToList);
  const mutation = meal ? update : create;
  const [values, setValues] = useState<FormValues>(() => initialValues(meal, language));
  const [photo, setPhoto] = useState<PhotoChange>({ kind: 'keep' });
  const [invalid, setInvalid] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const title = meal ? t('meals.form.editTitle', { name: meal.name }) : t('meals.form.createTitle');
  const back = meal ? `/meals/${meal.id}` : addToList ? `/lists/${addToList}` : '/meals';

  const serverFields = fieldErrorMessagesByPath(t, mutation.error);
  const shown = new Set(Object.keys(serverFields).filter(isShownPath));
  const showAlert = mutation.error !== null && needsErrorAlert(serverFields, shown);

  function fieldError(path: string): string | undefined {
    if (invalid.has(path)) {
      return path === 'servings' ? t('error.field.out_of_range') : t('error.field.invalid_format');
    }
    return serverFields[path];
  }

  function change(patch: Partial<FormValues>) {
    setValues((current) => ({ ...current, ...patch }));
  }

  /** The photo is uploaded (or removed) once the meal is saved; the meal stays saved if that fails. */
  async function savePhoto(saved: Meal): Promise<string | undefined> {
    try {
      if (photo.kind === 'new') await upload.mutateAsync({ mealId: saved.id, file: photo.file });
      if (photo.kind === 'remove' && saved.photo) await deletePhoto.mutateAsync(saved.id);
      return undefined;
    } catch (error) {
      return errorMessage(t, error);
    }
  }

  /** The new meal is on the list once it is saved; the list says if adding it failed. */
  async function addToTheList(saved: Meal, photoError: string | undefined) {
    const state: ListViewState = photoError ? { photoError } : {};
    try {
      await addToListMeal.mutateAsync({ mealId: saved.id });
    } catch (error) {
      state.addMealError = errorMessage(t, error);
    }
    void navigate(`/lists/${addToList}`, { replace: true, state });
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Submit events of dialogs opened from here (e.g. a new ingredient) bubble up through the
    // React tree; only this form's own submit saves the meal.
    if (event.target !== event.currentTarget || saving) return;
    const checked = checkValues(values);
    setInvalid(checked.ok ? new Set() : checked.problems);
    if (!checked.ok) return;

    setSaving(true);
    try {
      let saved: Meal;
      if (meal) {
        const body = updateBody(meal, values, checked);
        saved = Object.keys(body).length > 0 ? await update.mutateAsync(body) : meal;
      } else {
        saved = await create.mutateAsync(createBody(values, checked));
      }
      const photoError = await savePhoto(saved);
      if (!meal && addToList) {
        await addToTheList(saved, photoError);
        return;
      }
      const state: MealDetailState = photoError ? { photoError } : {};
      void navigate(`/meals/${saved.id}`, { replace: true, state });
    } catch {
      // The mutation keeps the error; it is shown next to the fields or in the alert.
    } finally {
      setSaving(false);
    }
  }

  return (
    <Screen title={title} testId={testIds.screenMealForm}>
      <Link
        to={back}
        className="-mt-3 inline-flex min-h-(--tap-target) items-center gap-1 self-start font-medium text-primary underline-offset-4 hover:underline"
      >
        <ChevronLeft aria-hidden="true" className="size-5" />
        {meal ? meal.name : addToList ? t('meals.form.backToList') : t('meals.detail.back')}
      </Link>
      <form
        onSubmit={(event) => void onSubmit(event)}
        noValidate
        aria-label={title}
        data-testid={testIds.mealForm}
        className="flex flex-col gap-6"
      >
        <FormField label={t('meals.field.name')} error={fieldError('name')}>
          {(control) => (
            <Input
              {...control}
              name="name"
              autoComplete="off"
              required
              maxLength={80}
              value={values.name}
              onChange={(event) => change({ name: event.target.value })}
            />
          )}
        </FormField>
        <ServingsField
          value={values.servingsText}
          onChange={(servingsText) => change({ servingsText })}
          error={fieldError('servings')}
        />
        <CuisineField
          value={values.cuisineId}
          onChange={(cuisineId) => change({ cuisineId })}
          error={fieldError('cuisine_id')}
        />
        <TagsField
          tags={values.tags}
          onChange={(tags) => change({ tags })}
          error={
            fieldError('tags') ??
            Object.entries(serverFields).find(([path]) => /^tags\.\d+$/.test(path))?.[1]
          }
        />
        <IngredientRows
          rows={values.rows}
          onChange={(rows) => {
            // Server errors name rows by position, which may no longer fit.
            mutation.reset();
            // So do the form's own, once a row moved or was removed.
            if (values.rows.some((row, index) => rows[index]?.key !== row.key)) {
              setInvalid((current) => withoutRowProblems(current));
            }
            change({ rows });
          }}
          fieldError={fieldError}
        />
        <FormField label={t('meals.field.instructions')} error={fieldError('instructions')}>
          {(control) => (
            <textarea
              {...control}
              name="instructions"
              rows={8}
              maxLength={10000}
              value={values.instructions}
              onChange={(event) => change({ instructions: event.target.value })}
              className="min-h-32 w-full rounded-md border border-input bg-background px-3 py-2 text-(length:--control-font-size) outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring aria-invalid:border-destructive"
            />
          )}
        </FormField>
        <FormField
          label={t('meals.field.sourceUrl')}
          hint={t('meals.field.sourceUrlHint')}
          error={fieldError('source_url')}
        >
          {(control) => (
            <Input
              {...control}
              name="source_url"
              type="url"
              inputMode="url"
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              maxLength={2000}
              value={values.sourceUrl}
              onChange={(event) => change({ sourceUrl: event.target.value })}
            />
          )}
        </FormField>
        <PhotoField
          current={meal?.photo?.url ?? null}
          mealName={values.name}
          change={photo}
          onChange={setPhoto}
        />
        {showAlert && <ErrorAlert error={mutation.error} />}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={saving || values.name.trim() === ''}>
            {saving ? t('meals.form.saving') : meal ? t('common.save') : t('meals.form.create')}
          </Button>
          <Button variant="outline" asChild>
            <Link to={back}>{t('meals.form.cancel')}</Link>
          </Button>
        </div>
      </form>
    </Screen>
  );
}
