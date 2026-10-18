import { useTranslation } from 'react-i18next';
import { useNotices, useRecurringItems } from './api';

/**
 * The value of the row "Regelmäßige Artikel" on the Settings tab (UI-07, D-45, D-51): "1 Hinweis"
 * while notices are unread, "2 fällig" while items are due, both when both apply, else nothing.
 * Each part shows once its own query has answered.
 */
export function RecurringValue() {
  const { t } = useTranslation();
  const notices = useNotices().data?.count ?? 0;
  const due = useRecurringItems().data?.due_count ?? 0;
  const parts = [
    notices > 0 ? t('recurring.noticeCount', { count: notices }) : null,
    due > 0 ? t('recurring.dueCount', { count: due }) : null,
  ].filter((part) => part !== null);
  return parts.length > 0 ? parts.join(' · ') : null;
}
