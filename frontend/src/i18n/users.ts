import type { TFunction } from 'i18next';
import type { components } from '@/api/generated/schema';

type UserRef = components['schemas']['UserRef'];

/** A user's display name, "(deactivated)" added (ADM-02); "Deleted user" when gone (ADM-03). */
export function userLabel(t: TFunction, user: UserRef | null | undefined): string {
  if (!user) return t('common.deletedUser');
  return user.deactivated
    ? t('common.userDeactivated', { name: user.display_name })
    : user.display_name;
}
