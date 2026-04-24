# Block 17: FE Remaining — Routing Rules, Integrations, Analytics, Overview, Logs — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-17-frontend-remaining.md`.

## What to build

Replace the remaining Placeholder routes from B15 (`/`, `/routing`, `/analytics`) and stub pages (`IntegrationsPage`, `LogsPage`, `OverviewPage`) with real implementations. Create new hooks for routing rules, analytics, integrations, logs, and health. Install `recharts` for charts. Zero `any`, all types from `types/generated/api.ts`.

## What B15+B16 delivered (your starting point)

**Infrastructure (DO NOT recreate):**
- SPA shell: AppShell (CSS grid: sidebar 240px + header 64px + content)
- Auth: `AuthContext.tsx` with JWT tokens in `useRef` (login, logout, refresh, `configureClient`)
- Theme: `ThemeContext.tsx` with CSS custom properties via `data-theme` attribute
- API client: `api/client.ts` — axios with `/api/v1` baseURL, Bearer interceptor, 401 refresh+retry
- Router: `router.tsx` — protected routes with role guards, lazy-loaded admin pages
- TanStack Query: `QueryClient` with `staleTime: 30_000`, `retry: 1` wrapping `RouterProvider`
- @dnd-kit: `@dnd-kit/core` + `@dnd-kit/sortable` + `@dnd-kit/utilities` installed
- Tests: 169 tests passing (27 B15 + 142 B16) via Vitest + @testing-library/react + jsdom
- CSS variables: `styles/variables.css` — full light/dark palette, typography scale, spacing
- CSS components: `styles/components.css` — ~2000 lines of BEM component styles

**Reusable components from B16 (DO NOT recreate):**
- `components/ClassificationBadge.tsx` — action + type pills from `ClassificationSummary | null`
- `components/ConfidenceBadge.tsx` — `"high"` (green) / `"low"` (amber) badge
- `components/FilterBar.tsx` — 6-input filter with debounced text (state, action, type, sender, dates)
- `components/EmailTable.tsx` — paginated table with multi-select checkboxes
- `components/DraftReview.tsx` — side-by-side email context + draft content
- `components/CategoryList.tsx` — @dnd-kit/sortable drag-to-reorder with CRUD
- `components/FewShotEditor.tsx` — create/edit form for few-shot examples

**Reusable hooks from B16 (DO NOT recreate):**
- `hooks/useEmails.ts` — `useEmails(filters, pagination)`, `useEmailDetail(id)`, `useEmailClassification(id)`, `useEmailMutations()`
- `hooks/useDrafts.ts` — `useDrafts(params)`, `useDraftDetail(id)`, `useDraftMutations()`
- `hooks/useReviewQueue.ts` — `useLowConfidenceEmails()`, `usePendingDrafts()`, `useReviewQueueCounts()`
- `hooks/useCategories.ts` — `useActionCategories()`, `useTypeCategories()`, `useCategoryMutations(layer)`, `useFewShotExamples()`, `useFewShotMutations()`, `useLLMConfig()`, `useTestLLM()`

**API modules from B16 (DO NOT recreate):**
- `api/emails.ts` — 6 typed functions for email endpoints
- `api/drafts.ts` — 5 typed functions for draft endpoints
- `api/categories.ts` — 14 typed functions for categories + examples + LLM

**Placeholders to replace:**
```tsx
// router.tsx — line 74-75: these become real pages
{ path: "/routing",    element: <Placeholder label="Routing Rules" /> },
{ path: "/analytics",  element: <Placeholder label="Analytics" /> },
```

**Stub pages to replace with real content:**
- `pages/OverviewPage.tsx` — currently says "Dashboard Overview — Block 16 Coming soon"
- `pages/IntegrationsPage.tsx` — currently says "Integrations — Block 16 Admin only"
- `pages/LogsPage.tsx` — currently says "Logs — Block 17 Admin only"

**NOT created by B16 (B17 must create):**
- No `StatusIndicator` component — B17 must create it
- No `recharts` — B17 must install it
- No `hooks/useRoutingRules.ts`, `hooks/useAnalytics.ts`, `hooks/useIntegrations.ts`, `hooks/useLogs.ts`
- No `api/routing-rules.ts`, `api/analytics.ts`, `api/integrations.ts`, `api/logs.ts`, `api/health.ts`

**NOT installed (B17 must decide):**
- `recharts` — REQUIRED for charts (spec mandates it)
- `date-fns` — OPTIONAL for date formatting. `Intl.DateTimeFormat` may suffice

## CRITICAL: Spec vs. codebase deltas

The B17 spec has an Amendments section with 11 deltas. **Follow the codebase, not the original spec text.**

| # | Spec says | Codebase reality | Action |
|---|-----------|-------------------|--------|
| X5 | `/api/...` paths | Prefix is `/api/v1/...` in client.ts baseURL | Client prepends prefix — use paths without prefix |
| X8 | `IntegrationConfig` DB model | Does NOT exist — config from env vars via `Settings` | Read-only display, no PUT/PATCH |
| 1 | Routing rules CRUD "under B14" | Already in B13: `src/api/routers/routing_rules.py` | Endpoints exist — no backend work |
| 2 | `PUT /api/integrations/{type}` (update config) | NO PUT exists. Only GET + POST /test per type | Read-only config view + test button only |
| 3 | `GET /api/analytics/summary` | B14 has 4 separate endpoints: `volume`, `classification-distribution`, `accuracy`, `routing` | Use actual endpoint names |
| 4 | `GET /api/analytics/timeseries` | No "timeseries" — `VolumeResponse.data_points[]` IS the time series | Volume endpoint IS the time series |
| 5 | `GET /api/emails/recent-activity` | Does NOT exist | Derive activity from recent emails list or system logs |
| 6 | `LogEntry.stack_trace` | `SystemLog` has no `stack_trace` — only `context: dict[str, str]` | Drop stack_trace from frontend type |
| 7 | `ActivityEvent` generated type | No backend model or endpoint | Derive from SystemLog entries or recent Email state changes |
| 8 | `GET /api/health` path | `GET /api/v1/health` (has `/v1` prefix) | Use `/health` (client adds prefix) |
| 9 | `AnalyticsSummary`, `AnalyticsTimeseries` | B14: `VolumeResponse`, `ClassificationDistributionResponse`, `AccuracyResponse`, `RoutingResponse` | Use actual types from backend |
| 10 | B16 `StatusIndicator` component | B16 did NOT create it — only ClassificationBadge + ConfidenceBadge | B17 must create StatusIndicator |
| 11 | `RoutingTestResult.matched_rules` | B13 has `RuleTestResponse` with `matching_rules: RuleTestMatchResponse[]` | Use actual schema name |

### Impact on spec exit criteria

These deltas invalidate some spec criteria. Corrected versions:

- **Integration "Formularios de config guardan con PUT"**: No PUT endpoint → **READ-ONLY display** of config per integration type. Only "Test Connection" button is interactive.
- **Overview "GET /api/analytics/summary"**: No single summary endpoint → **Call 4 separate analytics endpoints** (volume, distribution, accuracy, routing) and compose the overview.
- **Overview "ActivityFeed"**: No `ActivityEvent` endpoint → **Derive from GET /api/v1/emails** (recent state changes) or **GET /api/v1/logs** (recent system log entries). Define `ActivityEvent` as a local frontend type.
- **Logs "stack trace"**: No `stack_trace` field → **Show `context` dict entries** instead when expanding a log row.

## Backend API contracts — exact shapes

### Routing Rules (B13: `src/api/routers/routing_rules.py`)

**Auth: Admin only for ALL endpoints.**

```
GET    /routing-rules              → RoutingRuleResponse[]
POST   /routing-rules              → RoutingRuleResponse (201)
GET    /routing-rules/{rule_id}    → RoutingRuleResponse
PUT    /routing-rules/{rule_id}    → RoutingRuleResponse
DELETE /routing-rules/{rule_id}    → 204 No Content
PUT    /routing-rules/reorder      → RoutingRuleResponse[]
POST   /routing-rules/test         → RuleTestResponse
```

**Response schemas:**
```typescript
interface RoutingRuleResponse {
  id: string;             // UUID
  name: string;           // 1-255 chars
  is_active: boolean;
  priority: number;       // auto-assigned on create (MAX+1 or 1)
  conditions: RoutingConditionSchema[];
  actions: RoutingActionSchema[];
  created_at: string;     // ISO datetime
  updated_at: string;     // ISO datetime
}

interface RoutingConditionSchema {
  field: string;          // e.g. "action_slug", "type_slug", "sender_domain", "confidence"
  operator: string;       // e.g. "eq", "in", "contains", "matches"
  value: string | string[];  // single value or array for "in" operator
}

interface RoutingActionSchema {
  channel: string;        // e.g. "slack", "email", "crm"
  destination: string;    // e.g. channel ID, email address
  template_id?: string | null;
}

// POST /routing-rules body:
interface RoutingRuleCreate {
  name: string;           // min 1, max 255
  is_active?: boolean;    // default true
  conditions: RoutingConditionSchema[];  // min length 1
  actions: RoutingActionSchema[];        // min length 1
}

// PUT /routing-rules/{id} body (all optional — partial update):
interface RoutingRuleUpdate {
  name?: string | null;
  is_active?: boolean | null;
  conditions?: RoutingConditionSchema[] | null;
  actions?: RoutingActionSchema[] | null;
}

// PUT /routing-rules/reorder body:
interface RoutingRuleReorderRequest {
  ordered_ids: string[];  // UUIDs — index 0 → priority 1
}
```

**Rule Test endpoint:**
```typescript
// POST /routing-rules/test body (synthetic email context for dry-run):
interface RuleTestRequest {
  email_id: string;         // UUID
  action_slug: string;
  type_slug: string;
  confidence: string;       // "high" | "low"
  sender_email: string;
  sender_domain: string;
  subject: string;
  snippet: string;
  sender_name?: string | null;
}

// Response:
interface RuleTestResponse {
  matching_rules: RuleTestMatchResponse[];
  total_rules_evaluated: number;
  total_actions: number;
  dry_run: boolean;         // always true
}

interface RuleTestMatchResponse {
  rule_id: string;          // UUID
  rule_name: string;
  priority: number;
  would_dispatch: RoutingActionSchema[];  // actions that would be triggered
}
```

**Important:** `/routing-rules/reorder` and `/routing-rules/test` are literal paths that come BEFORE `/{rule_id}` in the router. The reorder endpoint expects `ordered_ids[0]` → priority 1, `ordered_ids[1]` → priority 2, etc.

### Analytics (B14: `src/api/routers/analytics.py`)

**Auth: Reviewer + Admin for dashboard views, Admin only for CSV export.**

```
GET    /analytics/volume                    → VolumeResponse
GET    /analytics/classification-distribution → ClassificationDistributionResponse
GET    /analytics/accuracy                  → AccuracyResponse
GET    /analytics/routing                   → RoutingResponse
GET    /analytics/export                    → StreamingResponse (text/csv, admin only)
```

**ALL endpoints require:** `start_date: date` and `end_date: date` as query params (required, "YYYY-MM-DD" format). Validation: `end_date >= start_date` (400 if violated). Both dates are inclusive.

**Response schemas:**
```typescript
interface VolumeResponse {
  data_points: VolumeDataPoint[];
  total_emails: number;
  start_date: string;     // "YYYY-MM-DD"
  end_date: string;       // "YYYY-MM-DD"
}

interface VolumeDataPoint {
  date: string;           // "YYYY-MM-DD"
  count: number;
}

interface ClassificationDistributionResponse {
  actions: DistributionItem[];
  types: DistributionItem[];
  total_classified: number;
}

interface DistributionItem {
  category: string;       // slug
  display_name: string;
  count: number;
  percentage: number;     // float, 0-100
}

interface AccuracyResponse {
  total_classified: number;
  total_overridden: number;
  accuracy_pct: number;   // float; 100.0 if no classifications
  period_start: string;   // "YYYY-MM-DD"
  period_end: string;     // "YYYY-MM-DD"
}

interface RoutingResponse {
  channels: RoutingChannelStat[];
  total_dispatched: number;
  total_failed: number;
  unrouted_count: number;
}

interface RoutingChannelStat {
  channel: string;        // e.g. "slack", "email"
  dispatched: number;
  failed: number;
  success_rate: number;   // float, 0-100
}
```

**CSV export:**
- `GET /analytics/export?start_date=...&end_date=...`
- Returns `StreamingResponse` with `Content-Type: text/csv`
- `Content-Disposition: attachment; filename=emails_YYYY-MM-DD_YYYY-MM-DD.csv`
- Admin only. Use `URL.createObjectURL` + dynamic `<a>` for download. Call `URL.revokeObjectURL` in cleanup.

### Integrations (B14: `src/api/routers/integrations.py`)

**Auth: Admin only for ALL endpoints.**

**ALL config endpoints are READ-ONLY — no PUT/PATCH exists. Config is from environment variables.**

```
GET    /integrations/email          → EmailIntegrationConfig
POST   /integrations/email/test     → ConnectionTestResult

GET    /integrations/channels       → ChannelIntegrationConfig
POST   /integrations/channels/test  → ConnectionTestResult

GET    /integrations/crm            → CRMIntegrationConfig
POST   /integrations/crm/test       → ConnectionTestResult

GET    /integrations/llm            → LLMIntegrationConfig  (already in B16 api/categories.ts)
POST   /integrations/llm/test       → ConnectionTestResult  (already in B16 api/categories.ts)
```

**Response schemas:**
```typescript
interface EmailIntegrationConfig {
  oauth_configured: boolean;
  credentials_file: string;
  token_file: string;
  poll_interval_seconds: number;
  max_results: number;
}

interface ChannelIntegrationConfig {
  bot_token_configured: boolean;
  signing_secret_configured: boolean;
  default_channel: string;
  snippet_length: number;
  timeout_seconds: number;
}

interface CRMIntegrationConfig {
  access_token_configured: boolean;
  auto_create_contacts: boolean;
  default_lead_status: string;
  rate_limit_per_10s: number;
  api_timeout_seconds: number;
}

// LLMIntegrationConfig already in types/generated/api.ts from B16

// ALL test endpoints return 200 OK regardless — check success boolean:
interface ConnectionTestResult {
  success: boolean;
  latency_ms: number | null;
  error_detail: string | null;
  adapter_type: string;   // "gmail", "slack", "hubspot", "litellm"
}
```

**Note:** `ConnectionTestResult` is already defined in `types/generated/api.ts` from B16 (as `LLMTestResult` alias). The LLM config and test functions are already in `api/categories.ts` — reuse them, don't duplicate.

### Logs (B14: `src/api/routers/logs.py`)

**Auth: Admin only.**

```
GET    /logs    → LogListResponse
```

**IMPORTANT: Logs use offset/limit pagination, NOT page/page_size.**

**Query params (all optional):**
```typescript
level?: string;       // filter by log level: "INFO", "WARNING", "ERROR"
source?: string;      // filter by source module
since?: string;       // ISO datetime — filter logs >= timestamp
until?: string;       // ISO datetime — filter logs <= timestamp
email_id?: string;    // UUID — filter by associated email
limit?: number;       // default: 50, range: 1-200
offset?: number;      // default: 0, >= 0
```

**Response schema:**
```typescript
interface LogListResponse {
  items: LogEntry[];
  total: number;      // total matching logs (ignoring pagination)
  limit: number;      // 1-200
  offset: number;     // >= 0
}

interface LogEntry {
  id: string;               // UUID
  timestamp: string;        // ISO datetime
  level: string;            // "INFO" | "WARNING" | "ERROR"
  source: string;           // module name
  message: string;
  email_id: string | null;  // nullable — logs may not relate to an email
  context: Record<string, string>;  // NO nested objects, NO Any
}
```

**Note:** No `stack_trace` field. The `context` dict contains additional string key-value pairs. Display these in the expanded log view instead.

### Health (B13: `src/api/routers/health.py`)

**Auth: NONE — public endpoint (no Bearer token required).**

```
GET    /health    → HealthResponse
```

**Response schema:**
```typescript
interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  adapters: AdapterHealthItem[];
}

interface AdapterHealthItem {
  name: string;                          // "database", "redis"
  status: "ok" | "degraded" | "unavailable";
  latency_ms: number | null;
  error: string | null;
}
```

**Behavior:**
- Always returns 200 OK (never 503, even if degraded)
- `status="ok"` if all adapters are "ok"
- `status="degraded"` if any adapter is "degraded" or "unavailable"
- Checks PostgreSQL and Redis in parallel

## Files to create/modify

### New files

| File | Purpose |
|------|---------|
| `frontend/src/api/routing-rules.ts` | Typed API functions for routing rules CRUD + reorder + test |
| `frontend/src/api/analytics.ts` | Typed API functions for 4 analytics endpoints + CSV export |
| `frontend/src/api/integrations.ts` | Typed API functions for 4 integration types (GET + test) |
| `frontend/src/api/logs.ts` | Typed API function for logs with offset/limit |
| `frontend/src/api/health.ts` | Typed API function for health check |
| `frontend/src/hooks/useRoutingRules.ts` | CRUD + reorder + test + toggle active |
| `frontend/src/hooks/useAnalytics.ts` | 4 analytics queries + CSV export download |
| `frontend/src/hooks/useIntegrations.ts` | Config fetch + test connection for 4 types |
| `frontend/src/hooks/useLogs.ts` | Paginated log fetch with filters (offset/limit) |
| `frontend/src/hooks/useHealth.ts` | Health polling (30s interval) |
| `frontend/src/components/StatCard.tsx` | Metric card with label, value, optional delta |
| `frontend/src/components/StatusIndicator.tsx` | Status dot: "ok" (green) / "degraded" (yellow) / "unavailable" (red) |
| `frontend/src/components/Chart.tsx` | Recharts wrapper — encapsulates ALL recharts imports |
| `frontend/src/components/RuleCard.tsx` | Draggable routing rule card |
| `frontend/src/components/RuleBuilder.tsx` | Modal/drawer form for create/edit routing rule |
| `frontend/src/components/RuleTestPanel.tsx` | Rule dry-run test panel (Tier 2) |
| `frontend/src/components/IntegrationPanel.tsx` | Read-only config display + test button per integration |
| `frontend/src/components/DateRangeSelector.tsx` | Preset range selector (7d/30d/90d/custom) |
| `frontend/src/components/ActivityFeed.tsx` | Recent system events list |
| `frontend/src/components/LogRow.tsx` | Expandable log entry row |

### Files to modify

| File | Change |
|------|--------|
| `frontend/src/router.tsx` | Replace 2 Placeholders (`/routing`, `/analytics`) with lazy-loaded pages |
| `frontend/src/pages/OverviewPage.tsx` | Replace stub with real dashboard content |
| `frontend/src/pages/IntegrationsPage.tsx` | Replace stub with real integration panels |
| `frontend/src/pages/LogsPage.tsx` | Replace stub with real log viewer |
| `frontend/src/types/generated/api.ts` | Add B17 schemas: routing rules, analytics, logs, health, integrations |
| `frontend/src/styles/components.css` | Append B17 component styles |
| `frontend/package.json` | Add `recharts` dependency |

### New pages

| File | Route | Purpose |
|------|-------|---------|
| `frontend/src/pages/RoutingRulesPage.tsx` | `/routing` | Draggable rule cards + RuleBuilder modal |
| `frontend/src/pages/AnalyticsPage.tsx` | `/analytics` | DateRangeSelector + 4 chart sections + CSV export |

### Tests to create

| File | Coverage |
|------|----------|
| `frontend/src/pages/__tests__/OverviewPage.test.tsx` | StatCards render, health polling, activity feed |
| `frontend/src/pages/__tests__/RoutingRulesPage.test.tsx` | Rule list, create, edit, delete, toggle, reorder |
| `frontend/src/pages/__tests__/IntegrationsPage.test.tsx` | 4 panels render, test connection |
| `frontend/src/pages/__tests__/AnalyticsPage.test.tsx` | Date range change re-fetches, charts render |
| `frontend/src/pages/__tests__/SystemLogsPage.test.tsx` | Filter by level, expand row, pagination |
| `frontend/src/components/__tests__/RuleBuilder.test.tsx` | Create mode, edit mode, submit |
| `frontend/src/components/__tests__/Chart.test.tsx` | Line, bar, pie render without error |
| `frontend/src/components/__tests__/RuleTestPanel.test.tsx` | Submit test, show results |
| `frontend/src/hooks/__tests__/useRoutingRules.test.ts` | Reorder sends ordered_ids array |
| `frontend/src/hooks/__tests__/useAnalytics.test.ts` | Date range params, CSV download |
| `frontend/src/hooks/__tests__/useIntegrations.test.ts` | Test connection, error handling |
| `frontend/src/hooks/__tests__/useLogs.test.ts` | Offset/limit pagination, level filter |

## Pre-implementation decisions needed

### 1. Chart library

**recharts** (spec mandates it). Install: `npm install recharts`.
- All `import from 'recharts'` must be ONLY in `Chart.tsx` and its test file
- Use `ResponsiveContainer` for viewport-responsive charts
- Types are bundled with the package (no `@types/recharts` needed)

### 2. Activity Feed data source

No dedicated backend endpoint exists. Two options:
- **Option A**: Derive from `GET /api/v1/emails?page_size=20` (recent emails as "activity")
- **Option B**: Derive from `GET /api/v1/logs?limit=20` (recent system logs as events)
- **Recommended**: Option A for user-facing activity (email state changes), with `ActivityEvent` as a local frontend type that maps from `EmailListItem`

### 3. Overview data composition

The Overview page needs data from multiple endpoints. Compose from:
1. `GET /analytics/volume?start_date=...&end_date=...` — email volume chart + total
2. `GET /analytics/classification-distribution?...` — action/type breakdown
3. `GET /analytics/accuracy?...` — accuracy percentage
4. `GET /analytics/routing?...` — channel distribution
5. `GET /health` — adapter health status (polled every 30s)
6. `GET /emails?page_size=20` — recent activity feed

### 4. Logs pagination (offset/limit, NOT page-based)

Logs use `offset`/`limit` (not `page`/`page_size`). The frontend must calculate:
- Page N → `offset = (N - 1) * limit`
- Total pages → `Math.ceil(total / limit)`

### 5. Recharts encapsulation

Spec mandates: `import from 'recharts'` must appear ONLY in `Chart.tsx` (and its tests). The `Chart` component wrapper should accept a `type` prop to select chart variant.

## Types to add to `types/generated/api.ts`

**Routing Rules schemas:**
- `RoutingConditionSchema`, `RoutingActionSchema`
- `RoutingRuleResponse`, `RoutingRuleCreate`, `RoutingRuleUpdate`
- `RoutingRuleReorderRequest`
- `RuleTestRequest`, `RuleTestResponse`, `RuleTestMatchResponse`

**Analytics schemas:**
- `VolumeResponse`, `VolumeDataPoint`
- `ClassificationDistributionResponse`, `DistributionItem`
- `AccuracyResponse`
- `RoutingResponse`, `RoutingChannelStat`

**Integration schemas (new):**
- `EmailIntegrationConfig`, `ChannelIntegrationConfig`, `CRMIntegrationConfig`
- (`LLMIntegrationConfig` and `ConnectionTestResult` already exist from B16)

**Log schemas:**
- `LogListResponse`, `LogEntry`

**Health schemas:**
- `HealthResponse`, `AdapterHealthItem`

**Local frontend types (NOT generated — define in component/hook files):**
- `DateRange = { from: string; to: string; preset?: '7d' | '30d' | '90d' | 'custom' }`
- `ActivityEvent = { type: string; timestamp: string; description: string; email_id?: string }`
- `ChartDataPoint = Record<string, string | number>` (documented exception to "no loose types")

## CSS custom properties available (from variables.css)

```css
/* Colors */
var(--color-bg), var(--color-bg-surface), var(--color-bg-elevated)
var(--color-border)
var(--color-text), var(--color-text-muted), var(--color-text-inverse)
var(--color-primary), var(--color-primary-hover), var(--color-primary-light)
var(--color-success)    /* StatusIndicator: ok, ConfidenceBadge: high */
var(--color-warning)    /* StatusIndicator: degraded, ConfidenceBadge: low */
var(--color-error)      /* StatusIndicator: unavailable, delete/reject actions */
var(--color-info)

/* Typography */
var(--font-size-xs) through var(--font-size-xl)
var(--font-family-sans), var(--font-family-mono)

/* Layout */
var(--radius-sm/md/lg), var(--shadow-sm/md/lg)
var(--transition-fast/normal)
var(--sidebar-width: 240px), var(--header-height: 64px)
```

**Invariant**: zero hardcoded colors in components. All via `var(--color-*)`.

## Access control

| Feature | Admin | Reviewer |
|---------|-------|----------|
| Overview dashboard | Yes | Yes |
| Analytics (view) | Yes | Yes |
| Analytics (CSV export) | Yes | No |
| Routing rules (all CRUD) | Yes | No |
| Integrations (view + test) | Yes | No |
| System logs | Yes | No |
| Health endpoint | Public | Public |

Use `useAuth().user.role` to conditionally show/hide admin-only actions.

**Route guards already configured in `router.tsx`:**
- `/routing` — currently under `ProtectedRoute` (any auth). Spec says admin-only → **move to admin route group**
- `/analytics` — currently under `ProtectedRoute` (any auth). Keep as-is (reviewer can view analytics)
- `/integrations`, `/logs` — already under `ProtectedRoute requiredRole="admin"`

## Named constants (pre-mortem Cat 8)

All load-bearing defaults must be named constants, not magic numbers:

```typescript
// In frontend/src/utils/constants.ts or at top of relevant hook/page:
const HEALTH_POLL_INTERVAL_MS = 30_000;       // Health polling interval
const ACTIVITY_FEED_LIMIT = 20;               // Items shown in activity feed
const DEFAULT_DATE_PRESET = "30d" as const;   // Default analytics range
const LOGS_DEFAULT_LIMIT = 50;                // Default log page size
const LOGS_MAX_LIMIT = 200;                   // Max log entries per request
```

## Quality gates (same as B16 + expanded)

```bash
npm run typecheck       # tsc --noEmit — 0 errors
npm run lint            # ESLint — 0 errors
npm run build           # Vite production build — success
npm run test            # vitest — all pass

# Architecture checks:
# 1. No any in B17 files
grep -rn ": any\|as any\|<any>" frontend/src/pages/OverviewPage.tsx frontend/src/pages/RoutingRulesPage.tsx frontend/src/pages/IntegrationsPage.tsx frontend/src/pages/AnalyticsPage.tsx frontend/src/pages/LogsPage.tsx frontend/src/components/StatCard.tsx frontend/src/components/RuleCard.tsx frontend/src/components/RuleBuilder.tsx frontend/src/components/IntegrationPanel.tsx frontend/src/components/Chart.tsx frontend/src/hooks/useRoutingRules.ts frontend/src/hooks/useAnalytics.ts frontend/src/hooks/useIntegrations.ts frontend/src/hooks/useLogs.ts
# Expected: EMPTY

# 2. Recharts encapsulated
grep -rn "from 'recharts'\|from \"recharts\"" frontend/src/
# Expected: ONLY in components/Chart.tsx and its test file

# 3. No manual type duplication
grep -rn "interface RoutingRuleResponse\|interface VolumeResponse\|interface LogEntry\|interface HealthResponse" frontend/src/pages/ frontend/src/components/ frontend/src/hooks/
# Expected: EMPTY (types imported from generated/, not redefined)
```
