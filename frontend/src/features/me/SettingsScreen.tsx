import { ChevronRight } from 'lucide-react';
import { useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { ErrorAlert } from '@/components/ErrorAlert';
import { Screen } from '@/components/Screen';
import { useLogout } from '@/features/auth/api';
import { useCurrentUser } from '@/features/auth/context';
import { useSyncEngine, useSyncStatus } from '@/features/sync/context';
import { testIds } from '@/testIds';
import { useMeRefresh } from './api';
import {
  SETTINGS_GROUPS,
  SETTINGS_ROWS,
  type SettingsGroup,
  type SettingsRow,
} from './settingsRows';

/** The grouped panel the rows sit in, separated by lines. */
const PANEL = 'flex flex-col divide-y overflow-hidden rounded-xl border bg-card';

/**
 * The Settings tab (UI-07, D-45): its headline, then rows that each open their own page, in
 * groups; Abmelden last. The profile is loaded again as it opens, so a display name changed on
 * another device shows.
 */
export function SettingsScreen() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  useMeRefresh();
  const groups = SETTINGS_GROUPS.filter((group) => !group.adminOnly || user.role === 'admin');

  return (
    <Screen title={t('nav.me')} testId={testIds.screenMe}>
      {groups.map((group) => (
        <RowGroup
          key={group.id}
          group={group}
          rows={SETTINGS_ROWS.filter((row) => row.group === group.id)}
        />
      ))}
      <LogoutRow />
    </Screen>
  );
}

function RowGroup({ group, rows }: { group: SettingsGroup; rows: readonly SettingsRow[] }) {
  const { t } = useTranslation();
  const headingId = useId();
  const list = (
    <ul className={PANEL}>
      {rows.map((row) => (
        <li key={row.to}>
          <RowLink row={row} />
        </li>
      ))}
    </ul>
  );

  if (!group.heading) return list;
  return (
    <section aria-labelledby={headingId} data-testid={group.testId} className="flex flex-col gap-2">
      <h2 id={headingId} className="px-4 text-sm font-semibold text-muted-foreground">
        {t(group.heading)}
      </h2>
      {list}
    </section>
  );
}

function RowLink({ row: { label, to, value: Value } }: { row: SettingsRow }) {
  const { t } = useTranslation();

  return (
    <Link
      to={to}
      className="flex min-h-(--tap-target) items-center gap-3 px-4 py-3 outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset"
    >
      {/* The label first, so the accessible name starts with it; at large text sizes the value
          wraps below it. The space between them is for screen readers only. */}
      <span className="flex min-w-0 flex-1 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="font-medium wrap-anywhere">{t(label)}</span>{' '}
        {Value && (
          <span className="text-muted-foreground wrap-anywhere empty:hidden">
            <Value />
          </span>
        )}
      </span>
      <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-muted-foreground" />
    </Link>
  );
}

/**
 * Abmelden, the red, centred last row. With changes still waiting to be sent it asks first:
 * logging out deletes them with the local copy (SYNC-05, SYNC-10). The outbox is read before
 * deciding, so a tap right after the start can't skip the question.
 */
function LogoutRow() {
  const { t } = useTranslation();
  const logout = useLogout();
  const engine = useSyncEngine();
  const { pending } = useSyncStatus();
  const [confirming, setConfirming] = useState(false);

  async function onLogout() {
    if ((await engine.waitingCount()) > 0) setConfirming(true);
    else logout.mutate();
  }

  return (
    <div className="flex flex-col gap-2">
      <div className={PANEL}>
        <button
          type="button"
          data-testid={testIds.logoutButton}
          disabled={logout.isPending}
          onClick={() => void onLogout()}
          className="min-h-(--tap-target) px-4 py-3 text-center font-medium text-destructive outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset disabled:opacity-50"
        >
          {t('me.logout')}
        </button>
      </div>
      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('me.logoutPending.title', { count: pending })}
        description={t('me.logoutPending.text')}
        confirmLabel={t('me.logoutPending.confirm')}
        destructive
        onConfirm={() => logout.mutate()}
      />
      <ErrorAlert error={logout.error} />
    </div>
  );
}
