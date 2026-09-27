/** A calendar date as `YYYY-MM-DD`. */
export type CalendarDate = string;

export interface WeekGroup<List> {
  /** The Monday the ISO week starts on, in the viewer's time zone. */
  monday: CalendarDate;
  lists: List[];
}

const PARTS_FORMAT = new Map<string, Intl.DateTimeFormat>();

function partsFormat(timeZone: string | undefined): Intl.DateTimeFormat {
  const key = timeZone ?? '';
  let format = PARTS_FORMAT.get(key);
  if (!format) {
    format = new Intl.DateTimeFormat('en-US', {
      timeZone,
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
    });
    PARTS_FORMAT.set(key, format);
  }
  return format;
}

/** The Monday of the ISO week `instant` falls into, as seen in `timeZone` (default: device). */
export function mondayOf(instant: string, timeZone?: string): CalendarDate {
  const parts = partsFormat(timeZone).formatToParts(new Date(instant));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    Number(parts.find((entry) => entry.type === type)?.value);
  // The local calendar day, then back to Monday in plain date arithmetic (UTC has no DST).
  const day = new Date(Date.UTC(part('year'), part('month') - 1, part('day')));
  const sinceMonday = (day.getUTCDay() + 6) % 7;
  day.setUTCDate(day.getUTCDate() - sinceMonday);
  return day.toISOString().slice(0, 10);
}

/**
 * SHOP-05: done lists grouped by the week they were finished in (ISO weeks, Monday first, in the
 * viewer's time zone). The lists keep the server's order (newest first), and so do the weeks.
 * Lists without `finished_at` are left out.
 */
export function groupByWeek<List extends { finished_at?: string | null }>(
  lists: readonly List[],
  timeZone?: string,
): WeekGroup<List>[] {
  const groups: WeekGroup<List>[] = [];
  const byMonday = new Map<CalendarDate, WeekGroup<List>>();
  for (const list of lists) {
    if (!list.finished_at) continue;
    const monday = mondayOf(list.finished_at, timeZone);
    let group = byMonday.get(monday);
    if (!group) {
      group = { monday, lists: [] };
      byMonday.set(monday, group);
      groups.push(group);
    }
    group.lists.push(list);
  }
  return groups;
}
