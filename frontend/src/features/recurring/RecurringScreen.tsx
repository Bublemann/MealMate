import { Info, X } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ErrorAlert } from '@/components/ErrorAlert';
import { LoadError } from '@/components/LoadError';
import { IngredientName } from '@/features/ingredients/IngredientName';
import { ingredientLabel } from '@/features/ingredients/label';
import { SettingsPage } from '@/features/me/SettingsPage';
import { useLanguage } from '@/i18n';
import { testIds } from '@/testIds';
import {
  useDismissNotice,
  useNotices,
  useRecurringItems,
  type Notice,
  type RecurringItem,
} from './api';
import { recurringLine } from './format';
import { RecurringDialog, type RecurringTarget } from './RecurringDialog';

/** The grouped panel the rows sit in, as on the Settings tab. */
const PANEL = 'flex flex-col divide-y overflow-hidden rounded-xl border bg-card';
const ROW_FOCUS =
  'outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-inset';

/** Settings → Regelmäßige Artikel (UI-07, D-45, LIST-16). */
export function RecurringScreen() {
  const { t } = useTranslation();
  const items = useRecurringItems();
  const notices = useNotices();
  const empty = items.data?.items.length === 0 && notices.data?.count === 0;
  const [target, setTarget] = useState<RecurringTarget | null>(null);

  return (
    <SettingsPage title={t('recurring.title')} testId={testIds.screenRecurring}>
      {notices.data && notices.data.notices.length > 0 && (
        <NoticeList notices={notices.data.notices} />
      )}
      {items.isPending && <p className="text-muted-foreground">{t('common.loading')}</p>}
      <LoadError error={items.error} />
      {items.data && items.data.items.length > 0 && (
        <ItemList
          items={items.data.items}
          onOpen={(item) => setTarget({ ingredient: item.ingredient, item })}
        />
      )}
      {empty && <p className="text-muted-foreground">{t('recurring.empty')}</p>}
      <RecurringDialog target={target} onClose={() => setTarget(null)} />
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
    <ul aria-label={t('recurring.items')} data-testid={testIds.recurringList} className={PANEL}>
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            data-testid={testIds.recurringItem}
            onClick={() => onOpen(item)}
            className={`flex min-h-(--tap-target) w-full flex-col items-start px-4 py-3 text-left ${ROW_FOCUS}`}
          >
            <IngredientName ingredient={item.ingredient} />
            <span className="text-sm text-muted-foreground">
              {recurringLine(t, language, item)}
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
          const name = ingredientLabel(notice.params.name ?? '', notice.params.brand ?? null);
          return (
            <li
              key={notice.id}
              className="flex items-start gap-3 rounded-xl border bg-card py-1 pr-1 pl-4"
            >
              <Info aria-hidden="true" className="mt-3 size-5 shrink-0 text-primary" />
              <p className="flex-1 py-2.5">{t('recurring.noticeDeleted', { name })}</p>
              <button
                type="button"
                data-testid={testIds.dismissNotice}
                aria-label={t('recurring.dismissNotice', { name })}
                disabled={dismiss.isPending}
                onClick={() => dismiss.mutate(notice.id)}
                className="flex size-(--tap-target) shrink-0 items-center justify-center rounded-md text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring disabled:opacity-50"
              >
                <X aria-hidden="true" className="size-5" />
              </button>
            </li>
          );
        })}
      </ul>
      <ErrorAlert error={dismiss.error} />
    </div>
  );
}
