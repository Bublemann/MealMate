import { describe, expect, it } from 'vitest';
import i18n from '@/i18n';
import { CATEGORIES } from '@/test/ingredients';
import { DETACHED_MEAL, listDetail, listMeal, PRIVATE_MEAL } from '@/test/lists';
import { exportText } from './exportText';

const categoryKeys = new Map(CATEGORIES.map((category) => [category.id, category.key]));

function exported(language: 'de' | 'en', list = listDetail()) {
  return exportText(list, { t: i18n.getFixedT(language), language, categoryKeys });
}

describe('exportText', () => {
  it('has name and date, meals, lines by category and the reminder, in English', () => {
    expect(exported('en')).toBe(
      [
        'Wochenende (26/09/2026)',
        '',
        '4× Pfannkuchen',
        '3× Private meal',
        '2× Alter Eintopf',
        '',
        'Fruit & vegetables',
        '- Zwiebeln: 2 pcs',
        '',
        'Dairy & eggs',
        '- Milch: 1.5 l',
        '',
        'Other',
        '- Geburtstagskerzen: 2 Packungen',
        '- Mehl: 850 g',
        '- Salz',
        '',
        "Didn't forget anything? Toilet paper? Salt?",
      ].join('\n'),
    );
  });

  it('uses the German texts, date and number format', () => {
    expect(exported('de')).toBe(
      [
        'Wochenende (26.09.2026)',
        '',
        '4× Pfannkuchen',
        '3× Privates Gericht',
        '2× Alter Eintopf',
        '',
        'Obst & Gemüse',
        '- Zwiebeln: 2 Stk.',
        '',
        'Milchprodukte & Eier',
        '- Milch: 1,5 l',
        '',
        'Sonstiges',
        '- Geburtstagskerzen: 2 Packungen',
        '- Mehl: 850 g',
        '- Salz',
        '',
        'Nichts vergessen? Klopapier? Salz?',
      ].join('\n'),
    );
  });

  it('joins amounts of different kinds and adds "+ some" for parts without an amount', () => {
    const list = listDetail({
      name: null,
      meals: [listMeal({ servings: 2 })],
      lines: [
        {
          key: 'i:ing-zwiebeln',
          kind: 'ingredient',
          ingredient_id: 'ing-zwiebeln',
          name: 'Zwiebeln',
          category_id: 'cat-fruit_vegetables',
          amounts: [
            { value: 1.25, unit: 'kg' },
            { value: 3, unit: 'piece' },
          ],
          has_unspecified: true,
          amount_text: null,
          hidden: false,
          sources: [],
        },
        {
          key: 'x:0190c0de-0000-7000-8000-0000000000c2',
          kind: 'text',
          ingredient_id: null,
          name: 'Servietten',
          category_id: 'cat-other',
          amounts: [],
          has_unspecified: false,
          amount_text: null,
          hidden: false,
          sources: [],
        },
      ],
    });

    expect(exported('en', list)).toBe(
      [
        'Shopping list (26/09/2026)',
        '',
        '2× Pfannkuchen',
        '',
        'Fruit & vegetables',
        '- Zwiebeln: 1.25 kg + 3 pcs + some',
        '',
        'Other',
        '- Servietten',
        '',
        "Didn't forget anything? Toilet paper? Salt?",
      ].join('\n'),
    );
    expect(exported('de', list)).toContain('Einkaufsliste (26.09.2026)');
    expect(exported('de', list)).toContain('- Zwiebeln: 1,25 kg + 3 Stk. + etwas');
  });

  it('leaves out removed lines and empty sections', () => {
    const list = listDetail({
      meals: [],
      lines: listDetail().lines.map((line) => ({ ...line, hidden: true })),
      reminder_seed: 6,
    });

    expect(exported('en', list)).toBe(
      ['Wochenende (26/09/2026)', '', 'Breakfast sorted? Bread, butter, jam?'].join('\n'),
    );
  });

  it('never shows the name of a meal the exporting user cannot see (VIS-06)', () => {
    const list = listDetail({ meals: [PRIVATE_MEAL, DETACHED_MEAL] });

    expect(exported('en', list)).toContain('3× Private meal\n2× Alter Eintopf');
  });
});
