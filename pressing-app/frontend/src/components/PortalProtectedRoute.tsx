import { Navigate, useLocation } from "react-router-dom";
import { usePortalAuth } from "@/contexts/PortalAuthContext";

export function PortalProtectedRoute({ children }: { children: React.ReactNode }) {
  const { customer, loading } = usePortalAuth();
  const location = useLocation();

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">Chargement...</div>;
  }
  if (!customer) {
    return <Navigate to="/portal/login" state={{ from: location.pathname }} replace />;
  }
  return <>{children}</>;
}
