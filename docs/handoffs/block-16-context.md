# Block 16: FE Core — Email Browser, Review Queue, Classification Config — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-16-frontend-core.md`.

## What to build

Replace the three Placeholder routes from B15 (`/emails`, `/emails/:id`, `/review`) with real implementations. Add classification config page for admin. Create typed hooks for data fetching and mutation. Zero `any`, all types from `types/generated/api.ts`.

## What B15 delivered (your starting point)

**Infrastructure (DO NOT recreate):**
- SPA shell: AppShell (CSS grid: sidebar 240px + header 64px + content)
- Auth: `AuthContext.tsx` with JWT tokens in `useRef` (login, logout, refresh, `configureClient`)
- Theme: `ThemeContext.tsx` with CSS custom properties via `data-theme` attribute
- API client: `api/client.ts` — axios with `/api/v1` baseURL, Bearer interceptor, 401 refresh+retry
- Router: `router.tsx` — protected routes with role guards, lazy-loaded admin pages
- Tests: 27 tests passing (Vitest + @testing-library/react + jsdom)
- CSS variables: `styles/variables.css` — full light/dark palette, typography scale, spacing

**Placeholders to replace:**
```tsx
// router.tsx — these become real pages
{ path: "/emails",     element: <Placeholder label="Email Browser" /> },
{ path: "/emails/:id", element: <Placeholder label="Email Detail" /> },
{ path: "/review",     element: <Placeholder label="Review Queue" /> },
```

**Existing stubs to flesh out:**
- `pages/ClassificationConfigPage.tsx` — says "Block 17" but B16 spec assigns it here

**NOT installed (B16 must decide):**
- No data fetching library (SWR / TanStack Query) — B16 must install one
- No drag-and-drop library — B16 needs `@dnd-kit/core` + `@dnd-kit/sortable` for CategoryList
- No `frontend/src/hooks/` directory — create it

## CRITICAL: Spec vs. codebase deltas

The B16 spec has an Amendments section with 14 deltas. **Follow the codebase, not the original spec text.**

| # | Spec says | Codebase reality | Action |
|---|-----------|-------------------|--------|
| X1 | `Email.received_at` | Schema field IS `received_at` (`EmailListItem.received_at`) | No change — spec amendment is about ORM (`Email.date`), API schema already uses `received_at` |
| X2 | `Email.from_address` | `EmailListItem.sender_email` / `EmailDetailResponse.sender_email` | Use `sender_email` |
| X3 | `Draft.body` | `DraftDetailResponse.content` | Use `content` |
| X5 | `/api/...` paths | Already `/api/v1/` in client.ts baseURL | No change needed — client prepends prefix |
| 1 | `POST /api/emails/{id}/reroute` | **Does NOT exist** — only `retry` and `reclassify` | Use `reclassify` (admin only). No reroute action. |
| 2 | `PUT /api/drafts/{id}` (edit body) | **Does NOT exist** — B13 has approve/reject/reassign only | No inline edit of draft content. Approve or reject only. |
| 3 | `GET /api/review-queue` | **Does NOT exist** | Compose from: `GET /api/v1/emails` (filtered by state/confidence) + `GET /api/v1/drafts?status=pending` |
| 4 | `GET /api/categories?layer=action` | Separate paths: `/api/v1/categories/actions` and `/api/v1/categories/types` | Two API calls, one per layer |
| 5 | `GET /api/few-shot-examples` | `GET /api/v1/classification/examples` | Use actual path |
| 6 | `GET /api/classification-config` + `PUT` | **Don't exist** — LLM config via `GET /api/v1/integrations/llm` (read-only) | Read-only display. No threshold/prompt editing. |
| 10 | `Email.draft_id` FK | **No FK** from Email to Draft. `Draft.email_id` FKs to Email | Query drafts by `email_id`, not from Email |
| 11 | Category `layer` discriminator field | Separate tables: `ActionCategory`, `TypeCategory` | No `layer` field — separate API calls per table |
| 14 | `confidence: 'high' \| 'low'` | Matches `ClassificationConfidence` enum — confirmed as string `"high"` / `"low"` | No change needed |

### Impact on spec exit criteria

These deltas invalidate some spec criteria. Corrected versions:

- **Review Queue "Edit draft"**: spec says `PUT /api/drafts/{id}`. Endpoint doesn't exist → **DROP inline edit feature**. DraftReview has Approve/Reject/Reassign only.
- **Classification Config "System prompt + threshold"**: spec says `PUT /api/classification-config`. Endpoint doesn't exist → **READ-ONLY section** showing LLM config from integrations. No slider, no save.
- **Bulk "Re-route selected"**: spec says `POST /api/emails/{id}/reroute`. Endpoint doesn't exist → **DROP reroute button**. Keep "Reclassify selected" only.

## Backend API contracts — exact shapes

### Emails (B13: `src/api/routers/emails.py`)

```
GET    /emails                                → PaginatedResponse[EmailListItem]
GET    /emails/{email_id}                     → EmailDetailResponse
POST   /emails/{email_id}/retry               → RetryResponse (admin)
POST   /emails/{email_id}/reclassify          → ReclassifyResponse (admin)
GET    /emails/{email_id}/classification       → ClassificationDetailResponse
POST   /emails/{email_id}/classification/feedback → FeedbackResponse (reviewer+, 201)
```

**Query params for GET /emails:**
```typescript
// PaginationParams
page?: number     // default 1, min 1
page_size?: number // default 20, min 1, max 100

// EmailFilter
state?: EmailState  // enum: "fetched" | "sanitized" | "classified" | "routed" | ...
action?: string     // slug: "respond", "escalate", etc.
type?: string       // slug: "complaint", "inquiry", etc.
sender?: string     // email address substring
date_from?: string  // ISO datetime
date_to?: string    // ISO datetime
```

**Response schemas:**
```typescript
interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;     // >= 1
  page_size: number; // 1-100
  pages: number;     // >= 0, ceil(total / page_size)
}

interface EmailListItem {
  id: string;            // UUID
  subject: string;
  sender_email: string;  // NOT from_address
  sender_name: string | null;
  received_at: string;   // ISO datetime
  state: EmailState;     // 12-state enum
  snippet: string | null;
  classification: ClassificationSummary | null;
}

interface ClassificationSummary {
  action: string;       // slug
  type: string;         // slug
  confidence: string;   // "high" | "low"
  is_fallback: boolean;
}

interface EmailDetailResponse extends EmailListItem {
  thread_id: string | null;
  routing_actions: RoutingActionSummary[];
  crm_sync: CRMSyncSummary | null;
  draft: DraftSummary | null;
  created_at: string;
  updated_at: string;
}

interface RoutingActionSummary {
  id: string;
  channel: string;
  destination: string;
  status: string;
  dispatched_at: string | null;
}

interface CRMSyncSummary {
  status: string;
  contact_id: string | null;
  activity_id: string | null;
  synced_at: string | null;
}

interface DraftSummary {
  id: string;
  status: string;       // "pending" | "approved" | "rejected"
  created_at: string;
}
```

### Drafts (B13: `src/api/routers/drafts.py`)

```
GET    /drafts                      → PaginatedResponse[DraftListItem]
GET    /drafts/{draft_id}           → DraftDetailResponse
POST   /drafts/{draft_id}/approve   → DraftApproveResponse
POST   /drafts/{draft_id}/reject    → 204 No Content
POST   /drafts/{draft_id}/reassign  → DraftDetailResponse (admin only)
```

**Query params for GET /drafts:**
```typescript
page?: number
page_size?: number
status?: string  // "pending" | "approved" | "rejected" — query param alias
```

**Response schemas:**
```typescript
interface DraftListItem {
  id: string;
  email_id: string;
  email_subject: string;
  email_sender: string;   // sender_email of the parent email
  status: string;          // "pending" | "approved" | "rejected"
  reviewer_id: string | null;
  created_at: string;
}

interface DraftDetailResponse {
  id: string;
  content: string;          // NOT "body"
  status: string;
  reviewer_id: string | null;
  reviewed_at: string | null;
  pushed_to_provider: boolean;
  email: EmailForDraftReview;  // context for side-by-side
  created_at: string;
  updated_at: string;
}

interface EmailForDraftReview {
  id: string;
  subject: string;
  sender_email: string;
  sender_name: string | null;
  snippet: string | null;
  received_at: string;
  classification: ClassificationSummary | null;
}

// POST /drafts/{id}/approve body:
interface DraftApproveRequest {
  push_to_gmail?: boolean;  // default true
}

// POST /drafts/{id}/reject body:
interface DraftRejectRequest {
  reason: string;  // min_length 1 — REQUIRED
}

// POST /drafts/{id}/reassign body:
interface DraftReassignRequest {
  reviewer_id: string;  // UUID
}
```

### Categories (B14: `src/api/routers/categories.py`)

```
GET    /categories/actions              → ActionCategoryResponse[]
POST   /categories/actions              → ActionCategoryResponse (201)
GET    /categories/actions/{id}         → ActionCategoryResponse
PUT    /categories/actions/{id}         → ActionCategoryResponse
DELETE /categories/actions/{id}         → 204 (or 409 if in use)
PUT    /categories/actions/reorder      → ActionCategoryResponse[]

(identical for /categories/types with TypeCategoryResponse)
```

**Schemas:**
```typescript
interface ActionCategoryResponse {  // same shape for TypeCategory
  id: string;
  slug: string;           // immutable after creation
  name: string;
  description: string;
  is_fallback: boolean;
  is_active: boolean;
  display_order: number;  // 1-based after reorder
  created_at: string;
  updated_at: string;
}

interface ActionCategoryCreate {
  name: string;           // min 1, max 255
  slug: string;           // min 1, max 100
  description?: string;   // default ""
  is_fallback?: boolean;  // default false
  is_active?: boolean;    // default true
}

interface ActionCategoryUpdate {
  name?: string;
  description?: string;
  is_fallback?: boolean;
  is_active?: boolean;
  // slug is NOT updatable
}

interface ReorderRequest {
  ordered_ids: string[];  // UUIDs — index 0 → display_order 1
}
```

**409 on DELETE**: If category is referenced by emails, returns:
```json
{ "error": "category_in_use", "affected_email_count": 42 }
```

### Classification examples (B14: same router file)

```
GET    /classification/examples           → FewShotExampleResponse[]
POST   /classification/examples           → FewShotExampleResponse (201)
PUT    /classification/examples/{id}      → FewShotExampleResponse
DELETE /classification/examples/{id}      → 204
GET    /classification/feedback           → PaginatedResponse[FeedbackItem] (admin)
```

**Schemas:**
```typescript
interface FewShotExampleResponse {
  id: string;
  email_snippet: string;
  action_slug: string;    // references ActionCategory.slug
  type_slug: string;      // references TypeCategory.slug
  rationale: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

interface FewShotExampleCreate {
  email_snippet: string;  // min 1
  action_slug: string;    // min 1, max 100
  type_slug: string;      // min 1, max 100
  rationale?: string;
}
```

### Integrations — LLM config (B14, read-only)

```
GET    /integrations/llm      → dict (config details, no credentials)
POST   /integrations/llm/test → { "status": "ok"/"error", "latency_ms": N }
```

No PUT endpoint exists. LLM config is read-only from environment variables.

## Files to create/modify

### New files

| File | Purpose |
|------|---------|
| `frontend/src/pages/EmailBrowserPage.tsx` | `/emails` — FilterBar + EmailTable + pagination |
| `frontend/src/pages/EmailDetailPage.tsx` | `/emails/:id` — full detail: body, classification, routing, CRM, draft |
| `frontend/src/pages/ReviewQueuePage.tsx` | `/review` — two tabs: Low Confidence + Pending Drafts |
| `frontend/src/hooks/useEmails.ts` | Paginated email fetch with filters |
| `frontend/src/hooks/useReviewQueue.ts` | Composed queries: low-confidence emails + pending drafts |
| `frontend/src/hooks/useCategories.ts` | CRUD + reorder for action/type categories |
| `frontend/src/hooks/useDrafts.ts` | Draft list + approve/reject/reassign mutations |
| `frontend/src/components/EmailTable.tsx` | Sortable paginated table |
| `frontend/src/components/FilterBar.tsx` | Date, action, type, sender, state filters |
| `frontend/src/components/ClassificationBadge.tsx` | Visual badge for action + type |
| `frontend/src/components/ConfidenceBadge.tsx` | `"high"` (green) / `"low"` (amber) |
| `frontend/src/components/DraftReview.tsx` | Side-by-side: email context + draft content + Approve/Reject/Reassign |
| `frontend/src/components/CategoryList.tsx` | Draggable list with CRUD |
| `frontend/src/components/FewShotEditor.tsx` | Add/edit form for few-shot examples |
| `frontend/src/api/emails.ts` | Typed API functions for email endpoints |
| `frontend/src/api/drafts.ts` | Typed API functions for draft endpoints |
| `frontend/src/api/categories.ts` | Typed API functions for categories + examples |

### Files to modify

| File | Change |
|------|--------|
| `frontend/src/router.tsx` | Replace 3 Placeholders with real pages |
| `frontend/src/pages/ClassificationConfigPage.tsx` | Replace stub with real content |
| `frontend/src/types/generated/api.ts` | Add B13/B14 schemas (placeholder expansion) |
| `frontend/package.json` | Add: data fetching lib + @dnd-kit/core + @dnd-kit/sortable |

### Tests to create

| File | Coverage |
|------|----------|
| `frontend/src/pages/__tests__/EmailBrowserPage.test.tsx` | Render, filters, pagination |
| `frontend/src/pages/__tests__/ReviewQueuePage.test.tsx` | Tab switch, approve/reject |
| `frontend/src/pages/__tests__/ClassificationConfigPage.test.tsx` | CRUD categories, reorder |
| `frontend/src/components/__tests__/DraftReview.test.tsx` | Side-by-side, action callbacks |
| `frontend/src/components/__tests__/CategoryList.test.tsx` | Drag reorder |
| `frontend/src/components/__tests__/FilterBar.test.tsx` | Filter change emits typed object |
| `frontend/src/hooks/__tests__/useEmails.test.ts` | Fetch, pagination, error |
| `frontend/src/hooks/__tests__/useReviewQueue.test.ts` | Optimistic mutations, rollback |
| `frontend/src/hooks/__tests__/useCategories.test.ts` | Reorder sends ordered_ids |

## Pre-implementation decisions needed

### 1. Data fetching library

Neither SWR nor TanStack Query is installed. Choose one:

| | SWR | TanStack Query |
|---|-----|----------------|
| Bundle | ~4KB | ~12KB |
| API | `useSWR` / `useSWRMutation` | `useQuery` / `useMutation` |
| Devtools | None built-in | Excellent devtools |
| Optimistic updates | Manual | Built-in |
| Stale-while-revalidate | Core feature | Configurable |

**Recommendation**: TanStack Query — optimistic mutations for approve/reject are a core B16 requirement, and devtools aid debugging.

### 2. Review queue composition (no dedicated endpoint)

**Low Confidence items**: `GET /api/v1/emails?state=classified` then filter client-side where `classification.confidence === "low"`. OR: backend already allows `action`/`type` filters but NOT a `confidence` filter — **confidence filtering must be client-side**.

**Pending Drafts**: `GET /api/v1/drafts?status=pending` — direct API support.

The `useReviewQueue` hook composes these two into a unified interface with separate tabs.

### 3. Confidence filter gap

The `EmailFilter` schema in the backend does NOT have a `confidence` field:
```python
class EmailFilter(BaseModel):
    state: EmailState | None = None
    action: str | None = None
    type: str | None = None
    sender: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    # NO confidence field
```

For the "Low Confidence" tab, the frontend must:
1. Fetch classified emails: `GET /api/v1/emails?state=classified`
2. Filter client-side: `items.filter(e => e.classification?.confidence === "low")`

This means pagination counts may not match (total includes high-confidence). Consider fetching larger pages and filtering, or flagging this as a backend enhancement.

## Generated types expansion

The current `types/generated/api.ts` is a placeholder with only auth schemas. B16 must expand it with all B13/B14 schemas. Since there's no running backend for `openapi-typescript`, add types manually matching the backend schemas listed above. Keep the placeholder header comment and structure.

**Key types to add** (matching backend Pydantic schemas exactly):
- `PaginatedResponse` (generic — use TypeScript generic)
- `EmailState` (enum union of 12 states)
- `EmailListItem`, `EmailDetailResponse`, `ClassificationSummary`
- `RoutingActionSummary`, `CRMSyncSummary`, `DraftSummary`
- `EmailFilter`, `PaginationParams`
- `DraftListItem`, `DraftDetailResponse`, `EmailForDraftReview`
- `DraftApproveRequest`, `DraftRejectRequest`, `DraftReassignRequest`, `DraftApproveResponse`
- `ActionCategoryResponse`, `ActionCategoryCreate`, `ActionCategoryUpdate`, `ReorderRequest`
- `FewShotExampleResponse`, `FewShotExampleCreate`, `FewShotExampleUpdate`
- `ReclassifyRequest`, `ReclassifyResponse`, `RetryRequest`, `RetryResponse`
- `ClassificationFeedbackRequest`, `FeedbackResponse`

## CSS custom properties available (from variables.css)

```css
/* Colors */
var(--color-bg), var(--color-bg-surface), var(--color-bg-elevated)
var(--color-border)
var(--color-text), var(--color-text-muted), var(--color-text-inverse)
var(--color-primary), var(--color-primary-hover), var(--color-primary-light)
var(--color-success)    /* ConfidenceBadge: high */
var(--color-warning)    /* ConfidenceBadge: low */
var(--color-error)      /* delete/reject actions */
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
| View all emails | Yes | Yes |
| Email detail | Yes | Yes |
| Retry/Reclassify email | Yes | No |
| View all drafts | Yes | Own only |
| Approve/Reject drafts | Yes | Own only |
| Reassign drafts | Yes | No |
| Classification feedback | Yes | Yes |
| Manage categories | Yes | No |
| Manage few-shot examples | Yes | No |

Use `useAuth().user.role` to conditionally show/hide admin-only actions.

## Quality gates (same as B15 + expanded)

```bash
npm run typecheck       # tsc --noEmit — 0 errors
npm run lint            # ESLint — 0 errors
npm run build           # Vite production build — success
npm run test            # vitest — all pass

# Architecture checks:
grep -rn ": any\|as any\|<any>" frontend/src/pages/EmailBrowserPage.tsx frontend/src/pages/EmailDetailPage.tsx frontend/src/pages/ReviewQueuePage.tsx frontend/src/pages/ClassificationConfigPage.tsx frontend/src/components/EmailTable.tsx frontend/src/components/FilterBar.tsx frontend/src/components/DraftReview.tsx frontend/src/components/CategoryList.tsx frontend/src/hooks/
# Expected: EMPTY

grep -rn "interface EmailListItem\|interface DraftListItem\|interface ActionCategoryResponse" frontend/src/pages/ frontend/src/components/ frontend/src/hooks/
# Expected: EMPTY (types imported from generated/, not redefined)
```
