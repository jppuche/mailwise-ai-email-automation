# Block 04: LLM Adapter — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-04-llm-adapter.md`.

## What to build

`src/adapters/llm/` — LLMAdapter ABC + LiteLLMAdapter concrete impl + output parser.

### Files to create

| File | Purpose |
|------|---------|
| `src/adapters/llm/exceptions.py` | Error hierarchy (LLMAdapterError base) |
| `src/adapters/llm/schemas.py` | Typed contracts: ClassificationResult, DraftText, LLMConfig, etc. |
| `src/adapters/llm/parser.py` | Output parser: 7 shapes, conditionals only (D8), returns None on failure |
| `src/adapters/llm/base.py` | ABC with 3 abstract methods |
| `src/adapters/llm/litellm_adapter.py` | LiteLLMAdapter (litellm.acompletion) |
| `src/adapters/llm/__init__.py` | Public exports |

### Files to modify

| File | Change |
|------|--------|
| `src/core/config.py` | Add `llm_fallback_model`, `llm_timeout_seconds`, `llm_classify_max_tokens`, `llm_draft_max_tokens`, `llm_base_url` |
| `pyproject.toml` | Verify litellm already present |

## ABC methods (3)

```python
classify(prompt: str, system_prompt: str, options: ClassifyOptions) -> ClassificationResult
generate_draft(prompt: str, system_prompt: str, options: DraftOptions) -> DraftText
test_connection() -> ConnectionTestResult  # silences ALL errors, health-check semantics
```

## Critical decisions (from SCRATCHPAD)

- `OutputParseError` NEVER re-raised to caller — adapter applies fallback internally
- `generate_draft()` has NO fallback — errors propagate (no safe default for free text)
- `LLM_FALLBACK_MODEL` must differ from classify model (thinking-mode failures)
- Parser is pure local computation: conditionals only, NO try/except (D8)
- `raw_llm_output` always preserved as `str` for debugging/audit
- **Naming collision**: adapter `ClassificationResult` ≠ DB model `ClassificationResult` — alias as `AdapterClassificationResult` when both needed (B08)

## Exception strategy (try-except D7/D8)

- LLM API calls (`litellm.acompletion`): `try/except` with specific types
  - `litellm.exceptions.RateLimitError` → `LLMRateLimitError`
  - `litellm.exceptions.Timeout` → `LLMTimeoutError`
  - `litellm.exceptions.APIConnectionError` → `LLMConnectionError`
- Parser (`parse_classification`): conditionals ONLY, returns `None` on failure
- Validation errors: `if/raise ValueError`, NOT try/except
- No bare `except Exception` (except `test_connection`)

## Exception hierarchy

```python
LLMAdapterError(Exception)              # base, has original_error: Exception | None
  LLMConnectionError(LLMAdapterError)   # network, DNS, endpoint unreachable
  LLMRateLimitError(LLMAdapterError)    # 429, has retry_after_seconds: int | None
  LLMTimeoutError(LLMAdapterError)      # exceeds LLM_TIMEOUT_SECONDS
  OutputParseError(LLMAdapterError)     # parse failure, has raw_output: str (internal only)
```

## Parser — 7 output shapes (Cat 4 pre-mortem)

| # | Case | Strategy |
|---|------|----------|
| 1 | Pure JSON | `json.loads` directly |
| 2 | JSON in markdown code block | Regex strip of `` ```json `` fences |
| 3 | Explanatory text around JSON | Regex extract first `{...}` object |
| 4 | Wrong casing in values | `.lower()` before validation |
| 5 | Thinking-mode tags | Strip `<think>...</think>` with regex |
| 6 | Extra fields | Pydantic `extra="ignore"` |
| 7 | Alternate key names | Mapping: `category→action`, `intent→action`, `email_type→type`, `classification→type` |

Parser returns `ClassificationResult | None`. Never raises. Caller applies fallback on `None`.

## Schemas (Pydantic)

```python
class ClassificationResult(BaseModel):
    action: str             # validated against allowed_actions
    type: str               # validated against allowed_types
    confidence: Literal["high", "low"]
    raw_llm_output: str     # always preserved
    fallback_applied: bool = False

class DraftText(BaseModel):
    content: str
    model_used: str         # traceability
    fallback_applied: bool = False

class ClassifyOptions(BaseModel):
    allowed_actions: list[str]  # non-empty
    allowed_types: list[str]    # non-empty
    temperature: float = 0.1
    max_tokens: int = 500
    model: str | None = None    # override default

class DraftOptions(BaseModel):
    temperature: float = 0.7
    max_tokens: int = 2000
    model: str | None = None

class LLMConfig(BaseModel):
    classify_model: str
    draft_model: str
    fallback_model: str
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: int = 30

class ConnectionTestResult(BaseModel):
    success: bool
    model_used: str
    latency_ms: int
    error_detail: str | None = None
```

## Existing code you need to know

### Settings pattern — `src/core/config.py`

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # LLM (existing)
    llm_model_classify: str = Field(default="gpt-4o-mini")
    llm_model_draft: str = Field(default="gpt-4o")
    llm_temperature_classify: float = Field(default=0.1)
    llm_temperature_draft: float = Field(default=0.7)
    openai_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    # ... needs: llm_fallback_model, llm_timeout_seconds, llm_classify_max_tokens,
    #            llm_draft_max_tokens, llm_base_url
```

### Email adapter pattern (B03 — replicate this structure)

```
src/adapters/email/
├── exceptions.py   # EmailAdapterError base + 6 subclasses, original_error field
├── schemas.py      # Pydantic models + TypedDicts, NewType(DraftId)
├── base.py         # ABC, contract-docstrings (4 questions), fully typed
├── gmail.py        # Concrete: _ensure_connected(), _map_http_error(), structured try/except
└── __init__.py     # Re-exports all public types
```

Key patterns to replicate:
- `original_error: Exception | None` field on base exception
- `_ensure_connected()` → raises if not configured
- `assert self._service is not None` after `_ensure_connected()` for mypy narrowing
- `# noqa: BLE001` on `test_connection()` bare except
- Module-level docstring with `contract-docstrings:` and `try-except D7:` tags

### DB model — `src/models/classification.py`

```python
class ClassificationResult(Base, TimestampMixin):
    email_id: UUID FK → emails.id
    action_category_id: UUID FK → action_categories.id   # prevents hallucination
    type_category_id: UUID FK → type_categories.id
    confidence: ClassificationConfidence (HIGH | LOW)
    raw_llm_output: dict (JSONB)
    fallback_applied: bool
```

**IMPORTANT**: The adapter `ClassificationResult` (schemas.py) is a different type from this DB model. The service layer (B08) maps between them.

### Domain exceptions — `src/core/exceptions.py`

5 existing: `InvalidStateTransitionError`, `CategoryNotFoundError`, `DuplicateEmailError`, `AuthenticationError`, `AuthorizationError`. Block 04 adds its own hierarchy in `adapters/llm/exceptions.py`.

### Dependencies — `pyproject.toml`

`litellm>=1.40` — already present. mypy override for `litellm.*` already configured with `ignore_missing_imports = true`.

### Test patterns

- `tests/unit/test_gmail_adapter.py` — reference for mocking SDK: `MagicMock` service, `_make_http_error()` helpers, class-based test grouping
- `tests/contract/test_email_adapter_contract.py` — MockAdapter implementing ABC, verifies return types + ValueError contracts
- Root `conftest.py`: `--run-integration` flag, `integration` marker
- `asyncio_mode = "auto"` in pyproject.toml

### LiteLLM mocking pattern

```python
from unittest.mock import AsyncMock, MagicMock, patch

@patch("litellm.acompletion", new_callable=AsyncMock)
async def test_classify_success(mock_completion):
    mock_completion.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(
            content='{"action": "reply", "type": "support"}'
        ))]
    )
    # ... test adapter.classify()
```

## Load-bearing defaults (Cat 8)

| Default | Value | Env Var | Risk if wrong |
|---------|-------|---------|---------------|
| Classify temperature | `0.1` | `LLM_TEMPERATURE_CLASSIFY` | Too high: inconsistent classifications |
| Draft temperature | `0.7` | `LLM_TEMPERATURE_DRAFT` | Too low: robotic; too high: hallucination |
| Classify max tokens | `500` | `LLM_CLASSIFY_MAX_TOKENS` | Too low: truncated JSON → parse failure |
| Draft max tokens | `2000` | `LLM_DRAFT_MAX_TOKENS` | Too low: incomplete drafts |
| Timeout | `30`s | `LLM_TIMEOUT_SECONDS` | Too low: timeouts on complex emails |
| Fallback model | `gpt-3.5-turbo` | `LLM_FALLBACK_MODEL` | Same as classify model → fallback useless |

## Quality gates (must pass before commit)

```bash
python -m ruff check src/adapters/llm/
python -m ruff format src/adapters/llm/ --check
python -m mypy src/adapters/llm/
pytest tests/unit/test_llm_schemas.py tests/unit/test_llm_parser.py -v
pytest tests/unit/test_litellm_adapter.py -v
pytest tests/ -q                    # full non-integration suite
grep -n "ModelResponse" src/adapters/llm/base.py src/adapters/llm/schemas.py  # D1: expect 0
bash scripts/validate-docs.sh
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]` at boundaries
- Contract docstrings: invariants, guarantees, errors raised, state transitions
- `# noqa: BLE001` on `test_connection()` bare except
- `datetime.UTC` not `timezone.utc` (ruff UP017)
- Commit: `feat(llm): block-04 — LLM adapter, parser, N tests`
