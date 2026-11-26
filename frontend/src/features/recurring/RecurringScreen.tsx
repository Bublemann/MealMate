import { Info, X } from 'lucide-react';
import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { LoadError } from '@/components/LoadError';
import { LoadingState } from '@/components/LoadingState';
import { Button } from '@/components/ui/button';
import { ItemName } from '@/features/items/ItemName';
import { itemLabel } from '@/features/items/label';
import { SettingsPage } from '@/features/me/SettingsPage';
import { SETTINGS_PANEL, SETTINGS_ROW_FOCUS } from '@/features/me/settingsPanel';
import { useConnected } from '@/features/sync/context';
import { useLanguage } from '@/i18n';
import { testIds } from '@/testIds';
import {
  itemOf,
  useDismissNotice,
  useNotices,
  useRecurringItems,
  type Notice,
  type RecurringItem,
} from './api';
import { recurringLine } from './format';
import { RecurringDialog, type RecurringTarget } from './RecurringDialog';
import { RecurringItemField } from './RecurringItemField';

/**
 * Settings → Regelmäßige Artikel (UI-07, D-45, LIST-16): unread notices first (D-51), then the
 * item field, then the set in the server's order, due first. A picked item, or a
 * tapped row, opens the recurring pop-up; one that is recurring already opens for editing. The
 * page needs a connection (SYNC-09).
 */
export function RecurringScreen() {
  const { t } = useTranslation();
  const connected = useConnected();
  const items = useRecurringItems();
  const notices = useNotices();
  // The hint waits for the notices too, but not on them: one that failed to load hides nothing.
  const empty = items.data?.items.length === 0 && !notices.isPending && !notices.data?.count;
  const [query, setQuery] = useState('');
  const fieldRef = useRef<HTMLInputElement>(null);
  const [target, setTarget] = useState<RecurringTarget | null>(null);
  /** The pop-up was opened from the field, which gets the focus back when it closes. */
  const [fromField, setFromField] = useState(false);

  function open(next: RecurringTarget, field: boolean) {
    setFromField(field);
    setTarget(next);
  }

  return (
    <SettingsPage title={t('recurring.title')} testId={testIds.screenRecurring}>
      {notices.data && notices.data.notices.length > 0 && (
        <NoticeList notices={notices.data.notices} />
      )}
      <RecurringItemField
        value={query}
        onValueChange={setQuery}
        onPick={(item) => open({ item, recurring: itemOf(items.data, item.id) }, true)}
        disabled={!connected || !items.data}
        inputRef={fieldRef}
      />
      {items.isPending && <LoadingState />}
      <LoadError error={items.error} />
      {items.data && items.data.items.length > 0 && (
        <ItemList
          items={items.data.items}
          onOpen={(recurring) => open({ item: recurring.item, recurring }, false)}
        />
      )}
      {empty && <p className="text-muted-foreground">{t('recurring.empty')}</p>}
      <RecurringDialog
        target={target}
        onClose={() => setTarget(null)}
        // Added from the field: it empties for the next one (D-41).
        onDone={() => fromField && setQuery('')}
        onCloseAutoFocus={(event) => {
          if (!fromField) return;
          event.preventDefault();
          fieldRef.current?.focus();
        }}
      />
    </SettingsPage>
  );
}

function ItemList({
  items,
  onOpen,
}: {
  items: readonly RecurringItem[];
  onOpen: (item: RecurringItem) => void;
}) {
  const { t } = useTranslation();
  const language = useLanguage();

  return (
    <ul
      aria-label={t('recurring.items')}
      data-testid={testIds.recurringList}
      className={SETTINGS_PANEL}
    >
      {items.map((recurring) => (
        <li key={recurring.id}>
          <button
            type="button"
            data-testid={testIds.recurringItem}
            onClick={() => onOpen(recurring)}
            className={`flex min-h-(--tap-target) w-full flex-col items-start px-4 py-3 text-left ${SETTINGS_ROW_FOCUS}`}
          >
            <ItemName item={recurring.item} />
            <span className="text-sm text-muted-foreground">
              {recurringLine(t, language, recurring)}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

/**
 * The unread notices at the top of the page (D-51), each with a ✕ that dismisses it for this user
 * only. The backend sends the kind and its parameters; the words are the app's (I18N-03).
 */
function NoticeList({ notices }: { notices: readonly Notice[] }) {
  const { t } = useTranslation();
  const dismiss = useDismissNotice();

  return (
    <div data-testid={testIds.recurringNotices} className="flex flex-col gap-2">
      <ul aria-label={t('recurring.notices')} className="flex flex-col gap-2">
        {notices.map((notice) => {
          const name = itemLabel(notice.params.name ?? '', notice.params.brand ?? null);
          return (
            <li
              key={notice.id}
              className="flex items-start gap-3 rounded-xl border bg-card py-1 pr-1 pl-4"
            >
              <Info aria-hidden="true" className="mt-3 size-5 shrink-0 text-primary" />
              <p className="flex-1 py-2.5">{t('recurring.noticeDeleted', { name })}</p>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                data-testid={testIds.dismissNotice}
                aria-label={t('recurring.dismissNotice', { name })}
                pending={dismiss.isPending && dismiss.variables === notice.id}
                disabled={dismiss.isPending}
                onClick={() => dismiss.mutate(notice.id)}
                className="text-muted-foreground"
              >
                <X aria-hidden="true" />
              </Button>
            </li>
          );
        })}
      </ul>
      <ErrorAlert error={dismiss.error} />
    </div>
  );
}
