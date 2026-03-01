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

### Open questions — unresolved (carry to development blocks)

- [inquisidor] B07: asyncio.Lock vs Redis SET NX EX for poll lock (Redis correct for multi-worker)
- [RESOLVED] B08: `tuple[str, str]` for `build_classify_prompt()` return (simple, spec says tuple)
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

### What worked well

- 4 parallel test agents: schemas (46) + prompt_builder (30) + heuristics (52) + service (47) = 175 new tests
- Only 7 batch test failures from agents (MagicMock vs Pydantic) — quick fix
- All grep enforcement checks passed on first try (0 try/except in pure modules, alias present)
- 865 total tests, 0 regressions
