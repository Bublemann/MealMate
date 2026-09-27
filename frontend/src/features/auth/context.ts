import { createContext, useContext, useSyncExternalStore } from 'react';
import type { AuthSession, AuthState } from './session';
import type { Me } from './storage';

export const AuthContext = createContext<AuthSession | null>(null);

export function useAuthSession(): AuthSession {
  const session = useContext(AuthContext);
  if (!session) throw new Error('useAuthSession needs an <AuthProvider>');
  return session;
}

/** The auth state; re-renders on sign-in, sign-out and profile changes. */
export function useAuth(): AuthState {
  const session = useAuthSession();
  return useSyncExternalStore(session.subscribe, session.getState);
}

/** The signed-in user; only for screens behind the route guard. */
export function useCurrentUser(): Me {
  const { user } = useAuth();
  if (!user) throw new Error('useCurrentUser is only available behind <RequireAuth>');
  return user;
}
