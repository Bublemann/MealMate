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

export function formatNumber(
  value: number,
  language: Language,
  options?: Intl.NumberFormatOptions,
): string {
  return new Intl.NumberFormat(LOCALES[language], options).format(value);
}

/** `26.09.2026` (de) or `26/09/2026` (en), in the device's time zone. */
export function formatDate(date: Date | number | string, language: Language): string {
  return new Intl.DateTimeFormat(LOCALES[language], DATE_OPTIONS).format(new Date(date));
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
