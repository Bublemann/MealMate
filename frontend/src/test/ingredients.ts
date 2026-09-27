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
    base_unit: 'g',
    product_count: 0,
    ...overrides,
  };
}

const UNKNOWN: Schemas['NutrientInfo'] = {
  value: null,
  source: 'unknown',
  products_mean: null,
  products_count: 0,
};

const NO_VALUES: Schemas['NutrientValues'] = {
  kcal: null,
  protein: null,
  carbs: null,
  sugar: null,
  fat: null,
};

/** Äpfel: kcal entered by hand (with a product average as hint), protein from 2 products. */
export const APPLES: Schemas['Ingredient'] = {
  id: 'ing-aepfel',
  name: 'Äpfel',
  category_id: 'cat-fruit_vegetables',
  base_unit: 'g',
  piece_weight_g: 180,
  density_g_per_ml: null,
  manual: { ...NO_VALUES, kcal: 52 },
  nutrition: {
    kcal: { value: 52, source: 'manual', products_mean: 49.5, products_count: 2 },
    protein: { value: 0.3, source: 'products', products_mean: 0.3, products_count: 2 },
    carbs: UNKNOWN,
    sugar: UNKNOWN,
    fat: UNKNOWN,
  },
  product_count: 2,
  created_by: null,
  updated_by: userRef(TEST_USER.display_name, TEST_USER.id),
  created_at: '2026-09-20T10:00:00Z',
  updated_at: '2026-09-26T10:00:00Z',
};

export function ingredient(overrides: Partial<Schemas['Ingredient']> = {}): Schemas['Ingredient'] {
  return {
    id: 'ing-new',
    name: 'New',
    category_id: 'cat-other',
    base_unit: 'g',
    piece_weight_g: null,
    density_g_per_ml: null,
    manual: NO_VALUES,
    nutrition: { kcal: UNKNOWN, protein: UNKNOWN, carbs: UNKNOWN, sugar: UNKNOWN, fat: UNKNOWN },
    product_count: 0,
    created_by: BEN,
    updated_by: BEN,
    created_at: '2026-09-26T10:00:00Z',
    updated_at: '2026-09-26T10:00:00Z',
    ...overrides,
  };
}

export function product(overrides: Partial<Schemas['Product']> = {}): Schemas['Product'] {
  return {
    id: 'prod-1',
    barcode: '4000000000006',
    ingredient_id: APPLES.id,
    nutrition_basis: 'g',
    name: 'Elstar',
    brand: 'Hofgut',
    quantity_text: '1 kg',
    pack_quantity: 1,
    pack_unit: 'kg',
    nutrients: { ...NO_VALUES, kcal: 50, protein: 0.3 },
    source: 'manual',
    user_edited_fields: ['name', 'brand', 'nutrients.kcal', 'nutrients.protein'],
    fetched_at: null,
    created_by: BEN,
    updated_by: BEN,
    created_at: '2026-09-21T10:00:00Z',
    updated_at: '2026-09-21T10:00:00Z',
    ...overrides,
  };
}

/** Answers for the reference data every ingredient screen loads. */
export const REFERENCE_ROUTES: Record<string, unknown> = {
  'GET /api/categories': CATEGORIES,
  'GET /api/units': UNITS,
};
