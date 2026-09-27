import type { components } from '@/api/generated/schema';
import { BEN, CARL } from './api';
import { CATEGORIES } from './ingredients';
import { EGGS, FLOUR, ME, MEAL_ROUTES, MILK, SALT } from './meals';

type Schemas = components['schemas'];

export const LIST_ID = '0190c0de-0000-7000-8000-0000000000b1';

export const ONIONS_ID = 'ing-zwiebeln';
export const CANDLES_EXTRA_ID = '0190c0de-0000-7000-8000-0000000000c1';
export const FLOUR_EXTRA_ID = '0190c0de-0000-7000-8000-0000000000f1';

export function listMeal(
  overrides: Partial<Schemas['ListMealEntry']> = {},
): Schemas['ListMealEntry'] {
  return {
    id: 'lm-pancakes',
    meal_id: 'meal-pancakes',
    name: 'Pfannkuchen',
    private: false,
    owner: ME,
    thumb_url: '/api/media/p-thumb.webp?sig=x',
    servings: 4,
    meal_servings: 2,
    detached: null,
    ...overrides,
  };
}

export const PRIVATE_MEAL = listMeal({
  id: 'lm-private',
  meal_id: null,
  name: null,
  private: true,
  owner: null,
  thumb_url: null,
  servings: 3,
  meal_servings: 3,
});

export const DETACHED_MEAL = listMeal({
  id: 'lm-detached',
  meal_id: null,
  name: 'Alter Eintopf',
  thumb_url: null,
  servings: 2,
  meal_servings: 2,
  detached: 'deleted',
});

function mealSource(overrides: Partial<Schemas['LineSource']> = {}): Schemas['LineSource'] {
  return {
    kind: 'meal',
    list_meal_id: 'lm-pancakes',
    extra_id: null,
    meal_name: 'Pfannkuchen',
    private: false,
    servings: 4,
    amount: null,
    unit: null,
    amount_text: null,
    ...overrides,
  };
}

/** The check state of a line nobody checked (always so in a draft). */
export const UNCHECKED = {
  checked: false,
  checked_at: null,
  checked_by: null,
  new: false,
  needs_more: null,
} satisfies Partial<Schemas['ListLine']>;

export function line(
  overrides: Partial<Schemas['ListLine']> & { name: string },
): Schemas['ListLine'] {
  return {
    key: `i:${overrides.name}`,
    kind: 'ingredient',
    ingredient_id: null,
    category_id: 'cat-other',
    amounts: [],
    has_unspecified: false,
    amount_text: null,
    hidden: false,
    sources: [mealSource()],
    ...UNCHECKED,
    ...overrides,
  };
}

/** In the server's order: category order (fruit_vegetables, dairy_eggs, other), then name. */
export const LINES: Schemas['ListLine'][] = [
  line({
    key: `i:${ONIONS_ID}`,
    name: 'Zwiebeln',
    ingredient_id: ONIONS_ID,
    category_id: 'cat-fruit_vegetables',
    amounts: [{ value: 2, unit: 'piece' }],
    sources: [mealSource()],
  }),
  line({
    key: `i:${EGGS.id}`,
    name: EGGS.name,
    ingredient_id: EGGS.id,
    category_id: 'cat-dairy_eggs',
    amounts: [{ value: 4, unit: 'piece' }],
    hidden: true,
    sources: [mealSource()],
  }),
  line({
    key: `i:${MILK.id}`,
    name: MILK.name,
    ingredient_id: MILK.id,
    category_id: 'cat-dairy_eggs',
    amounts: [{ value: 1.5, unit: 'l' }],
    sources: [
      mealSource(),
      mealSource({ list_meal_id: 'lm-private', meal_name: null, private: true, servings: 3 }),
    ],
  }),
  line({
    key: 'x:' + CANDLES_EXTRA_ID,
    kind: 'text',
    name: 'Geburtstagskerzen',
    amount_text: '2 Packungen',
    sources: [
      {
        kind: 'extra',
        list_meal_id: null,
        extra_id: CANDLES_EXTRA_ID,
        meal_name: null,
        private: false,
        servings: null,
        amount: null,
        unit: null,
        amount_text: '2 Packungen',
      },
    ],
  }),
  line({
    key: `i:${FLOUR.id}`,
    name: FLOUR.name,
    ingredient_id: FLOUR.id,
    amounts: [{ value: 850, unit: 'g' }],
    sources: [
      mealSource(),
      {
        kind: 'extra',
        list_meal_id: null,
        extra_id: FLOUR_EXTRA_ID,
        meal_name: null,
        private: false,
        servings: null,
        amount: 450,
        unit: 'g',
        amount_text: null,
      },
    ],
  }),
  line({
    key: `i:${SALT.id}`,
    name: SALT.name,
    ingredient_id: SALT.id,
    amounts: [],
    has_unspecified: true,
    sources: [mealSource()],
  }),
];

export const EXTRA_ITEMS: Schemas['ExtraItem'][] = [
  {
    id: FLOUR_EXTRA_ID,
    ingredient_id: FLOUR.id,
    text: null,
    amount: 450,
    unit: 'g',
    amount_text: null,
    category_id: null,
    added_by: ME,
    created_at: '2026-09-26T10:00:00Z',
  },
  {
    id: CANDLES_EXTRA_ID,
    ingredient_id: null,
    text: 'Geburtstagskerzen',
    amount: null,
    unit: null,
    amount_text: '2 Packungen',
    category_id: 'cat-other',
    added_by: ME,
    created_at: '2026-09-26T10:05:00Z',
  },
];

/** "Wochenende" of 26.09.2026: my own draft with a visible, a private and a detached meal. */
export function listDetail(overrides: Partial<Schemas['ListDetail']> = {}): Schemas['ListDetail'] {
  return {
    id: LIST_ID,
    name: 'Wochenende',
    status: 'draft',
    version: 3,
    created_at: '2026-09-26T10:00:00Z',
    updated_at: '2026-09-26T12:00:00Z',
    owner: ME,
    is_owner: true,
    can_edit: true,
    shared_with_partner: false,
    reminder_seed: 1230,
    shopping_started_at: null,
    finished_at: null,
    meals: [listMeal(), PRIVATE_MEAL, DETACHED_MEAL],
    lines: LINES,
    extra_items: EXTRA_ITEMS,
    ...overrides,
  };
}

/** A draft without anything on it yet. */
export function emptyList(overrides: Partial<Schemas['ListDetail']> = {}): Schemas['ListDetail'] {
  return listDetail({
    id: 'list-new',
    name: null,
    meals: [],
    lines: [],
    extra_items: [],
    reminder_seed: 4,
    ...overrides,
  });
}

export function listSummary(
  overrides: Partial<Schemas['ListSummary']> = {},
): Schemas['ListSummary'] {
  return {
    id: LIST_ID,
    name: 'Wochenende',
    status: 'draft',
    created_at: '2026-09-26T10:00:00Z',
    updated_at: '2026-09-26T12:00:00Z',
    owner: ME,
    is_owner: true,
    can_edit: true,
    shared_with_partner: false,
    meal_count: 3,
    line_count: 5,
    finished_at: null,
    ...overrides,
  };
}

export const MY_LISTS: Schemas['ListSummary'][] = [
  listSummary({ shared_with_partner: true }),
  listSummary({
    id: 'list-ben',
    name: null,
    created_at: '2026-09-20T10:00:00Z',
    owner: BEN,
    is_owner: false,
    shared_with_partner: true,
    meal_count: 1,
    line_count: 1,
  }),
];

export const OTHERS_LISTS: Schemas['ListSummary'][] = [
  listSummary({
    id: 'list-carl',
    name: 'Grillabend',
    owner: CARL,
    is_owner: false,
    can_edit: false,
    meal_count: 2,
    line_count: 7,
  }),
];

/** Answers for the reference data, users and meals the list screens load. */
export const LIST_ROUTES: Record<string, unknown> = {
  ...MEAL_ROUTES,
  'GET /api/categories': CATEGORIES,
  'GET /api/users/visible': [ME, BEN, CARL],
  'GET /api/lists?scope=mine': MY_LISTS,
  'GET /api/lists?scope=others': OTHERS_LISTS,
  [`GET /api/lists/${LIST_ID}`]: listDetail(),
  'GET /api/meals/recent': [],
};

/** A line checked off by `user` at 13:30 on 26.09.2026. */
export function checkedBy(user: Schemas['UserRef']): Partial<Schemas['ListLine']> {
  return { checked: true, checked_at: '2026-09-26T13:30:00Z', checked_by: user };
}

/**
 * The lines of "Wochenende" while shopping: Zwiebeln to buy, Eier removed in the draft, Milch in
 * the cart (checked by Ben), Geburtstagskerzen new, Mehl checked but now needing more, Salz in the
 * cart (checked by me).
 */
export const SHOPPING_LINES: Schemas['ListLine'][] = LINES.map((entry) => {
  switch (entry.name) {
    case MILK.name:
      return { ...entry, ...checkedBy(BEN) };
    case 'Geburtstagskerzen':
      return { ...entry, new: true };
    case FLOUR.name:
      return {
        ...entry,
        needs_more: {
          grown: [{ value: 300, unit: 'g' }],
          new_unit: true,
          new_unspecified: true,
          changed: false,
        },
      };
    case SALT.name:
      return { ...entry, ...checkedBy(ME) };
    default:
      return entry;
  }
});

/** "Wochenende" being shopped. */
export function shoppingList(
  overrides: Partial<Schemas['ListDetail']> = {},
): Schemas['ListDetail'] {
  return listDetail({
    status: 'shopping',
    version: 5,
    shopping_started_at: '2026-09-26T13:00:00Z',
    lines: SHOPPING_LINES,
    ...overrides,
  });
}

/** "Wochenende" after shopping, finished on Saturday 26.09.2026 in the afternoon. */
export function doneList(overrides: Partial<Schemas['ListDetail']> = {}): Schemas['ListDetail'] {
  return shoppingList({
    status: 'done',
    version: 9,
    finished_at: '2026-09-26T14:00:00Z',
    ...overrides,
  });
}
