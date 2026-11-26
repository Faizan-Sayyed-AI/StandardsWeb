import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/useAuth";
import { Skeleton } from "@/components/ui/skeleton";

interface ProtectedRouteProps {
  children?: React.ReactNode;
  requireAdmin?: boolean;
  requireManager?: boolean;
}

export function ProtectedRoute({ children, requireAdmin, requireManager }: ProtectedRouteProps) {
  const { isAuthenticated, isAdmin, isManager, isLoading } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="space-y-3 w-64">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Remember where the user was heading (e.g. a link from the weekly digest
    // email) so the login page can send them back there afterwards.
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}${location.hash}` }}
      />
    );
  }

  if (requireAdmin && !isAdmin) {
    return <Navigate to="/dashboard" replace />;
  }

  if (requireManager && !isManager) {
    return <Navigate to="/dashboard" replace />;
  }

  // Render children if provided (wrapper mode), otherwise render Outlet (layout route mode)
  return <>{children ?? <Outlet />}</>;
}
