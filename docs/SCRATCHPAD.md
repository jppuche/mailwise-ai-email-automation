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

- [inquisidor] B16: `confidence` in `ReviewQueueItem` — `'high' | 'low'` or float 0.0–1.0?
- [backend-worker] B17: `PUT /api/routing-rules/reorder` — `string[]` or `{ id, priority }[]`?
- [inquisidor] B18: `SQLAlchemyModelFactory` async pattern, DB isolation E2E with Celery eager
- [sentinel] B18-B19: `CELERY_TASK_ALWAYS_EAGER` security diffs, `PiiSanitizingFilter` false positives, `.env.example` parity

---

## 2026-02-20 -- Security findings (carry forward) [Lorekeeper]

- WARNING-01: `LLM_ALLOWED_MODELS` allowlist needed (B04/B14)
- WARNING-02: `DRAFT_ORG_SYSTEM_PROMPT` max-length + startup warning (B11)
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

---

## 2026-03-01 -- Block 13 Phase 1+2: schemas, exceptions, deps [backend-worker]

### Implementation notes

- RESOLVED: `PaginatedResponse[T]` — use PEP 695 syntax `class PaginatedResponse[T](BaseModel)` not `Generic[T]`. ruff UP046 rejects `Generic` subclass on py312 target. Pydantic v2 supports PEP 695 natively (verified).
- `NotFoundError` + `DuplicateResourceError` added to `src/core/exceptions.py`
- `api_health_adapter_timeout_ms` + `app_version` added to `Settings` (Cat 8)
- `src/api/exception_handlers.py` created — 7 handlers, zero try/except (domain exceptions propagate from routers)
- `src/api/deps.py` extended: `require_draft_access` (Admin sees all, Reviewer sees own) + `get_routing_service` (DI factory with lazy Slack connect)
- `get_routing_service` uses deferred imports inside the function body — avoids circular imports at module load time
- Channel adapter import: `from src.adapters.channel.base import ChannelAdapter` (not `.abstract`) — file is named `base.py`
- mypy 0, ruff 0 on all 8 new/modified files

---

## 2026-03-01 -- Block 13 API unit tests: health, auth, pagination [Inquisidor]

### Implementation notes

- [GRADUATED] PaginatedResponse[T] PEP 695 syntax, API unit test fixtures pattern, asyncio_mode auto, Docker Desktop requirement → CLAUDE.md
- Health router tests: patch `src.api.routers.health._check_db` / `_check_redis` at module path
- Auth path tests: client fixture (no DB override) → non-404 assertion; 422 validation tests don't need DB
- 3 files: test_health_router.py (9), test_auth_router.py (10), test_pagination.py (14) = 33 tests

---

## 2026-03-02 -- Block 13 test fixes + completion [agent]

### Test fixes

- `RoutingRuleResponse` Pydantic error: `created_at`/`updated_at` None — mock `db.refresh` with `side_effect` that sets timestamps (ORM `server_default=func.now()` not triggered without real DB)
- `DraftDetailResponse.classification` is inside `email` object, not root — test should assert `body["email"]["classification"]` not `body["classification"]`
- `scalar_one_or_none()` vs `scalar_one()` mock mismatch: endpoint calls `scalar_one_or_none()` for `func.max()`, test was using `_scalar_one_result()` helper which sets `scalar_one()` — must use `_scalar_result()` which sets `scalar_one_or_none()`
- Docker Desktop must be running for `import sqlalchemy` on Python 3.14 — engines hang without TCP connectivity

### Block 13 final results

- 110 new API tests, 1477 total (110 new + 1367 existing), 0 regressions
- mypy 0, ruff 0 on all B13 files (src/api/ + tests/api/)
- Architecture: zero try/except in routers, no dict[str, Any] in schemas

---

## 2026-03-02 -- Block 14 session start: baseline health check [backend-worker]

### Baseline verified

- Docker: db (postgres:16) + redis:7 healthy on ports 5432/6379
- pytest: 1477 passed, 58 skipped, 28 warnings — 0 failures, 0 errors
- mypy: 0 issues in 84 source files
- ruff: 0 issues in src/
- 28 RuntimeWarning (coroutine never awaited) — pre-existing, from B12 mock pattern for async Celery task internals; non-blocking
