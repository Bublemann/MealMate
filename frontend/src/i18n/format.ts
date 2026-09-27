import type { Language } from '.';

/** Formats follow the UI language (I18N-05); English uses day-first British formats. */
const LOCALES: Record<Language, string> = {
  de: 'de-DE',
  en: 'en-GB',
};

const DATE_OPTIONS: Intl.DateTimeFormatOptions = {
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
};

/** A number in the UI language; `-0` (which JSON can carry) is shown as `0`, never `-0`. */
export function formatNumber(
  value: number,
  language: Language,
  options?: Intl.NumberFormatOptions,
): string {
  return new Intl.NumberFormat(LOCALES[language], options).format(Object.is(value, -0) ? 0 : value);
}

const BYTE_UNITS = ['byte', 'kilobyte', 'megabyte', 'gigabyte', 'terabyte'] as const;

/**
 * `18.6 GB` (en) or `18,6 GB` (de), in decimal units as disks are labelled; one decimal below 10
 * of a unit, none above.
 */
export function formatBytes(bytes: number, language: Language): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < BYTE_UNITS.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return formatNumber(value, language, {
    style: 'unit',
    unit: BYTE_UNITS[unit],
    unitDisplay: 'short',
    maximumFractionDigits: value < 10 ? 1 : 0,
  });
}

/** `26.09.2026` (de) or `26/09/2026` (en), in the device's time zone. */
export function formatDate(date: Date | number | string, language: Language): string {
  return new Intl.DateTimeFormat(LOCALES[language], DATE_OPTIONS).format(new Date(date));
}

/**
 * `26.09.` (de) or `26/09` (en): a day in the current year, e.g. "bought on 26.09." (SHOP-05).
 * In the device's time zone unless `timeZone` is given (`'UTC'` for a calendar date such as
 * `2026-09-21`, which `Date` reads as midnight UTC).
 */
export function formatDayMonth(
  date: Date | number | string,
  language: Language,
  timeZone?: string,
): string {
  return new Intl.DateTimeFormat(LOCALES[language], {
    day: '2-digit',
    month: '2-digit',
    timeZone,
  }).format(new Date(date));
}

const DATE_TIME_OPTIONS: Intl.DateTimeFormatOptions = {
  ...DATE_OPTIONS,
  hour: '2-digit',
  minute: '2-digit',
};

/** `26.09.2026, 14:05` (de) or `26/09/2026, 14:05` (en), in the device's time zone. */
export function formatDateTime(date: Date | number | string, language: Language): string {
  return new Intl.DateTimeFormat(LOCALES[language], DATE_TIME_OPTIONS).format(new Date(date));
}

/** One run of digits with at most one decimal separator, which may be `,` or `.`. */
const AMOUNT_PATTERN = /^(?:\d+(?:[.,]\d*)?|[.,]\d+)$/;

/**
 * Parses a typed amount such as `1,5`, `1.5` or ` 2 `. Returns null for empty input, anything
 * that isn't a plain non-negative decimal, and numbers with more than one separator.
 */
export function parseAmount(input: string): number | null {
  const text = input.trim();
  if (!AMOUNT_PATTERN.test(text)) return null;
  const value = Number(text.replace(',', '.'));
  return Number.isFinite(value) ? value : null;
}

/** `a, b and c` (en) or `a, b und c` (de). */
export function formatList(items: readonly string[], language: Language): string {
  return new Intl.ListFormat(LOCALES[language], { type: 'conjunction' }).format(items);
}
