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
- [sentinel] B18-B19: `CELERY_TASK_ALWAYS_EAGER` security diffs, `PiiSanitizingFilter` false positives, `.env.example` parity

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

## 2026-03-01 -- Block 18-19 key facts (consolidated) [Lorekeeper]

- Docker: scheduler cmd is `python -m src.scheduler` (NOT `src.tasks.scheduler`); API health path is `/api/v1/health`
- Alpine images: use `wget` not `curl` — curl not guaranteed in alpine
- Worker health check: `celery inspect ping -d "celery@${HOSTNAME}"` — HOSTNAME set by Docker runtime
- Logging: `configure_logging` called in lifespan, Celery `worker_init` signal, scheduler `main()` — deferred import to avoid circular deps
- `.env.example` parity: 60+ Settings fields; parity test critical in B19

---

## 2026-03-01 -- Block 19: deployment.md + adapter-guide.md [Lorekeeper]

### What was delivered

- `docs/deployment.md`: 6-section deployment guide covering prerequisites, quick start, full env var reference table, first-time setup (Python REPL pattern for admin creation), production considerations, troubleshooting table
- `docs/adapter-guide.md`: adapter extension guide with glossary, ABC method signatures, 5-step extension pattern for all 4 families (Outlook/Email, Teams/Channel, Salesforce/CRM, Ollama/LLM), contract-docstrings in example implementations, common patterns section

### Key notes

- Admin creation via Python REPL (no CLI module exists) — `AuthService.create_user()` REPL pattern documented
- Adapter guide opens with class→integration glossary (concept-analysis requirement)
- `_ensure_connected()` + `assert self._client is not None` pattern documented as standard mypy narrowing idiom
- `classify()` fallback contract explicitly documented: MUST return result on parse failure, MUST NOT raise
- CORS_ORIGINS: no default in production — startup fails if not set (B19 requirement)

---

## 2026-03-01 -- Block 19: Infrastructure tests (40 tests) [Inquisidor]

### What was delivered

- `tests/infrastructure/__init__.py` — package marker
- `tests/infrastructure/test_env_example.py` — 6 tests: AST-based Settings field extraction vs .env.example parity, smoke tests for both parsers, required-fields guard
- `tests/infrastructure/test_logging.py` — 20 tests: JSON/text output, log level filtering, logger interface, logger name/level/timestamp in JSON, correlation ID ContextVar (default, set, overwrite, injection in output), PII redaction (7 fields parametrized, raw value absent, simultaneous, nested NOT redacted by design)
- `tests/infrastructure/test_health_checks.py` — 14 tests: 8 static compose file checks (no Docker), 2 Docker-gated checks under `@pytest.mark.docker`
- `pyproject.toml`: added `markers` key to `[tool.pytest.ini_options]` — registered `e2e` and `docker` marks

### Key discoveries

- `capsys` capture of structlog output requires `configure_logging()` to be called INSIDE the test body (not in an autouse fixture). `logging.basicConfig(force=True)` recreates the StreamHandler pointing at pytest's redirected stderr only when called after capsys starts redirecting. If called in a fixture first, the handler captures real stderr and `capsys.readouterr().err` is empty.
- `structlog.get_logger()` returns `BoundLoggerLazyProxy`, not `BoundLogger`. `isinstance(logger, structlog.stdlib.BoundLogger)` is always False. Test the interface (callable `.info`, `.warning`, etc.) not the internal type.
- `yaml` deferred import inside Docker-gated test: needs `# type: ignore[import-untyped]` even with `ignore_missing_imports = true` because the import is inside a function body that mypy resolves separately.
- `pytest_configure` hook inside a test module for registering marks works at collection time but the mark assignment at module level happens before it — causes `PytestUnknownMarkWarning`. Solution: register marks in `pyproject.toml [tool.pytest.ini_options] markers`.

