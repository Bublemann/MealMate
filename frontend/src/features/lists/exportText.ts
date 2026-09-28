import type { TFunction } from 'i18next';
import type { Language } from '@/i18n';
import type { ListDetail } from './api';
import { groupByCategory, lineAmount, lineLabel, listDisplayName, reminderText } from './format';

/** What the export needs of a list: exactly what the list view already loaded. */
export type ExportableList = Pick<
  ListDetail,
  'name' | 'created_at' | 'status' | 'reminder_seed' | 'meals' | 'lines'
>;

type ExportLine = ExportableList['lines'][number];

interface ExportOptions {
  t: TFunction;
  language: Language;
  /** Category keys by id, for the translated headings. */
  categoryKeys: ReadonlyMap<string, string>;
}

/**
 * The list as plain text for the share sheet (EXP-02), in the exporting user's language and
 * number format: name and date, the meals with their servings, the lines grouped by category in
 * the list's order (removed lines left out), then the reminder. Within a category the lines still
 * to buy come first, then the checked ones marked "✓"; on a done list the lines that weren't
 * bought say so, as plain text can't be greyed out (SHOP-05). Built synchronously from loaded
 * data, so the share button can call `navigator.share` within the tap (plan § 8).
 */
export function exportText(list: ExportableList, { t, language, categoryKeys }: ExportOptions) {
  const blocks: string[] = [listDisplayName(list, t, language)];

  if (list.meals.length > 0) {
    blocks.push(
      list.meals
        .map((meal) =>
          t('lists.export.meal', {
            servings: meal.servings,
            name: meal.name ?? t('lists.meals.private'),
          }),
        )
        .join('\n'),
    );
  }

  const shown = list.lines.filter((line) => !line.hidden);
  const openKey = list.status === 'done' ? 'lists.export.notBought' : 'lists.export.open';
  const item = (line: ExportLine) => {
    const amount = lineAmount(t, language, line);
    return amount ? t('lists.export.item', { name: lineLabel(line), amount }) : lineLabel(line);
  };
  for (const group of groupByCategory(shown, categoryKeys, t)) {
    const open = group.lines.filter((line) => !line.checked);
    const checked = group.lines.filter((line) => line.checked);
    blocks.push(
      [
        group.name,
        ...open.map((line) => t(openKey, { item: item(line) })),
        ...checked.map((line) => t('lists.export.checked', { item: item(line) })),
      ].join('\n'),
    );
  }

  blocks.push(reminderText(t, list.reminder_seed));
  return blocks.join('\n\n');
}
