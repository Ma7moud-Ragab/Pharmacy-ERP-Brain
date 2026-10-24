/**
 * Pharmacy ERP — Central Application Router
 *
 * Configured using React Router v7 createBrowserRouter.
 * Follows STRUCTURE.md: routes/router.tsx.
 */

import { createBrowserRouter, type RouteObject } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import { PublicOnlyRoute } from './PublicOnlyRoute';
import { PATHS } from './paths';
import { LoginPage } from '../features/auth/pages/LoginPage';
import { DashboardPage } from '../features/dashboard/pages/DashboardPage';

export const routes: RouteObject[] = [
  {
    path: PATHS.LOGIN,
    element: (
      <PublicOnlyRoute>
        <LoginPage />
      </PublicOnlyRoute>
    ),
  },
  {
    path: PATHS.HOME,
    element: (
      <ProtectedRoute>
        <DashboardPage />
      </ProtectedRoute>
    ),
  },
];

export const router = createBrowserRouter(routes);
