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

- WARNING-01: `LLM_ALLOWED_MODELS` allowlist needed (B04/B14) -- RESOLVED B20
- WARNING-02: `DRAFT_ORG_SYSTEM_PROMPT` max-length + startup warning (B11) -- RESOLVED B20
- WARNING-B02-01: Timing oracle in login — bcrypt not called for nonexistent users (B02) -- RESOLVED B20

---

## 2026-03-02 -- Blocks 14-19 (consolidated) [Lorekeeper]

- B14-B17: spec amendments, frontend patterns (recharts hex, CSS vars, JWT decode)
- B18: 18 E2E tests, 9 factories; pipeline sync, API async; `task.run()` + patch `.delay()`
- B19: structured JSON logging, Docker health checks 6 services, deployment docs, 40 tests

---

## 2026-03-02 -- Block 20: Security fixes + Docker + Coverage [consolidated]

- WARNING-01/02/B02-01 all resolved (LLM allowlist, prompt max-length, timing oracle)
- Docker smoke: 6 services healthy after COPY/CRLF/pgrep fixes
- Coverage: 85.49% -> 93.20% (1682 tests, 7 new test files)

---

## 2026-03-02 -- Architecture review [Sentinel] [security]

### Findings (14 total: 5 Medium, 7 Low, 1 Info, 1 Medium/Security)

- [security] F-08: ILIKE filter `%{filters.sender}%` in `emails.py:109` — SQL wildcards not escaped. Not SQL injection but allows pattern enumeration.
- F-01: EmailAdapter ABC is sync, other 3 are async — inconsistency a reviewer would probe
- F-03: N+1 query in `_load_feedback_examples` — up to 31 queries for 10 examples
- F-04: `get_settings()` creates new instance on every call — needs `@lru_cache`
- F-09: Bare `except Exception` in Celery tasks retries programming errors (TypeError, etc.)
- F-14: Missing index on `routing_actions.dispatch_id` — idempotency check is full table scan

### Strengths documented (for portfolio positioning)

- Adapter pattern textbook-quality across all 4 families
- State machine dual-enforced (Python + DB ENUM)
- D7/D8 separation consistently applied with cross-references
- Timing-safe login with dummy hash
- 7-shape LLM parser, FK-backed categories, independent commits (D13)

### Report

- Full report at `docs/reviews/architecture-review.md`

---

## 2026-03-02 -- Expert review fixes (7 critical/high/medium) [backend-worker]

### What was fixed

- F-04 RESOLVED: `get_settings()` now `@lru_cache(maxsize=1)` — `.env` parsed once per process
- Docker security: db/redis `ports:` removed from base `docker-compose.yml`; moved to `docker-compose.dev.yml` (plus no-password override for dev redis)
- Redis password: `command: redis-server --requirepass ${REDIS_PASSWORD:-mailwise_redis}` added to base compose; healthcheck updated to pass `-a` flag; `REDIS_PASSWORD` added to `.env.example`
- Dockerfile: `pip install -e .` → `pip install .` (editable installs are dev-only)
- F-09 PARTIALLY RESOLVED: `_run_classification` and `_run_routing` in `pipeline.py` now catch `LLMAdapterError`/`ChannelAdapterError`/`OSError` specifically — programming errors (TypeError, AttributeError) propagate immediately. `ingest_task` top-level handler intentionally left as bare except (D7 permits one per Celery task entry point).
- F-14 RESOLVED: `dispatch_id` column in `RoutingAction` model now has `index=True`
- `docs/deployment.md`: corrected false claim about `docker-compose.prod.yml` + updated `docker compose ps` example table

### What worked well

- All 1345 unit+API tests pass after changes (no regressions)
- `ruff check` + `ruff format --check` pass on all modified files

### Notes

- `dispatch_id` index requires a new Alembic migration to take effect in existing DBs
- Redis password in dev overlay is intentionally disabled (`command: redis-server`) for zero-friction local access — REDIS_URL in dev does not need `:password@` format
- `ingest_task` bare `except Exception` is D7-compliant — it is a top-level Celery task entry point, not a nested handler

---

## 2026-03-02 -- Block 20 final: test fixes + lint + README [agent]

- Narrowed exception handlers broke 3 pipeline tests: mock modules must include real exception classes (LLMAdapterError, ChannelAdapterError) for `except` clauses — MagicMock auto-attributes cause `TypeError: catching classes that do not inherit from BaseException`
- ruff --fix auto-resolved 27/39 issues; 12 manual fixes (E501 string splits, F841 unused var, SIM117 nested with, E402 noqa)
- Final: 1780 passed, 76 skipped, ruff clean, README/STATUS/CHANGELOG updated
- All 3 security warnings RESOLVED and marked in SCRATCHPAD
