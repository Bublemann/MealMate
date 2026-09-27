import { Navigate, Outlet, useLocation } from 'react-router';
import { useAuth } from './context';
import { StartupScreen, UnreachableScreen } from './StatusScreens';

/** Route guard: everything except /login, /join and /reset needs a signed-in user. */
export function RequireAuth() {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'loading') return <StartupScreen />;
  if (status === 'unreachable') return <UnreachableScreen />;
  if (status === 'anonymous') {
    const from = `${location.pathname}${location.search}`;
    return <Navigate to="/login" replace state={{ from }} />;
  }
  return <Outlet />;
}

/** Route guard for the admin section; the backend checks the role on every request anyway. */
export function RequireAdmin() {
  const { user } = useAuth();
  if (user?.role !== 'admin') return <Navigate to="/me" replace />;
  return <Outlet />;
}
