import type { IngredientSummary } from '@/features/ingredients/api';
import { numberInputValue, parseOptionalAmount } from '@/features/ingredients/nutrients';
import type { Unit } from '@/features/reference/api';
import type { Language } from '@/i18n';
import type { Meal, MealCreate, MealIngredientInput, MealUpdate } from './api';

export const MIN_SERVINGS = 1;
export const MAX_SERVINGS = 99;
export const MAX_TAGS = 10;
export const MAX_TAG_LENGTH = 30;

/** One ingredient row as the form edits it. */
export interface RowState {
  /** Stable React key, also for rows not saved yet. */
  key: string;
  ingredient: IngredientSummary;
  amountText: string;
  /** The amount the row was loaded with, and how the field showed it. */
  initialAmount: number | null;
  initialAmountText: string;
  /** '' is "no unit". */
  unit: Unit | '';
  /** Once the user picked a unit (or loaded a row with one), the amount no longer chooses it. */
  unitChosen: boolean;
  note: string;
}

let nextKey = 0;
function rowKey(): string {
  nextKey += 1;
  return `row-${nextKey}`;
}

/** A new row for a picked ingredient: no amount and no unit yet ("to taste" is fine). */
export function newRow(ingredient: IngredientSummary): RowState {
  return {
    key: rowKey(),
    ingredient,
    amountText: '',
    initialAmount: null,
    initialAmountText: '',
    unit: '',
    unitChosen: false,
    note: '',
  };
}

export function rowsOf(meal: Meal, language: Language): RowState[] {
  return meal.ingredients.map((row) => {
    const text = numberInputValue(row.amount, language);
    return {
      key: rowKey(),
      ingredient: row.ingredient,
      amountText: text,
      initialAmount: row.amount,
      initialAmountText: text,
      unit: row.unit ?? '',
      // A "to taste" row picks the base unit like a new row once an amount is typed.
      unitChosen: row.unit !== null,
      note: row.note ?? '',
    };
  });
}

/**
 * Typing an amount into a row without a unit picks the ingredient's base unit (g or ml), unless
 * the user chose a unit (or "no unit") on purpose; the server would otherwise count the amount
 * as pieces. Clearing the amount again takes a picked unit back, so the row stays "to taste".
 */
export function withAmountText(row: RowState, amountText: string): RowState {
  if (row.unitChosen) return { ...row, amountText };
  const unit = amountText.trim() === '' ? '' : row.unit || row.ingredient.base_unit;
  return { ...row, amountText, unit };
}

export function moved<T>(items: readonly T[], index: number, offset: -1 | 1): T[] {
  const target = index + offset;
  if (target < 0 || target >= items.length) return [...items];
  const next = [...items];
  [next[index], next[target]] = [next[target] as T, next[index] as T];
  return next;
}

/** Adds a tag unless it is empty, already there (ignoring case) or the meal has 10 tags. */
export function withTag(tags: readonly string[], text: string): string[] {
  const tag = text.trim().slice(0, MAX_TAG_LENGTH);
  const lower = tag.toLocaleLowerCase();
  if (!tag || tags.length >= MAX_TAGS || tags.some((t) => t.toLocaleLowerCase() === lower)) {
    return [...tags];
  }
  return [...tags, tag];
}

/** Servings as typed: a whole number from 1 to 99, else null. */
export function parseServings(text: string): number | null {
  if (!/^\d{1,2}$/.test(text.trim())) return null;
  const value = Number(text.trim());
  return value >= MIN_SERVINGS && value <= MAX_SERVINGS ? value : null;
}

export interface FormValues {
  name: string;
  servingsText: string;
  cuisineId: string;
  tags: string[];
  rows: RowState[];
  instructions: string;
  sourceUrl: string;
}

/** The form's start: the meal's values, or a new meal with only `name` filled in (MEAL-09). */
export function initialValues(meal: Meal | undefined, language: Language, name = ''): FormValues {
  return {
    name: meal?.name ?? name,
    servingsText: String(meal?.servings ?? MIN_SERVINGS),
    cuisineId: meal?.cuisine?.id ?? '',
    tags: meal?.tags.map((tag) => tag.name) ?? [],
    rows: meal ? rowsOf(meal, language) : [],
    instructions: meal?.instructions ?? '',
    sourceUrl: meal?.source_url ?? '',
  };
}

export type Checked =
  | { ok: true; servings: number; ingredients: MealIngredientInput[] }
  | { ok: false; problems: Set<string> };

/**
 * Reads the typed numbers. Problems are keyed like the server's field paths (`servings`,
 * `ingredients.2.amount`), so they show in the same place.
 */
export function checkValues(values: FormValues): Checked {
  const problems = new Set<string>();
  const servings = parseServings(values.servingsText);
  if (servings === null) problems.add('servings');
  const ingredients = values.rows.map((row, index): MealIngredientInput => {
    let amount: number | null = row.initialAmount;
    if (row.amountText.trim() !== row.initialAmountText) {
      // Unchanged text keeps the stored value, which may have more decimals than shown.
      const parsed = parseOptionalAmount(row.amountText);
      if (parsed.ok) amount = parsed.value;
      else problems.add(`ingredients.${index}.amount`);
    }
    return {
      ingredient_id: row.ingredient.id,
      amount,
      unit: row.unit === '' ? null : row.unit,
      note: row.note.trim() === '' ? null : row.note.trim(),
    };
  });
  if (problems.size > 0 || servings === null) return { ok: false, problems };
  return { ok: true, servings, ingredients };
}

/**
 * The problems except those of ingredient rows (`ingredients.2.amount`): they name a row by its
 * position, which no longer fits once a row moved or was removed.
 */
export function withoutRowProblems(problems: ReadonlySet<string>): Set<string> {
  return new Set([...problems].filter((path) => !path.startsWith('ingredients.')));
}

/** Trimmed text, or null when empty (the server stores empty texts as null). */
function optionalText(text: string): string | null {
  const value = text.trim();
  return value === '' ? null : value;
}

export function createBody(
  values: FormValues,
  checked: Extract<Checked, { ok: true }>,
): MealCreate {
  const body: MealCreate = { name: values.name.trim(), servings: checked.servings };
  const instructions = optionalText(values.instructions);
  const sourceUrl = optionalText(values.sourceUrl);
  if (instructions !== null) body.instructions = instructions;
  if (sourceUrl !== null) body.source_url = sourceUrl;
  if (values.cuisineId) body.cuisine_id = values.cuisineId;
  if (values.tags.length > 0) body.tags = values.tags;
  if (checked.ingredients.length > 0) body.ingredients = checked.ingredients;
  return body;
}

function sameIngredients(meal: Meal, inputs: MealIngredientInput[]): boolean {
  const stored = meal.ingredients.map((row): MealIngredientInput => ({
    ingredient_id: row.ingredient.id,
    amount: row.amount,
    unit: row.unit,
    note: row.note,
  }));
  return JSON.stringify(stored) === JSON.stringify(inputs);
}

/**
 * Only what changed, so a field nobody touched is never overwritten. `tags` and `ingredients`
 * replace the whole list when sent; null clears an optional field.
 */
export function updateBody(
  meal: Meal,
  values: FormValues,
  checked: Extract<Checked, { ok: true }>,
): MealUpdate {
  const body: MealUpdate = {};
  const name = values.name.trim();
  const instructions = optionalText(values.instructions);
  const sourceUrl = optionalText(values.sourceUrl);
  const cuisineId = values.cuisineId === '' ? null : values.cuisineId;
  if (name !== meal.name) body.name = name;
  if (checked.servings !== meal.servings) body.servings = checked.servings;
  if (instructions !== (meal.instructions ?? null)) body.instructions = instructions;
  if (sourceUrl !== (meal.source_url ?? null)) body.source_url = sourceUrl;
  if (cuisineId !== (meal.cuisine?.id ?? null)) body.cuisine_id = cuisineId;
  if (JSON.stringify(values.tags) !== JSON.stringify(meal.tags.map((tag) => tag.name))) {
    body.tags = values.tags;
  }
  if (!sameIngredients(meal, checked.ingredients)) body.ingredients = checked.ingredients;
  return body;
}

/** The server's field paths the form shows next to an input; anything else goes to the alert. */
const SHOWN_PATH =
  /^(name|servings|cuisine_id|instructions|source_url|tags(\.\d+)?|ingredients(\.\d+(\.(ingredient_id|amount|unit|note))?)?)$/;

export function isShownPath(path: string): boolean {
  return SHOWN_PATH.test(path);
}
