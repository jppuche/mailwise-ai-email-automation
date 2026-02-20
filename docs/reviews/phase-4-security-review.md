# Phase 4 Security & Fragility Review

**Reviewer:** Sentinel (opus)
**Date:** 2026-02-20
**Scope:** All 18 block specs (B0-B17) in `docs/specs/`
**Methodology:** 7 review dimensions + 18 architecture directives + pre-mortem 10 categories + OWASP

---

## Executive Summary

The 18 block specs demonstrate a mature security posture across most dimensions. The state
machine enforcement via DB enum (D10), structured exception handling taxonomy (D7/D8),
PII-by-ID logging policy (D17), and HITL architectural constraint (B11) are well-designed
and consistently applied. The 5-layer prompt injection defense (B8) is thorough and exceeds
the original 4-layer design from FOUNDATION.md Sec 11.2.

This review surfaces 3 findings rated WARNING, 5 rated SUGGESTION, and 6 rated INFO.
No CRITICAL findings were identified -- the spec set addresses the most dangerous attack
vectors proactively. The most significant areas requiring attention during implementation
are: (1) LLM model string validation in B14, (2) org system prompt injection from config
in B11, and (3) the fallback category `StopIteration` crash path in B8.

---

## 1. Security Findings

### WARNING-01: LLM model string redirect via API endpoint

- **Severity:** WARNING
- **Blocks:** B14 (API Config), B4 (LLM Adapter)
- **Description:** `PUT /api/integrations/llm` accepts `classify_model` and `draft_model`
  as free-form strings in `LLMIntegrationUpdate`. LiteLLM resolves model strings to API
  endpoints dynamically. A malicious or misconfigured admin could set `classify_model` to
  a string that resolves to an attacker-controlled endpoint (e.g.,
  `openai/http://evil.example.com/v1`), causing all classification data -- including
  sanitized email bodies -- to be exfiltrated.
- **Spec awareness:** B14 explicitly flags this concern: "user-supplied model string could
  redirect LLM calls to arbitrary endpoints. Sentinel review requested." The spec mandates
  allowlist validation in `integration_service` and temperature range validation (0.0-2.0)
  in the Pydantic schema.
- **Assessment:** The spec acknowledges the risk and prescribes the correct mitigation
  (allowlist), but the allowlist itself is not defined in the spec. During implementation,
  the allowlist MUST be:
  - Loaded from `settings.llm_allowed_models` (env var `LLM_ALLOWED_MODELS`), not
    hardcoded in the service.
  - Validated before persisting to `IntegrationConfig` -- reject unknown models with
    HTTP 422.
  - Default allowlist should include only the models from B0 config: `gpt-4o-mini`,
    `gpt-4o`, `gpt-3.5-turbo` (fallback), and optionally `ollama/*` prefix for local
    models.
- **Recommendation:** Add `LLM_ALLOWED_MODELS` to the load-bearing defaults table in B14.
  Add a Pydantic `field_validator` on `LLMIntegrationUpdate.classify_model` and
  `draft_model` that checks against the allowlist.

### WARNING-02: Prompt injection from org system prompt configuration

- **Severity:** WARNING
- **Blocks:** B11 (Draft Generation), B0 (Config)
- **Description:** `DRAFT_ORG_SYSTEM_PROMPT` is loaded from an environment variable and
  injected directly as the `system_prompt` parameter to `LLMAdapter.generate_draft()`.
  This env var is user-supplied configuration. If an attacker gains access to the
  environment configuration (e.g., `.env` file, Docker Compose secrets, CI/CD variables),
  they can inject arbitrary instructions into the draft generation system prompt. Unlike
  email content (which passes through the 5-layer classification defense), this config
  value bypasses all prompt injection defenses because it IS the system prompt.
- **Spec awareness:** B11 explicitly calls out this risk: "Consultar Sentinel para revisar
  el manejo de `DRAFT_ORG_SYSTEM_PROMPT` desde env var -- este valor es user-supplied y
  podria contener instrucciones que modifiquen el comportamiento del LLM de forma no
  esperada (prompt injection desde configuracion)."
- **Assessment:** In a single-tenant system (D18), the person configuring the env vars is
  typically the same person operating the system. The threat model is:
  - **Low risk in single-tenant:** The admin controls the env. Misconfiguration is
    self-inflicted.
  - **Medium risk if env is shared:** CI/CD pipelines, cloud dashboards, or team members
    with env access but not admin intent could inject harmful instructions.
  - **Not a vulnerability per se** but an attack surface expansion point that should be
    documented.
- **Recommendation:** During implementation, add a validation layer in
  `DraftGenerationConfig` construction:
  - Max length check on `DRAFT_ORG_SYSTEM_PROMPT` (e.g., 2000 chars).
  - Log a WARNING at startup if the system prompt is empty (common misconfiguration).
  - Document in `.env.example` that this value controls LLM behavior and should be
    reviewed carefully.
  - Consider: should the org system prompt be settable via the API (`PUT
    /api/integrations/llm`) or only via env? If via API, the same allowlist concern from
    WARNING-01 applies but for free-form text.

### WARNING-03: Fallback category crash path via `StopIteration`

- **Severity:** WARNING
- **Blocks:** B8 (Classification Service), B1 (Models)
- **Description:** In `ClassificationService.classify()`, when the LLM returns an unknown
  category, the fallback logic uses:
  ```python
  fallback_action = next(c for c in action_categories if c.is_fallback)
  ```
  If no category has `is_fallback=True` in the database, `next()` raises
  `StopIteration`. This is an unhandled exception that would propagate as a bare
  `StopIteration` -- not a domain exception -- potentially causing confusing behavior
  in async generators or Celery task handlers.
- **Spec awareness:** B8's load-bearing defaults table notes: "Si no hay categoria con
  is_fallback=True: `next()` lanza `StopIteration`" and states "DB seed garantiza al
  menos 1 fallback por tabla." B1 seeds exactly one `is_fallback=True` per category table.
- **Assessment:** The spec relies on seed data as the sole defense. This is a Cat 4
  (unstated precondition) fragility. If an admin accidentally deletes or deactivates the
  fallback category via the API (B14), or if a migration runs incorrectly, the entire
  classification pipeline crashes on every LLM output that requires fallback.
- **Recommendation:** Replace the bare `next()` with `next(..., None)` and handle
  the `None` case explicitly:
  ```python
  fallback_action = next((c for c in action_categories if c.is_fallback), None)
  if fallback_action is None:
      raise ConfigurationError("No fallback ActionCategory found -- check DB seed data")
  ```
  Additionally, the `DELETE /api/categories/actions/{id}` endpoint (B14) should refuse
  to delete a category with `is_fallback=True` -- not just check FK usage.

---

## 2. Suggestion-Level Findings

### SUGGESTION-01: Health endpoint information disclosure

- **Blocks:** B13 (API Core)
- **Description:** `GET /api/v1/health` requires no authentication and returns detailed
  adapter status including adapter names, connection status, latency, and error messages.
  Error messages from adapter `test_connection()` failures may leak internal infrastructure
  details (Redis hostnames, PostgreSQL connection strings, Slack workspace names).
- **Spec note:** The spec justifies no-auth: "monitoring tools necesitan acceder sin auth."
  The status is always HTTP 200 (not 503).
- **Recommendation:** Sanitize error messages in `AdapterHealthItem.error` to generic
  strings ("connection failed", "timeout", "auth error") rather than passing through raw
  exception messages. Alternatively, return detailed errors only when the request includes
  a valid Bearer token; return only status ("ok"/"degraded"/"unavailable") without error
  details for unauthenticated requests.

### SUGGESTION-02: API key defaults as empty strings

- **Blocks:** B0 (Scaffolding)
- **Description:** In `Settings`, `openai_api_key`, `anthropic_api_key`, `gmail_client_id`,
  `gmail_client_secret`, `slack_bot_token`, `slack_signing_secret`, and
  `hubspot_access_token` all default to `""` (empty string). This means the application
  starts successfully without any external service credentials configured. Calls to these
  services will fail at runtime with potentially confusing error messages instead of
  failing fast at startup.
- **Contrast:** `jwt_secret_key` and `database_url` correctly use `Field(...)` (required,
  no default), which forces the application to fail at startup if missing.
- **Recommendation:** For production deployments, consider adding a startup validation
  step (in `lifespan()` of B13) that warns if critical integration keys are empty. Do not
  make them required (the system should start without Gmail configured for local dev), but
  log a clear WARNING: "OPENAI_API_KEY is empty -- LLM classification will fail."

### SUGGESTION-03: `_check_adapter` uses `Any` type

- **Blocks:** B13 (API Core)
- **Description:** The health check helper `_check_adapter(name: str, adapter: Any)` uses
  `Any` for the adapter parameter. This is the only `Any` in the API layer and is
  acknowledged in the spec with a recommendation to use a `Protocol` type.
- **Recommendation:** Define `HasTestConnection` Protocol in `src/adapters/` and use it
  as the type for `_check_adapter`. This closes the last `Any` gap in the API layer and
  enables mypy to verify that all adapters passed to health checks actually implement
  `test_connection()`.

### SUGGESTION-04: Prompt injection layer count discrepancy

- **Blocks:** B8 (Classification Service)
- **Description:** Architecture directive D16 references "4-layer architecture (Sec 11.2)"
  for prompt injection defense. B8 implements 5 layers: (1) system prompt with data-only
  instruction, (2) category definitions from DB, (3) few-shot examples from feedback,
  (4) DATA delimiters around email content, (5) post-LLM validation. The 5th layer
  (post-LLM validation) was not in the original FOUNDATION.md Sec 11.2 design.
- **Assessment:** The 5th layer is a beneficial addition, not a security concern. The spec
  evolved beyond the original design in a positive direction.
- **Recommendation:** Update D16 reference in DECISIONS.md to reflect "5-layer" (not
  "4-layer") to maintain documentation consistency. Alternatively, document that Layer 5
  was added during spec design as a defense-in-depth improvement.

### SUGGESTION-05: CORS wildcard risk documentation

- **Blocks:** B13 (API Core), B0 (Scaffolding)
- **Description:** `cors_origins` defaults to `["http://localhost:5173"]` in Settings.
  The spec includes a verification check: `grep -n 'CORS_ALLOWED_ORIGINS.*\*'
  src/core/config.py` must return empty. B13's load-bearing defaults table documents
  the consequence: "`[\"*\"]` en produccion expone la API a cualquier origen."
- **Assessment:** The defense is correctly specified. However, there is no runtime
  validation that prevents an admin from setting `CORS_ORIGINS=*` via env var. Pydantic
  will happily accept `["*"]` as a valid `list[str]`.
- **Recommendation:** Add a Pydantic `field_validator` on `cors_origins` that rejects
  `"*"` as a list element, or at minimum logs a WARNING at startup if `"*"` is detected.

---

## 3. Info-Level Findings

### INFO-01: `useRef` for access token -- browser console accessibility

- **Blocks:** B15 (Frontend Shell)
- **Spec question:** "Consultar Sentinel para revisar...confirmar que este patron
  efectivamente previene XSS vs localStorage, y que la referencia no es accesible desde
  la consola del browser."
- **Assessment:** `useRef` stores the token in a JavaScript variable within the React
  component tree's closure. It is NOT directly accessible via `localStorage` or
  `sessionStorage` (confirmed protection against XSS token theft via storage APIs).
  However, a determined attacker with console access CAN access React internals
  (`__REACT_DEVTOOLS_GLOBAL_HOOK__`, fiber tree inspection) to extract the ref value.
  This is expected and acceptable: if an attacker has console access, they already have
  the full session context. The threat model for `useRef` is XSS script injection
  (mitigated: scripts cannot read refs without React internals knowledge), not physical
  access to the browser console.
- **Verdict:** `useRef` is the correct pattern for SPA access tokens. Strictly superior
  to `localStorage` for XSS defense. The remaining exposure (console access) is inherent
  to any in-memory JavaScript storage and is not mitigable in a SPA.

### INFO-02: Redis DB index separation for Celery

- **Blocks:** B12 (Pipeline)
- **Spec question:** "Consultar Sentinel para revisar la configuracion de
  `CELERY_RESULT_BACKEND` compartiendo Redis...confirmar separacion de DB indices (broker
  en /0, backend en /1) es suficiente o se requiere namespace adicional."
- **Assessment:** Redis DB indices (`/0` for broker, `/1` for result backend) provide
  complete keyspace isolation. Keys in DB 0 are invisible to DB 1 and vice versa. This
  is sufficient for preventing interference between broker messages and task results.
  No additional keyspace prefix is needed. The `CELERY_RESULT_EXPIRES=3600` TTL on the
  result backend prevents memory accumulation.
- **Verdict:** Current design is sufficient. No additional namespacing required.

### INFO-03: CRMAuthError no-retry decision

- **Blocks:** B10 (CRM Sync), B12 (Pipeline)
- **Spec question:** "Consultar Sentinel para revisar CRMAuthError no-retry decision risk."
- **Assessment:** `CRMAuthError` indicates invalid credentials (expired token, revoked
  access). Retrying with the same credentials will produce the same error. The no-retry
  decision is correct: retrying auth failures wastes queue capacity and delays legitimate
  tasks. The risk of a transient auth error (e.g., HubSpot token rotation race condition)
  is mitigated by the dashboard's manual retry capability (B13
  `POST /api/emails/{id}/retry`). If the admin fixes credentials and retries, the next
  attempt succeeds.
- **Verdict:** No-retry for `CRMAuthError` is the correct decision. The manual retry
  path via the dashboard is the appropriate recovery mechanism.

### INFO-04: OAuth2 token persistence strategy

- **Blocks:** B3 (Email Adapter)
- **Spec question:** "Consultar Sentinel para revisar OAuth2 token refresh + persistence
  in gmail.py."
- **Assessment:** B3 specifies a `_save_credentials` callback pattern for persisting
  refreshed OAuth2 tokens. The credentials file path is configurable via
  `GMAIL_TOKEN_FILE`. The spec correctly separates credential management from the adapter
  logic. The risk areas are:
  - Token file must be in a directory not served by the web server (covered by Docker
    volume isolation).
  - Token file must be gitignored (covered by `.gitignore` for `secrets/`).
  - Token refresh must be atomic (write to temp file, then rename) to prevent corruption
    during concurrent refreshes.
- **Recommendation for implementation:** Use `tempfile` + `os.rename()` for atomic writes
  when persisting refreshed OAuth2 tokens.

### INFO-05: HubSpot Private App Token storage

- **Blocks:** B6 (CRM Adapter)
- **Spec question:** "Consultar Sentinel para revisar HubSpot Private App Token: env var
  vs secrets/ directory."
- **Assessment:** The token is loaded via `HUBSPOT_ACCESS_TOKEN` env var in Settings.
  This is the standard pattern for the project (all API keys via env vars). The `secrets/`
  directory alternative (Docker secrets) is a more secure option for production but adds
  complexity. For the current single-tenant model (D18), env var storage is acceptable.
- **Verdict:** Env var is sufficient for Phase N. If the project scales to multi-tenant,
  revisit with Docker secrets or a vault integration.

### INFO-06: `ClassificationResult` naming collision

- **Blocks:** B1 (Models), B4 (LLM Adapter), B8 (Classification Service)
- **Description:** Three distinct types share the name `ClassificationResult`:
  1. `src/models/classification.py` -- SQLAlchemy model (DB persistence)
  2. `src/adapters/llm/schemas.py` -- Pydantic BaseModel (adapter boundary)
  3. `src/services/schemas/classification.py` -- `ClassificationServiceResult` (service layer)
- **Assessment:** B8 explicitly addresses this: "alias `AdapterClassificationResult`" and
  "ClassificationResult del adapter (B4) y ClassificationResult modelo DB (B1) nunca
  confundidos." B8's exit conditions include a verification that imports are clearly
  separated. The service layer uses `ClassificationServiceResult` (distinct name).
- **Verdict:** The spec handles this correctly. The naming collision is documented and
  the mitigation (aliased imports, distinct service result type) is prescribed.

---

## 4. Cross-Block Fragility Analysis (pre-mortem)

### Cat 1 -- Implicit Ordering

| Fragility | Blocks | What Breaks | Spec Hardening |
|-----------|--------|-------------|----------------|
| Pipeline task execution order | B12, B7-B11 | Task N runs before N-1 commits | Each task verifies email state precondition via `transition_to()`. Chain built in single function `run_pipeline`. No `link` -- explicit `.delay()` after commit. |
| Routing rule evaluation order | B9 | Rules evaluated out of priority order | `RuleEngine` receives rules pre-sorted by `priority ASC`. Frontend reorder (B16, B17) emits full ordered array. |
| Category deletion vs classification | B14, B8 | Delete category referenced by active classifications | Explicit count query before DELETE, HTTP 409 with `affected_email_count`. |

**Assessment:** Cat 1 is well-hardened across all specs. The state machine + `transition_to()` pattern is the primary defense and is consistently applied.

### Cat 3 -- Stringly-Typed

| Fragility | Blocks | What Breaks | Spec Hardening |
|-----------|--------|-------------|----------------|
| Classification categories | B1, B8 | LLM hallucinates invalid category slug | FK to `ActionCategory.id` and `TypeCategory.id`. Post-LLM validation against DB slugs (Layer 5). Fallback on mismatch. |
| Routing conditions | B1, B9 | Free-form condition fields | `RoutingConditions` TypedDict with defined `field` and `operator` values. `RoutingConditionSchema` (Pydantic) at API boundary (B13). |
| Email state values | B1 | Invalid state written to DB | PostgreSQL ENUM type rejects values outside `EmailState`. |

**Assessment:** Cat 3 is comprehensively addressed. DB-backed enums + FK validation at the data layer, Pydantic validation at the API layer.

### Cat 4 -- Unstated Preconditions

| Fragility | Blocks | What Breaks | Spec Hardening |
|-----------|--------|-------------|----------------|
| LLM output shape assumptions | B4, B8 | LLM returns unexpected format | Parser handles 7 documented shapes. Fallback on any parse failure. `raw_llm_output` always preserved. |
| Fallback category existence | B8, B1 | No `is_fallback=True` category in DB | DB seed provides fallback categories. **Gap: no runtime guard if seed data is deleted** (see WARNING-03). |
| `body_snippet` truncation precondition | B11 | Full body passed to LLM instead of snippet | Field name `body_snippet` (not `body`) encodes the precondition. Caller truncates before constructing `EmailContent`. |
| Categories changed between load and validate | B8 | Category valid at prompt build, invalid at validation | Categories reloaded from DB each classification call. |

**Assessment:** Cat 4 is well-documented. The main gap is WARNING-03 (fallback category existence guard).

### Cat 6 -- Non-Atomic Operations

| Fragility | Blocks | What Breaks | Spec Hardening |
|-----------|--------|-------------|----------------|
| Pipeline stage independence | B12, B7-B11 | Failure at stage N rolls back N-1 | Each stage commits independently (D13). Explicit `.delay()` after commit. No `link` chains. |
| Routing action independence | B9 | One dispatch failure reverts successful dispatches | Each `RoutingAction` has own `db.commit()`. `dispatch_id` idempotency prevents duplicates on retry. |
| Draft generation + Gmail push | B11 | Gmail push fails, draft lost | `db.commit()` before Gmail push. Push failure = `DRAFT_GENERATED` (not `DRAFT_FAILED`). |
| CSV export mid-stream failure | B14 | DB error during streaming breaks response | Generator catches `SQLAlchemyError`, logs, and terminates stream gracefully. |

**Assessment:** Cat 6 is the most thoroughly addressed fragility category across the spec set. The "commit before enqueue" pattern is consistently applied.

### Cat 8 -- Load-Bearing Defaults

| Fragility | Blocks | What Breaks | Spec Hardening |
|-----------|--------|-------------|----------------|
| All 14+ defaults from Appendix C | B0 | Hardcoded values prevent operational tuning | All defaults configurable via env vars in `Settings`. Documented in load-bearing defaults tables per spec. |
| `lock_ttl >= poll_interval` | B12 | Concurrent polls for same account | Assertion at scheduler startup (fail-fast). |
| `CELERY_RESULT_EXPIRES` | B12 | Redis OOM from accumulated results | Default 3600s. Documented consequence of `None`. |
| LLM temperature values | B0, B4, B8, B14 | Classification inconsistency or draft quality degradation | Range-validated in Pydantic schema (0.0-2.0). Separate values for classify (0.1) and draft (0.7). |

**Assessment:** Cat 8 is comprehensively addressed. Every spec with configurable values includes a load-bearing defaults table with env var name, default value, and consequence of misconfiguration. This is exemplary documentation.

### Cat 9 -- Implicit Resource Lifecycle

| Fragility | Blocks | What Breaks | Spec Hardening |
|-----------|--------|-------------|----------------|
| Scheduler lock TTL | B12 | Lock expires before processing completes | `lock_ttl >= poll_interval` assertion. TTL via `SET NX EX` atomic. |
| Celery result backend accumulation | B12 | Redis OOM | `CELERY_RESULT_EXPIRES=3600`. Business results in DB, not result backend. |
| Redis lock release on crash | B12 | Lock held indefinitely | TTL-based expiration as fallback. `finally` block for normal release. |

**Assessment:** Cat 9 is addressed with appropriate TTL-based lifecycle management.

### Cat 10 -- Version-Coupled

| Fragility | Blocks | What Breaks | Spec Hardening |
|-----------|--------|-------------|----------------|
| SDK version pinning | B0 | Breaking changes in LiteLLM, slack-sdk, hubspot-api-client | D15 mandates pinning in `pyproject.toml`. B0 lists all dependencies. |
| Pydantic v2 Generic BaseModel | B13 | `PaginatedResponse[T]` may require `model_rebuild()` | Spec acknowledges: "Pydantic v2 may require `model_rebuild()` for named OpenAPI schema." |

**Assessment:** D15 is referenced but implementation verification is deferred to build time. The spec awareness is present.

---

## 5. Architecture Directive Coverage

The following table maps each of the 18 architecture directives to the specs that
reference or implement them. A directive is considered "covered" if at least 2 specs
reference it meaningfully (not just listing it as applicable).

| Directive | Description | Specs Referencing | Coverage |
|-----------|-------------|-------------------|----------|
| D1 | No `dict[str, Any]` at adapter boundaries | B0, B1, B3, B4, B5, B6, B7, B8, B9, B10, B11, B13, B14 | STRONG |
| D2 | LLM adapter returns typed results, not raw `ModelResponse` | B4, B8, B11 | ADEQUATE |
| D3 | Celery task results as typed dataclasses via DB/Redis | B7, B8, B9, B10, B11, B12 | STRONG |
| D4 | Frontend auto-generated TypeScript types from OpenAPI | B15, B16, B17 | ADEQUATE |
| D5 | Adapter specs document invariants, guarantees, errors | B3, B4, B5, B6 | STRONG |
| D6 | Pipeline state transitions document pre/postconditions | B1, B7, B8, B9, B10, B11, B12 | STRONG |
| D7 | External-state operations use structured try/except | B2, B3, B4, B5, B6, B7, B8, B9, B10, B11, B12, B13, B14 | STRONG |
| D8 | Local computation uses conditionals, not try/except | B0, B4, B5, B8, B9, B11, B12 | STRONG |
| D9 | Each pipeline stage defines retry/backoff/fallback | B7, B8, B9, B10, B11, B12 | STRONG |
| D10 | State machine transitions enforced via DB enum | B1, B7, B8, B9, B10, B11, B12 | STRONG |
| D11 | Routing conditions and categories as DB-backed enums/FKs | B1, B8, B9, B13, B14 | STRONG |
| D12 | LLM output shape assumptions documented + validation layer | B4, B8 | ADEQUATE |
| D13 | Each pipeline stage commits independently | B7, B8, B9, B10, B11, B12 | STRONG |
| D14 | Load-bearing defaults configurable via env/config | B0, B2, B4, B5, B6, B7, B8, B9, B10, B11, B12, B13, B14 | STRONG |
| D15 | Pin all SDK versions in pyproject.toml | B0 | MINIMAL (single spec) |
| D16 | Prompt injection defense: multi-layer architecture | B4, B8, B11 | ADEQUATE |
| D17 | PII never in logs, reference by email_id only | B0, B7, B8, B12, B14 | STRONG |
| D18 | Single-tenant: CORS, rate limiting, input validation | B2, B13, B14, B15 | ADEQUATE |

### Coverage Summary

- **STRONG (13 directives):** D1, D3, D5, D6, D7, D8, D9, D10, D11, D13, D14, D17
  -- referenced by 4+ specs each with specific implementation guidance.
- **ADEQUATE (4 directives):** D2, D4, D12, D16, D18 -- referenced by 2-3 specs.
  Coverage is sufficient but concentrated in fewer specs.
- **MINIMAL (1 directive):** D15 -- only referenced in B0. Version pinning is a
  project-wide concern that should be verified during the build block, not just in
  scaffolding.

### D15 Gap Analysis

D15 (version pinning) is only explicitly referenced in B0. Each adapter spec (B3, B4, B5,
B6) names its SDK dependency but does not explicitly state "pin version X.Y.Z in
pyproject.toml." This is low-risk because B0's `pyproject.toml` is the single source of
truth for all dependencies, but the per-adapter specs should ideally include a note like
"Requires slack-sdk>=2.x pinned in pyproject.toml per D15."

---

## 6. Dimension-by-Dimension Assessment

### Dim 1: Compliance of Adapter Contracts (Sec 9.2-9.5)

All four adapter families have complete contract-docstrings in the 4-question format:

| Adapter | Spec | Methods | Contract Quality |
|---------|------|---------|-----------------|
| Email (Gmail) | B3 | 7 ABC methods | Complete: invariants, guarantees, errors, silenced |
| Channel (Slack) | B5 | 4 ABC methods | Complete |
| CRM (HubSpot) | B6 | 7 ABC methods | Complete |
| LLM (LiteLLM) | B4 | 3 ABC methods | Complete |

All adapter boundaries produce typed outputs (Pydantic models or frozen dataclasses).
No `dict[str, Any]` escapes any adapter boundary.

### Dim 2: Pipeline Security (Sec 11.2, 11.4)

- **Prompt injection defense:** 5-layer architecture in B8 (exceeds D16's 4-layer
  requirement). System prompt never contains email content. DATA delimiters are
  constants. Post-LLM validation against DB categories. Heuristics never override LLM.
- **PII in logs:** Consistently enforced across B0, B7, B8, B12, B14. All log statements
  reference emails by `email_id` only. B14 documents `LogEntry.context: dict[str, str]`
  with values restricted to IDs and slugs by PII policy.
- **HITL constraint:** B11 architecturally prohibits automatic sending. Exit conditions
  include a grep verification for `send_message`/`auto_send`/`send_after`. The system
  only creates drafts, never sends.

### Dim 3: Exception Safety

Every spec classifies operations as external-state (try/except) or local computation
(conditionals). The taxonomy is consistently applied:

- **Zero try/except in pure computation modules:** B8 mandates grep verification that
  `prompt_builder.py` and `heuristics.py` have 0 try blocks.
- **Top-level except Exception only in Celery tasks:** B12 specifies exactly 5 matches
  (one per task) with grep verification.
- **Thin routers without try/except:** B13 mandates grep verification that routers
  (except health) have 0 try blocks.

### Dim 4: State Machine Integrity

- **DB enum enforcement:** EmailState is a PostgreSQL ENUM (not VARCHAR). Invalid values
  rejected at the DB level.
- **`transition_to()` validation:** All state changes go through the model method.
  `VALID_TRANSITIONS` dict defines the complete transition graph.
- **Recovery paths:** Error states (CLASSIFICATION_FAILED, etc.) can transition back to
  the appropriate retry state.
- **No state skipping:** The transition graph does not allow FETCHED -> CLASSIFIED
  (must go through SANITIZED).

### Dim 5: Configuration Security

- **All 14+ defaults externalized:** Every load-bearing default has an env var, a
  documented default value, and a documented consequence of misconfiguration.
- **Required vs optional:** `jwt_secret_key` and `database_url` are required (no default).
  Integration API keys default to empty string (see SUGGESTION-02).
- **Range validation:** Temperature values validated to [0.0, 2.0] in Pydantic schemas.
  Pagination limits validated (ge=1, le=100).

### Dim 6: Dependency Health

- **SDK selection:** All SDKs are official/maintained: `google-api-python-client` (Google),
  `slack-sdk` (Slack), `hubspot-api-client` (HubSpot), `litellm` (BerriAI).
- **Version pinning:** D15 mandates pinning in pyproject.toml but specific versions are
  not listed in specs (deferred to implementation).
- **No deprecated dependencies:** PostgreSQL MCP rejected, Slack MCP skipped (both
  archived). HubSpot MCP deferred (beta).

### Dim 7: Data Contract Validation

- **Pydantic models at all boundaries:** API request/response schemas, adapter
  input/output schemas, and service layer schemas are all Pydantic BaseModel or frozen
  dataclasses.
- **TypedDict for JSONB:** B1 defines TypedDict for all JSONB columns (RecipientData,
  AttachmentData, RoutingConditions, RoutingActions). Only `raw_llm_output: dict` is
  intentionally untyped.
- **OpenAPI codegen:** B15 generates TypeScript types from the FastAPI OpenAPI spec.
  Manual type duplication is prohibited.

---

## 7. Recommendations

### Priority 1 (implement during affected block)

1. **B8/B14:** Guard against missing fallback category (WARNING-03). Replace bare
   `next()` with `next(..., None)` + explicit `ConfigurationError`. Prevent deletion
   of `is_fallback=True` categories via the API.

2. **B14:** Define and enforce LLM model allowlist (WARNING-01). Add
   `LLM_ALLOWED_MODELS` to Settings. Validate in `IntegrationService` before persisting.

3. **B11:** Add max-length validation and startup warning for `DRAFT_ORG_SYSTEM_PROMPT`
   (WARNING-02).

### Priority 2 (implement during integration/hardening)

4. **B13:** Sanitize health check error messages for unauthenticated requests
   (SUGGESTION-01).

5. **B13:** Replace `adapter: Any` with `HasTestConnection` Protocol in
   `_check_adapter` (SUGGESTION-03).

6. **B0/B13:** Add startup warnings for empty API keys (SUGGESTION-02).

7. **DECISIONS.md:** Update D16 from "4-layer" to "5-layer" prompt injection defense
   (SUGGESTION-04).

### Priority 3 (documentation/hygiene)

8. **B0:** Add CORS wildcard rejection validator (SUGGESTION-05).

9. **D15:** Add version pinning notes to individual adapter specs (B3, B4, B5, B6).

---

## 8. Open Questions Resolved

This review resolves the following open questions from `docs/SCRATCHPAD.md` that were
addressed to Sentinel:

| Question | Source | Resolution |
|----------|--------|------------|
| B03: OAuth2 token refresh + persistence | SCRATCHPAD | INFO-04: Use atomic writes (tempfile + rename). Callback pattern is correct. |
| B06: HubSpot Private App Token: env var vs secrets/ | SCRATCHPAD | INFO-05: Env var sufficient for single-tenant (D18). |
| B08: 5-layer prompt injection defense | SCRATCHPAD | SUGGESTION-04: 5th layer is beneficial addition. Update D16 docs. |
| B10: CRMAuthError no-retry decision risk | SCRATCHPAD | INFO-03: No-retry is correct. Manual retry via dashboard is the recovery path. |
| B11: DRAFT_ORG_SYSTEM_PROMPT injection risk | SCRATCHPAD | WARNING-02: Low risk in single-tenant, but add validation guards. |
| B12: Redis DB index separation | SCRATCHPAD | INFO-02: DB indices provide complete keyspace isolation. Sufficient. |
| B13: CORS posture | SCRATCHPAD | SUGGESTION-05: Add wildcard rejection validator. |
| B14: LLM model allowlist validation | SCRATCHPAD | WARNING-01: Must implement allowlist. Define `LLM_ALLOWED_MODELS` in Settings. |
| B15: useRef for access token accessibility | SCRATCHPAD | INFO-01: useRef is correct pattern. Superior to localStorage for XSS. Console access is inherent to any JS storage. |

---

## Appendix: Methodology

This review was conducted by reading all 18 block specs (B0-B17) in their entirety,
cross-referencing against:

- 18 architecture directives (D1-D18) from `docs/DECISIONS.md`
- Pre-mortem fragility categories (Cat 1, 3, 4, 6, 8, 9, 10)
- OWASP Top 10 for LLM Applications (prompt injection, model manipulation)
- OWASP MCP Top 10 (tool poisoning, excessive permissions)
- FOUNDATION.md Sections 9 (Adapters), 11 (Security), 12 (Performance)

Findings classified by severity:
- **CRITICAL:** Exploitable vulnerability with immediate impact. None found.
- **WARNING:** Design weakness that could lead to security incidents under specific
  conditions. 3 found.
- **SUGGESTION:** Improvement opportunity that strengthens defense in depth. 5 found.
- **INFO:** Informational note, resolved question, or acknowledgment of correct design.
  6 found.
