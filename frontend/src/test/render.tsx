import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { connectAuth } from '@/api/client';
import { AppProviders } from '@/app/providers';
import { createQueryClient } from '@/app/queryClient';
import { routes } from '@/app/router';
import { createAuthSession } from '@/features/auth/session';
import type { Me } from '@/features/auth/storage';
import { TEST_USER } from './api';

interface RenderAppOptions {
  /** The signed-in user (default TEST_USER); `null` starts signed out and runs the start-up refresh. */
  user?: Me | null;
}

/** Renders the whole app (router, providers) at `path`, with retries off for fast failures. */
export function renderApp(path = '/', { user = TEST_USER }: RenderAppOptions = {}) {
  const queryClient = createQueryClient();
  const defaults = queryClient.getDefaultOptions();
  queryClient.setDefaultOptions({ ...defaults, queries: { ...defaults.queries, retry: false } });
  const authSession = createAuthSession(
    user ? { initial: { user, accessToken: 'test-access-token' } } : {},
  );
  connectAuth(authSession);
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const userEvents = userEvent.setup();
  const view = render(
    <AppProviders queryClient={queryClient} authSession={authSession}>
      <RouterProvider router={router} />
    </AppProviders>,
  );
  return { ...view, router, user: userEvents, authSession, queryClient };
}
