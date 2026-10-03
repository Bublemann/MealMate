import type { Language } from '@/i18n';
import type { BaseUnit, EditedField, Ingredient, OffProposal } from './api';
import { NUTRIENT_KEYS, numberInputValue, type NutrientKey } from './nutrients';

/** The longest ingredient name the server accepts; a name from Open Food Facts may be longer. */
export const NAME_MAX_LENGTH = 60;
export const BRAND_MAX_LENGTH = 80;

/** The text fields of the form. */
export const TEXT_FIELDS = ['name', 'brand'] as const;
export type TextField = (typeof TEXT_FIELDS)[number];

/**
 * What the form shows, as typed: numbers stay text until saving, so a half-typed "0," isn't
 * turned into something else, and a field counts as changed only when its text changed. The
 * pack size isn't typed in: it comes with an Open Food Facts proposal (D-38).
 */
export interface FormValues {
  name: string;
  brand: string;
  /** The chosen category; null until one is chosen, then `categoryKey` or "other" is shown. */
  categoryId: string | null;
  /** A category guessed from Open Food Facts, by key (the ids are only known once loaded). */
  categoryKey: string | null;
  baseUnit: BaseUnit;
  /** Only for base unit Stück (ING-02). */
  piece_weight_g: string;
  barcode: string;
  nutrients: Record<NutrientKey, string>;
}

/** A barcode looked up or a result of the Open Food Facts search, to start a new ingredient. */
export interface Prefill {
  barcode: string;
  /** The values from Open Food Facts; null for a barcode it doesn't know (or couldn't answer). */
  proposal: OffProposal | null;
}

function nutrientTexts(
  values: Partial<Record<NutrientKey, number | null>> | undefined,
  language: Language,
): Record<NutrientKey, string> {
  return Object.fromEntries(
    NUTRIENT_KEYS.map((key) => [key, numberInputValue(values?.[key], language)]),
  ) as Record<NutrientKey, string>;
}

/** An empty form, optionally with a name (e.g. what was searched for). */
export function emptyValues(name = '', language: Language): FormValues {
  return {
    name,
    brand: '',
    categoryId: null,
    categoryKey: null,
    baseUnit: 'g',
    piece_weight_g: '',
    barcode: '',
    nutrients: nutrientTexts(undefined, language),
  };
}

/** The form of an existing ingredient. */
export function valuesFromIngredient(ingredient: Ingredient, language: Language): FormValues {
  return {
    name: ingredient.name,
    brand: ingredient.brand ?? '',
    categoryId: ingredient.category_id,
    categoryKey: null,
    baseUnit: ingredient.base_unit,
    piece_weight_g: numberInputValue(ingredient.piece_weight_g, language),
    barcode: ingredient.barcode ?? '',
    nutrients: nutrientTexts(ingredient.nutrients, language),
  };
}

/**
 * A name that fits the name field: longer names from Open Food Facts are cut at the last word
 * boundary before the limit (the whole name stays readable in the proposal's brand and pack).
 */
export function fitName(name: string): string {
  const trimmed = name.trim();
  if (trimmed.length <= NAME_MAX_LENGTH) return trimmed;
  const cut = trimmed.slice(0, NAME_MAX_LENGTH + 1);
  const space = cut.lastIndexOf(' ');
  return (space > 0 ? cut.slice(0, space) : cut.slice(0, NAME_MAX_LENGTH)).trim();
}

/**
 * The form with a barcode and, if Open Food Facts knows it, its proposal (BAR-03). What the
 * proposal has no value for (the piece weight, and a name, brand, category guess, base unit or
 * nutrient when it has none) stays as it was: a category the user chose is kept unless the
 * proposal guesses one.
 */
export function valuesFromPrefill(
  { barcode, proposal }: Prefill,
  current: FormValues,
  language: Language,
): FormValues {
  if (!proposal) return { ...current, barcode };
  const nutrients = { ...current.nutrients };
  for (const key of NUTRIENT_KEYS) {
    const value = proposal.nutrients[key];
    if (value !== null && value !== undefined) nutrients[key] = numberInputValue(value, language);
  }
  return {
    ...current,
    name: proposal.name ? fitName(proposal.name) : current.name,
    brand: proposal.brand ? proposal.brand.slice(0, BRAND_MAX_LENGTH) : current.brand,
    categoryId: proposal.category_key ? null : current.categoryId,
    categoryKey: proposal.category_key ?? current.categoryKey,
    baseUnit: proposal.nutrition_basis ?? current.baseUnit,
    barcode,
    nutrients,
  };
}

/**
 * The form without the texts and nutrients an earlier proposal filled in (`proposed` is its
 * `proposalValues`) and the user left as they were: a product chosen instead keeps only the ones
 * the user typed, so another product's values are never saved as user-edited (BAR-03, BAR-04).
 */
export function typedValues(values: FormValues, proposed: FormValues): FormValues {
  const typed: FormValues = { ...values, nutrients: { ...values.nutrients } };
  for (const field of TEXT_FIELDS) {
    if (values[field].trim() === proposed[field].trim()) typed[field] = '';
  }
  for (const key of NUTRIENT_KEYS) {
    if (values.nutrients[key].trim() === proposed.nutrients[key]) typed.nutrients[key] = '';
  }
  return typed;
}

/**
 * The proposal's own values, to tell the edited fields by: not the form as it was filled, which
 * keeps what the proposal lacks (a name typed before choosing a product without one is the
 * user's, not Open Food Facts').
 */
export function proposalValues(prefill: Prefill, language: Language): FormValues {
  return valuesFromPrefill(prefill, emptyValues('', language), language);
}

/**
 * The Open Food Facts fields the user changed compared with the proposal (BAR-04; `proposed` is
 * `proposalValues`): only these count as edited by a user, so a later Open Food Facts update may
 * still change the rest.
 */
export function editedFields(values: FormValues, proposed: FormValues): EditedField[] {
  const edited: EditedField[] = [];
  for (const field of TEXT_FIELDS) {
    if (values[field].trim() !== proposed[field].trim()) edited.push(field);
  }
  for (const key of NUTRIENT_KEYS) {
    if (values.nutrients[key].trim() !== proposed.nutrients[key]) edited.push(`nutrients.${key}`);
  }
  return edited;
}
