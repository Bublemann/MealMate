import type { TFunction } from 'i18next';
import type { Language } from '@/i18n';
import { formatCalendarDay } from '@/i18n/format';
import type { DueItem, RecurringItem } from './api';

// The words of a recurring item, from the display values the server computed (MNT-02): the
// frontend only picks the sentence, it never counts days or rounds an interval.

/** "alle ~4 Wochen" while it adapts, "alle 2 Wochen" when set by hand, "alle ~5 Tage". */
export function intervalText(t: TFunction, { value, unit, automatic }: RecurringItem['interval']) {
  if (unit === 'day') {
    return automatic
      ? t('recurring.interval.daysAuto', { count: value })
      : t('recurring.interval.days', { count: value });
  }
  return automatic
    ? t('recurring.interval.weeksAuto', { count: value })
    : t('recurring.interval.weeks', { count: value });
}

/** "fällig heute", "fällig morgen", "fällig in 5 Tagen" or "fällig seit 3 Tagen". */
export function dueText(t: TFunction, daysUntilDue: number) {
  if (daysUntilDue === 0) return t('recurring.due.today');
  if (daysUntilDue === 1) return t('recurring.due.tomorrow');
  if (daysUntilDue > 1) return t('recurring.due.in', { count: daysUntilDue });
  return t('recurring.due.since', { count: -daysUntilDue });
}

/** "zuletzt 02.10.", with the year when it isn't this year's. */
export function lastBoughtText(t: TFunction, language: Language, lastPurchasedOn: string) {
  return t('recurring.lastBought', { date: formatCalendarDay(lastPurchasedOn, language) });
}

/** The grey line of a row: "alle ~4 Wochen · zuletzt 02.10. · fällig in 5 Tagen". */
export function recurringLine(t: TFunction, language: Language, item: RecurringItem) {
  return [
    intervalText(t, item.interval),
    lastBoughtText(t, language, item.last_purchased_on),
    dueText(t, item.days_until_due),
  ].join(' · ');
}

/** The grey line of a due item in a draft's "Fällig" box: "fällig seit 3 Tagen · zuletzt 02.10.". */
export function dueLine(t: TFunction, language: Language, item: DueItem) {
  return [
    dueText(t, item.days_until_due),
    lastBoughtText(t, language, item.last_purchased_on),
  ].join(' · ');
}
