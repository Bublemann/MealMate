import { Navigate, type RouteObject } from 'react-router';
import { IngredientsScreen } from '@/features/ingredients/IngredientsScreen';
import { ListsScreen } from '@/features/lists/ListsScreen';
import { MealsScreen } from '@/features/meals/MealsScreen';
import { MeScreen } from '@/features/me/MeScreen';
import { Layout } from './Layout';

/** The app opens on Lists (UI-02); unknown paths lead there too. */
export const routes: RouteObject[] = [
  {
    path: '/',
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/lists" replace /> },
      { path: 'lists', element: <ListsScreen /> },
      { path: 'meals', element: <MealsScreen /> },
      { path: 'ingredients', element: <IngredientsScreen /> },
      { path: 'me', element: <MeScreen /> },
      { path: '*', element: <Navigate to="/lists" replace /> },
    ],
  },
];
