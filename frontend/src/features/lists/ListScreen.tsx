import { ShoppingCart } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation, useNavigate, useParams } from 'react-router';
import { ErrorAlert } from '@/components/ErrorAlert';
import { FloatingBar, FloatingBarButton } from '@/components/FloatingBar';
import { LoadError } from '@/components/LoadError';
import { Screen } from '@/components/Screen';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card } from '@/components/ui/card';
import { useCategories, type Category } from '@/features/reference/api';
import type { PendingList } from '@/features/sync/applyPending';
import { useConnected, usePendingList, useSyncEngine } from '@/features/sync/context';
import { ListOfflineBanner } from '@/features/sync/ListOfflineBanner';
import { SyncIndicator } from '@/features/sync/SyncIndicator';
import { useLanguage } from '@/i18n';
import { userLabel } from '@/i18n/users';
import { testIds } from '@/testIds';
import { isUnreachable, useList, useStartShopping } from './api';
import { DoneView } from './DoneView';
import { listDisplayName } from './format';
import { ListLines } from './ListLines';
import { ItemField } from './ItemField';
import { ListMeals } from './ListMeals';
import { MealField } from './MealField';
import { ListMenu, ListNotices, type ListNotice } from './ListMenu';
import { ShoppingView } from './ShoppingView';

/** Passed along when navigating to a list, e.g. from "+ New list" or a copy. */
export interface ListViewState {
  /** Show the meal field's list right away, keyboard closed ("New list", LIST-01). */
  showMeals?: boolean;
  /** Meals a copy left out (VIS-03/06). */
  leftOut?: number;
  /** A meal created from the meal field could not be added (translated message). */
  addMealError?: string;
  /** A meal created from the meal field was saved without its photo (translated message). */
  photoError?: string;
}

function viewState(state: unknown): ListViewState {
  if (typeof state !== 'object' || state === null) return {};
  const { showMeals, leftOut, addMealError, photoError } = state as Record<string, unknown>;
  return {
    showMeals: showMeals === true,
    leftOut: typeof leftOut === 'number' ? leftOut : undefined,
    addMealError: typeof addMealError === 'string' ? addMealError : undefined,
    photoError: typeof photoError === 'string' ? photoError : undefined,
  };
}

/**
 * `/lists/:id`: one list, editable for its editors, read-only for everyone else; a draft, the
 * shopping view or a done list by its state (LIST-10, plan § 8). It is checked for changes every
 * few seconds while on screen (SYNC-08). It shows the local copy until the server answers and
 * while it can't be reached, with the user's waiting changes on top (SYNC-03/09).
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
  const shown = usePendingList(list.data);
  const categories = useCategories();
  const engine = useSyncEngine();
  // Read once: the state is removed from the history entry, so a reload doesn't repeat it.
  const [initial] = useState(() => viewState(location.state));
  const [notice, setNotice] = useState<ListNotice>(null);
  const title = list.data ? listDisplayName(list.data, t, language) : t('nav.lists');
  // With the list on screen, not reaching the server is what the sync indicator and the offline
  // banner say; anything else (e.g. the list was deleted) is shown here. Without the list (not in
  // the copy) it is a friendly offline message.
  const unreachable = list.data !== undefined && list.error !== null && isUnreachable(list.error);
  const loadError = unreachable ? null : list.error;

  useEffect(() => {
    if (location.state !== null && location.state !== undefined) {
      void navigate(`${location.pathname}${location.search}`, { replace: true, state: null });
    }
  }, [location.state, location.pathname, location.search, navigate]);

  return (
    <Screen
      title={title}
      testId={testIds.screenList}
      back={{ to: '/lists', label: t('lists.detail.back') }}
      action={
        shown &&
        categories.data && (
          <ListMenu list={shown} categories={categories.data} onNotice={setNotice} />
        )
      }
    >
      <ListNotices notice={notice} />
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
      <LoadError error={loadError ?? categories.error} />
      {shown && categories.data && (
        <ListContent
          list={shown}
          categories={categories.data}
          showMeals={initial.showMeals === true}
          onRefresh={() => {
            void engine.flush();
            void list.refetch();
          }}
        />
      )}
    </Screen>
  );
}

interface ListContentProps {
  list: PendingList;
  categories: readonly Category[];
  showMeals: boolean;
  onRefresh: () => void;
}

/**
 * A draft has two sections, Gerichte and Artikel, each starting with its add field for editors
 * (LIST-05, D-41); offline both fields are inactive (SYNC-03). While shopping and on a done list
 * the views lay the sections out themselves.
 */
function ListContent({ list, categories, showMeals, onRefresh }: ListContentProps) {
  const { t } = useTranslation();
  const connected = useConnected();
  // Meals and extra items can change while shopping too (LIST-12); a done list is read-only.
  const editable = list.can_edit && list.status !== 'done';
  const draft = list.status === 'draft';
  const start = useStartShopping(list.id);

  return (
    <>
      {/* SYNC-07, SHOP-03; "Refresh" while shopping, when the partner's changes matter most. */}
      <SyncIndicator onRefresh={list.status === 'shopping' ? onRefresh : undefined} />
      <ListOfflineBanner shopping={list.status === 'shopping' && list.can_edit} />
      {!list.can_edit && (
        <Card data-testid={testIds.listReadOnly} className="px-5 py-4">
          <p>{t('lists.detail.readOnly', { name: userLabel(t, list.owner) })}</p>
        </Card>
      )}
      {draft && (
        <>
          <ListMeals
            list={list}
            editable={editable}
            field={
              editable && (
                <MealField listId={list.id} disabled={!connected} openOnStart={showMeals} />
              )
            }
          />
          <ListLines
            list={list}
            categories={categories}
            editable={editable}
            top={editable && <ItemField listId={list.id} />}
          />
        </>
      )}
      {list.status === 'shopping' && <ShoppingView list={list} categories={categories} />}
      {list.status === 'done' && <DoneView list={list} categories={categories} />}
      {draft && list.can_edit && (
        // Inactive offline and while starting; its error shows here, where it was tapped (D-39).
        <FloatingBar>
          <ErrorAlert error={start.error} />
          <FloatingBarButton
            data-testid={testIds.startShopping}
            disabled={start.isPending || !connected}
            onClick={() => start.mutate()}
          >
            <ShoppingCart aria-hidden="true" />
            {t('lists.shop.start')}
          </FloatingBarButton>
        </FloatingBar>
      )}
    </>
  );
}
