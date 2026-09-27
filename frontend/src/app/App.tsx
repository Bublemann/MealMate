import { useState } from 'react';
import { createBrowserRouter, RouterProvider } from 'react-router';
import type { AuthSession } from '@/features/auth/session';
import { AppProviders } from './providers';
import { createQueryClient } from './queryClient';
import { routes } from './router';

export function App({ authSession }: { authSession: AuthSession }) {
  const [queryClient] = useState(createQueryClient);
  const [router] = useState(() => createBrowserRouter(routes));

  return (
    <AppProviders queryClient={queryClient} authSession={authSession}>
      <RouterProvider router={router} />
    </AppProviders>
  );
}
