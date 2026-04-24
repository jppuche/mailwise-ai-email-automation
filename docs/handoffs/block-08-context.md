# Block 08: Classification Service — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-08-classification.md`.

## What to build

`src/services/` — ClassificationService that orchestrates: load categories → build prompt → call LLM → validate → heuristics check → store result. Plus PromptBuilder (pure local) and HeuristicClassifier (pure local).

### Files to create

| File | Purpose |
|------|---------|
| `src/services/schemas/classification.py` | ActionCategoryDef, TypeCategoryDef, FeedbackExample, HeuristicResult, ClassificationRequest, ClassificationServiceResult, ClassificationBatchResult |
| `src/services/prompt_builder.py` | PromptBuilder — builds LLM prompt from categories + email + feedback. **0 try/except, 0 ORM imports** |
| `src/services/heuristics.py` | HeuristicClassifier — rule-based hints (never overrides LLM). **0 try/except, 0 ORM imports** |
| `src/services/classification.py` | ClassificationService class (classify_email + classify_batch) |
| `tests/unit/test_classification_schemas.py` | Schema tests |
| `tests/unit/test_prompt_builder.py` | PromptBuilder tests |
| `tests/unit/test_heuristics.py` | HeuristicClassifier tests |
| `tests/unit/test_classification_service.py` | Service tests (mocked LLM adapter + DB) |

### Files to modify

| File | Change |
|------|--------|
| `src/core/config.py` | Add `classify_max_few_shot_examples`, `classify_feedback_snippet_chars`, `classify_internal_domains` |

## Architecture overview

```
ClassificationService.classify_email(email_id)
  1. Load email from DB (must be SANITIZED)
  2. Load active categories from DB (action + type)
  3. Load recent feedback examples from DB (few-shot)
  4. PromptBuilder.build(categories, email, feedback) → (system_prompt, user_prompt)
  5. HeuristicClassifier.classify(email) → HeuristicResult
  6. LLMAdapter.classify(user_prompt, system_prompt, options) → AdapterClassificationResult
  7. Validate action/type slugs against DB categories
  8. If invalid slug → use fallback category (next(c for c in cats if c.is_fallback))
  9. Compare heuristic vs LLM → log disagreement (heuristic NEVER overrides)
  10. Store ClassificationResult in DB
  11. Transition email to CLASSIFIED → commit
  12. Return ClassificationServiceResult
```

## CRITICAL: Naming collision

There are **two different classes** named `ClassificationResult`:

| Import | What it is |
|--------|-----------|
| `from src.adapters.llm.schemas import ClassificationResult` | Pydantic model from LLM adapter — has `action: str`, `type: str`, `confidence`, `raw_llm_output` |
| `from src.models.classification import ClassificationResult` | SQLAlchemy ORM model — has FK UUIDs to category tables |

**Mandatory aliasing pattern everywhere both are needed:**
```python
from src.adapters.llm.schemas import ClassificationResult as AdapterClassificationResult
from src.models.classification import ClassificationResult  # ORM model
```

## LLM Adapter interface (B04 — what B08 calls)

```python
class LLMAdapter(abc.ABC):
    async def classify(
        self,
        prompt: str,           # non-empty sanitized email content
        system_prompt: str,    # non-empty, with category definitions
        options: ClassifyOptions,
    ) -> ClassificationResult:  # adapter schema, not ORM
        """
        Errors raised: ValueError, LLMConnectionError, LLMRateLimitError, LLMTimeoutError
        Errors silenced: OutputParseError → fallback applied internally
        """

class ClassifyOptions(BaseModel):
    allowed_actions: list[str]    # Field(min_length=1)
    allowed_types: list[str]      # Field(min_length=1)
    temperature: float = 0.1
    max_tokens: int = 500
    model: str | None = None
```

**LLM exceptions (from `src/adapters/llm/exceptions.py`):**
```python
class LLMAdapterError(Exception):           # base
class LLMConnectionError(LLMAdapterError):  # network failure
class LLMRateLimitError(LLMAdapterError):   # 429, has retry_after_seconds
class LLMTimeoutError(LLMAdapterError):     # exceeded timeout
class OutputParseError(LLMAdapterError):    # internal — adapter silences it
```

## DB Models needed (B01 — what B08 reads/writes)

### Category tables (read at classify time)

```python
# src/models/category.py
class ActionCategory(Base, TimestampMixin):
    id: Mapped[uuid.UUID]
    slug: Mapped[str]         # unique, String(100) — matched against LLM output
    name: Mapped[str]
    description: Mapped[str]
    is_fallback: Mapped[bool] # exactly one True per table (seed guarantees)
    is_active: Mapped[bool]
    display_order: Mapped[int]

class TypeCategory(Base, TimestampMixin):
    # identical structure to ActionCategory
```

**Seed data (from Alembic migration):**
- Action categories: `respond`, `forward`, `escalate`, `inform` (fallback: `inform`)
- Type categories: `complaint`, `inquiry`, `request`, `feedback`, `notification`, `internal`, `spam`, `urgent`, `follow_up`, `other` (fallback: `notification`)

### Classification result (write)

```python
# src/models/classification.py
class ClassificationConfidence(StrEnum):
    HIGH = "high"
    LOW = "low"

class ClassificationResult(Base, TimestampMixin):
    id: Mapped[uuid.UUID]
    email_id: Mapped[uuid.UUID]            # FK → emails.id CASCADE
    action_category_id: Mapped[uuid.UUID]  # FK → action_categories.id
    type_category_id: Mapped[uuid.UUID]    # FK → type_categories.id
    confidence: Mapped[ClassificationConfidence]
    raw_llm_output: Mapped[dict]           # JSONB
    fallback_applied: Mapped[bool]
    classified_at: Mapped[datetime.datetime]
```

### Feedback (read — few-shot examples)

```python
# src/models/feedback.py
class ClassificationFeedback(Base, TimestampMixin):
    id: Mapped[uuid.UUID]
    email_id: Mapped[uuid.UUID]
    original_action_id: Mapped[uuid.UUID]
    original_type_id: Mapped[uuid.UUID]
    corrected_action_id: Mapped[uuid.UUID]
    corrected_type_id: Mapped[uuid.UUID]
    corrected_by: Mapped[uuid.UUID]
    corrected_at: Mapped[datetime.datetime]
```

### Email state transitions for B08

```python
# Precondition: email.state == SANITIZED
# Happy path: SANITIZED → CLASSIFIED
# Error path: SANITIZED → CLASSIFICATION_FAILED
# Recovery: CLASSIFICATION_FAILED → SANITIZED (for retries)
```

## Ingestion result (B07 — what feeds B08)

B07 stores emails with `state=SANITIZED`. B08 reads these emails. Relevant fields:
- `email.body_plain` — sanitized, max 4000 chars (guaranteed non-empty for SANITIZED)
- `email.subject` — raw from adapter
- `email.sender_email` — raw from adapter
- `email.id` — UUID

## Exception strategy (try-except D7/D8)

### External-state operations (try/except with specific types)

| Boundary | Exception type | Scope |
|----------|---------------|-------|
| DB: load email | `SQLAlchemyError` | Per-email failure |
| DB: load categories | `SQLAlchemyError` | Batch abort if no categories |
| DB: load feedback | `SQLAlchemyError` | Fallback to no feedback (not fatal) |
| LLMAdapter.classify | `LLMAdapterError` | Per-email → CLASSIFICATION_FAILED |
| DB: store result | `SQLAlchemyError` | Per-email failure |
| DB: transition email | `SQLAlchemyError` | Per-email failure |

### Local computation (NO try/except — D8)

| Operation | Why no try/except |
|-----------|-------------------|
| `PromptBuilder.build()` | Pure function — 0 try/except enforced |
| `HeuristicClassifier.classify()` | Pure function — 0 try/except enforced |
| Slug validation against categories | Conditional check (if slug not in dict) |
| Fallback category lookup | `next(c for c if c.is_fallback)` — WARNING-03: use `next(..., None)` |
| Domain extraction from email | `email.split("@")[-1]` — always valid for stored emails |

## PromptBuilder (pure local — 0 try/except, 0 ORM imports)

```python
class PromptBuilder:
    """Constructs LLM prompts from frozen category defs + email data.

    Takes ONLY service-layer schemas (ActionCategoryDef, TypeCategoryDef,
    FeedbackExample), NEVER ORM models. This decouples prompt logic from DB.
    """

    def build(
        self,
        action_categories: list[ActionCategoryDef],
        type_categories: list[TypeCategoryDef],
        email_body: str,
        email_subject: str,
        sender_email: str,
        feedback_examples: list[FeedbackExample] | None = None,
    ) -> tuple[str, str]:
        """Returns (system_prompt, user_prompt)."""
```

## HeuristicClassifier (pure local — 0 try/except, 0 ORM imports)

```python
class HeuristicClassifier:
    """Rule-based classification hints. NEVER overrides LLM — only lowers confidence.

    Heuristic DISAGREES with LLM: log the disagreement, use LLM result,
    but set heuristic_disagreement=True in the service result.
    """

    def classify(
        self,
        subject: str,
        body: str,
        sender_domain: str,
        internal_domains: list[str],
    ) -> HeuristicResult:
```

**Example heuristic rules:**
- `urgent` type hint: subject contains "URGENT" or "ASAP" (case-insensitive)
- `complaint` type hint: body contains "dissatisfied", "unacceptable", "refund"
- `internal` type hint: sender_domain in internal_domains list
- `spam` type hint: body contains "unsubscribe" + "click here"
- `escalate` action hint: subject contains "CEO", "legal", "lawsuit"

## Service schemas to create

```python
# src/services/schemas/classification.py

@dataclass(frozen=True)
class ActionCategoryDef:
    id: uuid.UUID
    slug: str
    name: str
    description: str
    is_fallback: bool

@dataclass(frozen=True)
class TypeCategoryDef:
    id: uuid.UUID
    slug: str
    name: str
    description: str
    is_fallback: bool

class FeedbackExample(BaseModel):
    email_snippet: str        # first N chars of body
    correct_action: str       # ActionCategory slug
    correct_type: str         # TypeCategory slug

class HeuristicResult(BaseModel):
    action_hint: str | None = None
    type_hint: str | None = None
    rules_fired: list[str]    # names of rules that matched
    has_opinion: bool          # True if any hint is non-None

class ClassificationRequest(BaseModel):
    email_id: uuid.UUID
    sanitized_body: str
    subject: str
    sender_email: str
    sender_domain: str

class ClassificationServiceResult(BaseModel):
    email_id: uuid.UUID
    action_slug: str
    type_slug: str
    confidence: Literal["high", "low"]
    fallback_applied: bool
    heuristic_disagreement: bool
    heuristic_result: HeuristicResult | None
    db_record_id: uuid.UUID

class ClassificationBatchResult(BaseModel):
    total: int
    succeeded: int
    failed: int
    results: list[ClassificationServiceResult]
    failures: list[tuple[uuid.UUID, str]]  # (email_id, error_message)
```

## Load-bearing defaults (Cat 8) — to add to config.py

| Default | Value | Env Var | Already in config? |
|---------|-------|---------|--------------------|
| Max few-shot examples | `10` | `CLASSIFY_MAX_FEW_SHOT_EXAMPLES` | **No — add** |
| Feedback snippet chars | `200` | `CLASSIFY_FEEDBACK_SNIPPET_CHARS` | **No — add** |
| Internal domains | `""` (empty) | `CLASSIFY_INTERNAL_DOMAINS` | **No — add** (comma-separated) |
| LLM classify temp | `0.1` | `LLM_TEMPERATURE_CLASSIFY` | Yes |
| LLM classify model | `gpt-4o-mini` | `LLM_MODEL_CLASSIFY` | Yes |
| LLM classify max tokens | `500` | `LLM_CLASSIFY_MAX_TOKENS` | Yes |

## Open questions (from SCRATCHPAD — resolve during implementation)

- `tuple[str, str]` vs named dataclass for `build()` return → spec says tuple; consider `PromptPair` namedtuple for clarity
- WARNING-03: `next(..., None)` for fallback category — handle None explicitly (raise `CategoryNotFoundError`)

## Privacy (Sec 11.4 — MANDATORY)

- Logger NEVER logs `subject`, `body_plain`, `from_address`, `snippet`
- OK to log: `email_id` (UUID), `action_slug`, `type_slug`, `confidence`, `fallback_applied`
- `raw_llm_output` stored in JSONB but never logged (may contain email content)
- Few-shot feedback snippet: truncated to `classify_feedback_snippet_chars` (PII minimization)

## Hard enforcement rules (grep-verifiable exit conditions)

These **must** pass before commit:
```bash
# PromptBuilder: 0 try/except, 0 ORM imports
grep "^    try:" src/services/prompt_builder.py  # must return EMPTY
grep "src.models" src/services/prompt_builder.py  # must return EMPTY

# HeuristicClassifier: 0 try/except, 0 ORM imports
grep "^    try:" src/services/heuristics.py  # must return EMPTY
grep "src.models" src/services/heuristics.py  # must return EMPTY

# Naming alias present wherever both ClassificationResults coexist
grep "as AdapterClassificationResult" src/services/classification.py  # must match
```

## Test patterns

### Test file locations (flat convention)

```
tests/unit/test_classification_schemas.py
tests/unit/test_prompt_builder.py
tests/unit/test_heuristics.py
tests/unit/test_classification_service.py
```

### Key test scenarios

**PromptBuilder:**
1. Happy path: categories + email → system_prompt contains category descriptions, user_prompt contains email content
2. With feedback: few-shot examples included in system prompt
3. Empty feedback: prompt works without examples
4. Category ordering: system prompt lists categories deterministically

**HeuristicClassifier:**
1. Urgent keywords → type_hint="urgent", has_opinion=True
2. Complaint keywords → type_hint="complaint"
3. Internal domain match → type_hint="internal"
4. No rules fire → has_opinion=False, hints are None
5. Multiple rules fire → rules_fired lists all matched rules

**ClassificationService:**
1. Happy path: SANITIZED email → classified, CLASSIFIED state, DB record created
2. Invalid LLM slug → fallback category used, fallback_applied=True
3. Heuristic disagrees → heuristic_disagreement=True, LLM result used (not heuristic)
4. LLM error → CLASSIFICATION_FAILED state
5. No active categories → error (batch cannot proceed)
6. Feedback loading fails → classify proceeds without feedback (not fatal)
7. Batch: 3 emails, one fails → others succeed (per-email isolation)
8. Email not SANITIZED → skip/error

## Existing code you need to know

### IngestionService pattern (B07 — follow same patterns)

- Constructor injection: `__init__(*, adapter, session, redis, settings)`
- Per-item isolation in batch processing
- Two commits per successful operation
- `structlog.get_logger(__name__)` for logging
- `FailureReason` enum for error classification

### B07 resolved question applied here

- `mapped_column(default=uuid.uuid4)` is INSERT-time only → always pass explicit `id=uuid.uuid4()` in constructor
- `[] or [default]` is falsy → use `x if x is None else x` for optional list params

## Quality gates (must pass before commit)

```bash
python -m mypy src/services/ src/tasks/
python -m ruff check src/services/
python -m ruff format src/services/ --check
pytest tests/unit/test_classification_schemas.py -v
pytest tests/unit/test_prompt_builder.py -v
pytest tests/unit/test_heuristics.py -v
pytest tests/unit/test_classification_service.py -v
pytest tests/ -q  # full non-integration suite
# Enforcement greps:
grep "^    try:" src/services/prompt_builder.py && echo "FAIL: try in prompt_builder" || echo "OK"
grep "^    try:" src/services/heuristics.py && echo "FAIL: try in heuristics" || echo "OK"
grep "src.models" src/services/prompt_builder.py && echo "FAIL: ORM in prompt_builder" || echo "OK"
grep "src.models" src/services/heuristics.py && echo "FAIL: ORM in heuristics" || echo "OK"
bash scripts/validate-docs.sh
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]` at boundaries
- Contract docstrings: Preconditions, Guarantees, Errors raised, Errors silenced
- `structlog.get_logger(__name__)` — no `# type: ignore` needed
- Commit: `feat(classification): block-08 — classification service, N tests`
