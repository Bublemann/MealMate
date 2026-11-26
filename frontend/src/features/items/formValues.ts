import type { Language } from '@/i18n';
import type { BaseUnit, EditedField, Item, ItemKind, OffProposal } from './api';
import { NUTRIENT_KEYS, numberInputValue, type NutrientKey } from './nutrients';

/** The longest item name the server accepts; a name from Open Food Facts may be longer. */
export const NAME_MAX_LENGTH = 60;
export const BRAND_MAX_LENGTH = 80;

/** The text fields of the form, each an Open Food Facts field (BAR-04). */
export const TEXT_FIELDS = ['name', 'brand'] as const;
export type TextField = (typeof TEXT_FIELDS)[number];

/**
 * What the form shows, as typed: numbers stay text until saving, so a half-typed "0," isn't
 * turned into something else, and a field counts as changed only when its text changed.
 */
export interface FormValues {
  /** Food or a supply (D-55); Open Food Facts never sets it. */
  kind: ItemKind;
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
    kind: 'food',
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

/** The form of an existing item. */
export function valuesFromItem(item: Item, language: Language): FormValues {
  return {
    kind: item.kind,
    name: item.name,
    brand: item.brand ?? '',
    categoryId: item.category_id,
    categoryKey: null,
    baseUnit: item.base_unit,
    piece_weight_g: numberInputValue(item.piece_weight_g, language),
    barcode: item.barcode ?? '',
    nutrients: nutrientTexts(item.nutrients, language),
  };
}

/**
 * A name that fits the name field: longer names from Open Food Facts are cut at the last word
 * boundary before the limit.
 */
export function fitName(name: string): string {
  const trimmed = name.trim();
  if (trimmed.length <= NAME_MAX_LENGTH) return trimmed;
  const cut = trimmed.slice(0, NAME_MAX_LENGTH + 1);
  const space = cut.lastIndexOf(' ');
  return (space > 0 ? cut.slice(0, space) : cut.slice(0, NAME_MAX_LENGTH)).trim();
}

/**
 * The form filled with an Open Food Facts proposal, its barcode included (BAR-03, BAR-11). What
 * the proposal has no value for (the piece weight, and a name, brand, category guess,
 * base unit or nutrient when it has none) stays as it was: a category the user chose is kept
 * unless the proposal guesses one.
 */
export function valuesFromProposal(
  proposal: OffProposal,
  current: FormValues,
  language: Language,
): FormValues {
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
    barcode: proposal.barcode,
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
export function proposalValues(proposal: OffProposal, language: Language): FormValues {
  return valuesFromProposal(proposal, emptyValues('', language), language);
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
