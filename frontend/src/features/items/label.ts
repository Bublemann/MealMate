/**
 * How an item is named wherever it appears (meal detail and form, list lines, history,
 * export, offline copy): the name, and the brand in brackets when there is one. Two brands of the
 * same thing are different items and separate lines on a list, so without the brand they
 * would look like duplicates ("Milch", "Milch") instead of "Milch (Weidehof)", "Milch (Alpenhof)".
 */
export function itemLabel(name: string, brand?: string | null): string {
  const trimmed = brand?.trim();
  return trimmed ? `${name} (${trimmed})` : name;
}
