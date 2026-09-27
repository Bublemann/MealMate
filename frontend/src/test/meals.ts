import type { components } from '@/api/generated/schema';
import { BEN, CARL, TEST_USER, userRef } from './api';
import { CATEGORIES, summary, UNITS } from './ingredients';

type Schemas = components['schemas'];

export const ME = userRef(TEST_USER.display_name, TEST_USER.id);

export const CUISINES: Schemas['Cuisine'][] = [
  { id: 'cui-german', key: 'german', name: null },
  { id: 'cui-italian', key: 'italian', name: null },
  { id: 'cui-nordic', key: null, name: 'Nordisch' },
];

export const TAGS: Schemas['Tag'][] = [
  { id: 'tag-quick', name: 'schnell' },
  { id: 'tag-veggie', name: 'vegetarisch' },
];

export const FLOUR = summary('Mehl', 'other');
export const MILK = summary('Milch', 'dairy_eggs', { base_unit: 'ml' });
export const EGGS = summary('Eier', 'dairy_eggs');
export const SALT = summary('Salz', 'other');

const EMPTY_VALUES: Schemas['NutrientValues'] = {
  kcal: null,
  protein: null,
  carbs: null,
  sugar: null,
  fat: null,
};

/** Pancakes: 200 g flour, 300 ml milk, 2 eggs, salt to taste (no amount). */
export function meal(overrides: Partial<Schemas['Meal']> = {}): Schemas['Meal'] {
  return {
    id: 'meal-pancakes',
    name: 'Pfannkuchen',
    owner: ME,
    is_owner: true,
    instructions: 'Alles verrühren.\nIn der Pfanne backen.',
    source_url: 'https://example.org/pfannkuchen',
    servings: 2,
    cuisine: CUISINES[0] ?? null,
    tags: [TAGS[0] as Schemas['Tag']],
    photo: {
      url: '/api/media/abc.webp?exp=1&sig=x',
      thumb_url: '/api/media/abc-thumb.webp?exp=1&sig=x',
    },
    ingredients: [
      { id: 'row-1', position: 0, ingredient: FLOUR, amount: 200, unit: 'g', note: null },
      { id: 'row-2', position: 1, ingredient: MILK, amount: 300, unit: 'ml', note: null },
      { id: 'row-3', position: 2, ingredient: EGGS, amount: 2, unit: 'piece', note: 'Größe M' },
      { id: 'row-4', position: 3, ingredient: SALT, amount: null, unit: null, note: 'to taste' },
    ],
    nutrition: {
      per_meal: { kcal: 1106, protein: 40.5, carbs: 160.2, sugar: 15, fat: 30.25 },
      per_serving: { kcal: 553, protein: 20.25, carbs: 80.1, sugar: 7.5, fat: 15.125 },
      incomplete: true,
      estimate: false,
      missing: [
        {
          ingredient_id: SALT.id,
          ingredient_name: SALT.name,
          reason: 'no_amount',
          nutrient: null,
        },
      ],
    },
    based_on: null,
    created_at: '2026-09-20T10:00:00Z',
    updated_at: '2026-09-26T10:00:00Z',
    ...overrides,
  };
}

/** A meal without rows, photo and optional fields. */
export function bareMeal(overrides: Partial<Schemas['Meal']> = {}): Schemas['Meal'] {
  return meal({
    id: 'meal-new',
    name: 'Neu',
    instructions: null,
    source_url: null,
    servings: 1,
    cuisine: null,
    tags: [],
    photo: null,
    ingredients: [],
    nutrition: {
      per_meal: EMPTY_VALUES,
      per_serving: EMPTY_VALUES,
      incomplete: false,
      estimate: false,
      missing: [],
    },
    ...overrides,
  });
}

export function mealSummary(
  name: string,
  overrides: Partial<Schemas['MealSummary']> = {},
): Schemas['MealSummary'] {
  return {
    id: `meal-${name.toLowerCase()}`,
    name,
    owner: ME,
    cuisine: null,
    tags: [],
    servings: 2,
    thumb_url: null,
    updated_at: '2026-09-26T10:00:00Z',
    ...overrides,
  };
}

/** Answers for the reference data and users the meal screens load. */
export const MEAL_ROUTES: Record<string, unknown> = {
  'GET /api/categories': CATEGORIES,
  'GET /api/units': UNITS,
  'GET /api/cuisines': CUISINES,
  'GET /api/tags': TAGS,
  'GET /api/meals/tags': TAGS,
  'GET /api/users/visible': [ME, BEN, userRef(CARL.display_name, CARL.id, true)],
  'GET /api/ingredients/similar': [],
};
