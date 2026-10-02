import type { TFunction } from 'i18next';
import type { Language } from '@/i18n';
import { userLabel } from '@/i18n/users';
import type { AdminEvent } from './api';

const ACTION_KEYS = {
  'invite.create': 'admin.events.action.inviteCreate',
  'invite.revoke': 'admin.events.action.inviteRevoke',
  'user.reset_link': 'admin.events.action.userResetLink',
  'user.role_change': 'admin.events.action.userRoleChange',
  'user.deactivate': 'admin.events.action.userDeactivate',
  'user.reactivate': 'admin.events.action.userReactivate',
  'user.delete': 'admin.events.action.userDelete',
  'category.create': 'admin.events.action.categoryCreate',
  'category.rename': 'admin.events.action.categoryRename',
  'category.reorder': 'admin.events.action.categoryReorder',
  'ingredient.merge': 'admin.events.action.ingredientMerge',
  'ingredient.delete': 'admin.events.action.ingredientDelete',
  'system.backup_request': 'admin.events.action.systemBackupRequest',
} as const;

function isKnownAction(action: string): action is keyof typeof ACTION_KEYS {
  return action in ACTION_KEYS;
}

/** "Anna made Ben an admin", from the event's action and the users it names. */
export function describeEvent(t: TFunction, event: AdminEvent, language: Language): string {
  const actor = userLabel(t, event.actor);
  const target = userLabel(t, event.target);
  if (!isKnownAction(event.action)) return t('admin.events.action.unknown', { actor });
  if (event.action === 'user.role_change') {
    const role = event.details.role;
    if (role === 'admin') return t('admin.events.action.userPromote', { actor, target });
    if (role === 'user') return t('admin.events.action.userDemote', { actor, target });
  }
  // Ingredient and category events name them as they were called then (they may be gone now).
  const text = (key: string) => {
    const value = event.details[key];
    return typeof value === 'string' ? value : '';
  };
  if (event.action === 'category.create') {
    // A category's names, one per language (D-31): the UI language's, else the English one.
    const name = text(`name_${language}`) || text('name_en');
    return t(ACTION_KEYS[event.action], { actor, name });
  }
  if (event.action === 'category.rename') {
    // A rename may change one name only: shown in the UI language if that one changed.
    const changed =
      [language, 'en', 'de'].find((code) => text(`old_name_${code}`) !== text(`name_${code}`)) ??
      language;
    const from = text(`old_name_${changed}`);
    return t(ACTION_KEYS[event.action], { actor, from, to: text(`name_${changed}`) });
  }
  return t(ACTION_KEYS[event.action], {
    actor,
    target,
    name: text('name'),
    from: text('from_name'),
    into: text('into_name'),
  });
}
