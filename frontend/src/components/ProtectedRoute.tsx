// src/components/ProtectedRoute.tsx
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import ForbiddenPage from "@/pages/ForbiddenPage";

// RouteConfig: tipo local — config de ProtectedRoute sin equivalente en backend
interface ProtectedRouteProps {
  requiredRole?: "Admin" | "Reviewer";
}

export default function ProtectedRoute({ requiredRole }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, user } = useAuth();

  // Mientras restauramos sesion: no redirigir todavia
  if (isLoading) {
    return <div className="auth-loading" aria-label="Loading..." />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Sin rol requerido: cualquier usuario autenticado puede acceder
  if (!requiredRole) {
    return <Outlet />;
  }

  // Admin puede acceder a rutas de Admin y Reviewer
  // Reviewer solo puede acceder a rutas de Reviewer
  const hasRole =
    user?.role === "Admin" ||
    (requiredRole === "Reviewer" && user?.role === "Reviewer");

  if (!hasRole) {
    return <ForbiddenPage />;
  }

  return <Outlet />;
}
