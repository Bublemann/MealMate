import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { api, unwrap } from '@/api/client';
import type { components } from '@/api/generated/schema';
import { useAuthSession, useCurrentUser } from '@/features/auth/context';

/** What the saved filters hide: users on Meals and on Lists, and list states on Lists. */
type SavedFilters = components['schemas']['FilterHidden'];

/** Whose meals (MEAL-10) or whose lists (UI-02) a user filter chooses. */
export type UserFilterKind = 'meals' | 'lists';

/** Everyone whose meals or lists the user can see, the user first (MEAL-10, UI-02, VIS-02). */
export function useVisibleUsers(kind: UserFilterKind) {
  return useQuery({
    queryKey: ['users', 'visible', kind],
    queryFn: ({ signal }) =>
      unwrap(api.GET('/api/users/visible', { params: { query: { for: kind } }, signal })),
  });
}

/**
 * The saves of every saved filter, which share `filter_hidden`: they run one after another, as
 * each sends all of it.
 */
const SAVE_KEY = ['me', 'filter-hidden'] as const;

/**
 * Saves what one of the saved filters hides: whom the user filter on Meals or on Lists hides
 * (MEAL-10, UI-02), or which states the state filter on Lists hides (UI-02). The choice changes
 * at once (optimistic), is saved on the server in `filter_hidden` so it follows the user to other
 * devices, and `reloadKey` (the query the filter narrows) loads again once it is saved; the last
 * waiting save stays pending until that answer is in. Saves run one after another, each sending
 * every filter; the saved state only replaces the choice once no other save is waiting, as it
 * doesn't know those yet. When saving fails, the profile and `reloadKey` are loaded again: going
 * back to a snapshot could undo a change queued after the failed one.
 */
export function useSaveFilter<K extends keyof SavedFilters>(kind: K, reloadKey: QueryKey) {
  const session = useAuthSession();
  const user = useCurrentUser();
  const queryClient = useQueryClient();
  const current = () => session.getState().user ?? user;
  const reload = () => queryClient.invalidateQueries({ queryKey: reloadKey });
  return useMutation({
    mutationKey: SAVE_KEY,
    scope: { id: SAVE_KEY.join('-') },
    mutationFn: (hidden: SavedFilters[K]) =>
      unwrap(
        api.PATCH('/api/me', {
          body: { filter_hidden: { ...current().filter_hidden, [kind]: hidden } },
        }),
      ),
    onMutate: (hidden) => {
      const me = current();
      session.setUser({ ...me, filter_hidden: { ...me.filter_hidden, [kind]: hidden } });
    },
    onError: async () => {
      void reload();
      try {
        session.setUser(await unwrap(api.GET('/api/me')));
      } catch {
        // Offline: the choice stays as it is until the next successful load.
      }
    },
    onSuccess: async (me) => {
      // This save still counts as running here.
      if (queryClient.isMutating({ mutationKey: SAVE_KEY }) > 1) {
        void reload();
        return;
      }
      session.setUser(me);
      // Until the results follow the choice, the screen can't tell "nothing to show" yet.
      await reload();
    },
  });
}
