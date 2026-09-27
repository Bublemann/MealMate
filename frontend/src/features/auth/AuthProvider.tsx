import { useQueryClient } from '@tanstack/react-query';
import { useEffect, type ReactNode } from 'react';
import { AuthContext } from './context';
import type { AuthSession } from './session';

interface AuthProviderProps {
  session: AuthSession;
  children: ReactNode;
}

/**
 * Provides the session and runs the start-up refresh. When a session ends (logout, expiry,
 * revocation) the TanStack Query cache is dropped, so no data of that user stays on screen or in
 * memory (SYNC-10); the session itself deletes the user-specific localStorage keys.
 */
export function AuthProvider({ session, children }: AuthProviderProps) {
  const queryClient = useQueryClient();

  useEffect(() => session.onEnd(() => queryClient.clear()), [session, queryClient]);
  useEffect(() => {
    void session.start();
  }, [session]);

  return <AuthContext value={session}>{children}</AuthContext>;
}
