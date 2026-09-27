import { describe, expect, it } from 'vitest';
import i18n from '@/i18n';
import { CATEGORIES } from '@/test/ingredients';
import { LINES } from '@/test/lists';
import {
  groupByCategory,
  initialOf,
  lineAmount,
  listDisplayName,
  needsMoreTexts,
  otherCategoryId,
  reminderText,
  sourceAmount,
} from './format';

const en = i18n.getFixedT('en');
const de = i18n.getFixedT('de');

function amounts(
  values: { value: number; unit: 'g' | 'kg' | 'ml' | 'l' | 'piece' | 'tbsp' | 'tsp' }[],
  hasUnspecified = false,
) {
  return {
    kind: 'ingredient',
    amounts: values,
    has_unspecified: hasUnspecified,
    amount_text: null,
  };
}

describe('listDisplayName (LIST-02)', () => {
  const created_at = '2026-09-26T10:00:00Z';

  it('shows the name and the creation date in the viewer’s format', () => {
    expect(listDisplayName({ name: 'Grillabend', created_at }, de, 'de')).toBe(
      'Grillabend (26.09.2026)',
    );
    expect(listDisplayName({ name: 'Grillabend', created_at }, en, 'en')).toBe(
      'Grillabend (26/09/2026)',
    );
  });

  it('uses the translated default name of the viewer’s language', () => {
    expect(listDisplayName({ name: null, created_at }, de, 'de')).toBe(
      'Einkaufsliste (26.09.2026)',
    );
    expect(listDisplayName({ name: null, created_at }, en, 'en')).toBe(
      'Shopping list (26/09/2026)',
    );
  });
});

describe('lineAmount', () => {
  it('formats the display amounts per locale, side by side', () => {
    const line = amounts([
      { value: 1.5, unit: 'kg' },
      { value: 2, unit: 'piece' },
    ]);
    expect(lineAmount(en, 'en', line)).toBe('1.5 kg + 2 pcs');
    expect(lineAmount(de, 'de', line)).toBe('1,5 kg + 2 Stk.');
  });

  it('adds "+ some" after the amounts for parts without one, and says nothing without amounts (AGG-03)', () => {
    expect(lineAmount(en, 'en', amounts([{ value: 500, unit: 'g' }], true))).toBe('500 g + some');
    expect(lineAmount(de, 'de', amounts([{ value: 0.5, unit: 'tbsp' }], true))).toBe(
      '0,5 EL + etwas',
    );
    expect(lineAmount(en, 'en', amounts([], true))).toBe('');
    expect(lineAmount(de, 'de', amounts([], true))).toBe('');
    expect(lineAmount(en, 'en', amounts([]))).toBe('');
  });

  it('shows a free-text item’s own amount as it is', () => {
    const line = { kind: 'text', amounts: [], has_unspecified: false, amount_text: '2 Packungen' };
    expect(lineAmount(en, 'en', line)).toBe('2 Packungen');
    expect(lineAmount(en, 'en', { ...line, amount_text: null })).toBe('');
  });
});

describe('sourceAmount', () => {
  it('shows the source’s own amount or its free text, else nothing', () => {
    expect(sourceAmount(de, 'de', { amount: 112.5, unit: 'g', amount_text: null })).toBe('112,5 g');
    expect(sourceAmount(en, 'en', { amount: null, unit: null, amount_text: '1 Tüte' })).toBe(
      '1 Tüte',
    );
    expect(sourceAmount(en, 'en', { amount: null, unit: null, amount_text: null })).toBe('');
    expect(sourceAmount(en, 'en', { amount: 3, unit: null, amount_text: null })).toBe('3');
  });
});

describe('groupByCategory', () => {
  it('keeps the server’s order and translates the headings', () => {
    const keys = new Map(CATEGORIES.map((category) => [category.id, category.key]));
    const groups = groupByCategory(LINES, keys, en);

    expect(groups.map(({ name, lines }) => [name, lines.map((line) => line.name)])).toEqual([
      ['Fruit & vegetables', ['Zwiebeln']],
      ['Dairy & eggs', ['Eier', 'Milch']],
      ['Other', ['Geburtstagskerzen', 'Mehl', 'Salz']],
    ]);
  });

  it('puts lines of an unknown category under Other', () => {
    const [group] = groupByCategory(LINES.slice(0, 1), new Map(), de);
    expect(group?.name).toBe('Sonstiges');
  });
});

describe('reminderText (LIST-14)', () => {
  it('picks one of the ten reminders by the list’s seed', () => {
    expect(reminderText(en, 0)).toBe(en('reminder.1'));
    expect(reminderText(en, 9)).toBe(en('reminder.10'));
    expect(reminderText(de, 1234)).toBe(de('reminder.5'));
  });
});

describe('otherCategoryId', () => {
  it('finds the category Other', () => {
    expect(otherCategoryId(CATEGORIES)).toBe('cat-other');
    expect(otherCategoryId(undefined)).toBe('');
  });
});

describe('needsMoreTexts (LIST-12)', () => {
  const none = { grown: [], new_unit: false, new_unspecified: false, changed: false };

  it('says how much more per grown amount, formatted per language', () => {
    const grown = {
      ...none,
      grown: [
        { value: 300, unit: 'g' as const },
        { value: 1.5, unit: 'l' as const },
        { value: 2, unit: 'piece' as const },
      ],
    };
    expect(needsMoreTexts(en, 'en', grown)).toEqual(['+300 g', '+1.5 l', '+2 pcs']);
    expect(needsMoreTexts(de, 'de', grown)).toEqual(['+300 g', '+1,5 l', '+2 Stk.']);
  });

  it('names a new unit, a part without an amount and a changed free-text item', () => {
    expect(
      needsMoreTexts(en, 'en', { ...none, new_unit: true, new_unspecified: true, changed: true }),
    ).toEqual(['new unit', '+ some', 'changed']);
    expect(needsMoreTexts(de, 'de', { ...none, new_unspecified: true, changed: true })).toEqual([
      '+ etwas',
      'geändert',
    ]);
    expect(needsMoreTexts(en, 'en', none)).toEqual([]);
  });
});

describe('initialOf (SHOP-01)', () => {
  it('is the first letter, upper case', () => {
    expect(initialOf('ben')).toBe('B');
    expect(initialOf(' Anna ')).toBe('A');
    expect(initialOf('Özlem')).toBe('Ö');
    expect(initialOf('')).toBe('?');
  });
});
