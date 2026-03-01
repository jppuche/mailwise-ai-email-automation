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

- [B12] Chain bifurcation inside `route_task` — conditional `.delay()` after routing. Dual lock: scheduler (producer) + IngestionService (consumer). `run_pipeline` NOT a Celery task. Broker Redis/0, backend Redis/1, `CELERY_RESULT_EXPIRES=3600s`.
- [B13] Routers: zero try/except. Domain exceptions → `exception_handlers.py`. Health check: asyncio.gather, 200ms timeout, always HTTP 200.
- [B14] Category DELETE: explicit count query, never IntegrityError. Analytics: `GROUP BY + func.count()`, 0 Python loops. CSV: `AsyncGenerator` + StreamingResponse.
- [B15-B17] Frontend: access token in `useRef`, httpOnly cookie refresh, `openapi.json` committed, ESLint `no-explicit-any`, CSS vars `[data-theme="dark"]`, types from `types/generated/`.
- [B18] alignment-chart enforced as exit criteria. `CELERY_TASK_ALWAYS_EAGER=True` for E2E. `pytest --cov-fail-under=70`.
- [B19] `CorrelationIdContext` via contextvars. Docker images pinned to patch. `CORS_ORIGINS` no default (fail-fast).

### Open questions — unresolved (carry to development blocks)

- [inquisidor] B12: conditional `.delay()` in `route_task` vs `chord`/`group` — race conditions?
- [inquisidor] B13: `PaginatedResponse[T]` Generic BaseModel + Pydantic v2 + `model_rebuild()`?
- [inquisidor] B16: `confidence` in `ReviewQueueItem` — `'high' | 'low'` or float 0.0–1.0?
- [backend-worker] B17: `PUT /api/routing-rules/reorder` — `string[]` or `{ id, priority }[]`?
- [inquisidor] B18: `SQLAlchemyModelFactory` async pattern, DB isolation E2E with Celery eager
- [sentinel] B18-B19: `CELERY_TASK_ALWAYS_EAGER` security diffs, `PiiSanitizingFilter` false positives, `.env.example` parity

---

## 2026-02-20 -- Security findings (carry forward) [Lorekeeper]

- WARNING-01: `LLM_ALLOWED_MODELS` allowlist needed (B04/B14)
- WARNING-02: `DRAFT_ORG_SYSTEM_PROMPT` max-length + startup warning (B11)
- WARNING-03: `next(..., None)` for fallback category (B08)
- WARNING-B02-01: Timing oracle in login — bcrypt not called for nonexistent users (B02)

---

## 2026-02-21 -- Blocks 02-05 (consolidated) [Lorekeeper]

- B02: `HTTPBearer(auto_error=False)` for custom 401; Sentinel PASS
- B03: `Credentials()` needs `# type: ignore[no-untyped-call]`
- B04: patch at import site for litellm mocks; keyword args for exception constructors
- B05: `dict[str, object]` not `Any` (D1); `contextlib.suppress` for Retry-After; module-level `frozenset` for error codes (Cat 3)

---

## 2026-02-28 -- Blocks 06-07 (consolidated) [Lorekeeper]

- B06: `connected_adapter` fixture bypasses `connect()` by setting `_connected = True` directly
- B07: Redis SET NX EX for poll lock; two commits per email (FETCHED+SANITIZED)
- B07: `mapped_column(default=uuid.uuid4)` is INSERT-time only — explicit `id=uuid.uuid4()` in constructor
- Handoff docs contain all info needed — minimal codebase exploration required

---

## 2026-02-28 -- Block 08 Classification Service [backend-worker]

### Implementation notes

- `raw_llm_output`: adapter returns `str`, ORM wants `dict` (JSONB) — `json.loads()` with fallback to `{"raw_response": str}`
- mypy re-use of loop var name across typed loops: `for cat in action_cats` then `for cat in type_cats` → mypy error. Use different var names (`cat`/`tcat`)
- Batch tests: `MagicMock()` in `list[ClassificationServiceResult]` fails Pydantic validation — must use real instances
- Heuristic hints should use actual DB seed slugs for meaningful disagreement detection (not spec's non-matching slugs)
- `_find_fallback`: `next((c for c if c.is_fallback), None)` with explicit `CategoryNotFoundError` (WARNING-03 resolved)

- B08: 175 tests (4 parallel agents), B09: 135 tests (5 parallel agents) — 0 regressions both

---

## 2026-02-28 -- Block 09 Routing Service (consolidated) [Lorekeeper]

- `AsyncMock` for `AsyncSession` warns on `db.add()` (sync method) — mock limitation, not a bug
- `transition_to` side_effect on mock mutates `email.state` → real assertion after routing

---

## 2026-02-28 -- Block 10 CRM Sync Service (Agent B) [backend-worker]

- `overall_success = contact_id is not None and _compute_overall_success(ops)` — short-circuit for "lookup None, no auto-create"
- `_do_contact_create` nested try/except: specific (CRMAuth/RateLimit re-raise, DuplicateContactError re-lookup) before generic CRMAdapterError
- `_make_db_no_record()` uses `return_value` (not `side_effect`) — only one `db.execute` call (idempotency check)
- [GRADUATED] `ruff B904: raise ... from exc`, `server_default` vs explicit datetime → CLAUDE.md Learned Patterns
- 3 parallel agents: 57 new tests (28+19+10), 1057 total, 0 regressions

---

## 2026-03-01 -- Block 11 commit + Block 12 handoff [Lorekeeper]

- B11 committed with 138 tests, 1195 total, 0 regressions
- B12 handoff doc created from spec

---

## 2026-02-28 -- Block 11 Draft Generation Service [Lorekeeper]

### Implementation notes

- Schema types: `received_at: str` (ISO 8601) and `confidence: str` ("high"/"low") — agents used datetime/float, required test fixes
- `email_adapter.create_draft()` is sync → wrap with `asyncio.to_thread()` in async service
- D13 enforced: draft committed before Gmail push. Gmail push failure → DRAFT_GENERATED (not DRAFT_FAILED)
- `LLMRateLimitError` is the ONLY exception re-raised from service → Celery task retries
- Task deferred imports: sys.modules injection (B10 pattern), real Pydantic classes for schema construction
- `body_plain` read once in task, truncated to `body_snippet`, never logged (privacy Sec 6.5)
- 4 parallel agents: 39 (schemas) + 57 (context builder) + 15 (service) + 14 (task) = 125 → 138 B11 tests
- 1195 total tests, 0 regressions, mypy 0, ruff 0
