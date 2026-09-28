import type { TFunction } from 'i18next';
import { ingredientLabel } from '@/features/ingredients/label';
import { categoryName, unitLabel } from '@/features/reference/labels';
import type { Language } from '@/i18n';
import { formatDate, formatNumber } from '@/i18n/format';

// Only formatting happens here: amounts, units and their rounding come from the backend
// (AGG-01, MNT-02), the frontend puts them into words in the viewer's language.

/** Joins the amounts of one line: "500 g + 2 pcs" (AGG-03). */
const AMOUNT_SEPARATOR = ' + ';

/**
 * LIST-02: `<name> (<creation date>)`, e.g. "Grillabend (26.09.2026)". A list without a name of
 * its own gets the translated default in the viewer's language.
 */
export function listDisplayName(
  list: { name: string | null; created_at: string },
  t: TFunction,
  language: Language,
): string {
  return t('lists.displayName', {
    name: list.name ?? t('lists.defaultName'),
    date: formatDate(list.created_at, language),
  });
}

/**
 * A line's name as shown and exported: "Milch (Weidehof)". Two brands of the same thing are
 * separate lines, so the brand tells them apart; a free-text line has none.
 */
export function lineLabel(line: { name: string; brand: string | null }): string {
  return ingredientLabel(line.name, line.brand);
}

/** "550 g", "1,5 kg" (de) or "1.5 kg" (en), "2 Stk." / "2 pcs". */
export function formatAmount(
  t: TFunction,
  language: Language,
  value: number,
  unit: string | null,
): string {
  return t('common.amount', {
    value: formatNumber(value, language, { maximumFractionDigits: 2 }),
    unit: unit ? unitLabel(t, unit) : '',
  }).trim();
}

interface LineAmounts {
  kind: string;
  amounts: readonly { value: number; unit: string }[];
  has_unspecified: boolean;
  amount_text: string | null;
}

/**
 * What to buy of a line (AGG-03): its display amounts side by side ("500 g + 2 pcs"), followed by
 * "+ some" when parts without an amount come on top, or a free-text item's own amount. Empty when
 * there is nothing to say, as for a line whose parts all come without an amount ("Salt").
 */
export function lineAmount(t: TFunction, language: Language, line: LineAmounts): string {
  if (line.kind === 'text') return line.amount_text ?? '';
  const parts = line.amounts.map(({ value, unit }) => formatAmount(t, language, value, unit));
  if (!line.has_unspecified || parts.length === 0) return parts.join(AMOUNT_SEPARATOR);
  return `${parts.join(AMOUNT_SEPARATOR)} ${t('lists.lines.plusSome')}`;
}

/**
 * A source's own amount, where the server gives one (LIST-08): an extra item's amount or its
 * free-text amount. Meals are named with their servings instead; empty when there is nothing.
 */
export function sourceAmount(
  t: TFunction,
  language: Language,
  source: { amount: number | null; unit: string | null; amount_text: string | null },
): string {
  if (source.amount_text) return source.amount_text;
  if (source.amount === null) return '';
  return formatAmount(t, language, source.amount, source.unit);
}

export interface CategoryGroup<Line> {
  categoryId: string;
  /** The translated category name. */
  name: string;
  lines: Line[];
}

/**
 * Groups lines under their category, keeping the order the server sorted them in (category
 * order, then name: AGG-05). `categoryKeys` maps category ids to their keys.
 */
export function groupByCategory<Line extends { category_id: string }>(
  lines: readonly Line[],
  categoryKeys: ReadonlyMap<string, string>,
  t: TFunction,
): CategoryGroup<Line>[] {
  const groups: CategoryGroup<Line>[] = [];
  const byId = new Map<string, CategoryGroup<Line>>();
  for (const line of lines) {
    let group = byId.get(line.category_id);
    if (!group) {
      const key = categoryKeys.get(line.category_id) ?? 'other';
      group = { categoryId: line.category_id, name: categoryName(t, key), lines: [] };
      byId.set(line.category_id, group);
      groups.push(group);
    }
    group.lines.push(line);
  }
  return groups;
}

/** LIST-14: the list's reminder, the same one every time (`reminder_seed` never changes). */
export function reminderText(t: TFunction, seed: number): string {
  const number = (Math.abs(Math.trunc(seed)) % 10) + 1;
  return t(`reminder.${number}` as 'reminder.1');
}

/** The id of the category *Other*, where free-text items go unless another is chosen (LIST-06). */
export function otherCategoryId(
  categories: readonly { id: string; key: string }[] | undefined,
): string {
  return categories?.find((category) => category.key === 'other')?.id ?? '';
}

interface NeedsMore {
  grown: readonly { value: number; unit: string }[];
  new_unit: boolean;
  new_unspecified: boolean;
  changed: boolean;
}

/**
 * LIST-12: why a line that was checked needs more, as badge texts: "+300 g" per grown amount
 * (the server computed and rounded the difference), "new unit", "+ some", "changed".
 */
export function needsMoreTexts(t: TFunction, language: Language, needsMore: NeedsMore): string[] {
  return [
    ...needsMore.grown.map(({ value, unit }) =>
      t('lists.shop.more', { amount: formatAmount(t, language, value, unit) }),
    ),
    ...(needsMore.new_unit ? [t('lists.shop.newUnit')] : []),
    ...(needsMore.new_unspecified ? [t('lists.lines.plusSome')] : []),
    ...(needsMore.changed ? [t('lists.shop.changed')] : []),
  ];
}

/** SHOP-01: who checked a line, as one letter: "B" for "ben". */
export function initialOf(name: string): string {
  return (Array.from(name.trim())[0] ?? '?').toLocaleUpperCase();
}
