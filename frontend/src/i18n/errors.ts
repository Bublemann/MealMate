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

/**
 * Like fieldErrorMessages, but keyed by the whole path below the body, so nested fields keep
 * their own message: `{"loc": ["body", "manual", "kcal"]}` becomes `manual.kcal`.
 */
export function fieldErrorMessagesByPath(
  t: TFunction,
  error: unknown,
): Partial<Record<string, string>> {
  const messages: Partial<Record<string, string>> = {};
  if (!isApiError(error)) return messages;
  for (const { loc, code } of error.fields) {
    const path = (loc[0] === 'body' ? loc.slice(1) : loc).join('.');
    if (path in messages) continue;
    const key = `error.field.${code}` as const;
    messages[path] = i18n.exists(key) ? t(key) : t('error.field.invalid');
  }
  return messages;
}

/**
 * Whether a form needs its general error alert: the error has no field problems, or one for a
 * path the form shows no input for (e.g. `ingredient_id`), which would otherwise go unseen.
 */
export function needsErrorAlert(
  fieldMessages: Partial<Record<string, string>>,
  shownPaths: ReadonlySet<string>,
): boolean {
  const paths = Object.keys(fieldMessages);
  return paths.length === 0 || paths.some((path) => !shownPaths.has(path));
}
