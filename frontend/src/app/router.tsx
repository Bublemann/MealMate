import { Navigate, type RouteObject } from 'react-router';
import { JoinScreen } from '@/features/auth/JoinScreen';
import { LoginScreen } from '@/features/auth/LoginScreen';
import { RequireAdmin, RequireAuth } from '@/features/auth/RequireAuth';
import { ResetScreen } from '@/features/auth/ResetScreen';
import { IngredientDetailScreen } from '@/features/ingredients/IngredientDetailScreen';
import { IngredientsScreen } from '@/features/ingredients/IngredientsScreen';
import { ListScreen } from '@/features/lists/ListScreen';
import { ListsScreen } from '@/features/lists/ListsScreen';
import { MealDetailScreen } from '@/features/meals/MealDetailScreen';
import { MealFormScreen } from '@/features/meals/MealFormScreen';
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
          { path: 'lists/:id', element: <ListScreen /> },
          { path: 'meals', element: <MealsScreen /> },
          { path: 'meals/new', element: <MealFormScreen /> },
          { path: 'meals/:id', element: <MealDetailScreen /> },
          { path: 'meals/:id/edit', element: <MealFormScreen /> },
          { path: 'ingredients', element: <IngredientsScreen /> },
          { path: 'ingredients/:id', element: <IngredientDetailScreen /> },
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
                path: 'categories',
                lazy: async () => ({
                  Component: (await import('@/features/admin/AdminCategoriesScreen'))
                    .AdminCategoriesScreen,
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
