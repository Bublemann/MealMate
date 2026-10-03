import type { components } from '@/api/generated/schema';
import type { FilterGroup } from '@/components/FilterPanel';

/**
 * What the saved filters hide, kept in the profile (`/me`) so they follow the user to other
 * devices: users on Meals (MEAL-10) and on Lists, and list states on Lists (UI-02).
 */
export type SavedFilters = components['schemas']['FilterHidden'];

/** Whose meals (MEAL-10) or whose lists (UI-02) a user filter chooses. */
export type UserFilterKind = Exclude<keyof SavedFilters, 'list_states'>;

/** A state of a shopping list, as the state filter offers it (UI-02). */
export type ListState = SavedFilters['list_states'][number];

/** A saved filter as a group of the filter panel. */
export interface SavedFilterGroup<Id extends string> {
  /** The group for the filter panel. */
  group: FilterGroup;
  /** What it hides, a change that is still being saved included. */
  hidden: ReadonlySet<Id>;
  /** A change is being saved, or the results are loading again after it. */
  saving: boolean;
  /** Ticks everything again: part of "Zurücksetzen" and "Filter zurücksetzen". */
  reset: () => void;
}
