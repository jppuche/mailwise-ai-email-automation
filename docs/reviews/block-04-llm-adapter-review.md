# Sentinel Review: Block 04 (LLM Adapter)

**Date:** 2026-02-21
**Reviewer:** Sentinel (opus)
**Scope:** `src/adapters/llm/` (6 files) + `src/core/config.py` changes
**Spec:** `docs/specs/block-04-llm-adapter.md`

---

## CRITICAL (blocks commit)

None.

---

## WARNING (document and track)

### WARNING-B04-01: API key stored in plain `str` field -- no `SecretStr` protection

**File:** `src/adapters/llm/schemas.py` line 59
**Severity:** WARNING
**Description:**
`LLMConfig.api_key` is typed as `str | None`. Pydantic `BaseModel` default `__repr__` will include the API key in plaintext if the object is ever printed, logged, or included in a traceback. Similarly, `.model_dump()` will expose it.

`pydantic.SecretStr` would mask the value in repr/serialization while still allowing `.get_secret_value()` for the single place it is needed (`litellm_adapter.py` line 57).

Additionally, `src/core/config.py` stores `openai_api_key` and `anthropic_api_key` as `str = Field(default="")` (lines 39-40) -- the same issue applies at the Settings level.

**Risk:** If `LLMConfig` appears in a log line, traceback, or debug output, the API key leaks.
**Mitigation:** Current code only accesses `config.api_key` in the constructor to assign to `litellm.api_key`. Risk is low if no logging of config objects is introduced later. However, defense in depth dictates using `SecretStr`.
**Track:** Implement in B04 or defer to hardening pass (B19).

### WARNING-B04-02: No `LLM_ALLOWED_MODELS` allowlist (SCRATCHPAD WARNING-01 carry-forward)

**File:** `src/adapters/llm/litellm_adapter.py` lines 98, 183; `src/adapters/llm/schemas.py` lines 42, 50
**Severity:** WARNING
**Description:**
`ClassifyOptions.model` and `DraftOptions.model` accept any `str | None`. There is no allowlist validation against `LLM_ALLOWED_MODELS`. A misconfigured or malicious caller could pass an arbitrary model identifier to `litellm.acompletion`, potentially routing requests to unintended providers, incurring unexpected costs, or targeting a model with weaker safety guardrails.

The spec and SCRATCHPAD both flag this as WARNING-01 with target blocks B04/B14.

**Risk:** Model substitution attack. Attacker with API access sends `model="ft:gpt-4o:attacker-org:..."` or similar, redirecting LLM calls to a fine-tuned model that bypasses classification guardrails.
**Mitigation:** Single-tenant system limits exposure. The `model` override is only consumed by service-layer code (B08/B11), not directly from user input in current architecture.
**Track:** Implement allowlist validation in B08 (classification service) where `ClassifyOptions` is constructed, or add a `model_validator` on `ClassifyOptions`/`DraftOptions` that checks against a config-provided allowlist. Recommend B08 implementation since the adapter should remain provider-agnostic.

### WARNING-B04-03: `test_connection()` leaks exception details via `error_detail=str(exc)`

**File:** `src/adapters/llm/litellm_adapter.py` line 250
**Severity:** WARNING
**Description:**
`str(exc)` on LiteLLM exceptions may include: API key fragments (in some error messages from providers), internal endpoint URLs, or model configuration details. This `error_detail` field flows to `ConnectionTestResult`, which is a Pydantic model that could be serialized to API responses (B13 health endpoint).

**Risk:** Information disclosure if `ConnectionTestResult` is returned directly in an API response without sanitization.
**Mitigation:** The B13 spec indicates the health endpoint always returns HTTP 200 with aggregated status. The `error_detail` field is designed for operator visibility, not end-user display. However, the adapter layer cannot control how callers use this field.
**Track:** B13 health endpoint should either omit `error_detail` from the API response schema or redact it to a generic message (e.g., "LLM provider unreachable"). Document this in the B13 spec.

### WARNING-B04-04: `fallback_model` field defined but never used in adapter

**File:** `src/adapters/llm/schemas.py` line 58, `src/adapters/llm/litellm_adapter.py` (entire file)
**Severity:** WARNING
**Description:**
`LLMConfig.fallback_model` is a required field, but `LiteLLMAdapter` never references `self._config.fallback_model`. The B04 spec states "LLM_FALLBACK_MODEL must differ from classify model (thinking-mode failures)" -- the implication is that when the primary model fails classification parsing (thinking-mode output), a fallback retry with a different model should be attempted.

Currently, the fallback path produces a static `ClassificationResult(action="inform", type="notification")` without attempting a retry on the fallback model. The SCRATCHPAD B04 entry confirms `OutputParseError never re-raised to caller` but does not address whether a retry on the fallback model was intended for this block or deferred to B08.

**Risk:** The `fallback_model` config field gives operators a false sense that model-level fallback is active. A required field that is never read is a latent bug.
**Mitigation:** This is likely intentional deferral -- B08 (classification service) may implement the retry-with-fallback-model logic. If so, the adapter's role is simply to accept a model override via `options.model`. However, this should be documented explicitly.
**Track:** Clarify in B08 spec whether `fallback_model` retry is implemented there or needs adapter-level support.

### WARNING-B04-05: `litellm.api_key` global state -- shared across adapter instances

**File:** `src/adapters/llm/litellm_adapter.py` lines 56-59
**Severity:** WARNING
**Description:**
Setting `litellm.api_key` and `litellm.api_base` as module-level globals means that if multiple `LiteLLMAdapter` instances are created with different credentials (unlikely in single-tenant, but possible in tests), the last one wins. This is a known LiteLLM pattern, but it means:

1. Test isolation: constructing an adapter in one test affects the global state for subsequent tests.
2. Future multi-tenant: this pattern would break.

**Risk:** Low for single-tenant. Test pollution is the main concern.
**Mitigation:** LiteLLM also supports passing `api_key` and `api_base` as kwargs to `acompletion()`. This would eliminate global state mutation. However, this is a LiteLLM design choice and the current approach matches their documentation.
**Track:** Consider passing credentials per-call if test isolation issues emerge. Document as a known limitation for multi-tenant scenarios (D18 already defers multi-tenant).

---

## SUGGESTIONS (deferred improvements)

### SUGGESTION-B04-01: ReDoS resilience -- `_THINKING_TAG_RE` with `re.DOTALL`

**File:** `src/adapters/llm/parser.py` line 31
**Description:**
`re.compile(r"<think>.*?</think>", re.DOTALL)` uses a non-greedy `.*?` with DOTALL. For adversarial input where many `<think>` opening tags exist without matching closing tags, the regex engine will backtrack across the entire input. On typical LLM outputs (< 4KB after body truncation), this is not exploitable. However, if body truncation is ever relaxed or the parser is used on untrusted input of unbounded length, this could become a concern.

`_JSON_OBJECT_RE = re.compile(r"\{[^{}]*\}")` is safe (character class negation, no backtracking).

`_MARKDOWN_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)` has the same non-greedy DOTALL pattern but is bounded by the triple-backtick anchors.

**Risk:** Negligible at current body truncation (4000 chars). Theoretical ReDoS on unbounded input.
**Recommendation:** Document the body truncation assumption as a precondition in `parse_classification()` docstring. No code change needed now.

### SUGGESTION-B04-02: `OutputParseError` exported but never instantiated

**File:** `src/adapters/llm/__init__.py` line 15, `src/adapters/llm/exceptions.py` line 42
**Description:**
`OutputParseError` is defined with a `raw_output` field and exported in `__all__`, but it is never instantiated anywhere in the codebase. The adapter's fallback path returns a result directly without raising `OutputParseError`. The class exists as part of the exception hierarchy design, presumably for future use (structured logging of parse failures in B08 or B19).

This is not a bug -- the design explicitly says "OutputParseError never re-raised to caller" and the parser returns `None` instead of raising. However, exporting an exception that is never raised could confuse downstream consumers who might try to catch it.

**Recommendation:** Add a comment to the `__init__.py` export clarifying that `OutputParseError` is available for type checking and logging contexts, not for catch blocks.

### SUGGESTION-B04-03: `generate_draft()` returns empty string content without error

**File:** `src/adapters/llm/litellm_adapter.py` line 214
**Description:**
When the LLM returns `None` content, the adapter coerces it to `""` and returns `DraftText(content="", ...)`. The ABC docstring guarantees "Returns DraftText with non-empty content" (base.py line 92), but the implementation allows empty content. The test explicitly verifies this behavior (`test_empty_llm_content_returns_empty_string`).

**Risk:** Caller (B11 draft generation service) receives a "successful" `DraftText` with empty content and may push an empty draft to Gmail.
**Recommendation:** Either raise `LLMAdapterError("LLM returned empty content")` when content is empty/None, or update the ABC docstring to remove the "non-empty" guarantee and let the caller validate. The latter is more consistent with the "no fallback for drafts" design principle.

### SUGGESTION-B04-04: `LLMConfig` does not validate `fallback_model != classify_model`

**File:** `src/adapters/llm/schemas.py` lines 53-62
**Description:**
The SCRATCHPAD explicitly states "`LLM_FALLBACK_MODEL` must differ from classify model." A Pydantic `model_validator` could enforce this at construction time. Currently, an operator could configure both to the same value, making the fallback mechanism ineffective.

**Recommendation:** Add a `@model_validator(mode="after")` that warns or raises if `fallback_model == classify_model`. This is a configuration correctness check, not a security issue. Fits naturally in B08 or B14 when the fallback retry is actually implemented.

### SUGGESTION-B04-05: Exception message propagation via `str(exc)`

**File:** `src/adapters/llm/litellm_adapter.py` lines 114, 119, 124, 199, 204, 209
**Description:**
`str(exc)` from LiteLLM exceptions is passed as the message to domain exceptions. LiteLLM exception `__str__` may include model names, provider details, partial request context, or other diagnostic information. While this is useful for debugging, in certain upstream error handlers (e.g., B13 API exception handlers) this message could be surfaced to the user.

**Recommendation:** B13 exception handlers should use generic messages for 5xx responses (e.g., "Classification service temporarily unavailable") and log the detailed exception message at WARNING/ERROR level server-side. This is a B13 concern, not B04.

---

## D7/D8 COMPLIANCE

### D7 (External-state operations: structured try/except with specific exception types)

| Method | Compliant | Notes |
|--------|-----------|-------|
| `classify()` | YES | Catches `RateLimitError`, `Timeout`, `APIConnectionError` individually. Maps to domain exceptions with `from exc` chain. |
| `generate_draft()` | YES | Same pattern as `classify()`. No fallback -- errors propagate. |
| `test_connection()` | YES | Bare `except Exception` with `# noqa: BLE001` -- health-check semantics, explicitly documented. |

All three external-state operations use structured try/except. No bare `except Exception` outside of `test_connection()`. Exception mapping preserves the chain via `from exc`. Domain exceptions carry `original_error` for debugging without coupling callers to LiteLLM types.

### D8 (Local computation: conditionals, not try/except)

| Component | Compliant | Notes |
|-----------|-----------|-------|
| `parser.py` | YES (with documented exception) | `_safe_json_loads` uses try/except because `json.loads` has no conditional API. Documented inline. All other functions use conditionals and return `None` on failure. |
| `litellm_adapter.py` preconditions | YES | `if not prompt: raise ValueError(...)` -- conditionals for validation. |
| `schemas.py` | YES | Pydantic validation via `Field(min_length=1)`, `Field(ge=0.0, le=1.0)` -- declarative, not try/except. |

The single documented exception (`_safe_json_loads`) is appropriate and well-justified.

---

## Prompt Injection Analysis (D16)

### Layer assessment for this block

The LLM adapter is a transport/execution layer. It does NOT construct prompts -- it receives `prompt` and `system_prompt` as strings from the caller (B08 classification service, B11 draft service).

| D16 Layer | Block 04 Responsibility | Status |
|-----------|------------------------|--------|
| L1: Input sanitization | NOT this block -- B07 ingestion sanitizes email body | N/A |
| L2: Defensive prompt engineering | NOT this block -- B08 PromptBuilder constructs prompts with delimiters | N/A |
| L3: Data delimiters | NOT this block -- B08 PromptBuilder | N/A |
| L4: Output validation against enum | YES -- parser validates `action in allowed_actions` and `type in allowed_types` | COMPLIANT |
| L5: No tool access during classification | YES -- `litellm.acompletion` with no `tools` or `functions` parameter | COMPLIANT |

**Key finding:** The parser's validation against `allowed_actions` and `allowed_types` (parser.py lines 69-70) is the critical D16 L4 defense. If the LLM is prompt-injected into outputting a rogue action/type, the parser returns `None` and the fallback is applied. This is correct behavior.

**Risk area:** The `raw_llm_output` field in `ClassificationResult` preserves the full LLM output, including any injected content. This is by design (for audit/debugging). Callers must NOT use `raw_llm_output` for any downstream logic -- it is strictly for human review. This is a documentation concern for B08.

---

## 7-Dimension Review Summary

| Dimension | Grade | Notes |
|-----------|-------|-------|
| 1. Adapter contract compliance | PASS | ABC matches FOUNDATION.md Sec 9.5. 3 methods, typed signatures, no `ModelResponse` leakage. |
| 2. Pipeline security (D16) | PASS | L4 (output validation) and L5 (no tool access) implemented. L1-L3 correctly deferred to upstream blocks. |
| 3. Exception safety | PASS | Structured hierarchy, `from exc` chaining, `original_error` preserved, no bare `except` outside health-check. |
| 4. State machine integrity | N/A | No state transitions in this block (adapter layer). |
| 5. Configuration security | PASS (with WARNING) | All defaults externalized via `LLMConfig`/`config.py`. WARNING-B04-01 (SecretStr) and WARNING-B04-02 (allowlist) are tracked. |
| 6. Dependency health | PASS | `litellm>=1.40` pinned in pyproject.toml. mypy ignore configured. No new dependencies introduced. |
| 7. Data contract validation | PASS | 6 Pydantic models match Appendix B contracts. `extra="ignore"` on `ClassificationResult`. `Field(min_length=1)` on allowed lists. |

---

## VERDICT: PASS

**0 CRITICAL, 5 WARNING, 5 SUGGESTION**

Block 04 is well-architected. The adapter boundary is clean: `ModelResponse` never escapes, exception mapping is thorough, D7/D8 compliance is complete, and the prompt injection defense at L4/L5 is correctly scoped. The warnings are all defensive-in-depth recommendations that can be addressed in their target blocks (B08, B13, B19) without blocking this commit.

**Carry-forward items for tracking:**

| ID | Target Block | Description |
|----|-------------|-------------|
| WARNING-B04-01 | B19 (hardening) | `LLMConfig.api_key` should use `SecretStr` |
| WARNING-B04-02 | B08 | `LLM_ALLOWED_MODELS` allowlist validation (SCRATCHPAD WARNING-01) |
| WARNING-B04-03 | B13 | `error_detail` redaction in health endpoint API response |
| WARNING-B04-04 | B08 | Document whether `fallback_model` retry is B08 responsibility |
| WARNING-B04-05 | N/A (noted) | `litellm.api_key` global state -- document limitation |
| SUGGESTION-B04-03 | B11 | Empty draft content: align docstring with implementation |
| SUGGESTION-B04-04 | B08/B14 | `fallback_model != classify_model` validator |
