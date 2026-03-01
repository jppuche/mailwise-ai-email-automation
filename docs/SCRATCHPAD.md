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

## 2026-03-02 -- Block 14: Analytics & Admin Endpoints [Lorekeeper]

### Implementation notes

- `IntegrationService` returns `dict[str, object]`; router uses `cast(int, config["key"])` — `int(config["key"])` fails mypy `call-overload` on `object` type
- `ClassificationFeedback` feedback query: 4-way JOIN with `ActionCategory.__table__.alias("orig_action")` — SQLAlchemy Core alias for self-referential category FK resolution; no `# type: ignore[attr-defined]` needed
- `func.count().label("count")` → mypy types `row.count` as `Callable`; fix: `cast(int, row._mapping["count"])`
- `categories_router` and `classification_router` exported from same file (`categories.py`) — two routers, two prefixes, one module
- `StreamingResponse` return: no `response_model` needed on CSV export endpoint
- CSV generator test: `MagicMock(return_value=_csv_gen())` NOT `AsyncMock` — `stream_csv_export` is sync method returning async generator, not a coroutine
- Module-level service singletons (`_analytics_service`, `_integration_service`, `_category_service`): patch at `src.api.routers.<module>.<singleton_name>` — same pattern as `_routing_service` in B13
- `ReorderRequest.ordered_ids` validator rejects empty list at Pydantic level → 422 without touching service
- `TestAuthGuards` loop pattern: single test iterates all endpoint paths of a router to assert reviewer-denied invariant compactly
- `MagicMock(spec=SystemLog)` required for logs tests — spec-less mock exposes arbitrary attributes silently
- `list[object]` annotation required when passing `list[MagicMock]` to functions typed as `list[object]` — mypy arg-type strictness
- `email_id=None` on mock log: set explicitly after construction (`log.email_id = None`) — MagicMock spec may return MagicMock for unset attrs
- `DateRangeFilter` validator uses `info.data` narrowing via `hasattr` guard — no `type: ignore[union-attr]` needed (mypy narrows through hasattr)
- `FewShotExample`: `action_slug`/`type_slug` stored as strings, not FK UUIDs — intentional (few-shot examples are text templates, not relational references)
- `SystemLog`: `email_id` is NOT a FK (logs may outlive emails); `context: dict[str, str]` not `dict[str, Any]`
- `CategoryInUseError` response body: `{"error": "category_in_use", "affected_email_count": N}` — confirmed from exception_handlers.py

### Block 14 final results

- 139 new tests (46 categories + 44 integrations + 33 analytics + 16 logs), 1616 total
- mypy 0, ruff 0 on all B14 files
- Architecture: zero try/except in routers, no dict[str, Any] in schemas, no credentials in integration responses
- Spec deltas applied: IntegrationConfig dropped, PUT integrations dropped, color_hex dropped, reviewer_note dropped, DELETE returns 204

---

## 2026-03-01 -- Spec amendments B14-B19 (continuation) [agent]

### What worked well

- Plan from previous session carried over cleanly — all 96 deltas verified and appended
- Parallel Edit calls for B18+B19 saved time (B19 succeeded, B18 needed re-read due to exact match)
- Cross-cutting delta table (X1-X8) avoids repetition across 6 specs

### Mistakes made

- B18 Edit failed on first attempt: multi-line `old_string` didn't match exactly (line ending/whitespace). Fixed by re-reading last lines and using shorter unique match.

### Implementation notes

- 6 spec files amended: B14 (20), B15 (9), B16 (14), B17 (11), B18 (21), B19 (21) = 96 total deltas
- Commit: `2824e60` — `docs: spec amendments B14-B19 — post-implementation review`
- validate-docs: 0 errors, 3 warnings (date discrepancy system clock vs session dates)

---
