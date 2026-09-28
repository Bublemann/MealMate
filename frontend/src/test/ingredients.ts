import type { components } from '@/api/generated/schema';
import { BEN, TEST_USER, userRef } from './api';

type Schemas = components['schemas'];

const KEYS = ['fruit_vegetables', 'dairy_eggs', 'cheese', 'other'] as const;

/** A few categories in their walking order (the real seed has 17). */
export const CATEGORIES: Schemas['Category'][] = KEYS.map((key, index) => ({
  id: `cat-${key}`,
  key,
  sort_order: index,
}));

export const UNITS: Schemas['UnitInfo'][] = [
  { unit: 'g', kind: 'mass' },
  { unit: 'kg', kind: 'mass' },
  { unit: 'ml', kind: 'volume' },
  { unit: 'l', kind: 'volume' },
  { unit: 'piece', kind: 'count' },
  { unit: 'tbsp', kind: 'volume' },
  { unit: 'tsp', kind: 'volume' },
];

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
  piece_weight_g: 180,
  density_g_per_ml: null,
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
    density_g_per_ml: null,
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

/** Answers for the reference data every ingredient screen loads. */
export const REFERENCE_ROUTES: Record<string, unknown> = {
  'GET /api/categories': CATEGORIES,
  'GET /api/units': UNITS,
};
