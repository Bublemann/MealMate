import { screen, waitFor, within } from '@testing-library/react';
import type { UserEvent } from '@testing-library/user-event';
import { expect } from 'vitest';
import type { components } from '@/api/generated/schema';
import { testIds } from '@/testIds';
import { BEN, TEST_USER, userRef } from './api';

type Schemas = components['schemas'];
type Category = Schemas['Category'];

const NAMES = {
  fruit_vegetables: { de: 'Obst & Gemüse', en: 'Fruit & vegetables' },
  dairy_eggs: { de: 'Milchprodukte & Eier', en: 'Dairy & eggs' },
  cheese: { de: 'Käse', en: 'Cheese' },
  other: { de: 'Sonstiges', en: 'Other' },
} as const;
const KEYS = Object.keys(NAMES) as (keyof typeof NAMES)[];

/**
 * A few categories in their walking order, named as seeded (the real seed has 18). Their
 * ingredient counts only matter for *Uncategorized*, which the Ingredients tab offers by its count.
 */
export const CATEGORIES: Schemas['Category'][] = KEYS.map((key, index) => ({
  id: `cat-${key}`,
  key,
  names: NAMES[key],
  sort_order: index,
  deleted: false,
  ingredient_count: 0,
}));

/** A category an admin added (REF-01): it has no key, and goes last until it is moved. */
export const CHEESE_COUNTER: Schemas['Category'] = {
  id: 'cat-cheese-counter',
  key: null,
  names: { de: 'Käsetheke', en: 'Cheese counter' },
  sort_order: CATEGORIES.length,
  deleted: false,
  ingredient_count: 0,
};

/**
 * The built-in *Uncategorized* (REF-01), seeded last: it holds the ingredients of deleted
 * categories and is never picked by hand. Empty, as seeded.
 */
export const UNCATEGORIZED: Schemas['Category'] = {
  id: 'cat-uncategorized',
  key: 'uncategorized',
  names: { de: 'Ohne Kategorie', en: 'Uncategorized' },
  sort_order: CATEGORIES.length,
  deleted: false,
  ingredient_count: 0,
};

/** The categories with *Uncategorized*, as the seed has them. */
export const CATEGORIES_WITH_UNCATEGORIZED: Schemas['Category'][] = [...CATEGORIES, UNCATEGORIZED];

/**
 * The categories once an admin deleted Cheese (D-30): it stays in the list, marked as deleted,
 * with its last place, which *Other* took over, so it comes right after *Other*. Its one
 * ingredient moved to *Uncategorized*.
 */
export const CATEGORIES_AFTER_DELETE: Schemas['Category'][] = (() => {
  const [fruit, dairy, cheese, other] = CATEGORIES as [Category, Category, Category, Category];
  return [
    fruit,
    dairy,
    { ...other, sort_order: 2 },
    { ...cheese, sort_order: 2, deleted: true },
    { ...UNCATEGORIZED, sort_order: 3, ingredient_count: 1 },
  ];
})();

/** The categories with CHEESE_COUNTER moved before *Other*, as an admin may do. */
export const CATEGORIES_WITH_ADDED: Schemas['Category'][] = [
  ...CATEGORIES.slice(0, -1),
  CHEESE_COUNTER,
  ...CATEGORIES.slice(-1),
].map((category, index) => ({ ...category, sort_order: index }));

/** The units as the server lists them, each with the base units it fits (REF-02). */
export const UNITS: Schemas['UnitInfo'][] = [
  { unit: 'g', kind: 'mass', base_units: ['g'] },
  { unit: 'kg', kind: 'mass', base_units: ['g'] },
  { unit: 'ml', kind: 'volume', base_units: ['ml'] },
  { unit: 'l', kind: 'volume', base_units: ['ml'] },
  { unit: 'piece', kind: 'count', base_units: ['piece'] },
  { unit: 'tbsp', kind: 'volume', base_units: ['g', 'ml'] },
  { unit: 'tsp', kind: 'volume', base_units: ['g', 'ml'] },
];

/** A unit select's options: the label and whether it is disabled (an older unit that doesn't fit). */
export function unitOptions(select: HTMLElement): [string | null, boolean][] {
  return within(select)
    .getAllByRole('option')
    .map((option) => [option.textContent, (option as HTMLOptionElement).disabled]);
}

/**
 * The elements follow each other on the page in the order given (e.g. the ingredient form's
 * fields); on failure, the indices show which ones are out of place.
 */
export function expectInPageOrder(elements: HTMLElement[]) {
  const onPage = [...elements].sort((a, b) =>
    a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1,
  );
  expect(onPage.map((element) => elements.indexOf(element))).toEqual(elements.map((_, i) => i));
}

export function summary(
  name: string,
  category: (typeof KEYS)[number],
  overrides: Partial<Schemas['IngredientSummary']> = {},
): Schemas['IngredientSummary'] {
  return {
    id: `ing-${name.toLowerCase()}`,
    name,
    category_id: `cat-${category}`,
    brand: null,
    barcode: null,
    source: 'manual',
    base_unit: 'g',
    ...overrides,
  };
}

const NO_VALUES: Schemas['NutrientValues'] = {
  kcal: null,
  protein: null,
  carbs: null,
  sugar: null,
  fat: null,
};

/** Äpfel, typed by hand: kcal and protein known, the rest unknown; used in 3 meals. */
export const APPLES: Schemas['Ingredient'] = {
  id: 'ing-aepfel',
  name: 'Äpfel',
  brand: null,
  barcode: null,
  category_id: 'cat-fruit_vegetables',
  base_unit: 'g',
  piece_weight_g: null,
  nutrients: { ...NO_VALUES, kcal: 52, protein: 0.3 },
  quantity_text: null,
  pack_quantity: null,
  pack_unit: null,
  source: 'manual',
  user_edited_fields: [],
  off_last_modified_at: null,
  fetched_at: null,
  pending_update: null,
  usage: { meals: 3, lists: 1 },
  created_by: null,
  updated_by: userRef(TEST_USER.display_name, TEST_USER.id),
  created_at: '2026-09-20T10:00:00Z',
  updated_at: '2026-09-26T10:00:00Z',
};

export function ingredient(overrides: Partial<Schemas['Ingredient']> = {}): Schemas['Ingredient'] {
  return {
    id: 'ing-new',
    name: 'New',
    brand: null,
    barcode: null,
    category_id: 'cat-other',
    base_unit: 'g',
    piece_weight_g: null,
    nutrients: NO_VALUES,
    quantity_text: null,
    pack_quantity: null,
    pack_unit: null,
    source: 'manual',
    user_edited_fields: [],
    off_last_modified_at: null,
    fetched_at: null,
    pending_update: null,
    usage: { meals: 0, lists: 0 },
    created_by: BEN,
    updated_by: BEN,
    created_at: '2026-09-26T10:00:00Z',
    updated_at: '2026-09-26T10:00:00Z',
    ...overrides,
  };
}

/** Weidehof's whole milk from Open Food Facts, with its barcode; the fat was corrected by hand. */
export const WEIDEHOF_MILK: Schemas['Ingredient'] = ingredient({
  id: 'ing-milch-weidehof',
  name: 'Vollmilch',
  brand: 'Weidehof',
  barcode: '4006381333931',
  category_id: 'cat-dairy_eggs',
  base_unit: 'ml',
  nutrients: { kcal: 64, protein: 3.4, carbs: 4.8, sugar: 4.8, fat: 3.6 },
  quantity_text: '1 l',
  pack_quantity: 1,
  pack_unit: 'l',
  source: 'off',
  user_edited_fields: ['nutrients.fat'],
  off_last_modified_at: '2026-09-01T10:00:00Z',
  fetched_at: '2026-09-02T10:00:00Z',
  usage: { meals: 1, lists: 0 },
});

/** A product as Open Food Facts proposes it (barcode lookup or name search). */
export function proposal(
  overrides: Partial<Schemas['ProductProposal']> = {},
): Schemas['ProductProposal'] {
  return {
    barcode: '4006381333931',
    name: 'Frische Vollmilch 3,5 %',
    brand: 'Weidehof',
    quantity_text: '1 l',
    pack_quantity: 1,
    pack_unit: 'l',
    nutrition_basis: 'ml',
    nutrients: { kcal: 64, protein: 3.4, carbs: 4.8, sugar: 4.8, fat: 3.5 },
    category_key: 'dairy_eggs',
    off_last_modified_at: '2026-09-01T10:00:00Z',
    ...overrides,
  };
}

/** The barcode lookup's answer (BAR-02, BAR-03); by default, a barcode nobody knows. */
export function lookupResult(
  overrides: Partial<Schemas['BarcodeLookup']> = {},
): Schemas['BarcodeLookup'] {
  return {
    barcode: '4006381333931',
    found_in: 'none',
    ingredient: null,
    proposal: null,
    off_unavailable: false,
    ...overrides,
  };
}

/**
 * Taps the scan icon of the ingredient pop-up `dialog` and types `digits` into the scanner, the
 * fallback without a camera (jsdom has none, BAR-01); returns once the scanner has closed.
 */
export async function scanInForm(user: UserEvent, dialog: HTMLElement, digits: string) {
  await user.click(within(dialog).getByTestId(testIds.ingredientFormScan));
  await typeInScanner(user, digits);
}

/** Types `digits` into the open scanner's manual input; returns once the scanner has closed. */
export async function typeInScanner(user: UserEvent, digits: string) {
  const scanner = await screen.findByTestId(testIds.barcodeScanDialog);
  await user.type(within(scanner).getByTestId(testIds.barcodeInput), `${digits}{Enter}`);
  await waitFor(() => expect(scanner).not.toBeInTheDocument());
}

/** Answers for the reference data every ingredient screen loads. */
export const REFERENCE_ROUTES: Record<string, unknown> = {
  'GET /api/categories': CATEGORIES,
  'GET /api/units': UNITS,
};
