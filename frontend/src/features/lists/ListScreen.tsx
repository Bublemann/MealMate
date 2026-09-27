import { ChevronLeft } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate, useParams } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Screen } from '@/components/Screen';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useCategories } from '@/features/reference/api';
import { useLanguage } from '@/i18n';
import { testIds } from '@/testIds';
import { useList, type ListDetail } from './api';
import { ExtraItemInput } from './ExtraItemInput';
import { listDisplayName } from './format';
import { ListActions } from './ListActions';
import { ListLines } from './ListLines';
import { ListMeals } from './ListMeals';
import { MealPicker } from './MealPicker';

/** Passed along when navigating to a list, e.g. from "+ New list" or a copy. */
export interface ListViewState {
  /** Open the meal picker right away (LIST-01). */
  openPicker?: boolean;
  /** Meals a copy left out (VIS-03/06). */
  leftOut?: number;
  /** A meal created from the picker could not be added (translated message). */
  addMealError?: string;
  /** A meal created from the picker was saved without its photo (translated message). */
  photoError?: string;
}

function viewState(state: unknown): ListViewState {
  if (typeof state !== 'object' || state === null) return {};
  const { openPicker, leftOut, addMealError, photoError } = state as Record<string, unknown>;
  return {
    openPicker: openPicker === true,
    leftOut: typeof leftOut === 'number' ? leftOut : undefined,
    addMealError: typeof addMealError === 'string' ? addMealError : undefined,
    photoError: typeof photoError === 'string' ? photoError : undefined,
  };
}

/** `/lists/:id`: one list, editable for its editors, read-only for everyone else (plan § 8). */
export function ListScreen() {
  const { id = '' } = useParams();
  return <ListView key={id} id={id} />;
}

function ListView({ id }: { id: string }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const location = useLocation();
  const navigate = useNavigate();
  const list = useList(id);
  const categories = useCategories();
  // Read once: the state is removed from the history entry, so a reload doesn't repeat it.
  const [initial] = useState(() => viewState(location.state));
  const title = list.data ? listDisplayName(list.data, t, language) : t('nav.lists');

  useEffect(() => {
    if (location.state !== null && location.state !== undefined) {
      void navigate(`${location.pathname}${location.search}`, { replace: true, state: null });
    }
  }, [location.state, location.pathname, location.search, navigate]);

  return (
    <Screen title={title} testId={testIds.screenList}>
      <Link
        to="/lists"
        className="-mt-3 inline-flex min-h-(--tap-target) items-center gap-1 self-start font-medium text-primary underline-offset-4 hover:underline"
      >
        <ChevronLeft aria-hidden="true" className="size-5" />
        {t('lists.detail.back')}
      </Link>
      {initial.leftOut !== undefined && initial.leftOut > 0 && (
        <Alert data-testid={testIds.listLeftOut}>
          <AlertDescription>
            {t('lists.detail.leftOut', { count: initial.leftOut })}
          </AlertDescription>
        </Alert>
      )}
      {initial.addMealError && (
        <Alert variant="destructive">
          <AlertDescription>
            {t('lists.detail.addMealFailed', { error: initial.addMealError })}
          </AlertDescription>
        </Alert>
      )}
      {initial.photoError && (
        <Alert variant="destructive">
          <AlertDescription>
            {t('meals.detail.photoFailed', { error: initial.photoError })}
          </AlertDescription>
        </Alert>
      )}
      {(list.isPending || categories.isPending) && (
        <p className="text-muted-foreground">{t('common.loading')}</p>
      )}
      <ErrorAlert error={list.error ?? categories.error} />
      {list.data && categories.data && (
        <ListContent
          list={list.data}
          categoryKeys={new Map(categories.data.map((category) => [category.id, category.key]))}
          openPicker={initial.openPicker === true}
        />
      )}
    </Screen>
  );
}

interface ListContentProps {
  list: ListDetail;
  categoryKeys: ReadonlyMap<string, string>;
  openPicker: boolean;
}

function ListContent({ list, categoryKeys, openPicker }: ListContentProps) {
  // M5a lists are drafts; the draft-only actions (LIST-07, meals and items here) stay guarded.
  const editable = list.can_edit && list.status === 'draft';
  const [pickerOpen, setPickerOpen] = useState(openPicker && editable);

  return (
    <>
      <ListActions list={list} categoryKeys={categoryKeys} />
      <ListMeals list={list} editable={editable} onAddMeals={() => setPickerOpen(true)} />
      {editable && <ExtraItemInput listId={list.id} />}
      <ListLines list={list} categoryKeys={categoryKeys} editable={editable} />
      {editable && <MealPicker listId={list.id} open={pickerOpen} onOpenChange={setPickerOpen} />}
    </>
  );
}
