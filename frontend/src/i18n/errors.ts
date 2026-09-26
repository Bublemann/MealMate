import type { TFunction } from 'i18next';
import { errorKey, isApiError } from '@/api/errors';
import i18n from '.';

/** The translated message for any error; codes this app version doesn't know get the generic one. */
export function errorMessage(t: TFunction, error: unknown): string {
  const key = errorKey(error);
  if (!i18n.exists(key)) return t('error.common.internal');
  return t(key, isApiError(error) ? error.params : {});
}
