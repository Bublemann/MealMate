import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { AuthProvider } from '@/features/auth/AuthProvider';
import type { AuthSession } from '@/features/auth/session';
import { SyncProvider } from '@/features/sync/SyncProvider';

interface AppProvidersProps {
  queryClient: QueryClient;
  authSession: AuthSession;
  children: ReactNode;
}

/**
 * App-wide context providers. i18n needs none: react-i18next uses the instance from src/i18n. The
 * sync module sits inside the session, whose sign-ins and ends it follows (SYNC-10).
 */
export function AppProviders({ queryClient, authSession, children }: AppProvidersProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider session={authSession}>
        <SyncProvider session={authSession}>{children}</SyncProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}
