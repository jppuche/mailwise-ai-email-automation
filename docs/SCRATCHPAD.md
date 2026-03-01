# Learning Scratchpad — mailwise

Granular log of errors, corrections, and preferences. Updated each session.
Compound learning: each session reads this file before working.

## Rules

- Limit: 150 lines. If exceeded, prune old consolidated entries.
- Graduation: pattern repeats 3+ times or is critical → move to CLAUDE.md "Learned Patterns"
- When graduating, remove original entries from scratchpad
- All agents write with [agent-name] tag, Lorekeeper organizes and prunes

<!-- Session format: ## YYYY-MM-DD -- [description] / ### Mistakes made / ### User corrections / ### What worked well / ### What did NOT work / ### Preferences discovered -->

---

## 2026-02-20 -- Phases 1-5 + B00-B19 (consolidated) [Lorekeeper]

### Key user preferences

- [user] Dual objective: portfolio + consultant showcase. All 20 specs upfront (consultant deliverable).
- [user] Prefers infrastructure (Celery+Redis) for professional appearance
- [user] Visualizations: larger readable text, typographic coherence (modular scale). Architecture: blueprint/neon. Decisions: editorial serif, cool slate/indigo palette.

### Standing architecture decisions (spec-level, not yet in code)

- [B15-B17] Frontend: access+refresh tokens in `useRef` (no cookies — backend has no httpOnly mechanism), ESLint `no-explicit-any`, CSS vars `[data-theme="dark"]`, types from `types/generated/`.
- [B18] alignment-chart enforced as exit criteria. `CELERY_TASK_ALWAYS_EAGER=True` for E2E. `pytest --cov-fail-under=70`.
- [B19] `CorrelationIdContext` via contextvars. Docker images pinned to patch. `CORS_ORIGINS` no default (fail-fast).

### Open questions — unresolved (carry to development blocks)

- [inquisidor] B16: `confidence` in `ReviewQueueItem` — `'high' | 'low'` or float 0.0–1.0?
- [RESOLVED B17] `PUT /api/routing-rules/reorder` — `{ ordered_ids: string[] }` (index 0 → priority 1)
- [RESOLVED B18] `SQLAlchemyModelFactory` → plain `factory.Factory` + manual DB insert; DB isolation via UUID-suffixed identifiers + cleanup
- [sentinel] B18-B19: `CELERY_TASK_ALWAYS_EAGER` security diffs, `PiiSanitizingFilter` false positives, `.env.example` parity

---

## 2026-02-20 -- Security findings (carry forward) [Lorekeeper]

- WARNING-01: `LLM_ALLOWED_MODELS` allowlist needed (B04/B14)
- WARNING-02: `DRAFT_ORG_SYSTEM_PROMPT` max-length + startup warning (B11)
- WARNING-B02-01: Timing oracle in login — bcrypt not called for nonexistent users (B02)

---

## 2026-03-02 -- Blocks 14-15 (consolidated) [Lorekeeper]

- B14: `cast(int, row._mapping["count"])` for `func.count().label()`; `FewShotExample` slugs are strings not FKs; `SystemLog.email_id` NOT a FK
- B15: `configureClient` pattern avoids circular dep AuthContext↔API client; refresh interceptor queues 401s; `getTokenExpSeconds()` decodes JWT `exp`
- Spec amendments B14-B19: 96 deltas across 6 specs (commit `2824e60`)

---

## 2026-03-02 -- Block 16: Frontend Core — Email Browser, Review Queue, Classification Config [Lorekeeper]

### Key discoveries

- `EmailState` API values are UPPERCASE (`CLASSIFIED`, `ROUTED`, etc.) — `values_callable` stores `.value` in PostgreSQL. Other enums (DraftStatus, ClassificationConfidence) use lowercase.
- Hook CWD issue recurred: `cd frontend && npm install` permanently changes Bash CWD; hook stubs needed again (same fix as B15)
- TanStack Query wrapper required for hook tests: `createWrapper()` factory with `retry: false` prevents cache bleed and retries
- `.tsx` extension required for any test file that renders JSX (even just as QueryClientProvider wrapper) — esbuild rejects JSX in `.ts`
- dnd-kit drag not testable in jsdom — CategoryList tests focus on CRUD + toggle; drag tested manually
- `vi.useFakeTimers({ shouldAdvanceTime: true })` required for `userEvent` debounce tests — plain `useFakeTimers()` causes 5000ms timeouts
- `screen.getByRole("dialog")` needed to scope assertions when text appears in both list item and modal

### Block 16 final results

- 115 new tests (37 hook + 78 component/page), 142 total frontend (up from 27 B15)
- tsc 0 errors, ESLint 0 errors, vite build 116KB gzip, 142/142 pass
- Architecture: 0 `any`, 0 manual type duplication, all types from generated schema

---

## 2026-03-02 -- Block 17: FE Remaining — Routing, Analytics, Integrations, Overview, Logs [agent]

### What was delivered

- 5 API modules (routing-rules, analytics, health, integrations, logs), 5 hooks, 10 components, 2 new pages + 3 stub replacements + router update
- 1081 CSS lines appended (13 BEM blocks), 12 test files (200 new tests)
- 342 total tests pass (200 new + 142 existing), tsc 0, ESLint 0, vite build success (235KB gzip)

### Key discoveries

- recharts SVG cannot resolve CSS custom properties — Chart.tsx DEFAULT_COLORS must be hex values
- `vi.stubGlobal("URL", {...})` breaks jsdom DOM rendering — use `Object.defineProperty(URL, "createObjectURL", {...})` instead
- `getAllByText` needed when text appears in both StatCard and detail sections (AnalyticsPage, OverviewPage)
- Log level badges: use `document.querySelector('[aria-label="Level: INFO"]')` to avoid collision with `<option>` text
- Chart mock in page tests: named export `{ Chart: ... }` since Chart.tsx uses `export function Chart`
- `@typescript-eslint/no-unused-vars` v8: `_prefix` convention NOT allowed by default — use no-param body arrows instead
- Hook CWD issue (3rd occurrence: B15, B16, B17) — graduated to CLAUDE.md

---

## 2026-03-02 -- Block 18: E2E Test Suite (consolidated) [backend-worker]

### What was delivered

- 18 E2E tests across 5 files: pipeline (5), partial failure (4), draft workflow (2), config changes (3), API integration (4)
- `tests/factories.py` — 9 factory-boy factories with corrected field names per B18 amendments
- `tests/e2e/conftest.py` — 4 mock adapter classes (ABC-verified), DB fixtures, helper functions
- `--run-e2e` flag + `e2e` marker; all 18 tests skip without flag, 1504 existing tests unaffected

### Architecture decisions

- Pipeline E2E: SYNC functions + `asyncio.run()` for DB (Celery uses `asyncio.run()` internally; nesting causes RuntimeError)
- API integration: ASYNC functions with httpx AsyncClient + `get_async_db` override (no Celery tasks executed)
- `task.run()` + patch NEXT task's `.delay()` prevents nested event loops
- `_make_test_settings()` pattern: `real_settings.model_dump()` for mock override; `_make_session_factory()` with NullPool
- `require_draft_access` access control: Admin all, Reviewer own (`draft.reviewer_id == current_user.id`); reviewer tests must set `reviewer_id`

### Key discoveries — service error handling

- `CRMSyncService._do_contact_lookup` silences `CRMConnectionError` → patch `HubSpotAdapter.connect()` NOT `lookup_contact` for failure test
- `DraftGenerationService.generate()` silences `LLMConnectionError` → DRAFT_FAILED state, no Retry
- `RoutingService._dispatch_rule_actions` silences `ChannelDeliveryError` per-action → ROUTING_FAILED, no Retry
- `ClassificationService._call_llm_or_fail` re-raises `LLMAdapterError` → Retry raised at task level
- `DraftStatus` changes do NOT touch `EmailState` — email stays `DRAFT_GENERATED`

---
