# Block 01 -- Sentinel Review

**Reviewer:** Sentinel (opus)
**Date:** 2026-02-20
**Scope:** `docs/specs/block-01-models.md` -- Database Models & Migrations
**Methodology:** contract-docstrings (D5-D6), pre-mortem (Cat 1, Cat 3), tighten-types (D1)
**Cross-references:** FOUNDATION.md Appendix B + Sec 4.2/4.3, existing code in `src/models/`, Phase 4 security review

---

## contract-docstrings Findings

### transition_to() Contract Specification

- [PASS] **Input invariants documented.** The spec docstring states: "`self.state` is the current persisted state of the email" and "`new_state` must be reachable from `self.state` via `VALID_TRANSITIONS`." Both are accurate preconditions that the code actually enforces. The already-implemented code in `src/models/email.py` lines 137-163 matches the spec exactly.

- [PASS] **Return guarantees documented.** "If the transition is valid, `self.state` is updated to `new_state`." This is a simple in-memory mutation with no ambiguity. The guarantee is minimal and correct -- there is nothing else to promise.

- [PASS] **Errors raised documented.** "Raises `InvalidStateTransitionError` if `new_state` is not in `VALID_TRANSITIONS[self.state]`." The exception is defined in `src/core/exceptions.py` with a docstring explicitly marking it as a programmer error. The error message includes `self.id`, `self.state`, `new_state`, and the allowed set -- sufficient for debugging.

- [PASS] **External state mutations documented.** "The DB commit is the caller's responsibility -- this method only mutates the in-memory object." This is the single most important line in the contract. Without it, a developer might assume `transition_to()` persists the change. The SCRATCHPAD reinforces this: "`transition_to()` outside try/except -- failure is a logic bug."

- [PASS] **State transitions documented.** "`self.state = new_state` (in-memory only; caller must commit to DB)." Clear and accurate.

- [WARN] **Implicit precondition: `self.state` must be a valid `EmailState`.** The code uses `VALID_TRANSITIONS.get(self.state, frozenset())`, which silently returns an empty frozenset if `self.state` is somehow not in the dict. If SQLAlchemy loads an `Email` whose DB enum was extended but `EmailState` Python enum was not updated (e.g., after a partial migration), `self.state` could be a value not present in `VALID_TRANSITIONS`. The `get(..., frozenset())` fallback would then reject ALL transitions from that state with no indication that the issue is a stale Python enum, not an invalid transition. This is an edge case that only manifests during schema evolution (adding a new state to the DB enum without updating the Python enum). **Severity: LOW** -- this would only occur during a migration mishap and is caught immediately by `InvalidStateTransitionError`. However, the error message would be misleading ("Allowed: frozenset()" implies no transitions exist, rather than "unknown state").

### Other Models -- Contract Docstring Necessity

- [INFO] **Category models, User, Draft, CRMSyncRecord, ClassificationFeedback:** These are data models with no business logic methods. Contract docstrings are not needed at the model level -- they become relevant when service-layer code operates on these models (B8 for classification, B9 for routing, B10 for CRM sync, B11 for drafts). The spec correctly focuses contract documentation on `transition_to()`, the only method with a non-trivial contract in B01.

- [INFO] **ClassificationResult model docstring.** The spec includes a disambiguation note: "No confundir con el dataclass `ClassificationResult` del LLM adapter (`src/adapters/llm/types.py`)." This is valuable documentation that prevents a real confusion risk identified in Phase 4 (INFO-06 in the security review). The implemented code should preserve this note.

---

## pre-mortem Findings

### Cat 1 -- Implicit Ordering

- [PASS] **`VALID_TRANSITIONS` uses `frozenset` (immutable).** The transition targets are `frozenset[EmailState]`, which prevents accidental mutation. The outer dict is typed as `dict[EmailState, frozenset[EmailState]]`. The dict itself is module-level and conventionally immutable (Python does not enforce this on dicts, but the pattern is standard and the frozenset values are truly immutable). Already implemented in `src/models/email.py` lines 51-65.

- [PASS] **`EmailState` is a PostgreSQL ENUM.** The spec mandates `sa.Enum(EmailState, name="emailstate", create_type=True)`. The implemented code at line 122-127 uses exactly this pattern. The DB will reject any `INSERT`/`UPDATE` with a value outside the enum, providing a second enforcement layer independent of Python code.

- [PASS] **All 12 states are present in `VALID_TRANSITIONS`.** Every `EmailState` member has a corresponding entry in the dict. No state is missing, which means `VALID_TRANSITIONS.get()` will never fall through to the default `frozenset()` for any legitimate state. Verified by inspection of both spec and implemented code.

- [PASS] **Recovery paths are correct.** Error states transition back to the last successful state (not to the state that would have been next). Example: `CLASSIFICATION_FAILED -> SANITIZED` (retry classification), not `CLASSIFICATION_FAILED -> CLASSIFIED` (which would skip the retry). This is semantically correct -- the recovery path repeats the failed step.

- [WARN] **Direct `email.state = EmailState.CLASSIFIED` assignment is not prevented by the model.** SQLAlchemy does not support Python-level property protection that would force all state mutations through `transition_to()`. Any code with access to an `Email` instance can bypass the state machine by directly assigning to `email.state`. The spec acknowledges this is enforced by convention and code review, not by the model itself.

  **Risk assessment:** MEDIUM during development, LOW in production (once code review establishes the pattern). The primary mitigation is the test suite (`tests/models/test_email_state.py`) which verifies that valid transitions work through `transition_to()` and invalid ones raise. However, no test can prevent a future developer from writing `email.state = EmailState.CLASSIFIED` in a service. The risk is that a developer unfamiliar with the pattern bypasses the state machine in a new service method, and code review misses it.

  **Existing mitigations:**
  1. The `InvalidStateTransitionError` docstring explicitly says "callers MUST NOT catch it in a try/except block."
  2. SCRATCHPAD documents "`transition_to()` outside try/except -- failure is a logic bug."
  3. Multiple spec exit conditions (B7-B12) include grep verification that state changes go through `transition_to()`.

  **Additional hardening (SUGGESTION):** Add a grep-based exit condition to B01 itself that verifies no code outside `transition_to()` directly assigns to `.state` on Email instances. This would be: `grep -rn 'email\.state\s*=' src/ --include='*.py' | grep -v 'transition_to' | grep -v 'default=EmailState'` should return only the model definition and `transition_to`. This creates a standing verification that future blocks can replicate.

### Cat 3 -- Stringly-Typed

- [PASS] **Classification categories are FK-backed.** `ClassificationResult.action_category_id` is a `UUID ForeignKey("action_categories.id")` and `ClassificationResult.type_category_id` is a `UUID ForeignKey("type_categories.id")`. No free-form string column exists for classification categories. An LLM that hallucinates an invalid category slug will fail at the FK constraint when the service attempts to insert a `ClassificationResult` with a non-existent category ID. This is the correct layered defense: Python validation first (in B08 classification service), DB FK constraint as backstop.

- [PASS] **`EmailState` is not stringly-typed.** Despite being `str, enum.Enum`, the DB stores it as a PostgreSQL ENUM type (not VARCHAR). The `str` base class is for serialization convenience (JSON, logs), not for storage. The DB rejects invalid enum values regardless of what Python sends.

- [WARN] **`RoutingAction.channel` is `sa.String(50)` -- stringly-typed risk.** The spec defines `channel` as a free-form string column that holds values like `"slack"`, `"email"`, `"hubspot"`. This is a Cat 3 (stringly-typed) pattern. If a developer misspells `"slcak"` or a new channel name is introduced inconsistently, the DB will accept it without complaint.

  **Analysis of alternatives:**
  - **Python Enum + DB ENUM:** Would enforce valid values but requires a migration every time a new channel is added. Since routing channels are meant to be extensible (new adapters can be added per Sec 9), a DB ENUM creates friction for extensibility.
  - **FK to a `channels` table:** Stronger validation, but the project does not have a channels configuration table in B01. Adding one would expand the scope.
  - **Pydantic `Literal` validation at the API boundary (B13):** This is the current mitigation path -- `RoutingConditionSchema` validates channel values at the API layer. The DB is the persistence layer, not the validation layer, for channel names.

  **Recommendation:** Accept the `String(50)` for `RoutingAction.channel` in B01. The validation responsibility is correctly placed at the API/service layer (B09, B13), not the data model. Document this as a deliberate design decision in the `RoutingAction` model docstring: "Channel is validated at the service layer, not by DB constraint, to allow extensibility without migrations." If the project later needs stricter enforcement, a `channels` config table can be added as a non-breaking change.

- [PASS] **`RoutingConditions` and `RoutingActions` TypedDicts restrict field semantics.** The `field` key in `RoutingConditions` documents allowed values (`"action_category" | "type_category" | "sender_domain" | "subject_contains"`) and `operator` documents (`"eq" | "contains" | "in" | "not_in"`). These are TypedDict-level documentation, not enforcement (JSONB is schema-less), but the Pydantic schema at the API boundary (B13/B14) will enforce these values. The spec correctly places validation at the boundary, not the storage layer.

- [WARN] **`RecipientData.type` is `str` with comment `# "to" | "cc" | "bcc"`.** This is a minor stringly-typed instance. The comment documents the intended values but nothing enforces them. Since recipients are ingested from Gmail (B03) and never user-edited via the API, the risk is that a new email provider returns a different recipient type string (e.g., `"replyTo"`). The impact is low: an unrecognized type would be stored and displayed but would not break any logic (no code branches on `RecipientData.type` in the current spec set).

  **Recommendation:** Accept as-is for B01. If recipient type branching is ever added, upgrade to `Literal["to", "cc", "bcc"]` in the TypedDict. For now, the comment is sufficient documentation.

---

## tighten-types Findings

### TypedDict Policy Compliance

- [PASS] **`RecipientData` TypedDict for `Email.recipients` JSONB.** Defined in `src/models/email.py` lines 68-73. Matches the spec.

- [PASS] **`AttachmentData` TypedDict for `Email.attachments` JSONB.** Defined in `src/models/email.py` lines 76-82. Matches the spec. Note: FOUNDATION.md Appendix B.1 uses `name`, `type`, `size` for attachments, while the spec/implementation uses `filename`, `mime_type`, `size_bytes`, `attachment_id`. The spec's version is more precise (avoids ambiguity of `type` and `size`). This is an intentional improvement over the FOUNDATION contract and is consistent -- both spec and code agree.

- [PASS] **`RoutingConditions` TypedDict for `RoutingRule.conditions` JSONB.** Defined in the spec. The `value` field is typed `str | list[str]` which accurately reflects the dual nature (single match vs. multi-match operators).

- [PASS] **`RoutingActions` TypedDict for `RoutingRule.actions` JSONB.** Defined in the spec. `template_id: str | None` correctly allows nullable optional templates.

- [PASS] **`Email.provider_labels` is `Mapped[list[str]]` -- no TypedDict needed.** Simple string list, correctly identified in the spec's TypedDict Policy table as not requiring a TypedDict.

- [PASS] **`ClassificationResult.raw_llm_output` is `Mapped[dict]`.** Intentionally untyped (raw LLM JSON output). The spec explicitly documents this exception: "raw output -- sin TypedDict, intencional: es el output crudo del LLM antes de parsear." This is the correct decision -- the raw output is preserved for debugging, and its structure varies by LLM provider.

- [WARN] **`ClassificationResult.raw_llm_output: Mapped[dict]` -- bare `dict` without type parameters.** While intentionally untyped at the semantic level, the Python annotation `Mapped[dict]` is equivalent to `Mapped[dict[str, Any]]` in mypy's eyes. The spec acknowledges this exception. However, for mypy strictness, `Mapped[dict[str, Any]]` would be the explicit form. The bare `dict` annotation works with mypy's default settings but may trigger warnings under `--disallow-any-generics`. **Recommendation:** Use `Mapped[dict[str, Any]]` with an inline comment explaining the intentional lack of structure, or suppress with `# type: ignore[type-arg]` if mypy is configured with strict generics. This is a hygiene issue, not a correctness issue.

### Mapped[] Usage

- [PASS] **All model fields use `Mapped[type]` (SA 2.0 style).** No pre-SA2.0 `Column(String)` patterns exist in the spec or the already-implemented code. Every field is `Mapped[T] = mapped_column(...)`. This enables full mypy coverage of model attributes.

### No `dict[str, Any]` at Model Signatures

- [PASS] **No model method accepts or returns `dict[str, Any]`.** The only method is `transition_to(self, new_state: EmailState) -> None`, which is fully typed. The JSONB fields use TypedDicts (documented exceptions noted above). No `dict[str, Any]` escapes any model boundary.

---

## Additional Findings

### WARN-01: Seed Data Category Slug Divergence from FOUNDATION.md

- **Severity:** WARNING
- **Description:** FOUNDATION.md Sec 4.2 defines Layer 1 (Action) categories as: `respond`, `review`, `inform`, `archive` with fallback `inform`. The B01 spec defines ActionCategory seeds as: `urgent`, `reply_needed`, `informational`, `unknown` with fallback `unknown`. These are entirely different slug sets.

  Similarly, FOUNDATION.md Sec 4.3 defines Layer 2 (Type) categories as: `customer-inquiry`, `complaint`, `sales-lead`, `partnership`, `vendor`, `internal`, `notification`, `newsletter`, `marketing`, `hr-recruiting` with fallback `notification`. The B01 spec defines TypeCategory seeds as: `customer_support`, `sales_inquiry`, `billing`, `technical`, `partnership`, `hr_internal`, `legal_compliance`, `marketing_promo`, `spam_automated`, `other` with fallback `other`.

  There is only partial overlap (`partnership` appears in both type sets). The slug naming convention also differs: FOUNDATION uses kebab-case (`customer-inquiry`) while B01 uses snake_case (`customer_support`).

- **Assessment:** This may be an intentional evolution of the category taxonomy between the FOUNDATION (requirements-level) and the implementation spec (architecture-level). The FOUNDATION categories were informed by the predecessor project's real-world testing, while the B01 categories may reflect a different business context or updated understanding. However, this divergence is not documented anywhere in DECISIONS.md or SCRATCHPAD.md.

- **Impact:** The LLM classification prompts (B04/B08) will use whatever slugs exist in the DB. If the slug names differ from what the LLM was tested against, classification accuracy may be affected. The category descriptions (B01 `name` field) are what the LLM actually sees in the prompt, not the slugs, so the impact is on developer understanding and consistency, not on runtime behavior.

- **Recommendation:** Document the slug divergence in DECISIONS.md as a deliberate decision, or reconcile the B01 seed data with FOUNDATION.md. At minimum, the backend-worker implementing B01 should be aware that the seed slugs do not match FOUNDATION verbatim.

### INFO-01: Exit Criteria Table Count Error

- **Severity:** INFO
- **Description:** The exit criteria state "crea las 9 tablas" but then enumerate 10 table names: `emails`, `action_categories`, `type_categories`, `classification_results`, `routing_rules`, `routing_actions`, `drafts`, `users`, `crm_sync_records`, `classification_feedback`. That is 10 tables, not 9.

- **Recommendation:** Correct the exit criteria text to "las 10 tablas" or verify if `classification_feedback` was a late addition and the count was not updated. The model count is correct (10 models including feedback); only the number in the text is wrong.

### INFO-02: `get_async_db()` Auto-Commit Pattern

- **Severity:** INFO
- **Description:** The `get_async_db()` dependency in the spec auto-commits on successful request completion and auto-rolls-back on exception. This is a common FastAPI pattern but creates an invisible invariant: the request handler does NOT need to call `session.commit()` -- it happens automatically in the generator cleanup. If a developer adds an explicit `await session.commit()` inside a route handler, the session will be committed twice (once explicitly, once in cleanup), which is harmless but wasteful. More importantly, if a developer adds an explicit `await session.rollback()` in a handler expecting it to "undo" changes but then the generator's cleanup `commit()` runs, the changes ARE committed (the rollback was inside the `try` block, the commit is after `yield`).

  Wait -- re-reading the spec code more carefully:
  ```python
  async with AsyncSessionLocal() as session:
      try:
          yield session
          await session.commit()
      except Exception:
          await session.rollback()
          raise
  ```
  The `commit()` is inside the `try` block, after `yield`. If the route handler raises, execution jumps to `except`, rolls back, and re-raises. If the route handler succeeds, `commit()` runs. This is correct and standard. The concern about explicit rollback inside the handler is not valid -- an explicit rollback in the handler would not propagate as an exception, so the cleanup would still attempt `commit()`, which would succeed (committing nothing, since rollback cleared the transaction). This is safe.

- **Assessment:** The pattern is correct. No action needed. Documenting here for completeness.

### INFO-03: `ClassificationConfidence` as Enum vs Float

- **Severity:** INFO
- **Description:** The spec defines `ClassificationConfidence` as a two-value enum (`HIGH`, `LOW`). SCRATCHPAD contains an open question from Inquisidor: "B16: `confidence` in `ReviewQueueItem` -- `'high' | 'low'` or float 0.0-1.0?" The model-level decision (enum) is correct for B01 -- the LLM classification system in FOUNDATION Sec 4 uses a binary confidence output, not a continuous score. The B16 frontend question is about display, not storage.

- **Assessment:** The enum decision at the model level is sound. The open question about float confidence is a service/presentation concern for B08/B16, not a model concern.

---

## Recommendations

1. **[SUGGESTION] Add grep-based exit condition for direct `.state` assignment.** Prevents bypassing `transition_to()` without detection. See Cat 1 finding above for the specific grep command. This is a standing verification pattern that every pipeline block (B07-B12) can inherit.

2. **[WARNING] Document or reconcile seed data slug divergence.** The B01 ActionCategory/TypeCategory seed slugs do not match FOUNDATION.md Sec 4.2/4.3. Either add a DECISIONS.md entry explaining the intentional divergence, or update the seeds to match FOUNDATION. The choice affects LLM prompt design in B04/B08.

3. **[SUGGESTION] `RoutingAction.channel` stringly-typed acceptance.** Document in the model docstring that channel validation happens at the service layer (B09), not at the DB constraint level, and explain the extensibility rationale.

4. **[INFO] Fix exit criteria count.** Change "9 tablas" to "10 tablas" in the exit criteria.

5. **[SUGGESTION] Consider `Mapped[dict[str, Any]]` over bare `Mapped[dict]`** for `ClassificationResult.raw_llm_output`. Explicit type parameters are clearer under strict mypy configurations.

6. **[SUGGESTION] Add a comment to `VALID_TRANSITIONS.get(self.state, frozenset())`.** Explain that the default `frozenset()` covers the case of an unknown state value loaded from a future DB schema, and that the resulting `InvalidStateTransitionError` is the correct behavior (fail-closed) even if the error message could be misleading.

---

## Verdict

**PASS WITH WARNINGS**

The B01 spec is well-designed and the already-implemented code (`src/models/email.py`, `src/models/base.py`, `src/core/exceptions.py`) matches the spec precisely. The state machine contract is thoroughly documented with all five contract-docstrings dimensions (invariants, guarantees, errors, state transitions, external state mutations). The pre-mortem analysis shows Cat 1 (implicit ordering) and Cat 3 (stringly-typed) are addressed with appropriate defense layers. TypedDict policy is complete and well-reasoned.

The two warnings require attention before implementation is considered complete:

1. **Seed data slug divergence** (WARN-01) -- This is a design consistency concern, not a correctness issue. The backend-worker should clarify intent before implementing seeds.
2. **Direct state assignment risk** (Cat 1 WARN) -- Mitigations exist across multiple specs, but B01 itself lacks a standing grep verification. This is a defense-in-depth gap, not a blocking issue.

No CRITICAL findings. The spec is ready for implementation by the backend-worker.
