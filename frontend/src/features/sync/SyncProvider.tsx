import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, type ReactNode } from 'react';
import type { AuthSession } from '@/features/auth/session';
import { SyncContext } from './context';
import { SyncEngine, type SyncEngineOptions } from './engine';

interface SyncProviderProps {
  session: AuthSession;
  /** Where the copy and the outbox live (tests); default IndexedDB, else memory. */
  openStorage?: SyncEngineOptions['openStorage'];
  children: ReactNode;
}

/**
 * Creates the sync module for the app (plan § 8) and runs it while mounted: it follows the
 * session (SYNC-10), the connection and the app's visibility (SYNC-04).
 */
export function SyncProvider({ session, openStorage, children }: SyncProviderProps) {
  const queryClient = useQueryClient();
  const [engine] = useState(() => new SyncEngine({ session, queryClient, openStorage }));

  useEffect(() => engine.start(), [engine]);

  return <SyncContext value={engine}>{children}</SyncContext>;
}
