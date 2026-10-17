import type { ParseKeys } from 'i18next';
import type { ComponentType } from 'react';
import { testIds, type TestId } from '@/testIds';

/** A group of rows on the Settings tab, in a panel of its own (UI-07). */
export interface SettingsGroup {
  id: 'own' | 'admin' | 'about';
  /** The group's heading above its panel, if it has one. */
  heading?: ParseKeys;
  /** Only admins see the group (ADM-01); the server checks the role on every admin request. */
  adminOnly?: boolean;
  testId?: TestId;
}

/** One row: a link to its page, with its label, a short value where it helps, and a chevron. */
export interface SettingsRow {
  group: SettingsGroup['id'];
  /** The row's label; its accessible name starts with it, whatever the value. */
  label: ParseKeys;
  to: string;
  /**
   * The row's value (D-45), loaded by the row itself so that it never holds the rows back:
   * nothing while it loads, fails or can't be fetched offline.
   */
  value?: ComponentType;
}

/** The groups, top to bottom; Abmelden follows them as the last row. */
export const SETTINGS_GROUPS: readonly SettingsGroup[] = [
  { id: 'own' },
  { id: 'admin', heading: 'admin.title', adminOnly: true, testId: testIds.adminEntry },
  { id: 'about' },
];

/**
 * The rows, top to bottom, each one entry: a later page (e.g. "Regelmäßige Artikel") adds its
 * row here, in its group, and its route in `app/router.tsx`.
 */
export const SETTINGS_ROWS: readonly SettingsRow[] = [
  { group: 'own', label: 'me.profile.title', to: '/me/profile' },
  { group: 'own', label: 'me.privacy.title', to: '/me/privacy' },
  { group: 'own', label: 'couple.title', to: '/me/couple' },
  { group: 'own', label: 'me.security.title', to: '/me/security' },
  // The admin pages are a separate chunk (PERF-03): only their addresses are named here.
  { group: 'admin', label: 'admin.users.title', to: '/me/admin/users' },
  { group: 'admin', label: 'admin.invites.title', to: '/me/admin/invites' },
  { group: 'admin', label: 'admin.categories.title', to: '/me/admin/categories' },
  { group: 'admin', label: 'admin.events.title', to: '/me/admin/events' },
  { group: 'admin', label: 'admin.system.title', to: '/me/admin/system' },
  { group: 'about', label: 'me.about', to: '/me/about' },
];
