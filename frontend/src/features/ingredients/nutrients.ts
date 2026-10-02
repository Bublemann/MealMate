import type { TFunction } from 'i18next';
import type { Language } from '@/i18n';
import { formatNumber, parseAmount } from '@/i18n/format';
import type { BaseUnit, NutrientValues } from './api';

export type NutrientKey = keyof NutrientValues;

/**
 * The tracked nutrients in display order (NUT-01). The server's registry is the source of truth;
 * adding a nutrient there changes the generated `NutrientValues` type, and the check below then
 * fails until the key is added here and translated (`nutrient.<key>`, `nutrientUnit.<key>`).
 */
export const NUTRIENT_KEYS = ['kcal', 'protein', 'carbs', 'sugar', 'fat'] as const;

type Missing = Exclude<NutrientKey, (typeof NUTRIENT_KEYS)[number]>;
// A compile-time error names a nutrient of the API that is missing from NUTRIENT_KEYS.
const allNutrientsListed: [Missing] extends [never] ? true : Missing = true;
void allNutrientsListed;

export function nutrientLabel(t: TFunction, key: NutrientKey): string {
  return t(`nutrient.${key}`);
}

/**
 * What an ingredient's nutrition values are per 100 of: g, or ml for an ingredient counted in
 * ml. Pieces count through the piece weight, so their values are per 100 g (ING-02).
 */
export function nutritionUnit(baseUnit: BaseUnit): 'g' | 'ml' {
  return baseUnit === 'ml' ? 'ml' : 'g';
}

/** "52 kcal" / "0,3 g": a value per 100 g or ml, formatted in the UI language. */
export function formatNutrient(
  t: TFunction,
  language: Language,
  key: NutrientKey,
  value: number,
): string {
  return t('common.amount', {
    value: formatNumber(value, language, { maximumFractionDigits: 1 }),
    unit: t(`nutrientUnit.${key}`),
  });
}

/** A number as a form field shows it: in the UI language, without grouping, so it parses back. */
export function numberInputValue(value: number | null | undefined, language: Language): string {
  if (value === null || value === undefined) return '';
  return formatNumber(value, language, { useGrouping: false, maximumFractionDigits: 6 });
}

export type ParsedNumber = { ok: true; value: number | null } | { ok: false };

/** An optional amount field: empty is `null`, anything unparsable is an error (`,` or `.`). */
export function parseOptionalAmount(text: string): ParsedNumber {
  if (text.trim() === '') return { ok: true, value: null };
  const value = parseAmount(text);
  return value === null ? { ok: false } : { ok: true, value };
}
