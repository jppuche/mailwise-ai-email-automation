# Development Changelog — mailwise

> Append-only. Format: ## YYYY-MM-DD -- Brief description.
> Record WHAT was done, not HOW. The "how" goes in CLAUDE.md Learned Patterns.

## 2026-02-19 -- Initial setup

- Project structure created (.claude/, docs/, scripts/)
- CLAUDE.md configured with required sections
- Agents and rules defined

## 2026-02-20 -- Phase 1: Technical Landscape

- 15 technology decisions recorded in DECISIONS.md (FastAPI, PostgreSQL, SQLAlchemy, React+Vite+TS, Celery+Redis, LiteLLM, Gmail API, Slack SDK, HubSpot, JWT, Docker Compose, pytest, ruff+mypy, src layout)
- Ecosystem scan: 8 MCP/skill candidates cataloged (HubSpot Official MCP highest impact)
- CLAUDE.md updated with full stack, commands, architecture notes
- quality-gate.json updated with ruff, mypy, pytest gates
- Dual objective documented: portfolio (AI Engineer) + consultant showcase (replicable template + methodology)
- Phase order adjusted: 2→3→5→4 (agents inform spec writing)
- 8 known gotchas documented with mitigations for specific blocks

## 2026-02-20 -- Phase 2: Tooling & Security

- 8 ecosystem candidates evaluated via Cerbero (4 agents in parallel)
- mcp-scan APPROVED and installed (--opt-out, scan-only, isolated via uvx)
- claude-code-security-review APPROVED (trusted PRs only, pin commit SHA, never sole gate)
- honnibal/claude-skills APPROVED selectively (4 of 7 skills: tighten-types, try-except, contract-docstrings, pre-mortem)
- PostgreSQL MCP REJECTED (SQL injection confirmed by Datadog Security Labs, archived, unpatched)
- SAST MCP REJECTED (untrusted publisher, offensive tools, unauthenticated server)
- HubSpot MCP DEFERRED (beta, closed-source, SDK already selected)
- Slack MCP + Python code quality skill SKIPPED (redundant with existing stack)
- Hash verification rule added to CLAUDE.md Security section

## 2026-02-20 -- Phase 3: Strategic Review

- 20 Phase 1 decisions re-evaluated against Phase 2 tooling results using 7 analytical dimensions
- Skill methodologies applied as analytical lenses: tighten-types, try-except, contract-docstrings, pre-mortem, Cerbero
- 15 decisions confirmed, 6 adjustments documented (LiteLLM typing, Celery return types, Docker service count, CI security layer, no DB MCP shortcut, full CRM adapter required)
- Agent composition confirmed: Lorekeeper + Inquisidor + Sentinel + backend-worker + frontend-worker
- Skill-to-agent mapping defined: tighten-types+try-except→Inquisidor, contract-docstrings+pre-mortem+Cerbero→Sentinel
- 18 architecture directives documented for Phase 4 block specs (4 tighten-types, 2 contract-docstrings, 3 try-except, 6 pre-mortem, 3 security)
- 2 newly discovered honnibal skills (alignment-chart, concept-analysis) flagged for Phase 5 Cerbero evaluation

## 2026-02-20 -- Phase 5: Team Assembly

- 4 agent templates created: Inquisidor (sonnet), Sentinel (opus), backend-worker (sonnet), frontend-worker (sonnet)
- 6 honnibal skills installed to .claude/skills/honnibal/ (tighten-types, try-except, contract-docstrings, pre-mortem, alignment-chart, concept-analysis)
- Cerbero evaluation of alignment-chart: APPROVED (clean, markdown-only, 1 false positive scanner hit)
- Cerbero evaluation of concept-analysis: APPROVED (clean, forensic analysis cleared false positive from agent context boundary confusion)
- AGENT-COORDINATION.md Section 5 updated with mailwise-specific file ownership paths
- AGENT-COORDINATION.md Section 13 populated with 7 skill triggers and 5 agent assignments
- CLAUDE.md Skills section updated with 7 installed skills (cerbero + 6 honnibal)
- 18 architecture directives embedded in agent prompts per skill methodology source
- Forensic discovery: agent context boundary confusion can produce false positives when system-reminder tags are confused with file content — always verify with hex dump

## 2026-02-20 -- Phase 4: Architecture Blueprint

- 20 block specs written to docs/specs/ (block-00 through block-19)
- Skills applied as analytical lenses in specs: pre-mortem (fragility), try-except (exception strategy), tighten-types (type decisions), contract-docstrings (adapter contracts), alignment-chart (test categorization), concept-analysis (naming consistency)
- Sentinel security review: 0 critical, 3 warnings, 5 suggestions (docs/reviews/phase-4-security-review.md)
- Architecture directives from Phase 3 embedded in all specs (D1-D18 coverage, D15 minimal)
- Tier 2 features explicitly assigned to blocks
- Dependency DAG verified acyclic
- D16 discrepancy found: specs implement 5-layer prompt injection defense (not 4 as in DECISIONS.md) — pending correction

## 2026-02-20 -- Block 00: Project Scaffolding

- Python package: pyproject.toml with all runtime + dev deps, ruff/mypy/pytest config
- src/ layout: core/ (config, sanitizer, logging), adapters/ (email, channel, crm, llm), services/, api/, models/, tasks/
- Core modules: Settings (14 load-bearing defaults), SanitizedText NewType + sanitize_email_body, structlog PII-safe logging
- Docker: Dockerfile (Python 3.12-slim multi-stage), Dockerfile.frontend (Node 20 + Nginx), docker-compose.yml (6 services), docker-compose.dev.yml
- Frontend: Vite 7 + React 19 + TypeScript scaffold with auth context, theme, routing, API layer (frontend-worker)
- Tests: 33 tests (10 config + 23 sanitizer) — all passing
- Quality gates: ruff format 0 diffs, ruff check 0 violations, mypy strict 0 errors, pytest 33/33 pass
- Docker verification deferred (Docker Desktop not running)

## 2026-02-20 -- Block 01: Database Models & Migrations

- 9 SQLAlchemy 2.0 models: Email (12-state machine), ActionCategory, TypeCategory, ClassificationResult, RoutingRule, RoutingAction, Draft, User, CRMSyncRecord, ClassificationFeedback
- EmailState as PostgreSQL ENUM (not VARCHAR) — DB-level enforcement (pre-mortem Cat 1)
- Categories as FK-backed DB tables — prevents LLM hallucination from corrupting classification (Cat 3)
- TypedDicts for all JSONB fields: RecipientData, AttachmentData, RoutingConditions, RoutingActions
- `transition_to()` with full contract docstring: invariants, guarantees, errors, state transitions
- Dual session factories: AsyncSessionLocal (FastAPI + asyncpg) + SyncSessionLocal (Celery + psycopg2)
- Alembic migration: 10 tables, 6 enum types, 14 seed rows (4 action + 10 type categories)
- Seed data: deterministic UUIDs, exactly 1 fallback per category type (unknown/other)
- Settings: added `extra="ignore"` for Docker env var tolerance
- 132 tests: 69 unit (state machine + imports) + 34 integration (seeds + migrations + FK enforcement)
- Sentinel review: PASS WITH WARNINGS (docs/reviews/block-01-sentinel-review.md)
- Quality gates: mypy 0 errors (26 files), ruff check 0 violations, ruff format 0 diffs

## 2026-02-21 -- Block 02: Auth & Users

- JWT auth via python-jose: access tokens (15 min) + opaque UUID refresh tokens in Redis
- bcrypt password hashing direct (passlib 1.7.4 dropped — incompatible with bcrypt>=4.2 on Python 3.14)
- Redis refresh token store: `src/adapters/redis_client.py` with async singleton + TTL
- RBAC: Admin / Reviewer roles as JWT claims; HTTPBearer(auto_error=False) for custom 401
- TokenPayload as TypedDict (resolved B02 open question)
- Fixed `from jose import JWTClaimsError` — must be `from jose.exceptions import JWTClaimsError`
- Fixed `sa.Enum(StrEnum)` — added `values_callable=_enum_values` to all 5 non-EmailState enums; `.name` (UPPERCASE) vs `.value` (lowercase) mismatch caused FK failures against Alembic-created PostgreSQL enums
- `_enum_values()` helper in `src/models/base.py` shared by all models
- Docker Compose db/redis: added `ports:` for local integration test access
- Root conftest.py DB credentials aligned to Docker Compose (mailwise:password)
- 231 total tests pass (42 new B02 + 189 existing); quality gates: ruff check, ruff format, mypy all clean

## 2026-02-21 -- Block 03: Gmail Adapter

- EmailAdapter ABC with 7 abstract methods and contract docstrings (4-question format)
- GmailAdapter concrete implementation: OAuth2 connect, fetch with pagination, MIME parsing, draft creation, label management, health-check test_connection
- Exception hierarchy: EmailAdapterError base + 6 specific types (AuthError, RateLimitError, EmailConnectionError, FetchError, DraftCreationError, LabelError) with original_error field
- Typed boundary schemas: EmailMessage (Pydantic), EmailCredentials, ConnectionStatus, ConnectionTestResult, DraftId (NewType), Label, RecipientData/AttachmentData (TypedDicts)
- Schema reconciliation: adapter RecipientData omits `type` field (implicit in list membership), adapter AttachmentData includes `attachment_id` (matches ORM)
- try-except D7: structured HttpError mapping by status code (401→AuthError, 429→RateLimitError, 5xx→EmailConnectionError)
- try-except D8: argument validation uses conditionals, per-message parse failure isolated (log + continue)
- Settings: added gmail_max_results (Cat 8), gmail_credentials_file, gmail_token_file
- 85 new tests: 18 schema, 23 parsing, 15 contract (MockEmailAdapter), 29 adapter (mocked Google API)
- 258 total tests passing; quality gates: ruff 0, mypy 0, D1 no dict[str, Any] at boundaries

## 2026-02-28 -- Block 06: HubSpot CRM Adapter

- CRMAdapter ABC with 7 async abstract methods and contract docstrings (4-question format)
- HubSpotAdapter concrete implementation: all SDK calls via `asyncio.to_thread()` (sync SDK)
- Exception hierarchy: CRMAdapterError base + 6 subclasses (Auth, RateLimit, Connection, DuplicateContact, ContactNotFound, FieldNotFound) with `original_error`
- Typed boundary schemas: Contact, CreateContactData, ActivityData, CreateLeadData, CRMCredentials, ConnectionStatus, ConnectionTestResult (Pydantic)
- `ActivityId`/`LeadId` as NewType (semantic distinction from bare str)
- try-except D7: `_raise_from_hubspot_exc()` classifies `ApiException` by HTTP status (401/404/409/429/400+PROPERTY)
- try-except D8: precondition validation via conditionals, SDK-to-Pydantic mapping via conditionals
- Sec 6.4: `update_field` silences `FieldNotFoundError` (log + skip, no fail)
- Sec 6.5: `_hash_email()` for PII-safe logging, no snippet/subject/sender data in logs
- Settings: 5 new HubSpot defaults in `src/core/config.py` (rate_limit, snippet_length, auto_create, lead_status, timeout)
- 170 new tests: 46 schema, 82 adapter (mocked SDK), 42 contract
- 637 total tests passing; quality gates: mypy 0 errors, ruff 0 violations, pytest 637/637

## 2026-02-21 -- Block 05: Slack Channel Adapter

- ChannelAdapter ABC with 4 async methods (connect, send_notification, test_connection, get_available_destinations)
- SlackAdapter concrete implementation using slack-sdk AsyncWebClient
- SlackBlockKitFormatter: pure local computation, 3 priority levels, Block Kit structure
- 5 domain exceptions with original_error chain (ChannelAdapterError base + Auth, RateLimit, Connection, Delivery)
- 8 Pydantic boundary schemas (no dict[str, Any]) — `dict[str, object]` for Block Kit output (D1)
- 4 configurable defaults (snippet_length=150, subject_max=100, timeout=10s, page_size=200)
- `_AUTH_ERROR_CODES` / `_DELIVERY_ERROR_CODES` as module-level frozenset (Cat 3: no magic strings)
- `contextlib.suppress` for Retry-After int parsing (ruff SIM105); `TimeoutError` not `asyncio.TimeoutError` (UP041)
- 103 new tests (36 schema, 22 formatter, 29 adapter, 16 contract), 467 total

## 2026-02-28 -- Block 08: Classification Service

- ClassificationService: orchestrates category load → prompt build → LLM call → validate → heuristics → persist
- PromptBuilder: 5-layer prompt injection defense (role, categories, few-shot, data delimiters, post-validation)
- HeuristicClassifier: 6 rule-based hints (urgent, complaint, internal, spam, escalate, noreply) — NEVER overrides LLM
- Service schemas: 7 types (ActionCategoryDef, TypeCategoryDef, FeedbackExample, HeuristicResult, ClassificationRequest, ClassificationServiceResult, ClassificationBatchResult)
- Naming collision resolved: `AdapterClassificationResult` alias enforced (grep-verifiable)
- `_find_fallback()`: `next(..., None)` with explicit `CategoryNotFoundError` (WARNING-03 resolved)
- Adapter `raw_llm_output: str` → ORM `raw_llm_output: dict` (JSONB): `json.loads()` with `{"raw_response": str}` fallback
- try-except D7: DB loads, LLM calls, persist/transition; D8: prompt build, heuristics, slug validation (0 try/except)
- Heuristic disagreement lowers confidence to LOW without overriding LLM result
- Feedback loop: load N most-recent corrections as few-shot examples, silenced on failure
- Settings: 3 new Cat 8 defaults (classify_max_few_shot_examples=10, classify_feedback_snippet_chars=200, classify_internal_domains="")
- 175 new tests: 46 schema, 30 prompt_builder, 52 heuristics, 47 service
- 865 total tests passing; quality gates: mypy 0 errors, ruff 0 violations, grep enforcement all pass

## 2026-02-28 -- Block 07: Ingestion Pipeline

- IngestionService: fetch → dedup → thread-check → sanitize → store (FETCHED → SANITIZED)
- Distributed lock via Redis SET NX EX per account_id (resolved B07 open question: Redis, not asyncio.Lock)
- Per-email isolation: DB errors on email N don't prevent N+1 (Cat 6)
- Two independent commits per email: FETCHED insert + SANITIZED transition (D13)
- Thread awareness: only newest message per thread_id proceeds to classification
- Adapter RecipientData (no type) → ORM RecipientData (with type: to/cc/bcc) mapping
- IngestionResult frozen dataclass + IngestionBatchResult mutable dataclass + SkipReason/FailureReason enums
- Celery task wrapper: sync→async bridge via asyncio.run() (B12 will formalize)
- Settings: added ingestion_lock_ttl_seconds (300) and ingestion_lock_key_prefix
- 53 new tests: 20 schema, 27 service, 6 task. 690 total, 0 regressions
- Quality gates: mypy 0 errors, ruff 0 violations, pytest 690/690

## 2026-03-01 -- Block 11: Draft Generation Service

- DraftContextBuilder: pure-local context assembly, zero try/except (D8), structured LLM prompt with 6 sections
- DraftGenerationService: LLM call → Draft persist (D13) → optional Gmail push → state transition
- DraftContextBuilder.build() never raises — missing data produces notes, not errors
- Gmail push failure → DRAFT_GENERATED (NOT DRAFT_FAILED): draft already persisted (D13)
- LLMRateLimitError is the only exception re-raised from service → Celery task retries
- email_adapter.create_draft() is sync → wrapped with asyncio.to_thread() in async service
- Celery task: sync→async bridge via asyncio.run(), deferred imports, sys.modules test pattern
- Service schemas: 8 Pydantic models (EmailContent, ClassificationContext, CRMContextData, OrgContext, DraftContext, DraftRequest, DraftResult, DraftGenerationConfig)
- Settings: 6 new draft_* Cat 8 configurable defaults (push_to_gmail, org_system_prompt, org_tone, org_signature, org_prohibited_language, generation_retry_max)
- Privacy: body_snippet (truncated), never body_plain in logs; HITL grep enforced (no auto-send paths)
- 138 new tests: 39 schema, 57 context builder, 15 service, 14 task (4 parallel agents)
- 1195 total tests passing; quality gates: mypy 0, ruff 0, grep enforcement all pass

## 2026-02-28 -- Block 10: CRM Sync Service

- CRMSyncService: orchestrates idempotency check → contact lookup → conditional create → activity log → lead create → field updates
- Per-operation try/except isolation (D7): CRMAuthError and CRMRateLimitError re-raised, CRMAdapterError silenced per-operation
- Idempotency via DB (never CRM API): existing SYNCED record → cached result
- Independent CRMSyncRecord commit (D13) — partial failure recorded
- contact_id=None short-circuit: operations after lookup require contact_id
- DuplicateContactError triggers re-lookup (race condition handling)
- Service schemas: CRMSyncConfig, CRMSyncRequest, CRMOperationStatus, CRMSyncResult
- Celery task: sync→async bridge, CRMAuthError=no retry, CRMRateLimitError=retry with countdown
- 57 new tests: 28 schema, 19 service, 10 task (3 parallel agents)
- 1057 total tests passing; quality gates: mypy 0, ruff 0

## 2026-02-28 -- Block 09: Routing Service

- RoutingService: orchestrates rule evaluation → idempotent dispatch → partial failure handling → state transition
- RuleEngine: pure local computation (0 try/except, 0 adapter imports) — 6 operators (eq, contains, in, not_in, starts_with, matches_domain)
- Service schemas: 7 Pydantic types (RoutingContext, RoutingRequest, RoutingActionDef, RuleMatchResult, RoutingResult, RuleTestResult)
- `_compute_dispatch_id()`: SHA-256[:32] of `"{email_id}:{rule_id}:{channel}:{destination}"` for idempotent re-dispatch detection
- Partial failure (Cat 6/D13): each RoutingAction gets own `db.commit()`; failure in action N does not revert N-1
- VIP sender priority escalation: email match, `*.domain` wildcard, `URGENT_KEYWORDS` frozenset, `escalate` action slug
- `test_route()` dry-run: evaluates rules without dispatching, creating actions, or changing email state
- Unrouted emails (no matching rules) transition to ROUTED (not ROUTING_FAILED) — valid business case
- try-except D7: DB loads (SQLAlchemyError), adapter dispatch (4 specific ChannelAdapter exceptions); D8: rule eval, dispatch_id, payload build, priority — all pure local
- Settings: 3 new Cat 8 defaults (routing_vip_senders, routing_dashboard_base_url, routing_snippet_length)
- 135 new tests: 35 schema, 44 rule_engine, 26 service, 10 idempotency, 20 test_mode (5 parallel agents)
- 1000 total tests passing; quality gates: mypy 0 errors, ruff 0 violations, grep enforcement all pass

## 2026-02-21 -- Block 04: LLM Adapter

- LLMAdapter ABC with 3 async abstract methods (classify, generate_draft, test_connection) and contract docstrings
- LiteLLMAdapter concrete implementation: classify with fallback, generate_draft, health-check test_connection
- Exception hierarchy: LLMAdapterError base + 4 subclasses (OutputParseError, LLMRateLimitError, LLMTimeoutError, LLMConnectionError)
- 7-shape output parser: handles pure JSON, thinking-tag-wrapped, markdown-fenced, JSON embedded in text, and mixed combinations
- Typed boundary schemas: ClassificationResult, DraftText, ClassifyOptions, DraftOptions, LLMConfig, ConnectionTestResult (Pydantic)
- try-except D7: three structured blocks mapping litellm exceptions (RateLimitError, Timeout, APIConnectionError) to adapter hierarchy
- try-except D8: `_safe_json_loads` is the only exception — `json.loads` has no conditional alternative (documented inline)
- Settings: 5 new LLM settings added to `src/core/config.py` (llm_classify_model, llm_draft_model, llm_fallback_model, llm_classify_temperature, llm_draft_temperature)
- classify() fallback: `action="inform"`, `type="notification"`, `confidence="low"`, `fallback_applied=True` on OutputParseError
- generate_draft() propagates errors to caller — free-text has no safe default (contrast with classify fallback)
- Fallback logs `llm_parse_fallback` with `raw_output_preview=raw_output[:200]` (PII-safe: LLM output only)
- 106 new tests: 29 schema, 28 parser, 35 adapter (mocked litellm.acompletion), 14 contract
- 364 total tests passing; quality gates: mypy 0 errors, ruff 0 violations, pytest 364/364

## 2026-03-01 -- Block 12: Pipeline & Scheduler

- Celery app: `src/tasks/celery_app.py` — broker Redis/0, backend Redis/1, JSON serializer, UTC, autodiscover
- Result types: `src/tasks/result_types.py` — 5 frozen dataclasses (IngestResult, ClassifyResult, RouteResult, CRMSyncTaskResult, DraftTaskResult), no `Any` fields
- Pipeline: `src/tasks/pipeline.py` — `run_pipeline()` + 5 Celery tasks (ingest→classify→route→crm_sync→draft), each calls `next.delay()` after commit (D13)
- Bifurcation: `route_task` checks `RoutingResult.was_routed` → enqueues `pipeline_crm_sync_task`; CRM sync chains to draft on CRM_SYNCED state
- Scheduler: `src/scheduler/main.py` (APScheduler entry point) + `src/scheduler/jobs.py` (Redis-locked poll per account)
- Lock safety: `SET NX EX` atomic acquisition, `contextlib.suppress` for release failure, TTL >= poll interval assertion at startup
- Config: 5 new settings in `src/core/config.py` (celery_broker_url, celery_result_backend, celery_result_expires, pipeline_scheduler_lock_key_prefix, pipeline_scheduler_lock_ttl_seconds)
- D3: `AsyncResult.get()` prohibited — all results via DB/typed dataclasses
- D7: exactly 5 `except Exception` across task files (one per task)
- Graduated to CLAUDE.md: Celery decorator typing, task.run() testing, retry testing patterns
- 172 new tests (80 result types + 29 chain + 20 partial failure + 12 scheduler lock + 31 poll job)
- 1367 total tests, 0 regressions, mypy 0 errors, ruff 0 violations

## 2026-03-02 -- Block 13: REST API Core

- 4 routers: health, emails, routing-rules, drafts — all under `/api/v1/` prefix
- 22 endpoints: health(1), emails(6), routing-rules(7), drafts(5), auth(existing 4, re-mounted)
- Schemas: `PaginatedResponse[T]` (PEP 695), 4 schema modules (common, emails, routing, drafts)
- Exception handlers: 7 centralized handlers in `exception_handlers.py` — zero try/except in routers
- Auth: `require_draft_access` (Admin all, Reviewer own), `get_routing_service` (DI with deferred imports)
- Config: `api_health_adapter_timeout_ms`, `app_version` (Cat 8 configurable defaults)
- Integration test paths updated: `/auth/*` → `/api/v1/auth/*`
- Architecture constraints enforced: zero try/except in routers, no `dict[str, Any]` in schemas, PII excluded from list responses
- 110 new tests: 10 health, 14 auth, 14 pagination, 29 emails, 20 routing-rules, 18 drafts + 5 misc
- 1477 total tests, 0 regressions, mypy 0 errors, ruff 0 violations
