import { Navigate, type RouteObject } from 'react-router';
import { JoinScreen } from '@/features/auth/JoinScreen';
import { LoginScreen } from '@/features/auth/LoginScreen';
import { RequireAdmin, RequireAuth } from '@/features/auth/RequireAuth';
import { ResetScreen } from '@/features/auth/ResetScreen';
import { CoupleScreen } from '@/features/couple/CoupleScreen';
import { IngredientDetailScreen } from '@/features/ingredients/IngredientDetailScreen';
import { IngredientsScreen } from '@/features/ingredients/IngredientsScreen';
import { ListScreen } from '@/features/lists/ListScreen';
import { ListsScreen } from '@/features/lists/ListsScreen';
import { MealDetailScreen } from '@/features/meals/MealDetailScreen';
import { MealFormScreen } from '@/features/meals/MealFormScreen';
import { MealsScreen } from '@/features/meals/MealsScreen';
import { AboutScreen } from '@/features/me/AboutScreen';
import { PrivacyScreen } from '@/features/me/PrivacyScreen';
import { ProfileScreen } from '@/features/me/ProfileScreen';
import { SecurityScreen } from '@/features/me/SecurityScreen';
import { SettingsScreen } from '@/features/me/SettingsScreen';
import { Layout } from './Layout';

/**
 * /login, /join, /reset and /diag are public; everything else needs a signed-in user (RequireAuth).
 * The app opens on Lists (UI-02); unknown paths lead there too.
 */
export const routes: RouteObject[] = [
  { path: '/login', element: <LoginScreen /> },
  { path: '/join', element: <JoinScreen /> },
  { path: '/reset', element: <ResetScreen /> },
  // The temporary diagnostics screen of the M1 platform spike (removed in M9); a separate chunk
  // with the scanner. Public, so Safari can open it before any login. A Home Screen app has no
  // address bar and reaches it only through Einstellungen → Über MealMate → Diagnose, i.e.
  // signed in; signing in doesn't touch the mm_diag cookie, so the cookie test (O-10) still
  // works after it.
  {
    path: '/diag',
    lazy: async () => ({
      Component: (await import('@/features/diagnostics/DiagnosticsScreen')).DiagnosticsScreen,
    }),
  },
  {
    element: <RequireAuth />,
    children: [
      {
        path: '/',
        element: <Layout />,
        children: [
          { index: true, element: <Navigate to="/lists" replace /> },
          { path: 'lists', element: <ListsScreen /> },
          // The former history page; done lists are in the feed now (UI-02).
          { path: 'lists/history', element: <Navigate to="/lists" replace /> },
          { path: 'lists/:id', element: <ListScreen /> },
          { path: 'meals', element: <MealsScreen /> },
          { path: 'meals/new', element: <MealFormScreen /> },
          { path: 'meals/:id', element: <MealDetailScreen /> },
          { path: 'meals/:id/edit', element: <MealFormScreen /> },
          { path: 'ingredients', element: <IngredientsScreen /> },
          { path: 'ingredients/:id', element: <IngredientDetailScreen /> },
          // The former scan page; scanning is inside "New ingredient" now (BAR-01, D-37).
          { path: 'scan', element: <Navigate to="/ingredients" replace /> },
          // The Settings tab and the pages its rows open (D-45); see features/me/settingsRows.ts.
          { path: 'me', element: <SettingsScreen /> },
          { path: 'me/profile', element: <ProfileScreen /> },
          { path: 'me/privacy', element: <PrivacyScreen /> },
          { path: 'me/couple', element: <CoupleScreen /> },
          { path: 'me/security', element: <SecurityScreen /> },
          { path: 'me/about', element: <AboutScreen /> },
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
              {
                path: 'system',
                lazy: async () => ({
                  Component: (await import('@/features/admin/AdminSystemScreen')).AdminSystemScreen,
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
