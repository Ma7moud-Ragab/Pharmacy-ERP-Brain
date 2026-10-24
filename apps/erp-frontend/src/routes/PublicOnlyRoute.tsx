import type { ReactNode } from 'react';
import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { resolveRedirectPath } from './paths';

interface PublicOnlyRouteProps {
  children?: ReactNode;
}

export function PublicOnlyRoute({ children }: PublicOnlyRouteProps) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isInitializing = useAuthStore((state) => state.isInitializing);
  const location = useLocation();

  if (isInitializing) {
    return null;
  }

  if (isAuthenticated) {
    return <Navigate to={resolveRedirectPath(location.state)} replace />;
  }

  return children ? <>{children}</> : <Outlet />;
}
