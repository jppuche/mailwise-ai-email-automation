# Bloque 15: Frontend Shell & Auth

## Objetivo

Implementar el esqueleto de la SPA React con routing del lado del cliente, flujo JWT completo
(login, refresh automatico, logout, guard por rol), layout shell (sidebar + header + area de
contenido), sistema de temas con CSS custom properties (claro/oscuro), y el pipeline de
codegen de tipos TypeScript desde la especificacion OpenAPI de FastAPI.

## Dependencias

- Bloque 13 (API Core): endpoints de auth (`POST /api/auth/login`,
  `POST /api/auth/refresh`, `POST /api/auth/logout`) operativos — el shell necesita
  llamadas reales para validar el flujo JWT end-to-end
- Bloque 1 (Models): schema de `User` y roles (`Admin`, `Reviewer`) — los roles son
  JWT claims que el frontend lee para guardar rutas

## Archivos a crear/modificar

### Backend (backend-worker)

- N/A — este bloque es exclusivamente frontend. El backend expone la spec OpenAPI en
  `GET /openapi.json` (FastAPI default). El script de codegen la consume en tiempo de build.

### Frontend (frontend-worker)

**Configuracion del proyecto:**

- `frontend/package.json` — Dependencias: `react@18`, `react-dom@18`,
  `react-router-dom@6`, `axios`, `openapi-typescript` (devDep para codegen).
  Scripts: `dev`, `build`, `lint`, `typecheck`, `generate-types`.
- `frontend/tsconfig.json` — TypeScript strict mode: `"strict": true`,
  `"noImplicitAny": true`, `"strictNullChecks": true`.
  `paths`: `"@/*": ["./src/*"]` para imports absolutos.
- `frontend/tsconfig.node.json` — Config para Vite config file.
- `frontend/vite.config.ts` — Plugin React, proxy `/api` → backend (`http://localhost:8000`),
  alias `@` → `src/`.
- `frontend/.eslintrc.cjs` — ESLint con `@typescript-eslint/recommended`,
  regla `no-explicit-any: error` (alineado con tighten-types D4).

**Entry points:**

- `frontend/src/main.tsx` — `ReactDOM.createRoot`, `<StrictMode>`, monta `<App />`
- `frontend/src/App.tsx` — Composicion de providers (`ThemeProvider`, `AuthProvider`) +
  `<RouterProvider>` con el objeto de rutas de `src/router.tsx`
- `frontend/src/router.tsx` — Definicion de rutas con `createBrowserRouter`. Rutas
  protegidas envueltas en `<ProtectedRoute>`. Rutas anidadas bajo `<AppShell>`.

**Componentes de layout:**

- `frontend/src/components/AppShell.tsx` — Layout principal: grid CSS con sidebar fijo
  de 240px + header de 64px + area de contenido. Responsive: sidebar colapsa en movil.
- `frontend/src/components/Sidebar.tsx` — Links de navegacion con estado activo via
  `useMatch`. Iconos + labels. Seccion de usuario en el pie del sidebar.
- `frontend/src/components/Header.tsx` — Titulo de pagina actual, toggle de tema,
  nombre de usuario, boton logout. Sin logica de negocio.
- `frontend/src/components/ProtectedRoute.tsx` — Guard de auth: si no autenticado,
  redirect a `/login`. Si autenticado pero sin el rol requerido, muestra pagina 403.
  Acepta prop `requiredRole?: "Admin" | "Reviewer"`.

**Contextos:**

- `frontend/src/contexts/AuthContext.tsx` — Estado JWT: `user`, `isAuthenticated`,
  `isLoading`, `login()`, `logout()`. Access token en memoria (no localStorage).
  Refresh token en httpOnly cookie (gestionado por el servidor). Auto-refresh antes
  de expiracion del access token via `setTimeout`.
- `frontend/src/contexts/ThemeContext.tsx` — Estado de tema: `theme` ("light" | "dark"),
  `toggleTheme()`. Persistencia en `localStorage`. Deteccion de preferencia del sistema
  via `window.matchMedia("(prefers-color-scheme: dark)")`.

**Estilos:**

- `frontend/src/styles/variables.css` — CSS custom properties para los dos temas.
  Ver seccion "Sistema de temas" abajo.
- `frontend/src/styles/global.css` — Estilos base: reset, tipografia, scroll,
  focus rings. Todos usando variables de `variables.css`.
- `frontend/src/styles/components.css` — Estilos de `AppShell`, `Sidebar`, `Header`
  usando variables.

**API client:**

- `frontend/src/api/client.ts` — Instancia de `axios` con `baseURL=/api`,
  interceptor de request (inyecta Bearer token), interceptor de response (detecta 401
  y dispara refresh antes de reintentar, o redirige a `/login` si refresh falla).
- `frontend/src/api/auth.ts` — Funciones tipadas: `loginRequest()`, `refreshRequest()`,
  `logoutRequest()`. Usan tipos generados (`components["schemas"]["LoginRequest"]`, etc.).

**Paginas:**

- `frontend/src/pages/LoginPage.tsx` — Formulario de login: email + password.
  Maneja estado de loading, error message. Redirige a `/` tras exito.
- `frontend/src/pages/OverviewPage.tsx` — Placeholder "Dashboard Overview" — contenido
  real en bloques futuros.
- `frontend/src/pages/NotFoundPage.tsx` — Pagina 404.
- `frontend/src/pages/ForbiddenPage.tsx` — Pagina 403 para acceso sin rol.

**Codegen de tipos:**

- `frontend/scripts/generate-types.ts` — Script Node/tsx que llama a `openapi-typescript`
  apuntando a `http://localhost:8000/openapi.json` (o al archivo estatico
  `openapi.json` en CI). Output: `src/types/generated/api.ts`.
- `frontend/src/types/generated/api.ts` — Auto-generado. Contiene `paths` y `components`
  tipados desde el OpenAPI spec de FastAPI. Nunca editar manualmente.
- `frontend/src/types/generated/.gitkeep` — Para mantener el directorio en git
  (el archivo generado SI se commitea para CI sin backend corriendo).

### Tests (Inquisidor)

- `frontend/src/components/__tests__/ProtectedRoute.test.tsx` — Casos: usuario no
  autenticado redirige a `/login`, usuario Reviewer sin rol Admin ve ForbiddenPage,
  usuario Admin con rol correcto renderiza children.
- `frontend/src/contexts/__tests__/AuthContext.test.tsx` — Login exitoso almacena user
  en context, logout limpia state, 401 en cualquier request activa refresh, refresh
  fallido redirige a `/login`, access token no aparece en `localStorage` (solo en memoria).
- `frontend/src/contexts/__tests__/ThemeContext.test.tsx` — Toggle cambia theme,
  preferencia persiste en `localStorage`, system preference detectada en primer render.
- `frontend/src/api/__tests__/client.test.ts` — Interceptor de 401: primer retry con
  refresh exitoso, segundo 401 tras refresh fallido redirige a `/login`. Bearer header
  presente en requests autenticados.

## Skills aplicables

- **tighten-types** (CRITICO — D4): Directiva maxima: tipos TypeScript autogenerados desde
  OpenAPI. Cero duplicacion manual de tipos de API. El script `generate-types.ts` es la
  unica fuente de tipos de API. El `api/client.ts` y todas las funciones de API usan
  `components["schemas"]["X"]` de `src/types/generated/api.ts`. Ningun `any` explicito
  (ESLint `no-explicit-any: error`). Ver "Type Decisions" abajo.
- **try-except** (NOTA para frontend): TypeScript no tiene el mismo patron que Python, pero
  el principio se traduce: llamadas a la API (estado externo) van dentro de `try/catch` en
  los hooks/servicios. Logica local de transformacion de datos (formatear fechas, calcular
  porcentajes) usa condicionales, no `try/catch`. El interceptor de 401 usa el patron
  "catch and retry" — equivalente a `except LLMRateLimitError: raise self.retry(...)`.

## Type Decisions

| Tipo | Kind | Justificacion |
|------|------|---------------|
| `components["schemas"]["LoginRequest"]` | Generado (openapi-typescript) | Request body de POST /api/auth/login — fuente: OpenAPI spec. Nunca duplicar a mano. |
| `components["schemas"]["LoginResponse"]` | Generado (openapi-typescript) | Response de login con `access_token`, `token_type`, `role`. |
| `components["schemas"]["UserInfo"]` | Generado (openapi-typescript) | Datos del usuario autenticado leidos del JWT o del endpoint `/api/auth/me`. |
| `AuthUser` | TypeScript interface (local) | Estado interno de `AuthContext`: `{ id: string; email: string; role: "Admin" \| "Reviewer" }`. Derivado de `UserInfo` del schema generado — NO duplica la definicion completa. |
| `Theme` | TypeScript type alias (local) | `"light" \| "dark"` — estado de `ThemeContext`. Tipo trivial, justificado como local. |
| `RouteConfig` | TypeScript interface (local) | Config de `ProtectedRoute`: `{ requiredRole?: "Admin" \| "Reviewer" }`. Local porque no tiene equivalente en el backend. |
| `ApiError` | TypeScript class (local) | Error estructurado del API client: `{ status: number; message: string; detail?: unknown }`. Encapsula errores de axios para que los componentes no importen axios. |
| `paths["/api/auth/login"]["post"]` | Generado (openapi-typescript) | Tipo de la operacion completa — usado en `auth.ts` para tipar el response exacto del endpoint. |

**Regla de oro:** si el tipo existe en el schema OpenAPI generado, se usa desde alli.
Si el tipo es exclusivo de la capa de presentacion (estado UI, config de componentes,
utilidades locales), se define localmente. Cero tipos de API duplicados a mano.

## Sistema de temas (CSS custom properties)

### variables.css

```css
/* ========================================
   Paleta claro — activada por :root o [data-theme="light"]
   ======================================== */
:root,
[data-theme="light"] {
  --color-bg:           #f8fafc;
  --color-bg-surface:   #ffffff;
  --color-bg-elevated:  #f1f5f9;
  --color-border:       #e2e8f0;

  --color-text:         #0f172a;
  --color-text-muted:   #64748b;
  --color-text-inverse: #ffffff;

  --color-primary:      #4f46e5;
  --color-primary-hover:#4338ca;
  --color-primary-light:#eef2ff;

  --color-success:      #16a34a;
  --color-warning:      #d97706;
  --color-error:        #dc2626;
  --color-info:         #0891b2;

  --color-sidebar-bg:   #1e293b;
  --color-sidebar-text: #cbd5e1;
  --color-sidebar-active:#4f46e5;
  --color-sidebar-hover: #334155;
}

/* ========================================
   Paleta oscura — activada por [data-theme="dark"]
   ======================================== */
[data-theme="dark"] {
  --color-bg:           #0f172a;
  --color-bg-surface:   #1e293b;
  --color-bg-elevated:  #334155;
  --color-border:       #334155;

  --color-text:         #f1f5f9;
  --color-text-muted:   #94a3b8;
  --color-text-inverse: #0f172a;

  --color-primary:      #818cf8;
  --color-primary-hover:#a5b4fc;
  --color-primary-light:#1e1b4b;

  --color-success:      #4ade80;
  --color-warning:      #fbbf24;
  --color-error:        #f87171;
  --color-info:         #22d3ee;

  --color-sidebar-bg:   #0f172a;
  --color-sidebar-text: #94a3b8;
  --color-sidebar-active:#818cf8;
  --color-sidebar-hover: #1e293b;
}

/* ========================================
   Escala tipografica modular (base 16px, ratio 1.25)
   ======================================== */
:root {
  --font-size-xs:   0.64rem;   /*  ~10px */
  --font-size-sm:   0.8rem;    /*  ~13px */
  --font-size-base: 1rem;      /*   16px */
  --font-size-md:   1.25rem;   /*   20px */
  --font-size-lg:   1.563rem;  /*   25px */
  --font-size-xl:   1.953rem;  /*   31px */

  --font-family-sans: "Inter", system-ui, -apple-system, sans-serif;
  --font-family-mono: "JetBrains Mono", "Fira Code", monospace;

  --line-height-tight:  1.25;
  --line-height-normal: 1.5;
  --line-height-loose:  1.75;

  --radius-sm:  4px;
  --radius-md:  8px;
  --radius-lg:  12px;

  --shadow-sm:  0 1px 2px rgb(0 0 0 / 0.05);
  --shadow-md:  0 4px 6px rgb(0 0 0 / 0.07);
  --shadow-lg:  0 10px 15px rgb(0 0 0 / 0.1);

  --transition-fast:   150ms ease;
  --transition-normal: 250ms ease;

  --sidebar-width:     240px;
  --header-height:     64px;
}
```

**Invariante del sistema de temas:** Ningun componente usa valores de color hardcodeados.
Todos los colores vienen de variables CSS. Un cambio de tema actualiza el atributo
`data-theme` en `<html>` — los colores cambian sin re-render de React.

## AuthContext — implementacion detallada

```typescript
// src/contexts/AuthContext.tsx
import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { loginRequest, refreshRequest, logoutRequest } from "@/api/auth";
import type { components } from "@/types/generated/api";

type UserInfo = components["schemas"]["UserInfo"];

interface AuthUser {
  id: string;
  email: string;
  role: "Admin" | "Reviewer";
}

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  getAccessToken: () => string | null;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  // Access token en memoria — NUNCA en localStorage (XSS protection)
  const accessTokenRef = useRef<string | null>(null);
  const refreshTimerRef = useRef<number | null>(null);

  const scheduleRefresh = (expiresInSeconds: number) => {
    // Refrescar 30s antes de la expiracion
    const delay = Math.max(0, (expiresInSeconds - 30) * 1000);
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current);
    }
    refreshTimerRef.current = window.setTimeout(async () => {
      try {
        const response = await refreshRequest();
        accessTokenRef.current = response.access_token;
        scheduleRefresh(response.expires_in);
      } catch {
        // Refresh fallido: limpiar estado y redirigir a login
        setUser(null);
        accessTokenRef.current = null;
      }
    }, delay);
  };

  const login = async (email: string, password: string): Promise<void> => {
    // Estado externo — try/catch en el caller (LoginPage.tsx)
    const response = await loginRequest({ email, password });
    accessTokenRef.current = response.access_token;
    setUser({
      id: response.user.id,
      email: response.user.email,
      role: response.user.role as "Admin" | "Reviewer",
    });
    scheduleRefresh(response.expires_in);
  };

  const logout = async (): Promise<void> => {
    try {
      await logoutRequest();
    } finally {
      // Limpiar estado local independientemente del resultado del servidor
      accessTokenRef.current = null;
      setUser(null);
      if (refreshTimerRef.current) {
        clearTimeout(refreshTimerRef.current);
      }
    }
  };

  // Intentar refresh silencioso al cargar la app (restaurar sesion si existe cookie)
  useEffect(() => {
    const tryRestore = async () => {
      try {
        const response = await refreshRequest();
        accessTokenRef.current = response.access_token;
        setUser({
          id: response.user.id,
          email: response.user.email,
          role: response.user.role as "Admin" | "Reviewer",
        });
        scheduleRefresh(response.expires_in);
      } catch {
        // Sin sesion previa — normal, no es un error
      } finally {
        setIsLoading(false);
      }
    };
    tryRestore();
    return () => {
      if (refreshTimerRef.current) {
        clearTimeout(refreshTimerRef.current);
      }
    };
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: user !== null,
        isLoading,
        login,
        logout,
        getAccessToken: () => accessTokenRef.current,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
```

## ProtectedRoute — implementacion

```typescript
// src/components/ProtectedRoute.tsx
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import ForbiddenPage from "@/pages/ForbiddenPage";

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
```

## API Client — interceptor de 401

```typescript
// src/api/client.ts
import axios, { type AxiosInstance, type AxiosError } from "axios";

// Instancia singleton — compartida por todos los modulos de api/
const apiClient: AxiosInstance = axios.create({
  baseURL: "/api",
  withCredentials: true,   // necesario para que el browser envie la cookie httpOnly de refresh
  headers: {
    "Content-Type": "application/json",
  },
});

// Referencia a getAccessToken — se setea desde AuthProvider para evitar circular dep
let _getAccessToken: (() => string | null) | null = null;
let _redirectToLogin: (() => void) | null = null;
let _isRefreshing = false;
let _refreshQueue: Array<(token: string | null) => void> = [];

export function configureClient(
  getToken: () => string | null,
  redirectFn: () => void,
): void {
  _getAccessToken = getToken;
  _redirectToLogin = redirectFn;
}

// Request interceptor: inyectar Bearer token
apiClient.interceptors.request.use((config) => {
  const token = _getAccessToken?.();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: manejar 401 con refresh y retry
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config;
    if (error.response?.status !== 401 || !originalRequest) {
      return Promise.reject(error);
    }

    if (_isRefreshing) {
      // Cola: esperar al refresh en curso
      return new Promise((resolve, reject) => {
        _refreshQueue.push((token) => {
          if (token && originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${token}`;
            resolve(apiClient(originalRequest));
          } else {
            reject(error);
          }
        });
      });
    }

    _isRefreshing = true;
    try {
      const { data } = await apiClient.post<{ access_token: string }>("/auth/refresh");
      const newToken = data.access_token;
      _refreshQueue.forEach((cb) => cb(newToken));
      _refreshQueue = [];
      if (originalRequest.headers) {
        originalRequest.headers.Authorization = `Bearer ${newToken}`;
      }
      return apiClient(originalRequest);
    } catch {
      _refreshQueue.forEach((cb) => cb(null));
      _refreshQueue = [];
      _redirectToLogin?.();
      return Promise.reject(error);
    } finally {
      _isRefreshing = false;
    }
  },
);

export default apiClient;
```

## Router — definicion de rutas

```typescript
// src/router.tsx
import { createBrowserRouter } from "react-router-dom";
import AppShell from "@/components/AppShell";
import ProtectedRoute from "@/components/ProtectedRoute";
import LoginPage from "@/pages/LoginPage";
import OverviewPage from "@/pages/OverviewPage";
import NotFoundPage from "@/pages/NotFoundPage";
import ForbiddenPage from "@/pages/ForbiddenPage";

// Lazy loading para paginas de admin-only (reducir bundle inicial de Reviewer)
const ClassificationConfigPage = React.lazy(() => import("@/pages/ClassificationConfigPage"));
const IntegrationsPage = React.lazy(() => import("@/pages/IntegrationsPage"));
const LogsPage = React.lazy(() => import("@/pages/LogsPage"));

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    // Rutas protegidas (cualquier usuario autenticado)
    element: <ProtectedRoute />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: "/",         element: <OverviewPage /> },
          { path: "/emails",   element: <Placeholder label="Email Browser" /> },
          { path: "/emails/:id", element: <Placeholder label="Email Detail" /> },
          { path: "/review",   element: <Placeholder label="Review Queue" /> },
          { path: "/routing",  element: <Placeholder label="Routing Rules" /> },
          { path: "/analytics", element: <Placeholder label="Analytics" /> },
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
              <React.Suspense fallback={<div>Loading...</div>}>
                <ClassificationConfigPage />
              </React.Suspense>
            ),
          },
          {
            path: "/integrations",
            element: (
              <React.Suspense fallback={<div>Loading...</div>}>
                <IntegrationsPage />
              </React.Suspense>
            ),
          },
          {
            path: "/logs",
            element: (
              <React.Suspense fallback={<div>Loading...</div>}>
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
```

## Script de codegen de tipos

```typescript
// frontend/scripts/generate-types.ts
// Ejecutar con: npx tsx scripts/generate-types.ts
// O via: npm run generate-types

import openapiTS, { astToString } from "openapi-typescript";
import * as fs from "node:fs/promises";
import * as path from "node:path";
import * as url from "node:url";

const OPENAPI_URL = process.env.OPENAPI_URL ?? "http://localhost:8000/openapi.json";
const OUTPUT_PATH = path.resolve(
  path.dirname(url.fileURLToPath(import.meta.url)),
  "../src/types/generated/api.ts",
);

async function main(): Promise<void> {
  console.log(`Fetching OpenAPI spec from ${OPENAPI_URL}...`);

  const ast = await openapiTS(new URL(OPENAPI_URL));
  const content = astToString(ast);

  await fs.mkdir(path.dirname(OUTPUT_PATH), { recursive: true });
  await fs.writeFile(
    OUTPUT_PATH,
    `// AUTO-GENERATED — DO NOT EDIT MANUALLY\n// Run: npm run generate-types\n// Source: ${OPENAPI_URL}\n\n${content}`,
  );

  console.log(`Types generated: ${OUTPUT_PATH}`);
}

main().catch((err) => {
  console.error("Type generation failed:", err);
  process.exit(1);
});
```

**Nota de CI:** En entornos CI sin backend corriendo, el script acepta un archivo local:

```bash
OPENAPI_URL=file://./openapi.json npm run generate-types
```

El archivo `openapi.json` se genera en el pipeline de CI corriendo el backend y haciendo
`GET /openapi.json`. Se commitea a `frontend/openapi.json` para que CI no necesite
el backend vivo.

## Estructura de archivos esperada

```
frontend/
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts
├── .eslintrc.cjs
├── openapi.json             # snapshot de la spec para CI
├── scripts/
│   └── generate-types.ts   # script de codegen
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── router.tsx
    ├── components/
    │   ├── AppShell.tsx
    │   ├── Sidebar.tsx
    │   ├── Header.tsx
    │   ├── ProtectedRoute.tsx
    │   └── __tests__/
    │       └── ProtectedRoute.test.tsx
    ├── contexts/
    │   ├── AuthContext.tsx
    │   ├── ThemeContext.tsx
    │   └── __tests__/
    │       ├── AuthContext.test.tsx
    │       └── ThemeContext.test.tsx
    ├── pages/
    │   ├── LoginPage.tsx
    │   ├── OverviewPage.tsx
    │   ├── NotFoundPage.tsx
    │   ├── ForbiddenPage.tsx
    │   ├── ClassificationConfigPage.tsx  # placeholder — contenido en B17
    │   ├── IntegrationsPage.tsx           # placeholder — contenido en B16
    │   └── LogsPage.tsx                  # placeholder — contenido en B17
    ├── api/
    │   ├── client.ts
    │   ├── auth.ts
    │   └── __tests__/
    │       └── client.test.ts
    ├── styles/
    │   ├── variables.css
    │   ├── global.css
    │   └── components.css
    └── types/
        └── generated/
            ├── .gitkeep
            └── api.ts      # AUTO-GENERADO
```

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Criterios de exito (deterministicos)

- [ ] `npm run dev` arranca el servidor Vite sin errores en `localhost:5173`
- [ ] `npm run build` produce un bundle en `frontend/dist/` sin errores de TypeScript ni de Vite
- [ ] `npm run typecheck` (`tsc --noEmit`) retorna 0 errores
- [ ] `npm run lint` (ESLint) retorna 0 errores; la regla `no-explicit-any: error` esta activa
- [ ] `npm run generate-types` con el backend corriendo genera `src/types/generated/api.ts`
  sin errores y el archivo contiene al menos los schemas `LoginRequest`, `LoginResponse`,
  `UserInfo`
- [ ] Ningun archivo en `src/api/` o `src/contexts/` contiene tipos de API definidos
  manualmente que dupliquen los del schema generado — verificable por grep
- [ ] Shell renderiza: sidebar visible con los 9 links de navegacion, header visible
  con toggle de tema y nombre de usuario
- [ ] Navegacion entre `/`, `/emails`, `/review`, `/analytics` funciona sin recargar la pagina
- [ ] `/classification`, `/integrations`, `/logs` muestran ForbiddenPage para usuario Reviewer
- [ ] `/login` es accesible sin autenticacion; todas las demas rutas redirigen a `/login` si no autenticado
- [ ] Flujo de login: formulario POST a `/api/auth/login`, respuesta almacena token en memoria
  (verificable via DevTools: no aparece en localStorage), usuario redirige a `/`
- [ ] Flujo de logout: POST a `/api/auth/logout`, estado limpiado, redirige a `/login`
- [ ] 401 en cualquier request autenticado: interceptor intenta refresh, si exitoso reintenta
  la request original; si fallido redirige a `/login`
- [ ] Access token NO aparece en `localStorage` ni en `sessionStorage` (verificable via
  DevTools Application panel)
- [ ] Toggle de tema cambia `data-theme` en `<html>` — colores cambian sin parpadeo
- [ ] Preferencia de tema persiste tras reload de pagina (localStorage)
- [ ] Primera visita sin preferencia guardada: respeta `prefers-color-scheme` del sistema
- [ ] CSS custom properties: `grep -rn "#[0-9a-fA-F]\{3,6\}" src/styles/components.css`
  retorna 0 resultados — todos los colores usan variables
- [ ] `AppShell` layout: sidebar 240px fijo, header 64px fijo, contenido ocupa el resto
  sin scroll horizontal
- [ ] `ProtectedRoute` con `requiredRole="Admin"` + usuario Reviewer renderiza `ForbiddenPage`
  (no redirect, no crash)
- [ ] Auto-refresh: el timer se cancela en cleanup de `useEffect` — sin memory leaks
  verificable via test de unmount
- [ ] `vite build` — bundle size del chunk inicial < 200KB gzip (sin lazy-loaded pages)

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**

1. `npm run generate-types` — prerequisito: tipos generados antes de typecheck
2. `npm run typecheck` — si falla, corregir tipos antes de cualquier otro gate
3. `npm run lint` — si falla, corregir ESLint antes de tests
4. `npm run build` — verifica que el bundle compilado es valido
5. `npx vitest run src/contexts/__tests__/AuthContext.test.tsx` — auth es el nucleo del shell
6. `npx vitest run src/contexts/__tests__/ThemeContext.test.tsx`
7. `npx vitest run src/components/__tests__/ProtectedRoute.test.tsx` — depende de AuthContext
8. `npx vitest run src/api/__tests__/client.test.ts` — interceptor de 401
9. `npx vitest run` — suite completa

**Verificaciones criticas (no automatizables):**

```bash
# Verificar que no hay tipos de API duplicados a mano
grep -rn "interface LoginRequest\|type LoginResponse\|interface UserInfo" src/api/ src/contexts/ src/components/
# El resultado debe estar vacio — estos tipos vienen SOLO de src/types/generated/api.ts

# Verificar que no hay colores hardcodeados en componentes
grep -rn "#[0-9a-fA-F]\{3,6\}" src/styles/components.css src/components/
# Resultado debe estar vacio (solo variables CSS)

# Verificar que el access token no se persiste en storage
grep -rn "localStorage.setItem\|sessionStorage.setItem" src/contexts/AuthContext.tsx src/api/
# Resultado debe estar vacio
```

**Consultas requeridas antes de implementar:**

- Consultar Inquisidor para confirmar el patron correcto de manejo del refresh token:
  httpOnly cookie (backend la setea via `Set-Cookie`) vs `localStorage` — confirmar que
  `withCredentials: true` en axios es suficiente para que el browser envie la cookie en
  requests a `/api/auth/refresh`, dado que el SPA corre en `localhost:5173` y el backend
  en `localhost:8000` (cross-origin en dev, mismo origen en prod via Nginx).
- Consultar Sentinel para revisar la estrategia de almacenamiento del access token en
  `useRef` dentro de `AuthContext`: confirmar que este patron efectivamente previene XSS
  vs localStorage, y que la referencia no es accesible desde la consola del browser.
