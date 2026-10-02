import { screen, within } from '@testing-library/react';
import type { components } from '@/api/generated/schema';
import { testIds } from '@/testIds';
import { requestsTo, type mockApi } from './api';
import type { renderApp } from './render';

type Me = components['schemas']['Me'];

/**
 * `PATCH /api/me` that saves the filters it is sent, as the server does (MEAL-10, UI-02);
 * `saved()` gives what is saved, e.g. for the route that the filters narrow.
 */
export function filterSaves(me: Me) {
  let saved = me.filter_hidden;
  return {
    saved: () => saved,
    route: async (request: Request) => {
      ({ filter_hidden: saved } = (await request.json()) as Pick<Me, 'filter_hidden'>);
      return { ...me, filter_hidden: saved };
    },
  };
}

/** The bodies of the profile saves, read from copies so a waitFor can read them again. */
export async function savedFilters(fetchMock: ReturnType<typeof mockApi>) {
  return Promise.all(
    requestsTo(fetchMock, 'PATCH /api/me').map((request) => request.clone().json()),
  );
}

/** Opens the filter panel of the tab's pinned block (UI-01). */
export async function openPanel(user: ReturnType<typeof renderApp>['user']) {
  await user.click(screen.getByTestId(testIds.filterButton));
  return screen.findByRole('dialog', { name: 'Filters' });
}

/** A group of checkboxes in the filter panel, by its name. */
export function group(panel: HTMLElement, name: string) {
  return within(panel).getByRole('group', { name });
}

/** The checkboxes' names: the text of the label each one sits in. */
export function checkboxNames(element: HTMLElement) {
  return within(element)
    .getAllByRole('checkbox')
    .map((box) => (box as HTMLInputElement).labels?.[0]?.textContent);
}
