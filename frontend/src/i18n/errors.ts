import type { TFunction } from 'i18next';
import { errorKey, fieldErrorCodes, isApiError } from '@/api/errors';
import i18n from '.';

/** The translated message for any error; codes this app version doesn't know get the generic one. */
export function errorMessage(t: TFunction, error: unknown): string {
  const key = errorKey(error);
  if (!i18n.exists(key)) return t('error.common.internal');
  return t(key, isApiError(error) ? error.params : {});
}

/** Translated field errors by field name, e.g. `{username: "Already taken"}`. */
export function fieldErrorMessages(t: TFunction, error: unknown): Partial<Record<string, string>> {
  const messages: Partial<Record<string, string>> = {};
  for (const [name, code] of Object.entries(fieldErrorCodes(error))) {
    if (!code) continue;
    const key = `error.field.${code}` as const;
    messages[name] = i18n.exists(key) ? t(key) : t('error.field.invalid');
  }
  return messages;
}
