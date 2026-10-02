import type { TFunction } from 'i18next';
import { categoryName } from '@/features/reference/labels';
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
  // A category is named in the UI language, as everywhere else (D-31).
  const category = (prefix = '') =>
    categoryName(
      { names: { de: text(`${prefix}name_de`), en: text(`${prefix}name_en`) } },
      language,
    );
  if (event.action === 'category.create') {
    return t(ACTION_KEYS[event.action], { actor, name: category() });
  }
  if (event.action === 'category.rename') {
    const from = category('old_');
    const to = category();
    // Only its name in another language changed.
    if (from === to) return t('admin.events.action.categoryRenameOther', { actor, name: to });
    return t(ACTION_KEYS[event.action], { actor, from, to });
  }
  return t(ACTION_KEYS[event.action], {
    actor,
    target,
    name: text('name'),
    from: text('from_name'),
    into: text('into_name'),
  });
}
