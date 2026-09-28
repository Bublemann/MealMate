import type { Unit } from '@/features/reference/api';
import type { Language } from '@/i18n';
import type { BaseUnit, EditedField, Ingredient, OffProposal } from './api';
import { NUTRIENT_KEYS, numberInputValue, type NutrientKey } from './nutrients';

/** The longest ingredient name the server accepts; a name from Open Food Facts may be longer. */
export const NAME_MAX_LENGTH = 60;
export const BRAND_MAX_LENGTH = 80;
export const QUANTITY_TEXT_MAX_LENGTH = 40;

/** The text fields of the form. */
export const TEXT_FIELDS = ['name', 'brand', 'quantity_text'] as const;
export type TextField = (typeof TEXT_FIELDS)[number];
/** The optional number fields of the ingredient itself (never from Open Food Facts). */
export const NUMBER_FIELDS = ['piece_weight_g', 'density_g_per_ml'] as const;
export type NumberField = (typeof NUMBER_FIELDS)[number];

/**
 * What the form shows, as typed: numbers stay text until saving, so a half-typed "0," isn't
 * turned into something else, and a field counts as changed only when its text changed.
 */
export interface FormValues {
  name: string;
  brand: string;
  /** The chosen category; null until one is chosen, then `categoryKey` or "other" is shown. */
  categoryId: string | null;
  /** A category guessed from Open Food Facts, by key (the ids are only known once loaded). */
  categoryKey: string | null;
  baseUnit: BaseUnit;
  piece_weight_g: string;
  density_g_per_ml: string;
  barcode: string;
  quantity_text: string;
  pack_quantity: string;
  pack_unit: Unit | '';
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
    density_g_per_ml: '',
    barcode: '',
    quantity_text: '',
    pack_quantity: '',
    pack_unit: '',
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
    density_g_per_ml: numberInputValue(ingredient.density_g_per_ml, language),
    barcode: ingredient.barcode ?? '',
    quantity_text: ingredient.quantity_text ?? '',
    pack_quantity: numberInputValue(ingredient.pack_quantity, language),
    pack_unit: ingredient.pack_unit ?? '',
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
 * proposal doesn't have (piece weight, density, a name and a category guess when it has none)
 * stays as it was: a category the user chose is kept unless the proposal guesses one.
 */
export function valuesFromPrefill(
  { barcode, proposal }: Prefill,
  current: FormValues,
  language: Language,
): FormValues {
  if (!proposal) return { ...current, barcode };
  return {
    ...current,
    name: proposal.name ? fitName(proposal.name) : current.name,
    brand: proposal.brand?.slice(0, BRAND_MAX_LENGTH) ?? '',
    categoryId: proposal.category_key ? null : current.categoryId,
    categoryKey: proposal.category_key ?? current.categoryKey,
    baseUnit: proposal.nutrition_basis ?? current.baseUnit,
    barcode,
    quantity_text: proposal.quantity_text?.slice(0, QUANTITY_TEXT_MAX_LENGTH) ?? '',
    pack_quantity: numberInputValue(proposal.pack_quantity, language),
    pack_unit: proposal.pack_unit ?? '',
    nutrients: nutrientTexts(proposal.nutrients, language),
  };
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
  if (values.pack_quantity.trim() !== proposed.pack_quantity) edited.push('pack_quantity');
  if (values.pack_unit !== proposed.pack_unit) edited.push('pack_unit');
  for (const key of NUTRIENT_KEYS) {
    if (values.nutrients[key].trim() !== proposed.nutrients[key]) edited.push(`nutrients.${key}`);
  }
  return edited;
}
