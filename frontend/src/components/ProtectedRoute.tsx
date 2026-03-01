// src/components/ProtectedRoute.tsx
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import ForbiddenPage from "@/pages/ForbiddenPage";

// RouteConfig: tipo local — config de ProtectedRoute sin equivalente en backend
// Roles son lowercase — match con UserRole del backend ("admin" | "reviewer")
interface ProtectedRouteProps {
  requiredRole?: "admin" | "reviewer";
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

  // admin puede acceder a rutas de admin y reviewer
  // reviewer solo puede acceder a rutas de reviewer
  const hasRole =
    user?.role === "admin" ||
    (requiredRole === "reviewer" && user?.role === "reviewer");

  if (!hasRole) {
    return <ForbiddenPage />;
  }

  return <Outlet />;
}
