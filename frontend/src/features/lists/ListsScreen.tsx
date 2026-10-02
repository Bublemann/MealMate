import {
  ChevronRight,
  CircleCheck,
  Lock,
  ShoppingCart,
  Users,
  type LucideIcon,
} from 'lucide-react';
import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { EmptyLine } from '@/components/EmptyLine';
import { ErrorAlert } from '@/components/ErrorAlert';
import { InitialMarker } from '@/components/InitialMarker';
import { LoadError } from '@/components/LoadError';
import { LoadingState } from '@/components/LoadingState';
import { OfflineNotice } from '@/components/OfflineNotice';
import { PinnedBlock } from '@/components/PinnedBlock';
import { Screen } from '@/components/Screen';
import { useCouple } from '@/features/couple/api';
import { FirstLoginHints } from '@/features/hints/FirstLoginHints';
import { useConnected, usePendingFinishes, useSyncEngine } from '@/features/sync/context';
import { SyncIndicator } from '@/features/sync/SyncIndicator';
import { useLanguage } from '@/i18n';
import { formatDayMonth } from '@/i18n/format';
import { userLabel } from '@/i18n/users';
import { cn } from '@/lib/utils';
import { testIds } from '@/testIds';
import { useCreateList, useListFeed, type ListSummary } from './api';
import { listDisplayName } from './format';
import type { ListViewState } from './ListScreen';

/**
 * The Lists tab, where the app opens (UI-02, UI-03): the pinned block with the "New list" tile,
 * the first-login hints and the sync notice, then the list feed: every list I can see, in every
 * state, newest created first, the next 30 as I scroll down.
 */
export function ListsScreen() {
  const { t } = useTranslation();

  return (
    <Screen variant="tab" title={t('nav.lists')} testId={testIds.screenLists}>
      <NewList />
      {/* Only when there is something to say: offline, or changes waiting (SYNC-07). */}
      <SyncIndicator quiet />
      <FirstLoginHints />
      <ListFeed />
    </Screen>
  );
}

/**
 * LIST-01: the "New list" tile creates a draft right away and opens it with the meal picker.
 * Creating a list needs the server, so offline the tile is disabled rather than failing on a tap.
 */
function NewList() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const create = useCreateList();
  const connected = useConnected();

  function newList() {
    create.mutate(undefined, {
      onSuccess: (list) => {
        const state: ListViewState = { openPicker: true };
        void navigate(`/lists/${list.id}`, { state });
      },
    });
  }

  return (
    <>
      <PinnedBlock
        newTile={{
          label: t('lists.new'),
          onClick: newList,
          disabled: !connected || create.isPending,
          testId: testIds.newList,
        }}
      />
      <ErrorAlert error={create.error} />
    </>
  );
}

/**
 * The feed below the pinned block (UI-02). Until the server's first page arrives it is the local
 * copy (SYNC-09); offline it is only the local copy, because read-only and done lists need a
 * connection. A list finished here whose finish hasn't been sent yet stays hidden.
 */
function ListFeed() {
  const { t } = useTranslation();
  const engine = useSyncEngine();
  const feed = useListFeed();
  const connected = useConnected();
  const finishing = usePendingFinishes();
  const lists = connected
    ? feed.data?.pages.flatMap((page) => page.lists)
    : engine.copiedSummaries();

  if (!lists) {
    if (feed.error) return <LoadError error={feed.error} />;
    // Offline before the copy was ever complete: the server's lists need a connection.
    if (!connected && feed.data) {
      return <OfflineNotice message={t('sync.offline.page')} testId={testIds.offlineNotice} />;
    }
    // Until the first answer (or the copy) it is unknown whether there are lists at all.
    return <LoadingState />;
  }
  const shown = lists.filter((list) => !finishing.has(list.id));
  if (shown.length === 0) return <EmptyLine text={t('lists.empty')} />;

  return (
    <div className="flex flex-col gap-3">
      {/* E.g. the first page failed while the copy is shown; offline the sync notice says it. */}
      <LoadError error={connected && !feed.isFetchNextPageError ? feed.error : null} />
      <ul
        data-testid={testIds.listFeed}
        aria-label={t('lists.feedLabel')}
        className="flex flex-col divide-y rounded-xl border bg-card"
      >
        {shown.map((list) => (
          <li key={list.id}>
            <ListRow list={list} />
          </li>
        ))}
      </ul>
      {connected && feed.hasNextPage && (
        <FeedEnd
          onReached={feed.fetchNextPage}
          // Not while the feed loads (a page, or all of them again), nor right after a page
          // failed: that would ask again and again. The next load of the feed resumes it.
          paused={feed.isFetching || feed.isFetchNextPageError}
          loading={feed.isFetchingNextPage}
        />
      )}
      <LoadError error={connected && feed.isFetchNextPageError ? feed.error : null} />
    </div>
  );
}

interface FeedEndProps {
  onReached: () => unknown;
  paused: boolean;
  loading: boolean;
}

/**
 * The end of the loaded part of the feed: when it comes near the screen, the next page is loaded
 * (UI-02). The observer starts again after every load, so it reports the end again if it is
 * still in view.
 */
function FeedEnd({ onReached, paused, loading }: FeedEndProps) {
  const { t } = useTranslation();
  const end = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    const target = end.current;
    if (!target || paused || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) onReached();
      },
      { rootMargin: '0px 0px 50% 0px' },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [onReached, paused]);

  return (
    <p ref={end} role="status" className="text-muted-foreground">
      {loading ? t('common.loading') : null}
    </p>
  );
}

/**
 * One list (UI-02): the owner's initial, the name and date, icons for a shared list, a read-only
 * one, one being shopped and a done one, and "3 meals · 5 items" with who shares it or whose it
 * is and when it was bought. The partner's name comes with the couple.
 */
function ListRow({ list }: { list: ListSummary }) {
  const { t } = useTranslation();
  const language = useLanguage();
  const partner = useCouple().data?.partner;
  // My list shared with my partner, or my partner's that I may change.
  const shared = list.is_owner ? list.shared_with_partner : list.can_edit;
  const details = [
    t('lists.card.meals', { count: list.meal_count }),
    t('lists.card.items', { count: list.line_count }),
    list.is_owner
      ? shared && partner
        ? t('lists.card.sharedWith', { name: userLabel(t, partner) })
        : null
      : t(shared ? 'lists.card.sharedBy' : 'lists.card.by', { name: userLabel(t, list.owner) }),
    list.status === 'done' && list.finished_at
      ? t('lists.card.boughtOn', { date: formatDayMonth(list.finished_at, language) })
      : null,
  ].filter((detail) => detail !== null);

  return (
    <Link
      to={`/lists/${list.id}`}
      data-testid={testIds.listCard}
      className="flex min-h-(--tap-target) items-center gap-3 px-4 py-3 outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
    >
      <InitialMarker user={list.owner} />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="font-medium break-words">{listDisplayName(list, t, language)}</span>
        <span className="text-sm text-muted-foreground">{details.join(' · ')}</span>
      </span>
      <span className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
        {shared && <RowIcon icon={Users} label={t('lists.card.shared')} />}
        {!list.can_edit && <RowIcon icon={Lock} label={t('lists.card.readOnly')} />}
        {list.status === 'shopping' && (
          <RowIcon icon={ShoppingCart} label={t('lists.card.shopping')} className="text-primary" />
        )}
        {list.status === 'done' && <RowIcon icon={CircleCheck} label={t('lists.card.done')} />}
      </span>
      <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
    </Link>
  );
}

/** An icon that marks the kind of list; screen readers read its name. */
function RowIcon({
  icon: Icon,
  label,
  className,
}: {
  icon: LucideIcon;
  label: string;
  className?: string;
}) {
  return (
    <span role="img" aria-label={label} className={cn('flex', className)}>
      <Icon aria-hidden="true" className="size-5" />
    </span>
  );
}
