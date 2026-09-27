import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { AuthProvider } from '@/features/auth/AuthProvider';
import type { AuthSession } from '@/features/auth/session';

interface AppProvidersProps {
  queryClient: QueryClient;
  authSession: AuthSession;
  children: ReactNode;
}

/** App-wide context providers. i18n needs none: react-i18next uses the instance from src/i18n. */
export function AppProviders({ queryClient, authSession, children }: AppProvidersProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider session={authSession}>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
