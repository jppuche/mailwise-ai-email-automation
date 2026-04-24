# Architecture Review -- mailwise

**Reviewer:** Sentinel (opus)
**Date:** 2026-03-02
**Scope:** Full codebase review -- 6 focus areas, 7 security dimensions
**Role:** Senior Developer / Software Architect perspective

---

## Executive Summary

mailwise is a well-architected portfolio project that demonstrates professional-grade patterns across its entire stack. The adapter pattern implementation is exemplary -- consistent ABCs, typed boundaries, no SDK leakage. The services layer cleanly separates orchestration from business logic with documented error strategies per method. The pipeline state machine is enforced at both Python and database levels. The codebase reads like it was built by a team that had a clear architecture blueprint and followed it with discipline.

The findings below are refinements, not structural flaws.

---

## 1. Adapter Pattern

### Files reviewed

- `src/adapters/email/base.py`, `gmail.py`, `schemas.py`, `exceptions.py`
- `src/adapters/channel/base.py`, `slack.py`, `schemas.py`, `exceptions.py`
- `src/adapters/crm/base.py`, `hubspot.py`, `schemas.py`, `exceptions.py`
- `src/adapters/llm/base.py`, `litellm_adapter.py`, `parser.py`, `schemas.py`, `exceptions.py`

### STRENGTH: Consistent adapter architecture across all 4 families

Every adapter family follows the same structural pattern: ABC with contract-docstrings, typed Pydantic schemas at the boundary, exception hierarchy with `original_error` wrapping, and private `_ensure_connected()` + `_map_*_error()` helper methods. Raw SDK objects (Google's `Resource`, Slack's `SlackResponse`, HubSpot's `SimplePublicObject`, LiteLLM's `ModelResponse`) never escape the adapter layer. The `test_connection()` method on every adapter follows identical semantics: never raises, always returns a result object. This is textbook adapter pattern execution.

### STRENGTH: 7-shape LLM output parser

The `src/adapters/llm/parser.py` handles real-world LLM output variance (thinking tags, markdown fences, key aliases, wrong casing) with pure conditionals per D8. The `parse_classification` function returns `None` on failure instead of raising, pushing fallback logic to the caller. This is a production-tested pattern.

### STRENGTH: Exception hierarchies with `original_error` chaining

All 4 adapter families define parallel exception hierarchies rooted in a base error (`EmailAdapterError`, `ChannelAdapterError`, `CRMAdapterError`, `LLMAdapterError`). Each wraps the provider-specific exception via `original_error` keyword argument, enabling debugging without coupling callers to SDK types. `from exc` chaining is used consistently.

### FINDING-01: Sync/async inconsistency in EmailAdapter ABC

**Severity:** Medium
**File:** `src/adapters/email/base.py`
**Detail:** The `EmailAdapter` ABC defines all methods as synchronous (no `async def`), while `ChannelAdapter`, `CRMAdapter`, and `LLMAdapter` all define their methods as `async def`. The `GmailAdapter` implementation is also synchronous, and the `DraftGenerationService` wraps its call with `asyncio.to_thread()` at line 295. This works, but creates an asymmetry: the Email adapter is the only one where callers must remember to wrap in `to_thread()`, while the other 3 adapters are natively awaitable.

**Why it matters for portfolio:** A reviewer comparing the 4 ABCs side-by-side will immediately notice that `email/base.py` breaks the pattern. This raises questions about whether a second email provider implementation (e.g., Microsoft Graph, which is async) could implement this ABC cleanly.

**Suggested fix:** Make `EmailAdapter` methods `async def` to match the other 3 families. Move the `to_thread()` wrapping inside `GmailAdapter` (same pattern used by `HubSpotAdapter` for its sync SDK). This keeps the interface consistent and future-proofs for async email providers.

### FINDING-02: `dict[str, Any]` usage in GmailAdapter private helpers

**Severity:** Low
**File:** `src/adapters/email/gmail.py`, lines 94, 122, 152, 306
**Detail:** Several private helper functions accept `dict[str, Any]` parameters for Gmail API response dicts (e.g., `_extract_body(payload: dict[str, Any])`, `_parse_message(raw_msg: dict[str, Any])`). These are internal to the adapter module and never cross the boundary, so they do not violate D1. However, the `request_kwargs: dict[str, Any]` at line 306 inside `fetch_new_messages` uses `Any` unnecessarily -- the values are `str | int`.

**Suggested fix:** `request_kwargs: dict[str, str | int]` at line 306. The private helpers dealing with raw Gmail dicts can stay as-is since `googleapiclient` is untyped.

---

## 2. Services Layer

### Files reviewed

- `src/services/ingestion.py`
- `src/services/classification.py`
- `src/services/routing.py`
- `src/services/crm_sync.py`
- `src/services/draft_generation.py`
- `src/services/prompt_builder.py`, `heuristics.py`, `rule_engine.py`
- `src/services/schemas/` (all 5 schema files)

### STRENGTH: Single-responsibility with clean DI

Each service has one job: `IngestionService` fetches and stores, `ClassificationService` classifies, `RoutingService` dispatches, `CRMSyncService` syncs, `DraftGenerationService` generates drafts. Dependencies are injected via constructor keyword arguments with explicit types -- no service locator or global state. The `RuleEngine` and `PromptBuilder` are stateless helpers extracted from the services that own them.

### STRENGTH: Independent commits per pipeline stage (D13)

Every service commits its own DB changes independently. `IngestionService` commits FETCHED then SANITIZED in two separate transactions. `RoutingService._record_success_action()` commits each routing action individually. `CRMSyncService._persist_sync_record()` commits independently. This means a failure at stage N never rolls back stage N-1, and the system can resume from the last successful state. This is a sophisticated pattern that most portfolio projects miss.

### STRENGTH: Documented error strategy per method

Every public method documents which exceptions it raises and which it silences, with explicit references to the D7/D8 directive. For example, `ClassificationService.classify_email()` raises `LLMAdapterError` after transitioning to `CLASSIFICATION_FAILED`, while `_load_feedback_examples()` silences `SQLAlchemyError` and returns an empty list. This makes the error behavior predictable for anyone reading the code.

### FINDING-03: N+1 query pattern in `_load_feedback_examples`

**Severity:** Medium
**File:** `src/services/classification.py`, lines 361-412
**Detail:** The method executes 1 query to get feedback rows, then for each row executes 3 additional queries (email body, action slug, type slug). With `classify_max_few_shot_examples=10`, this is up to 31 queries. A single query with JOINs would accomplish the same work.

**Suggested fix:** Replace with a joined query:
```python
select(
    Email.body_plain,
    ActionCategory.slug,
    TypeCategory.slug,
).join(ClassificationFeedback, ClassificationFeedback.email_id == Email.id)
 .join(ActionCategory, ActionCategory.id == ClassificationFeedback.corrected_action_id)
 .join(TypeCategory, TypeCategory.id == ClassificationFeedback.corrected_type_id)
 .order_by(ClassificationFeedback.corrected_at.desc())
 .limit(limit)
```

### FINDING-04: `get_settings()` creates a new instance on every call

**Severity:** Medium
**File:** `src/core/config.py`, lines 149-150
**Detail:** `get_settings()` returns `Settings()` every time, parsing `.env` on each call. This function is called from adapters, services, and Celery tasks. While Pydantic Settings caches `.env` parsing internally to some extent, the object instantiation and model validation run every time. FastAPI projects typically use `@lru_cache` on this function.

**Why it matters:** In a Celery worker processing 50 emails in a batch, this means 50+ Settings instantiations. In the API process, every request creates a new Settings.

**Suggested fix:**
```python
from functools import lru_cache

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### FINDING-05: `emails.py` router contains business logic

**Severity:** Low
**File:** `src/api/routers/emails.py`, lines 90-211
**Detail:** The `list_emails` endpoint contains ~120 lines of query building, category resolution, and response mapping directly in the router function. While it works, this is the one endpoint where the "thin API layer" principle breaks down. Other routers (auth, drafts, categories, analytics) delegate to services. The `list_emails` endpoint should delegate to a query service or at minimum an `EmailQueryService`.

**Suggested fix:** Extract `list_emails` query logic to `src/services/email_query.py` with a `list_emails(db, pagination, filters)` method. The router becomes a 5-line function that calls the service and returns the result.

### FINDING-06: `reclassify_email` bypasses state machine

**Severity:** Low
**File:** `src/api/routers/emails.py`, lines 369-370
**Detail:** `email.state = EmailState.SANITIZED` directly assigns the state, bypassing `transition_to()`. The docstring explains this is intentional ("admin power op"), and the `_RECLASSIFIABLE_STATES` guard prevents misuse. However, the lack of `transition_to()` means VALID_TRANSITIONS is not consulted. If someone adds the reclassify feature to a non-admin context later, the bypass could go unnoticed.

**Suggested fix:** Consider adding an explicit `force_state(new_state, *, admin_override=True)` method on the Email model that logs the override. This preserves the admin capability while making the bypass explicit and auditable.

---

## 3. API Layer

### Files reviewed

- `src/api/main.py`
- `src/api/deps.py`
- `src/api/exception_handlers.py`
- `src/api/routers/emails.py`, `auth.py`
- `src/api/schemas/common.py`, `emails.py`, `auth.py`

### STRENGTH: Zero try/except in routers

The routers are genuinely thin. Domain exceptions (`NotFoundError`, `InvalidStateTransitionError`, `AuthenticationError`, etc.) propagate to `exception_handlers.py` where they are mapped to HTTP status codes. The auth router is the sole exception, using try/except for Redis operations -- which is correct since Redis errors need to map to 503.

### STRENGTH: Clean dependency injection via FastAPI Depends

`get_current_user`, `require_admin`, `require_reviewer_or_admin`, and `require_draft_access` form a composable dependency chain. Each dependency has a single responsibility and raises appropriate domain exceptions. The `auto_error=False` on `HTTPBearer` is a smart choice -- it prevents FastAPI's default 403 and lets the code raise a proper 401.

### STRENGTH: Timing-safe login

`src/api/routers/auth.py` lines 57-61 and `src/core/security.py` lines 34-37 implement a dummy hash for nonexistent users, preventing timing-based username enumeration. This is a security detail that most portfolio projects miss entirely.

### FINDING-07: `get_routing_service` DI factory is untyped

**Severity:** Low
**File:** `src/api/deps.py`, lines 95-109
**Detail:** `async def get_routing_service():  # type: ignore[no-untyped-def]` has no return type annotation and creates adapter instances on every call (including connecting to Slack). In a production setting, this means every API request that needs routing creates a new SlackAdapter and calls `auth_test()`. The adapter should be created once at startup.

**Suggested fix:** Add return type `-> RoutingService`, and consider caching the connected adapter via application state or a startup hook.

### FINDING-08: ILIKE filter with unsanitized user input

**Severity:** Medium (Security)
**File:** `src/api/routers/emails.py`, line 109
**Detail:** `base_q = base_q.where(Email.sender_email.ilike(f"%{filters.sender}%"))` -- the `sender` filter value from the query string is interpolated into the ILIKE pattern without escaping SQL wildcard characters (`%`, `_`). While SQLAlchemy parameterizes the value (preventing SQL injection), a user can craft patterns like `%` (match everything) or `_@_` (single-char wildcards) to enumerate sender patterns.

**Why it matters:** This is not SQL injection, but it is a semantic bypass. A reviewer who knows ILIKE wildcards would flag this.

**Suggested fix:**
```python
import re
escaped = re.sub(r"([%_\\])", r"\\\1", filters.sender)
base_q = base_q.where(Email.sender_email.ilike(f"%{escaped}%"))
```

---

## 4. Error Handling

### Files reviewed

All adapter implementations, all services, all routers, `src/core/security.py`, `src/tasks/pipeline.py`

### STRENGTH: Disciplined D7/D8 separation

The codebase consistently applies structured try/except to external-state operations (DB, API calls, Redis) and uses conditionals for local computation. Comments reference the directive number (`# D7: external-state operation`, `# D8: conditionals, not try/except`) making the strategy auditable. The `noqa: BLE001` comments on `test_connection()` methods document the intentional bare `except Exception` usage.

### STRENGTH: Rate limit exceptions re-raised through the stack

`CRMRateLimitError` and `LLMRateLimitError` are explicitly re-raised in services (`except (CRMAuthError, CRMRateLimitError): raise`) and caught in Celery tasks for retry with backoff. Auth errors are also re-raised but without retry. This is a production-grade pattern.

### FINDING-09: Bare `except Exception` in Celery tasks masks programming errors

**Severity:** Medium
**File:** `src/tasks/pipeline.py`, lines 183-189, 246-252
**Detail:** After catching `LLMRateLimitError` specifically, the tasks fall through to `except Exception as exc: raise task.retry(exc=exc)`. This means a `TypeError`, `AttributeError`, or other programming bug will be retried 3 times before being logged, wasting time and obscuring the root cause.

**Suggested fix:** Add explicit catches for expected adapter exceptions before the bare `except`:
```python
except (LLMAdapterError, SQLAlchemyError, InvalidStateTransitionError) as exc:
    logger.error(...)
    raise task.retry(exc=exc) from exc
except Exception as exc:
    logger.critical("classify_task_unexpected_bug", ...)
    raise  # Do not retry programming errors
```

### FINDING-10: Missing `await db.rollback()` after `reclassify_email` flush

**Severity:** Low
**File:** `src/api/routers/emails.py`, line 371
**Detail:** `await db.flush()` is called but there is no corresponding `await db.commit()` within the endpoint. FastAPI's `get_async_db` dependency likely handles commit on success, but if `classify_task.delay()` on line 374 raises (Redis down), the flushed state change is left in an ambiguous state -- committed by the session teardown or rolled back depending on the dependency implementation.

**Suggested fix:** Use `await db.commit()` explicitly instead of `await db.flush()` to make the commit boundary clear, consistent with how other services handle state transitions.

---

## 5. Type Safety

### Files reviewed

- All `src/adapters/*/schemas.py` (4 files)
- All `src/api/schemas/*.py` (8 files)
- All `src/services/schemas/*.py` (5 files)
- `src/core/config.py`, `src/core/security.py`, `src/core/sanitizer.py`

### STRENGTH: No `dict[str, Any]` at any public boundary

Adapter schemas use Pydantic BaseModel or TypedDict exclusively. Service schemas are Pydantic models or dataclasses. API schemas are all Pydantic. The `SanitizedText = NewType("SanitizedText", str)` and `DraftId = NewType("DraftId", str)` provide semantic type branding. `TokenPayload` is a TypedDict, not `dict[str, Any]`. The `ClassifyOptions` and `DraftOptions` use `Field(ge=0.0, le=1.0)` for temperature validation.

### STRENGTH: PEP 695 generics in API schemas

`PaginatedResponse[T](BaseModel)` uses PEP 695 syntax (Python 3.12+), which is clean and modern. Pydantic v2 supports this natively.

### FINDING-11: `confidence` field inconsistency across layers

**Severity:** Low
**File:** Multiple files
**Detail:** The `confidence` field has different representations across layers:
- Adapter: `Literal["high", "low"]` in `ClassificationResult`
- ORM: `ClassificationConfidence` enum (StrEnum with values "high"/"low")
- API response: `str` (via `str(clf.confidence)`)
- Service: `Literal["high", "low"]` in `ClassificationServiceResult`
- Channel schema: `Literal["high", "low"]` in `ClassificationInfo`

The API response schema (`ClassificationSummary.confidence: str`) is the loosest type. When serialized, `str(clf.confidence)` produces `"ClassificationConfidence.HIGH"` or just `"high"` depending on StrEnum behavior. This could produce unexpected values in the API response.

**Suggested fix:** Use `clf.confidence.value` instead of `str(clf.confidence)` in the router, and type `ClassificationSummary.confidence` as `Literal["high", "low"]` for tighter API contracts.

### FINDING-12: `raw_llm_output` typed as bare `dict` in ORM model

**Severity:** Low
**File:** `src/models/classification.py`, line 76
**Detail:** `raw_llm_output: Mapped[dict] = mapped_column(JSONB, ...)  # type: ignore[type-arg]` uses bare `dict` with a type-ignore. The comment explains this is intentional (provider-dependent shape), but a `dict[str, str | int | float | bool | None]` would be more precise than `dict`.

**Suggested fix:** `Mapped[dict[str, object]]` removes the type-ignore while remaining flexible.

---

## 6. Database Models

### Files reviewed

- `src/models/base.py`, `email.py`, `classification.py`, `category.py`, `routing.py`, `user.py`, `draft.py`, `crm_sync.py`, `feedback.py`, `system_log.py`
- `src/models/__init__.py`

### STRENGTH: State machine enforced at DB level

`EmailState` is a PostgreSQL ENUM (not VARCHAR), preventing invalid values at the database level even if Python-level validation is bypassed. `VALID_TRANSITIONS` is a module-level dict with `frozenset` values, making it immutable. The `transition_to()` method on the `Email` model validates transitions before mutation. This is dual-layer enforcement -- exactly what D10 requires.

### STRENGTH: FK constraints on classification categories

`ClassificationResult.action_category_id` and `type_category_id` reference `action_categories.id` and `type_categories.id` via foreign keys. This means an LLM hallucination producing a free-form category slug is rejected at the DB level even if the service-level validation is bypassed. This is the D11 stringly-typed defense.

### STRENGTH: Composite indexes for common query patterns

`ix_emails_state_date` and `ix_emails_account_state` are composite indexes that match the query patterns in `list_emails` (filter by state, order by date) and `ingest_batch` (filter by account + state). `provider_message_id` has a unique constraint for dedup. `thread_id` is indexed for thread-aware ingestion.

### STRENGTH: `values_callable=_enum_values` on all StrEnum columns

Every StrEnum column (5 models: User, Classification, Routing, CRM, Draft) uses the shared `_enum_values` helper. This prevents the SQLAlchemy `.name` vs `.value` mismatch that was a recurring bug (documented in Learned Patterns).

### STRENGTH: Audit-preserving cascade rules

`RoutingAction.rule_id` uses `ondelete="SET NULL"` so routing history is preserved when rules are deleted. `Draft.reviewer_id` uses the same pattern. Email-dependent records use `ondelete="CASCADE"` appropriately.

### FINDING-13: ActionCategory and TypeCategory share identical structure

**Severity:** Low
**File:** `src/models/category.py`
**Detail:** `ActionCategory` and `TypeCategory` have identical columns (`slug`, `name`, `description`, `is_fallback`, `is_active`, `display_order`). They differ only in table name and semantic meaning. A single `Category` model with a `layer` discriminator column (`action` vs `type`) would reduce duplication.

**Suggested fix:** This is a conscious design decision documented in the model docstring. The separate tables make FK constraints simpler (one FK per layer) and the schema clearer. No change needed -- this is the right tradeoff for a two-layer classification system. Noted as INFO, not a real issue.

### FINDING-14: Missing index on `dispatch_id` for idempotency checks

**Severity:** Medium
**File:** `src/models/routing.py`, line 103
**Detail:** `dispatch_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)` has no index. The `RoutingService._find_existing_dispatch()` queries `WHERE dispatch_id = :id` on every dispatch attempt. Without an index, this is a full table scan on `routing_actions`.

**Suggested fix:** Add `index=True` to the `dispatch_id` column:
```python
dispatch_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True, index=True)
```

---

## Summary of Findings

| ID | Area | Severity | Description |
|----|------|----------|-------------|
| F-01 | Adapter | Medium | Sync/async inconsistency in EmailAdapter ABC |
| F-02 | Adapter | Low | `dict[str, Any]` in GmailAdapter private helper kwargs |
| F-03 | Services | Medium | N+1 query in `_load_feedback_examples` |
| F-04 | Services | Medium | `get_settings()` creates new instance on every call |
| F-05 | API | Low | `list_emails` router contains business logic |
| F-06 | API | Low | `reclassify_email` bypasses state machine without logging |
| F-07 | API | Low | `get_routing_service` untyped and reconnects on every call |
| F-08 | API | Medium | ILIKE filter with unescaped SQL wildcards |
| F-09 | Pipeline | Medium | Bare `except Exception` retries programming errors |
| F-10 | API | Low | Missing explicit commit after reclassify flush |
| F-11 | Types | Low | `confidence` field type inconsistency across layers |
| F-12 | Types | Low | `raw_llm_output` bare `dict` type |
| F-13 | Models | Info | ActionCategory/TypeCategory duplication (by design) |
| F-14 | Models | Medium | Missing index on `dispatch_id` |

**Counts:** 5 Medium, 7 Low, 1 Info, 1 Medium/Security

---

## Portfolio Assessment

**What a hiring manager would notice (positive):**
1. The adapter pattern is textbook-quality with real-world concerns (retries, fallbacks, SDK wrapping) handled cleanly.
2. The state machine is enforced at both application and database level -- this shows systems thinking.
3. Contract-docstrings on every ABC method document invariants, guarantees, and error strategies.
4. The D7/D8 separation is consistently applied and cross-referenced -- showing engineering discipline.
5. Security details (timing-safe login, PII exclusion from logs, invisible Unicode sanitization, prompt injection defense layers) demonstrate security awareness beyond typical portfolio projects.
6. The LLM output parser handles 7 real-world output shapes -- this shows production experience.
7. Independent commits per pipeline stage (D13) show understanding of distributed system failure modes.

**What a hiring manager might probe:**
1. Why is `EmailAdapter` sync when the other 3 are async? (F-01)
2. Why does `list_emails` have 120 lines of query logic in the router? (F-05)
3. Is `get_settings()` cached? (F-04)
4. How does the system handle truly unexpected errors in Celery tasks? (F-09)

---

*Review conducted by Sentinel agent. Read-only -- no production code modified.*
