// src/router.tsx
// Definicion de rutas con createBrowserRouter (React Router v7 / v6 compatible)
import React from "react";
import { createBrowserRouter } from "react-router-dom";
import AppShell from "@/components/AppShell";
import ProtectedRoute from "@/components/ProtectedRoute";
import LoginPage from "@/pages/LoginPage";
import OverviewPage from "@/pages/OverviewPage";
import NotFoundPage from "@/pages/NotFoundPage";

// Lazy loading para paginas admin-only (reducir bundle inicial de Reviewer)
const ClassificationConfigPage = React.lazy(
  () => import("@/pages/ClassificationConfigPage"),
);
const IntegrationsPage = React.lazy(
  () => import("@/pages/IntegrationsPage"),
);
const LogsPage = React.lazy(
  () => import("@/pages/LogsPage"),
);

// Placeholder para rutas no implementadas aun
function Placeholder({ label }: { label: string }) {
  return (
    <div className="page-placeholder">
      <h2 className="page-placeholder__title">{label}</h2>
      <span className="page-placeholder__badge">Coming soon</span>
    </div>
  );
}

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    // Rutas protegidas — cualquier usuario autenticado
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/",           element: <OverviewPage /> },
          { path: "/emails",     element: <Placeholder label="Email Browser" /> },
          { path: "/emails/:id", element: <Placeholder label="Email Detail" /> },
          { path: "/review",     element: <Placeholder label="Review Queue" /> },
          { path: "/routing",    element: <Placeholder label="Routing Rules" /> },
          { path: "/analytics",  element: <Placeholder label="Analytics" /> },
        ],
      },
    ],
  },
  {
    // Rutas admin-only
    element: <ProtectedRoute requiredRole="Admin" />,
    children: [
      {
        element: <AppShell />,
        children: [
          {
            path: "/classification",
            element: (
              <React.Suspense fallback={<div className="page-placeholder">Loading...</div>}>
                <ClassificationConfigPage />
              </React.Suspense>
            ),
          },
          {
            path: "/integrations",
            element: (
              <React.Suspense fallback={<div className="page-placeholder">Loading...</div>}>
                <IntegrationsPage />
              </React.Suspense>
            ),
          },
          {
            path: "/logs",
            element: (
              <React.Suspense fallback={<div className="page-placeholder">Loading...</div>}>
                <LogsPage />
              </React.Suspense>
            ),
          },
        ],
      },
    ],
  },
  {
    path: "*",
    element: <NotFoundPage />,
  },
]);
