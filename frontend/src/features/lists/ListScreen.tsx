import { ChevronLeft, ShoppingCart } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useNavigate, useParams } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Screen } from '@/components/Screen';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { useCategories } from '@/features/reference/api';
import { useLanguage } from '@/i18n';
import { testIds } from '@/testIds';
import { isUnreachable, useList, useStartShopping, type ListDetail } from './api';
import { DoneView } from './DoneView';
import { ExtraItemInput } from './ExtraItemInput';
import { listDisplayName } from './format';
import { ListActions } from './ListActions';
import { ListLines } from './ListLines';
import { ListMeals } from './ListMeals';
import { MealPicker } from './MealPicker';
import { ShoppingView } from './ShoppingView';

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

/**
 * `/lists/:id`: one list, editable for its editors, read-only for everyone else; a draft, the
 * shopping view or a done list by its state (LIST-10, plan § 8). It is checked for changes every
 * few seconds while on screen (SYNC-08).
 */
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
  // With the list on screen, not reaching the server is what the shopping view's status line
  // says; anything else (e.g. the list was deleted) is shown here.
  const unreachable = list.data !== undefined && list.error !== null && isUnreachable(list.error);
  const loadError = unreachable && list.data?.status === 'shopping' ? null : list.error;

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
      <ErrorAlert error={loadError ?? categories.error} />
      {list.data && categories.data && (
        <ListContent
          list={list.data}
          categoryKeys={new Map(categories.data.map((category) => [category.id, category.key]))}
          openPicker={initial.openPicker === true}
          unreachable={unreachable}
          onRefresh={() => void list.refetch()}
        />
      )}
    </Screen>
  );
}

interface ListContentProps {
  list: ListDetail;
  categoryKeys: ReadonlyMap<string, string>;
  openPicker: boolean;
  unreachable: boolean;
  onRefresh: () => void;
}

function ListContent({ list, categoryKeys, openPicker, unreachable, onRefresh }: ListContentProps) {
  const { t } = useTranslation();
  // Meals and extra items can change while shopping too (LIST-12); a done list is read-only.
  const editable = list.can_edit && list.status !== 'done';
  const draft = list.status === 'draft';
  const [pickerOpen, setPickerOpen] = useState(openPicker && editable && draft);
  const start = useStartShopping(list.id);
  const openPickerNow = () => setPickerOpen(true);

  return (
    <>
      <ListActions list={list} categoryKeys={categoryKeys} />
      {draft && list.can_edit && (
        <div className="flex flex-col gap-3">
          <Button
            data-testid={testIds.startShopping}
            disabled={start.isPending}
            onClick={() => start.mutate()}
            className="self-start"
          >
            <ShoppingCart aria-hidden="true" />
            {t('lists.shop.start')}
          </Button>
          <ErrorAlert error={start.error} />
        </div>
      )}
      {draft && (
        <>
          <ListMeals list={list} editable={editable} onAddMeals={openPickerNow} />
          {editable && <ExtraItemInput listId={list.id} />}
          <ListLines list={list} categoryKeys={categoryKeys} editable={editable} />
        </>
      )}
      {list.status === 'shopping' && (
        <ShoppingView
          list={list}
          categoryKeys={categoryKeys}
          unreachable={unreachable}
          onRefresh={onRefresh}
          onAddMeals={openPickerNow}
        />
      )}
      {list.status === 'done' && <DoneView list={list} categoryKeys={categoryKeys} />}
      {editable && <MealPicker listId={list.id} open={pickerOpen} onOpenChange={setPickerOpen} />}
    </>
  );
}
