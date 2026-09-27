import { ChevronRight, ListChecks, Plus } from 'lucide-react';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { EmptyState } from '@/components/EmptyState';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Screen } from '@/components/Screen';
import { UserFilterChips } from '@/components/UserFilterChips';
import { Button } from '@/components/ui/button';
import { useCurrentUser } from '@/features/auth/context';
import { useCouple } from '@/features/couple/api';
import { FirstLoginHints } from '@/features/hints/FirstLoginHints';
import { useLanguage } from '@/i18n';
import { userLabel } from '@/i18n/users';
import { testIds, type TestId } from '@/testIds';
import { useCreateList, useListUsers, useLists, useToggleListChip, type ListSummary } from './api';
import { listDisplayName } from './format';
import type { ListViewState } from './ListScreen';

/**
 * The Lists tab, where the app opens (UI-02): "+ New list" and my drafts (mine and the partner's
 * shared ones), most recently edited first, then others' lists with their own user chips.
 */
export function ListsScreen() {
  const { t } = useTranslation();

  return (
    <Screen title={t('nav.lists')} testId={testIds.screenLists}>
      <FirstLoginHints />
      {/* M5b: the "Continue shopping" card for a list being shopped goes here (UI-02). */}
      <MyLists />
      {/* M5b: the entry to the history goes here, between my lists and others' (UI-02). */}
      <OthersLists />
    </Screen>
  );
}

/** LIST-01: "+ New list" creates a draft right away and opens it with the meal picker. */
function MyLists() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const headingId = useId();
  const lists = useLists('mine');
  const create = useCreateList();

  function newList() {
    create.mutate(undefined, {
      onSuccess: (list) => {
        const state: ListViewState = { openPicker: true };
        void navigate(`/lists/${list.id}`, { state });
      },
    });
  }

  if (lists.data?.length === 0) {
    return (
      <div className="flex flex-col gap-3">
        <EmptyState
          icon={ListChecks}
          title={t('lists.empty.title')}
          text={t('lists.empty.text')}
          actionLabel={t('lists.empty.action')}
          onAction={create.isPending ? undefined : newList}
          actionTestId={testIds.newList}
        />
        <ErrorAlert error={create.error} />
      </div>
    );
  }

  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4">
      <Button
        data-testid={testIds.newList}
        onClick={newList}
        disabled={create.isPending}
        className="self-start"
      >
        <Plus aria-hidden="true" />
        {t('lists.new')}
      </Button>
      <ErrorAlert error={create.error} />
      <h2 id={headingId} className="text-xl font-semibold">
        {t('lists.mine.title')}
      </h2>
      {lists.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <ErrorAlert error={lists.error} />
      {lists.data && <ListCards lists={lists.data} testId={testIds.listDrafts} />}
    </section>
  );
}

/**
 * Other users' lists I may look at (public ones, and my partner's unshared ones), read-only,
 * with one chip per user; the choice is saved separately from the meal chips (UI-02, VIS-02).
 * There is no chip for me: my own lists are never here.
 */
function OthersLists() {
  const { t } = useTranslation();
  const headingId = useId();
  const user = useCurrentUser();
  const users = useListUsers();
  const lists = useLists('others');
  const toggle = useToggleListChip();
  const hidden = user.filter_hidden.lists;
  const others = users.data?.filter((person) => person.id !== user.id);
  // The server leaves out hidden owners; a chip switched off just now hides them right away.
  const shown = lists.data?.filter((list) => !hidden.includes(list.owner.id));

  return (
    <section
      aria-labelledby={headingId}
      data-testid={testIds.othersLists}
      className="flex flex-col gap-3"
    >
      <div className="flex flex-col gap-1">
        <h2 id={headingId} className="text-xl font-semibold">
          {t('lists.others.title')}
        </h2>
        <p className="text-muted-foreground">{t('lists.others.text')}</p>
      </div>
      <ErrorAlert error={users.error} />
      {others && others.length > 0 && (
        <div className="flex flex-col gap-2">
          <UserFilterChips
            users={others}
            hidden={hidden}
            meId={user.id}
            meLabel={t('meals.chips.me')}
            label={t('lists.chips.label')}
            testId={testIds.listUserChips}
            onChange={(next) => toggle.mutate(next)}
          />
          <ErrorAlert error={toggle.error} />
        </div>
      )}
      {lists.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <ErrorAlert error={lists.error} />
      {shown && shown.length === 0 && (
        <p className="text-muted-foreground">
          {others?.some((person) => hidden.includes(person.id))
            ? t('lists.others.noneShown')
            : t('lists.others.empty')}
        </p>
      )}
      {shown && shown.length > 0 && <ListCards lists={shown} />}
    </section>
  );
}

function ListCards({ lists, testId }: { lists: ListSummary[]; testId?: TestId }) {
  return (
    <ul data-testid={testId} className="flex flex-col divide-y rounded-xl border bg-card">
      {lists.map((list) => (
        <li key={list.id}>
          <ListCard list={list} />
        </li>
      ))}
    </ul>
  );
}

function ListCard({ list }: { list: ListSummary }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const couple = useCouple();
  const partner = couple.data?.partner;
  const details = [
    t('lists.card.meals', { count: list.meal_count }),
    t('lists.card.items', { count: list.line_count }),
    list.is_owner
      ? list.shared_with_partner && partner
        ? t('lists.card.sharedWith', { name: userLabel(t, partner) })
        : null
      : t('lists.card.by', { name: userLabel(t, list.owner) }),
  ].filter((detail) => detail !== null);

  return (
    <Link
      to={`/lists/${list.id}`}
      data-testid={testIds.listCard}
      className="flex min-h-(--tap-target) items-center gap-3 px-4 py-3 outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
    >
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="font-medium break-words">{listDisplayName(list, t, language)}</span>
        <span className="text-sm text-muted-foreground">{details.join(' · ')}</span>
      </span>
      <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
    </Link>
  );
}
