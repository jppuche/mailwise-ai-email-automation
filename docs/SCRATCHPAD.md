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

## 2026-03-02 -- Blocks 14-19 (consolidated) [Lorekeeper]

- B14-B17: spec amendments, frontend patterns (recharts hex, CSS vars, JWT decode)
- B18: 18 E2E tests, 9 factories; pipeline sync, API async; `task.run()` + patch `.delay()`
- B19: structured JSON logging, Docker health checks 6 services, deployment docs, 40 tests

---

## 2026-03-02 -- Block 20: Review & Polish (consolidated) [agent]

- 3 security warnings RESOLVED: LLM allowlist, prompt max-length, timing oracle with _DUMMY_HASH
- Docker: COPY healthchecks/alembic, scheduler __main__.py, CRLF fix, pgrep→/proc, pip install (not -e)
- Coverage: 85.49%→93.20% (1780 tests, 10 new test files); CI/CD: 5-job quality.yml + security-review.yml
- Expert reviews: 4 perspectives → `@lru_cache` get_settings(), Redis password, narrowed exceptions, dispatch_id index
- Mock modules must include real exception classes for `except` clauses — MagicMock auto-attrs cause TypeError
- Open: F-08 ILIKE wildcard pattern enum (low), F-01 EmailAdapter sync vs async (cosmetic), F-03 N+1 feedback query (low)
- `dispatch_id` index needs Alembic migration for existing DBs
