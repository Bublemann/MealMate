import type { QueryKey } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useCurrentUser } from '@/features/auth/context';
import { useSaveFilter } from './api';
import type { ListState, SavedFilterGroup } from './types';

/**
 * The states' labels, in the order a list goes through them (LIST-10). Keyed by state, so a new
 * state can't be left out.
 */
const STATE_LABELS = {
  draft: 'lists.filter.state.draft',
  shopping: 'lists.filter.state.shopping',
  done: 'lists.filter.state.done',
} as const satisfies Record<ListState, string>;

const STATES = Object.keys(STATE_LABELS) as ListState[];

/**
 * The state filter on Lists as a group of the filter panel (UI-02): "Entwurf", "Einkauf" and
 * "Erledigt", ticked while lists in that state are shown, all ticked by default. Each change is
 * saved on the server at once, next to the user filter, and loads `reloadKey` again
 * (`useSaveFilter`); a failed save shows in the group.
 */
export function useStateFilterGroup({
  label,
  reloadKey,
}: {
  label: string;
  reloadKey: QueryKey;
}): SavedFilterGroup<ListState> {
  const { t } = useTranslation();
  const me = useCurrentUser();
  const save = useSaveFilter('list_states', reloadKey);
  const hidden = new Set(me.filter_hidden.list_states);
  const active = hidden.size > 0;

  return {
    group: {
      label,
      options: STATES.map((state) => ({ id: state, label: t(STATE_LABELS[state]) })),
      checked: STATES.filter((state) => !hidden.has(state)),
      active,
      onChange: (checked) => save.mutate(STATES.filter((state) => !checked.includes(state))),
      error: save.error,
    },
    hidden,
    saving: save.isPending,
    reset: () => {
      if (active) save.mutate([]);
    },
  };
}
