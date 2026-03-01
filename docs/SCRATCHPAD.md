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

- [B13] Routers: zero try/except. Domain exceptions → `exception_handlers.py`. Health check: asyncio.gather, 200ms timeout, always HTTP 200.
- [B14] Category DELETE: explicit count query, never IntegrityError. Analytics: `GROUP BY + func.count()`, 0 Python loops. CSV: `AsyncGenerator` + StreamingResponse.
- [B15-B17] Frontend: access token in `useRef`, httpOnly cookie refresh, `openapi.json` committed, ESLint `no-explicit-any`, CSS vars `[data-theme="dark"]`, types from `types/generated/`.
- [B18] alignment-chart enforced as exit criteria. `CELERY_TASK_ALWAYS_EAGER=True` for E2E. `pytest --cov-fail-under=70`.
- [B19] `CorrelationIdContext` via contextvars. Docker images pinned to patch. `CORS_ORIGINS` no default (fail-fast).

### Open questions — unresolved (carry to development blocks)

- [inquisidor] B13: `PaginatedResponse[T]` Generic BaseModel + Pydantic v2 + `model_rebuild()`?
- [inquisidor] B16: `confidence` in `ReviewQueueItem` — `'high' | 'low'` or float 0.0–1.0?
- [backend-worker] B17: `PUT /api/routing-rules/reorder` — `string[]` or `{ id, priority }[]`?
- [inquisidor] B18: `SQLAlchemyModelFactory` async pattern, DB isolation E2E with Celery eager
- [sentinel] B18-B19: `CELERY_TASK_ALWAYS_EAGER` security diffs, `PiiSanitizingFilter` false positives, `.env.example` parity

---

## 2026-02-20 -- Security findings (carry forward) [Lorekeeper]

- WARNING-01: `LLM_ALLOWED_MODELS` allowlist needed (B04/B14)
- WARNING-02: `DRAFT_ORG_SYSTEM_PROMPT` max-length + startup warning (B11)
- WARNING-03: `next(..., None)` for fallback category (B08) — RESOLVED in B08
- WARNING-B02-01: Timing oracle in login — bcrypt not called for nonexistent users (B02)

---

## 2026-02-21 -- Blocks 02-07 (consolidated) [Lorekeeper]

- B02: `HTTPBearer(auto_error=False)` for custom 401; Sentinel PASS
- B03: `Credentials()` needs `# type: ignore[no-untyped-call]`
- B04: patch at import site for litellm mocks; keyword args for exception constructors
- B05: `dict[str, object]` not `Any` (D1); `contextlib.suppress` for Retry-After
- B06: `connected_adapter` fixture bypasses `connect()` by setting `_connected = True` directly
- B07: Redis SET NX EX for poll lock; two commits per email (FETCHED+SANITIZED)

---

## 2026-02-28 -- Blocks 08-11 (consolidated) [Lorekeeper]

- B08: `raw_llm_output` adapter→ORM needs `json.loads()` with fallback; 175 tests
- B09: `AsyncMock` for `AsyncSession` warns on sync methods — mock limitation; 135 tests
- B10: `overall_success` short-circuit for "lookup None, no auto-create"; 57 tests
- B11: Schema types `received_at: str` (ISO 8601), `confidence: str` ("high"/"low"); 138 tests
- B11: D13 enforced — draft committed before Gmail push. Gmail push failure → DRAFT_GENERATED

---

## 2026-03-01 -- Block 12 Pipeline & Scheduler [Lorekeeper]

### Implementation notes

- RESOLVED: conditional `.delay()` inside `route_task` (not `chord`/`group`) — no race conditions
- Chain: ingest→classify→route→crm_sync→draft. Each task calls `next.delay()` after commit
- `route_task` bifurcation: checks `RoutingResult.was_routed` → enqueues `pipeline_crm_sync_task`
- `pipeline_crm_sync_task` checks email state post-sync → enqueues `pipeline_draft_task` if CRM_SYNCED
- CRM sync + draft delegate to existing `_run_crm_sync` / `_run_draft_generation` async functions
- `run_pipeline(email_id)` is NOT a Celery task — plain function, enqueues `classify_task.delay()`
- APScheduler `UTC` from `datetime.UTC` (not `pytz.utc`) avoids `types-pytz` stub dependency
- `contextlib.suppress(Exception)` for Redis lock delete on enqueue failure (ruff SIM105)
- `dict[str, ChannelAdapter]` not `dict[str, SlackAdapter]` — dict invariance in mypy
- [GRADUATED] Celery decorator typing, task.run(), retry testing patterns → CLAUDE.md
- 172 new tests (80+29+20+12+31), 1367 total, 0 regressions, mypy 0, ruff 0

### Test patterns

- `task.run(...)` bypasses Celery dispatch — already bound, no mock `self` needed
- Patch `asyncio.run` for outer wrappers; patch individual async fns for inner tests
- `_run_draft_generation` is deferred import INSIDE task — must patch asyncio level
- `_close_coro_and_return` helper as `asyncio.run` side_effect suppresses coroutine warnings
