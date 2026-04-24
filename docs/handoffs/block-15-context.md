# Block 15: Frontend Shell & Auth — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-15-frontend-shell.md`.

## What to build

`frontend/` — React + Vite + TypeScript SPA with: JWT auth flow (login, refresh, logout), role-based route guard, app shell layout (sidebar + header + content area), dark/light theme system via CSS custom properties, and OpenAPI TypeScript codegen pipeline.

### Files to create

| File | Purpose |
|------|---------|
| `frontend/package.json` | Dependencies: react@18, react-router-dom@6, axios, openapi-typescript (dev) |
| `frontend/tsconfig.json` | Strict mode, `@/*` path alias |
| `frontend/tsconfig.node.json` | Vite config TS support |
| `frontend/vite.config.ts` | React plugin, `/api` proxy → `http://localhost:8000`, `@` alias |
| `frontend/.eslintrc.cjs` | `@typescript-eslint/recommended`, `no-explicit-any: error` |
| `frontend/index.html` | Entry HTML with `<div id="root">` |
| `frontend/src/main.tsx` | ReactDOM.createRoot, StrictMode, mounts `<App />` |
| `frontend/src/App.tsx` | ThemeProvider + AuthProvider + RouterProvider |
| `frontend/src/router.tsx` | createBrowserRouter: login, protected routes, admin routes, 404 |
| `frontend/src/components/AppShell.tsx` | CSS grid: sidebar 240px + header 64px + content |
| `frontend/src/components/Sidebar.tsx` | Nav links with active state (useMatch) |
| `frontend/src/components/Header.tsx` | Page title, theme toggle, user info, logout |
| `frontend/src/components/ProtectedRoute.tsx` | Auth guard + role check |
| `frontend/src/contexts/AuthContext.tsx` | JWT state: login/logout/refresh, token in useRef |
| `frontend/src/contexts/ThemeContext.tsx` | Light/dark, localStorage, prefers-color-scheme |
| `frontend/src/api/client.ts` | Axios instance, 401 interceptor with refresh+retry |
| `frontend/src/api/auth.ts` | loginRequest, refreshRequest, logoutRequest |
| `frontend/src/pages/LoginPage.tsx` | Login form: username + password |
| `frontend/src/pages/OverviewPage.tsx` | Placeholder dashboard |
| `frontend/src/pages/NotFoundPage.tsx` | 404 page |
| `frontend/src/pages/ForbiddenPage.tsx` | 403 page |
| `frontend/src/styles/variables.css` | CSS custom properties for light/dark themes |
| `frontend/src/styles/global.css` | Reset, typography, focus rings |
| `frontend/src/styles/components.css` | AppShell, Sidebar, Header styles |
| `frontend/scripts/generate-types.ts` | openapi-typescript codegen script |
| `frontend/src/types/generated/api.ts` | Auto-generated types (committed for CI) |

### Tests to create

| File | Coverage |
|------|----------|
| `frontend/src/components/__tests__/ProtectedRoute.test.tsx` | Auth guard + role check |
| `frontend/src/contexts/__tests__/AuthContext.test.tsx` | Login, logout, refresh, token storage |
| `frontend/src/contexts/__tests__/ThemeContext.test.tsx` | Toggle, persist, system preference |
| `frontend/src/api/__tests__/client.test.ts` | 401 interceptor, refresh retry |

## CRITICAL: Spec vs. codebase deltas

The B15 spec has an Amendments section with 9 deltas. **These are the ground truth — follow the codebase.**

| # | Spec says | Codebase reality | Action |
|---|-----------|-------------------|--------|
| 1 | `LoginRequest: {email, password}` | `LoginRequest: {username, password}` (`src/api/schemas/auth.py:14`) | Frontend form: "Username" field, not "Email" |
| 2 | Response has `{access_token, user: UserInfo, expires_in}` | `TokenResponse: {access_token, refresh_token, token_type}` — no `user`, no `expires_in` | After login, fetch user via `GET /api/v1/auth/me` |
| 3 | Refresh token in httpOnly cookie | Both tokens in response body, refresh sent via `RefreshRequest.refresh_token` | Store refresh in memory (same useRef pattern as access token) |
| 4 | `POST /api/auth/logout` clears cookie | Requires access token header + `RefreshRequest` body with refresh_token | Send both tokens on logout |
| 5 | `User.email` | `User.username` (`src/models/user.py`) | Display `username` everywhere |
| 6 | `UserResponse: {id, email, role}` | `UserResponse: {id, username, role, is_active}` | Use `username` field |
| 7 | Roles: `Admin`, `Reviewer` (PascalCase) | `UserRole` values: `"admin"`, `"reviewer"` (lowercase) | Role checks use lowercase |
| 8 | `POST /api/auth/login` | `POST /api/v1/auth/login` | All paths use `/api/v1/` prefix |
| 9 | httpOnly cookie for CSRF protection | No cookie — both tokens in body | No CSRF needed; XSS mitigated by useRef |

## Backend auth API — actual contracts

### `POST /api/v1/auth/login`

Request:
```json
{ "username": "string", "password": "string" }
```

Response (200):
```json
{
  "access_token": "eyJ...",
  "refresh_token": "uuid-string",
  "token_type": "bearer"
}
```

No user info in response. After login, call `GET /api/v1/auth/me` to get user.

### `GET /api/v1/auth/me`

Request: `Authorization: Bearer <access_token>`

Response (200):
```json
{
  "id": "uuid",
  "username": "string",
  "role": "admin" | "reviewer",
  "is_active": true
}
```

### `POST /api/v1/auth/refresh`

Request:
```json
{ "refresh_token": "uuid-string" }
```

Response (200): same as login (new access + refresh tokens). Token rotation: old refresh deleted.

### `POST /api/v1/auth/logout`

Request: `Authorization: Bearer <access_token>` + body `{ "refresh_token": "uuid-string" }`

Response: 204 No Content.

## Auth flow — corrected implementation

```
1. User submits username + password
2. POST /api/v1/auth/login → receive access_token + refresh_token
3. Store BOTH tokens in useRef (NOT localStorage — XSS protection)
4. GET /api/v1/auth/me with Bearer token → get user info (id, username, role)
5. Set user state in AuthContext
6. Schedule refresh: since no expires_in in response, decode JWT exp claim
   OR use fixed interval (e.g., 14 minutes for 15-min TTL tokens)
7. On refresh: POST /api/v1/auth/refresh with refresh_token body → new token pair
8. On logout: POST /api/v1/auth/logout with Bearer header + refresh_token body
9. On 401: interceptor tries refresh, then retries original request
```

## Available API endpoints (all prefixed with /api/v1)

```
# Auth (B02/B13)
POST   /auth/login      — login (public)
POST   /auth/refresh    — refresh tokens (public)
POST   /auth/logout     — logout (authenticated, 204)
GET    /auth/me         — current user info (authenticated)

# Health (B13)
GET    /health          — system health check

# Emails (B13)
GET    /emails          — paginated list (Reviewer+)
GET    /emails/{id}     — email detail (Reviewer+)

# Routing Rules (B13)
GET    /routing-rules        — list (Admin)
POST   /routing-rules        — create (Admin, 201)
PUT    /routing-rules/reorder — reorder (Admin)
PUT    /routing-rules/{id}    — update (Admin)
DELETE /routing-rules/{id}    — delete (Admin, 204)
POST   /routing-rules/test   — dry-run (Admin)

# Drafts (B13)
GET    /drafts                — list (Reviewer+)
GET    /drafts/{id}           — detail (access-controlled)
PUT    /drafts/{id}/approve   — approve (access-controlled)
DELETE /drafts/{id}           — delete (Admin, 204)

# Categories (B14)
GET    /categories/actions        — list (Reviewer+)
POST   /categories/actions        — create (Admin, 201)
GET    /categories/actions/{id}   — get (Reviewer+)
PUT    /categories/actions/{id}   — update (Admin)
DELETE /categories/actions/{id}   — delete (Admin, 204/409)
PUT    /categories/actions/reorder — reorder (Admin)
(same for /categories/types)

# Classification (B14)
GET    /classification/examples       — list (Admin)
POST   /classification/examples       — create (Admin, 201)
PUT    /classification/examples/{id}  — update (Admin)
DELETE /classification/examples/{id}  — delete (Admin, 204)
GET    /classification/feedback       — paginated list (Admin)

# Integrations (B14)
GET    /integrations/email       — config (Admin)
POST   /integrations/email/test  — test connection (Admin)
GET    /integrations/channels    — config (Admin)
POST   /integrations/channels/test
GET    /integrations/crm         — config (Admin)
POST   /integrations/crm/test
GET    /integrations/llm         — config (Admin)
POST   /integrations/llm/test

# Analytics (B14)
GET    /analytics/volume                    — time series (Reviewer+)
GET    /analytics/classification-distribution — pie charts (Reviewer+)
GET    /analytics/accuracy                  — accuracy % (Reviewer+)
GET    /analytics/routing                   — channel stats (Reviewer+)
GET    /analytics/export                    — CSV (Admin)

# Logs (B14)
GET    /logs — paginated filtered (Admin)
```

## Sidebar navigation — route mapping

```
Dashboard (/)           — OverviewPage (Reviewer+)
Emails (/emails)        — placeholder (Reviewer+)
Review Queue (/review)  — placeholder (Reviewer+)
Routing (/routing)      — placeholder (Reviewer+)
Analytics (/analytics)  — placeholder (Reviewer+)
---
Categories (/classification)  — placeholder (Admin) [lazy]
Integrations (/integrations)  — placeholder (Admin) [lazy]
Logs (/logs)                  — placeholder (Admin) [lazy]
```

## Theme system — CSS custom properties

All from spec `variables.css`. Key invariant: **no hardcoded colors in components**. All colors via `var(--color-*)`. Theme toggle sets `data-theme` attribute on `<html>`.

Light theme base: slate palette (#f8fafc bg, #0f172a text, #4f46e5 primary).
Dark theme base: dark slate (#0f172a bg, #f1f5f9 text, #818cf8 primary).
Sidebar always dark-styled in light mode (#1e293b bg).

Typography: Inter font, modular scale 1.25 (16px base).

## JWT decode for refresh scheduling

Since `TokenResponse` has no `expires_in`, decode the JWT to extract `exp`:

```typescript
function getTokenExpSeconds(token: string): number {
  const payload = JSON.parse(atob(token.split(".")[1]));
  return payload.exp - Math.floor(Date.now() / 1000);
}
```

Then schedule refresh 30s before expiration: `setTimeout(refresh, (expSeconds - 30) * 1000)`.

JWT settings: `jwt_access_ttl_minutes: 15` (900s), `jwt_algorithm: HS256`.

## Quality gates

```bash
# 1. Install + codegen
cd frontend && npm install
npm run generate-types   # requires backend running on :8000

# 2. Type check
npm run typecheck        # tsc --noEmit

# 3. Lint
npm run lint             # ESLint with no-explicit-any: error

# 4. Build
npm run build            # Vite production build

# 5. Tests
npx vitest run           # all frontend tests

# 6. Architecture checks
grep -rn "localStorage.setItem\|sessionStorage.setItem" src/contexts/AuthContext.tsx src/api/
# Expected: EMPTY (tokens in memory only)

grep -rn "interface LoginRequest\|type LoginResponse" src/api/ src/contexts/ src/components/
# Expected: EMPTY (types from generated/api.ts only)

grep -rn "#[0-9a-fA-F]\{3,6\}" src/styles/components.css src/components/
# Expected: EMPTY (all colors via CSS variables)
```
