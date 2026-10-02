import type { QueryKey } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { FilterGroup } from '@/components/FilterPanel';
import { useCurrentUser } from '@/features/auth/context';
import { userLabel } from '@/i18n/users';
import { useSaveUserFilter, useVisibleUsers, type UserFilterKind } from './api';

interface UserFilter {
  /** The group for the filter panel. */
  group: FilterGroup;
  /** The unticked users, a change that is still being saved included. */
  hidden: ReadonlySet<string>;
  /** A change is being saved, or the results are loading again after it. */
  saving: boolean;
  /** Ticks every visible user again: part of "Zurücksetzen" and "Filter zurücksetzen". */
  reset: () => void;
}

/**
 * The user filter on Meals or on Lists as a group of the filter panel (MEAL-10, UI-02): one
 * checkbox per user whose meals or lists are visible, "Me" first, ticked while their meals or
 * lists are shown. It is at its default while it hides none of them; users who can't be seen
 * right now stay hidden, also on a reset. Each change is saved on the server at once and loads
 * `reloadKey` again (`useSaveUserFilter`); a failed load or save shows in the group.
 */
export function useUserFilterGroup(
  kind: UserFilterKind,
  { label, reloadKey }: { label: string; reloadKey: QueryKey },
): UserFilter {
  const { t } = useTranslation();
  const me = useCurrentUser();
  const visible = useVisibleUsers(kind);
  const save = useSaveUserFilter(kind, reloadKey);
  const hidden = new Set(me.filter_hidden[kind]);
  const visibleIds = visible.data?.map((user) => user.id);
  // Until the users have loaded, anyone hidden counts.
  const active = visibleIds ? visibleIds.some((id) => hidden.has(id)) : hidden.size > 0;
  // Before the users have loaded, a reset shows everyone.
  const hiddenElsewhere = visibleIds ? [...hidden].filter((id) => !visibleIds.includes(id)) : [];

  return {
    group: {
      label,
      options: visible.data?.map((user) => ({
        id: user.id,
        label: user.id === me.id ? t('filter.me') : userLabel(t, user),
      })),
      checked: visibleIds?.filter((id) => !hidden.has(id)) ?? [],
      active,
      onChange: (checked) =>
        save.mutate([
          ...hiddenElsewhere,
          ...(visibleIds ?? []).filter((id) => !checked.includes(id)),
        ]),
      error: visible.error ?? save.error,
    },
    hidden,
    saving: save.isPending,
    reset: () => {
      if (active) save.mutate(hiddenElsewhere);
    },
  };
}
