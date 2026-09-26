import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';

interface AppProvidersProps {
  queryClient: QueryClient;
  children: ReactNode;
}

/** App-wide context providers. i18n needs none: react-i18next uses the instance from src/i18n. */
export function AppProviders({ queryClient, children }: AppProvidersProps) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
