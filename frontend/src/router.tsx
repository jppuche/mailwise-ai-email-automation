// src/router.tsx
// Definicion de rutas con createBrowserRouter (React Router v7 / v6 compatible)
import React from "react";
import { createBrowserRouter } from "react-router-dom";
import AppShell from "@/components/AppShell";
import ProtectedRoute from "@/components/ProtectedRoute";
import LoginPage from "@/pages/LoginPage";
import OverviewPage from "@/pages/OverviewPage";
import NotFoundPage from "@/pages/NotFoundPage";

// Lazy loading para paginas — reduce bundle inicial y mejora TTI
const EmailBrowserPage = React.lazy(() => import("@/pages/EmailBrowserPage"));
const EmailDetailPage = React.lazy(() => import("@/pages/EmailDetailPage"));
const ReviewQueuePage = React.lazy(() => import("@/pages/ReviewQueuePage"));
const AnalyticsPage = React.lazy(() => import("@/pages/AnalyticsPage"));

// Lazy loading para paginas admin-only (reducir bundle inicial de Reviewer)
const ClassificationConfigPage = React.lazy(
  () => import("@/pages/ClassificationConfigPage"),
);
const RoutingRulesPage = React.lazy(
  () => import("@/pages/RoutingRulesPage"),
);
const IntegrationsPage = React.lazy(
  () => import("@/pages/IntegrationsPage"),
);
const LogsPage = React.lazy(
  () => import("@/pages/LogsPage"),
);

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    // Rutas protegidas — cualquier usuario autenticado (reviewer + admin)
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/",           element: <OverviewPage /> },
          {
            path: "/emails",
            element: (
              <React.Suspense fallback={<div className="page-placeholder">Loading...</div>}>
                <EmailBrowserPage />
              </React.Suspense>
            ),
          },
          {
            path: "/emails/:id",
            element: (
              <React.Suspense fallback={<div className="page-placeholder">Loading...</div>}>
                <EmailDetailPage />
              </React.Suspense>
            ),
          },
          {
            path: "/review",
            element: (
              <React.Suspense fallback={<div className="page-placeholder">Loading...</div>}>
                <ReviewQueuePage />
              </React.Suspense>
            ),
          },
          {
            // Analytics: reviewer + admin can view
            path: "/analytics",
            element: (
              <React.Suspense fallback={<div className="page-placeholder">Loading...</div>}>
                <AnalyticsPage />
              </React.Suspense>
            ),
          },
        ],
      },
    ],
  },
  {
    // Rutas admin-only
    element: <ProtectedRoute requiredRole="admin" />,
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
            // Routing rules: admin only — moved from ProtectedRoute to admin group
            path: "/routing",
            element: (
              <React.Suspense fallback={<div className="page-placeholder">Loading...</div>}>
                <RoutingRulesPage />
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
