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

## 2026-02-20 -- Block 00 + Phase 4 close (consolidated) [Lorekeeper]

### Security findings (carry forward — implement in respective blocks)

- WARNING-01: `LLM_ALLOWED_MODELS` allowlist needed (B04/B14)
- WARNING-02: `DRAFT_ORG_SYSTEM_PROMPT` max-length + startup warning (B11)
- WARNING-03: `next(..., None)` for fallback category (B08)
- WARNING-B02-01: Timing oracle in login — bcrypt not called for nonexistent users (B02)

### B00 decisions (now in code)

- `src/api/main.py` minimal `/health` — Docker health check dependency
- `conftest.py` at root: `os.environ.setdefault()` for CI without `.env`
- Python 3.14 on host; Docker 3.12-slim. Worker/scheduler exit expected until B12.

### B15 decisions (now in code)

- Vite 7 flat ESLint config, `react-refresh` warn for contexts, placeholder `api.ts`
- `configureClient()` in AuthProvider useEffect avoids circular dep
- Bundle: 107.97 KB gzip (limit 200 KB). Node 24.13.0, npm 11.6.2.

---

## 2026-02-20 -- Block 01 (consolidated) [backend-worker + Inquisidor]

- `sys.executable -m alembic` on Windows — `alembic` not in PATH.
- Integration tests: `--run-integration` flag, Alembic API for in-process migrations.

---

## 2026-02-21 -- Block 02 Auth & Users (consolidated) [Lorekeeper]

### B02 decisions (now in code)

- `HTTPBearer(auto_error=False)` for custom 401 (FastAPI default returns 403)
- `override_db` fixture: NullPool engine + `app.dependency_overrides[get_async_db]`
- `admin_user`/`reviewer_user` fixtures: separate NullPool engines to avoid session entanglement
- Test-only RBAC endpoints registered on `app` at module load; `# noqa: B008` on Depends defaults
- 231 total tests (13u security, 19u schemas, 17i endpoints, 7i redis)

### B02 Sentinel review: PASS (0 CRITICAL, 1 WARNING)

- WARNING-B02-01: Timing oracle in login (mitigated: single-tenant + future rate limiting)
- Suggestions deferred: password max_length, jwt_algorithm Literal, cors_origins default

---

## 2026-02-21 -- Block 03 Gmail Adapter [backend-worker]

### B03 decisions (now in code)

- `DraftId = NewType("DraftId", str)` — follows `SanitizedText` pattern from sanitizer.py
- Adapter `RecipientData` omits `type` field (implicit in list: to_addresses vs cc_addresses)
- Adapter `AttachmentData` includes `attachment_id` (matches ORM, avoids data loss at boundary)
- `_service: Any | None` — untyped SDK stays private, `assert self._service is not None` after `_ensure_connected()` for mypy
- `timezone.utc` → `datetime.UTC` alias required by ruff UP017
- `except (KeyError, ValueError, TypeError)` for per-message parse isolation (not bare Exception)
- `# noqa: BLE001` on `test_connection()` — only bare except in adapter (health-check semantics)
- google modules in mypy `ignore_missing_imports` — no `type: ignore[import-untyped]` needed on imports
- `Credentials()` constructor needs `# type: ignore[no-untyped-call]`
- 85 new tests (18u schemas, 23u parsing, 15 contract, 29u adapter), 258 total passing

---

## 2026-02-21 -- Block 04 LLM Adapter (consolidated) [backend-worker + Lorekeeper]

### B04 decisions (now in code)

- `import litellm.exceptions as litellm_exc` — mypy-compatible path; `litellm.RateLimitError` direct access triggers `attr-defined` even with `ignore_missing_imports = true` for `litellm.*`
- `litellm_exc.Timeout` (not `litellm_exc.TimeoutError`) — litellm names it `Timeout`
- `litellm.api_key` / `litellm.api_base` set as globals in `__init__` (LiteLLM uses global config)
- `_safe_json_loads` is the single D8 exception: `json.loads` has no conditional alternative — documented with inline comment
- `_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}")` — flat brace match sufficient for classification JSON
- Regex constants compiled at module level (`_THINKING_TAG_RE`, `_MARKDOWN_FENCE_RE`, `_JSON_OBJECT_RE`) — not inside functions
- `ClassifyOptions.allowed_actions/allowed_types`: `Field(min_length=1)` enforces non-empty list (D1)
- `ConnectionTestResult.error_detail` (not `error`) — avoids naming collision with email adapter schema
- Fallback path logs `llm_parse_fallback` with `raw_output_preview=raw_output[:200]` (PII-safe)
- Mock target: `@patch("src.adapters.llm.litellm_adapter.litellm.acompletion")` — patch at import site
- Post-construction mutation bypasses `Field(min_length=1)` — use for testing guard logic inside adapter
- litellm exception positional arg order: use keyword args in tests to avoid positional ambiguity
- 106 new tests (29u schemas, 28u parser, 35u adapter, 14 contract), 364 total passing
