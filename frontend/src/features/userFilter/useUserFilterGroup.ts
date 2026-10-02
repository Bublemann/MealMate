import type { QueryKey } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { FilterGroup } from '@/components/FilterPanel';
import { useCurrentUser } from '@/features/auth/context';
import { userLabel } from '@/i18n/users';
import { useSaveUserFilter, useVisibleUsers, type UserFilterKind } from './api';

interface UserFilterOptions {
  /** Names the group, e.g. "Gerichte von". */
  label: string;
  /** The query whose results the filter narrows: it loads again once a change is saved. */
  reload: QueryKey;
}

interface UserFilter {
  /** The group for the filter panel. */
  group: FilterGroup;
  /** The unticked users, a change that is still being saved included. */
  hidden: ReadonlySet<string>;
  /** Ticks everyone again: part of "Zurücksetzen" and "Filter zurücksetzen". */
  reset: () => void;
}

/**
 * The user filter on Meals or on Lists as a group of the filter panel (MEAL-10, UI-02): one
 * checkbox per user whose meals or lists are visible, "Me" first, ticked while their meals or
 * lists are shown. It is at its default while it hides none of them. Each change is saved on the
 * server at once (`useSaveUserFilter`); a failed load or save shows in the group.
 */
export function useUserFilterGroup(
  kind: UserFilterKind,
  { label, reload }: UserFilterOptions,
): UserFilter {
  const { t } = useTranslation();
  const me = useCurrentUser();
  const users = useVisibleUsers(kind);
  const save = useSaveUserFilter(kind, reload);
  const hidden = new Set(me.filter_hidden[kind]);
  const userIds = users.data?.map((user) => user.id);

  return {
    group: {
      label,
      options: users.data?.map((user) => ({
        id: user.id,
        label: user.id === me.id ? t('filter.me') : userLabel(t, user),
      })),
      checked: userIds?.filter((id) => !hidden.has(id)) ?? [],
      // Until the users have loaded, anyone hidden counts.
      active: userIds ? userIds.some((id) => hidden.has(id)) : hidden.size > 0,
      // Users who can't be seen right now stay hidden, as they were.
      onChange: (checked) =>
        save.mutate([
          ...[...hidden].filter((id) => !userIds?.includes(id)),
          ...(userIds ?? []).filter((id) => !checked.includes(id)),
        ]),
      error: users.error ?? save.error,
    },
    hidden,
    reset: () => {
      if (hidden.size > 0) save.mutate([]);
    },
  };
}
