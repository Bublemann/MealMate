import { useTranslation } from 'react-i18next';
import type { FilterGroup } from '@/components/FilterPanel';
import { useCurrentUser } from '@/features/auth/context';
import { useSaveFilter } from '@/features/userFilter/api';
import type { ListSummary } from './api';
import { FEED_KEY } from './keys';

type ListState = ListSummary['status'];

/** Every state of a list, in the order a list goes through them (LIST-10). */
const STATES: readonly ListState[] = ['draft', 'shopping', 'done'];

interface StateFilter {
  /** The group for the filter panel. */
  group: FilterGroup;
  /** The unticked states, a change that is still being saved included. */
  hidden: ReadonlySet<ListState>;
  /** A change is being saved, or the feed is loading again after it. */
  saving: boolean;
  /** Ticks every state again: part of "Zurücksetzen" and "Filter zurücksetzen". */
  reset: () => void;
}

/**
 * The state filter on Lists as a group of the filter panel (UI-02): "Entwurf", "Einkauf" and
 * "Erledigt", ticked while lists in that state are shown, all ticked by default. Each change is
 * saved on the server at once, next to the user filter, and loads the feed again
 * (`useSaveFilter`); a failed save shows in the group.
 */
export function useStateFilterGroup(): StateFilter {
  const { t } = useTranslation();
  const me = useCurrentUser();
  const save = useSaveFilter('list_states', FEED_KEY);
  const hidden = new Set(me.filter_hidden.list_states);
  const active = hidden.size > 0;

  return {
    group: {
      label: t('lists.filter.states'),
      options: STATES.map((state) => ({ id: state, label: t(`lists.filter.state.${state}`) })),
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
