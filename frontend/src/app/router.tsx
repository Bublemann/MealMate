import { Navigate, type RouteObject } from 'react-router';
import { JoinScreen } from '@/features/auth/JoinScreen';
import { LoginScreen } from '@/features/auth/LoginScreen';
import { RequireAdmin, RequireAuth } from '@/features/auth/RequireAuth';
import { ResetScreen } from '@/features/auth/ResetScreen';
import { IngredientsScreen } from '@/features/ingredients/IngredientsScreen';
import { ListsScreen } from '@/features/lists/ListsScreen';
import { MealsScreen } from '@/features/meals/MealsScreen';
import { MeScreen } from '@/features/me/MeScreen';
import { Layout } from './Layout';

/**
 * /login, /join and /reset are public; everything else needs a signed-in user (RequireAuth).
 * The app opens on Lists (UI-02); unknown paths lead there too.
 */
export const routes: RouteObject[] = [
  { path: '/login', element: <LoginScreen /> },
  { path: '/join', element: <JoinScreen /> },
  { path: '/reset', element: <ResetScreen /> },
  {
    element: <RequireAuth />,
    children: [
      {
        path: '/',
        element: <Layout />,
        children: [
          { index: true, element: <Navigate to="/lists" replace /> },
          { path: 'lists', element: <ListsScreen /> },
          { path: 'meals', element: <MealsScreen /> },
          { path: 'ingredients', element: <IngredientsScreen /> },
          { path: 'me', element: <MeScreen /> },
          {
            path: 'me/admin',
            element: <RequireAdmin />,
            children: [
              { index: true, element: <Navigate to="/me/admin/users" replace /> },
              // Admin screens are a separate chunk: most people never open them.
              {
                path: 'users',
                lazy: async () => ({
                  Component: (await import('@/features/admin/AdminUsersScreen')).AdminUsersScreen,
                }),
              },
              {
                path: 'invites',
                lazy: async () => ({
                  Component: (await import('@/features/admin/AdminInvitesScreen'))
                    .AdminInvitesScreen,
                }),
              },
              {
                path: 'events',
                lazy: async () => ({
                  Component: (await import('@/features/admin/AdminEventsScreen')).AdminEventsScreen,
                }),
              },
            ],
          },
          { path: '*', element: <Navigate to="/lists" replace /> },
        ],
      },
    ],
  },
];
