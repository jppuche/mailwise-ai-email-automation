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

### Standing architecture decisions

- [B15-B17] Frontend: access+refresh tokens in `useRef`, ESLint `no-explicit-any`, CSS vars `[data-theme="dark"]`, types from `types/generated/`.
- [B18] alignment-chart enforced as exit criteria. `CELERY_TASK_ALWAYS_EAGER=True` for E2E.

### Open questions — unresolved

- [inquisidor] B16: `confidence` in `ReviewQueueItem` — `'high' | 'low'` or float 0.0–1.0?

---

## 2026-02-20 -- Security findings (carry forward) [Lorekeeper]

- WARNING-01: `LLM_ALLOWED_MODELS` allowlist needed (B04/B14)
- WARNING-02: `DRAFT_ORG_SYSTEM_PROMPT` max-length + startup warning (B11)
- WARNING-B02-01: Timing oracle in login — bcrypt not called for nonexistent users (B02)

---

## 2026-03-02 -- Blocks 14-17 (consolidated) [Lorekeeper]

- B14: `cast(int, row._mapping["count"])` for `func.count().label()`; `FewShotExample` slugs are strings not FKs; `SystemLog.email_id` NOT a FK
- B15: `configureClient` pattern avoids circular dep AuthContext↔API client; refresh interceptor queues 401s; `getTokenExpSeconds()` decodes JWT `exp`
- B16: `EmailState` API values UPPERCASE; `.tsx` extension required for JSX test files; `vi.useFakeTimers({ shouldAdvanceTime: true })` for debounce tests
- B17: recharts cannot resolve CSS vars — hex values only in Chart.tsx; `vi.stubGlobal("URL",...)` breaks jsdom — use `Object.defineProperty` instead
- Spec amendments B14-B19: 96 deltas across 6 specs (commit `2824e60`)

---

## 2026-03-02 -- Block 18: E2E Test Suite (consolidated) [backend-worker]

- Pipeline E2E: SYNC functions + `asyncio.run()` — Celery uses `asyncio.run()` internally; nesting causes RuntimeError
- API integration E2E: ASYNC (httpx AsyncClient + `get_async_db` override) — no Celery tasks executed
- `task.run()` + patch NEXT task's `.delay()` prevents nested event loops
- `require_draft_access`: Admin all, Reviewer own (`draft.reviewer_id == current_user.id`)
- Service error silencing: CRMSyncService silences `CRMConnectionError`; DraftGenService silences `LLMConnectionError`; RoutingService silences `ChannelDeliveryError`; ClassificationService re-raises `LLMAdapterError`

---

## 2026-03-01 -- Blocks 18-19 (consolidated) [Lorekeeper]

- B18: 18 E2E tests, 9 factories; pipeline E2E sync, API E2E async; `task.run()` + patch next `.delay()`
- B19: structured JSON logging (CorrelationIdFilter + PiiSanitizingFilter), Docker health checks all 6 services, `.env.example` 60+ fields, deployment.md + adapter-guide.md, 40 infrastructure tests
- Docker: scheduler cmd `python -m src.scheduler`; API health `/api/v1/health`; Alpine uses `wget` not `curl`
- Admin creation via Python REPL (no CLI module) — documented in deployment.md
- structlog processor signatures: `MutableMapping[str, Any]` — graduated to CLAUDE.md
- capsys + structlog testing: call `configure_logging()` inside test body — graduated to CLAUDE.md
- pytest marks: register in `pyproject.toml [tool.pytest.ini_options] markers` not `pytest_configure` hook

