import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { AppProviders } from '@/app/providers';
import { createQueryClient } from '@/app/queryClient';
import { routes } from '@/app/router';

/** Renders the whole app (router, providers) at `path`, with retries off for fast failures. */
export function renderApp(path = '/') {
  const queryClient = createQueryClient();
  const defaults = queryClient.getDefaultOptions();
  queryClient.setDefaultOptions({ ...defaults, queries: { ...defaults.queries, retry: false } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const user = userEvent.setup();
  const view = render(
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...view, router, user };
}

export const VERSION_INFO = {
  version: '2.0.0-alpha.1',
  commit: '0123456789abcdef0123456789abcdef01234567',
  source_url: 'https://github.com/Bublemann/MealMate/tree/0123456789abcdef0123456789abcdef01234567',
};
