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

- [B00] `SanitizedText = NewType(...)` — branded type. PII policy: email_id only in logs.
- [B01] EmailState/ActionCategory/TypeCategory as PostgreSQL ENUMs + DB tables. `alembic.ini` URL never set (Settings override). `transition_to()` outside try/except — failure is a logic bug.
- [B02] Refresh tokens: opaque UUIDs in Redis (not JWTs). `redis_client.py` in `src/adapters/`.
- [B03] Deduplication in calling service, not adapter. `test_connection()` silences all errors (health-check semantics).
- [B04] LLM parser: pure local computation, 7 output shapes, conditionals only. `LLM_FALLBACK_MODEL` must differ from classify model. `OutputParseError` never re-raised to caller.
- [B05] `SlackApiError` classified by `response["error"]` string (Slack returns 200 OK on errors). `SlackBlockKitFormatter` is pure local computation.
- [B06] `ActivityId`/`LeadId` as NewType. Duplicate contacts: most recent by `createdate`. Snippet truncated by calling SERVICE not adapter.
- [B07] `IngestionResult` frozen dataclass. Lock key per account_id. Two independent commits per email (FETCHED then SANITIZED).
- [B08] ClassificationResult naming collision: alias `AdapterClassificationResult`. Heuristics NEVER override LLM — only lower confidence. PromptBuilder/HeuristicClassifier: 0 try/except (enforced by grep in exit conditions).
- [B09] `dispatch_id` = SHA-256[:32] of `"{email_id}:{rule_id}:{channel}:{destination}"`. Unrouted → ROUTED (not ROUTING_FAILED). Each RoutingAction has own `db.commit()`.
- [B10] `CRMAuthError`: no retry. Idempotency check via DB, never CRM API. `dict[str, str]` for `field_updates` is documented exception to no-dict rule.
- [B11] `DraftContextBuilder.build()` never raises. `body_snippet` name encodes truncation precondition. Gmail push failure → `DRAFT_GENERATED` (not `DRAFT_FAILED`). Commit before push (D13).
- [B12] Chain bifurcation inside `route_task` — conditional `.delay()` after routing. Dual lock: scheduler (producer) + IngestionService (consumer). `run_pipeline` NOT a Celery task. Broker Redis/0, backend Redis/1, `CELERY_RESULT_EXPIRES=3600s`.
- [B13] Routers: zero try/except. Domain exceptions → `exception_handlers.py`. Health check: asyncio.gather, 200ms timeout, always HTTP 200. `API_CORS_ALLOWED_ORIGINS` never hardcoded.
- [B14] Category DELETE: explicit count query, never IntegrityError. `ConnectionTestResult` always HTTP 200. Analytics: `GROUP BY + func.count()` in SQL, 0 Python loops. CSV: `AsyncGenerator` + StreamingResponse.
- [B15] Access token in `useRef` (memory only). httpOnly cookie for refresh. `openapi.json` committed. ESLint `no-explicit-any: error`. CSS vars on `[data-theme="dark"]`.
- [B16] All types from `types/generated/`. Review Queue: "Low Confidence" vs "Pending Drafts" — distinct concepts, not collapsed. Hooks encapsulate SWR/TanStack choice.
- [B17] `Chart.tsx` encapsulates ALL recharts imports. `ChartDataPoint` transformation in Page component. Rules sorted by `priority` in hook.
- [B18] alignment-chart categorization enforced as exit criteria. `CELERY_TASK_ALWAYS_EAGER=True` for E2E. Mocked adapters implement ABCs (Cat 10). `pytest --cov-fail-under=70`.
- [B19] `CorrelationIdContext` via contextvars. Docker images pinned to patch. `CORS_ORIGINS` no default (fail-fast). Adapter guide: 5-step pattern.
- [tooling] Async Alembic: `run_sync` pattern. `gh` CLI not installed — WebFetch fallback. mypy before ruff (type errors cause ruff false positives).
- [security] Agent context boundary confusion: always verify security findings with hex dump before acting.

### Open questions — unresolved (carry to development blocks)

- [inquisidor] B02: TypedDict vs dataclass for TokenPayload
- [inquisidor] B07: asyncio.Lock vs Redis SET NX EX for poll lock (Redis correct for multi-worker)
- [inquisidor] B08: `tuple[str, str]` vs named dataclass for `build_classify_prompt()` return
- [inquisidor] B09: `frozenset[str]` vs `set[str]` for VIP senders
- [inquisidor] B10: `dict[str, str]` vs `list[FieldUpdate]` for field_updates
- [inquisidor] B11: `list[str]` vs `list[InteractionRecord]` for recent_interactions
- [inquisidor] B12: conditional `.delay()` in `route_task` vs `chord`/`group` — race conditions?
- [inquisidor] B13: `PaginatedResponse[T]` Generic BaseModel + Pydantic v2 + `model_rebuild()`?
- [inquisidor] B16: `confidence` in `ReviewQueueItem` — `'high' | 'low'` or float 0.0–1.0?
- [backend-worker] B17: `PUT /api/routing-rules/reorder` — `string[]` or `{ id, priority }[]`?
- [inquisidor] B18: `SQLAlchemyModelFactory` async pattern
- [inquisidor] B18: DB isolation E2E with Celery eager
- [sentinel] B18: `CELERY_TASK_ALWAYS_EAGER=True` — security behavior differences vs real worker?
- [sentinel] B19: `PiiSanitizingFilter` — false positive risk?
- [inquisidor] B19: `.env.example` parity test approach

---

## 2026-02-20 -- Phase 4 close: STATUS + CHANGELOG + SCRATCHPAD [Lorekeeper]

### What worked well

- Reading all 18 specs before security review (Sentinel pattern) produces comprehensive cross-block analysis
- Pre-mortem 10 categories provide systematic fragility coverage — D1-D18 directive table useful for tracking
- Parallel spec-writing (backend-worker B00-B19, frontend-worker B15-B17, Sentinel review) reduced elapsed time significantly

### Security findings from Sentinel review

- [security] WARNING-01: LLM model string redirect via `PUT /api/integrations/llm` — mitigation: `LLM_ALLOWED_MODELS` allowlist
- [security] WARNING-02: `DRAFT_ORG_SYSTEM_PROMPT` bypasses prompt injection defenses — add max-length + startup warning
- [security] WARNING-03: `next(c for c in categories if c.is_fallback)` crashes StopIteration if no fallback — use `next(..., None)`
- [security] D16 discrepancy: specs implement 5-layer defense (not 4 as in DECISIONS.md) — pending DECISIONS.md update

### Phase 4 verification status

- [x] 20 spec files in docs/specs/ (block-00 through block-19)
- [x] Sentinel security review complete: 0 critical, 3 warnings, 5 suggestions
- [x] STATUS.md updated: Phase 4 marked complete, current phase = Development Blocks
- [x] CHANGELOG-DEV.md appended with Phase 4 entry
- [x] D16 discrepancy in DECISIONS.md — corrected to 5-layer (Sec 11.2 + Sec 4.5)
- [ ] D15 directive (version pinning) minimally covered — address in block-00 pyproject.toml

---

## 2026-02-20 -- Block 00 scaffolding [backend-worker]

### Mistakes made

- [backend-worker] `setuptools.backends._legacy:_Backend` is wrong build-backend — correct is `setuptools.build_meta`
- [backend-worker] `where = ["src"]` in setuptools packages.find discovers packages WITHOUT `src.` prefix. For `from src.core.config import Settings` to work, need `where = ["."]` + `include = ["src*"]`
- [backend-worker] mypy `type: ignore[return-value]` wrong code — structlog returns `Any`, correct code is `type: ignore[no-any-return]`

### What worked well

- Spec-verbatim config.py: 0 iterations needed, all 33 tests passed first try
- Frontend agent (parallel): delivered comprehensive scaffold in background while backend progressed — auth context, theme, routing, API layer, all quality gates passed
- ruff format --check catches formatting drift immediately

### Decisions made

- [B00] `src/api/main.py` minimal health endpoint added (not in spec) — required for Docker health check exit criterion
- [B00] `conftest.py` at root sets env defaults — tests work without `.env` in CI
- [B00] Docker worker/scheduler: no health check at B00 (celery_app doesn't exist) — show as `running`
- [B00] Python 3.14 on host; Docker uses 3.12-slim (spec target)

---

## 2026-02-20 -- B15 Frontend scaffold [frontend-worker]

### What worked well

- Vite 7 + React 19 + React Router 7 scaffold works cleanly — all APIs compatible with spec (createBrowserRouter, RouterProvider, NavLink still identical interface)
- TypeScript strict mode already active in Vite scaffold (tsconfig.app.json has `"strict": true`) — no changes needed
- Parallel file writes (styles + contexts + components + pages) efficient
- `npm run build` produces gzip 107.97 KB initial chunk — well under 200 KB spec limit

### Decisions made

- [B15] Vite 7 uses flat ESLint config (eslint.config.js) not .eslintrc.cjs — works equivalently, kept as-is
- [B15] `react-refresh/only-export-components` downgraded to `warn` for context files — Provider+hook co-location is universal React pattern, false positive as error
- [B15] Type aliases `type X = components["schemas"]["X"]` in api/auth.ts are D4-compliant — local aliases pointing to generated types, not manual re-implementation
- [B15] `src/types/generated/api.ts` ships as placeholder with correct schema shape until backend is live; `npm run generate-types` overwrites it
- [B15] `configureClient()` called inside AuthProvider useEffect to avoid circular dependency between api/client.ts and AuthContext.tsx

### Tooling notes

- Node 24.13.0, npm 11.6.2 on Windows 11 bash shell
- `npm audit` reports vulnerabilities in transitive deps — standard for new Vite scaffold, does not block dev
- `@types/node` installed automatically with tsx devDep (needed for vite.config.ts path resolution)

### Quality gates passed

- [x] `npm run typecheck` — 0 errors
- [x] `npm run lint` — 0 errors (3 warnings, expected)
- [x] `npm run build` — bundle: 107.97 KB gzip initial chunk
- [x] No hardcoded colors in components.css
- [x] No access token storage in localStorage/sessionStorage
- [x] No manual API type duplication (D4 compliant)
