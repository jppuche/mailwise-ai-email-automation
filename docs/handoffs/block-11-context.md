# Block 11: Draft Generation Service — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-11-draft-generation.md`.

## What to build

`src/services/` — DraftContextBuilder (pure-local context assembly, 0 try/except) + DraftGenerationService (LLM call → persist Draft → optional Gmail push → state transition). Celery task bridges sync→async via `asyncio.run()`.

### Files to create

| File | Purpose |
|------|---------|
| `src/services/schemas/draft.py` | `EmailContent`, `ClassificationContext`, `CRMContextData`, `OrgContext`, `DraftContext`, `DraftRequest`, `DraftResult`, `DraftGenerationConfig` |
| `src/services/draft_context.py` | `DraftContextBuilder` — local-pure, zero try/except (D8) |
| `src/services/draft_generation.py` | `DraftGenerationService` — LLM call, DB persist, Gmail push, state transition |
| `src/tasks/draft_generation_task.py` | Celery task: async bridge, retry on `LLMRateLimitError` |
| `tests/unit/test_draft_schemas.py` | Schema validation tests |
| `tests/unit/test_draft_context_builder.py` | Builder tests (pure-local, 5+ scenarios) |
| `tests/unit/test_draft_generation_service.py` | Service tests (LLM success/fail, Gmail push, HITL) |
| `tests/unit/test_draft_generation_task.py` | Task retry/no-retry behavior |

### Files to modify

| File | Change |
|------|--------|
| `src/core/config.py` | Add 6 `draft_*` settings (see Config section — many LLM settings already exist) |

## CRITICAL: Spec vs actual code discrepancies

| Spec says | Actual code (use this) |
|-----------|----------------------|
| `ROUTED → DRAFT_GENERATED` (shortcut) | **Does NOT exist** — only `CRM_SYNCED → DRAFT_GENERATED` |
| `ROUTED → DRAFT_FAILED` (shortcut) | **Does NOT exist** — only `CRM_SYNCED → DRAFT_FAILED` |
| `DRAFT_FAILED → ROUTED` (recovery) | **Does NOT exist** — recovery is `DRAFT_FAILED → CRM_SYNCED` only |
| `CRMSyncRecord.metadata` JSONB field | **Does NOT exist** — only `contact_id`, `activity_id`, `lead_id` available |
| `gmail_draft_id: str \| None` | `DraftId \| None` (`DraftId = NewType("DraftId", str)` from `src.adapters.email.schemas`) |
| `email_adapter.create_draft(...)` as `async def` | ABC is `def` (sync) — wrap with `asyncio.to_thread()` in async service |
| `Draft.model_used` column | **Does NOT exist** — store `model_used` in `DraftResult` only (not ORM) |
| `tests/services/` test location | Use `tests/unit/` (flat convention from B03-B10) |
| Add all draft settings to config | `max_body_length`, `llm_model_draft`, `llm_temperature_draft`, `llm_draft_max_tokens` already exist — add only the 6 `draft_*` settings |

## State machine — verified from `src/models/email.py` (lines 55-64)

```python
# B11 valid transitions:
EmailState.CRM_SYNCED → frozenset({EmailState.DRAFT_GENERATED, EmailState.DRAFT_FAILED})
EmailState.DRAFT_GENERATED → frozenset({EmailState.COMPLETED})
# Recovery:
EmailState.DRAFT_FAILED → frozenset({EmailState.CRM_SYNCED})  # back to precondition for retry
```

**Precondition:** email.state MUST be `CRM_SYNCED`. Always use `email.transition_to()`, never direct assignment.

## LLM Adapter ABC — actual method signatures (from `src/adapters/llm/base.py`)

```python
class LLMAdapter(abc.ABC):
    async def classify(self, prompt: str, system_prompt: str, options: ClassifyOptions) -> ClassificationResult: ...
    async def generate_draft(self, prompt: str, system_prompt: str, options: DraftOptions) -> DraftText: ...
    async def test_connection(self) -> ConnectionTestResult: ...
```

**`generate_draft()` has NO fallback** — errors propagate to caller. No `OutputParseError` silencing for drafts.

### LLM adapter schemas (from `src/adapters/llm/schemas.py`)

```python
class DraftText(BaseModel):
    content: str                     # the generated draft text
    model_used: str                  # which model produced it
    fallback_applied: bool = False

class DraftOptions(BaseModel):
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    max_tokens: int = Field(default=2000, gt=0)
    model: str | None = None         # None → uses LLMConfig.draft_model

class LLMConfig(BaseModel):
    classify_model: str
    draft_model: str                 # used when DraftOptions.model is None
    fallback_model: str
    api_key: str | None = None
    base_url: str | None = None
    timeout_seconds: int = Field(default=30, gt=0)
```

### LLM exceptions (from `src/adapters/llm/exceptions.py`)

```python
class LLMAdapterError(Exception):          # base — has original_error attribute
class LLMConnectionError(LLMAdapterError): ...   # network/DNS/endpoint
class LLMRateLimitError(LLMAdapterError):        # 429 — has retry_after_seconds: int | None
class LLMTimeoutError(LLMAdapterError): ...      # exceeded timeout_seconds
class OutputParseError(LLMAdapterError): ...     # internal to adapter — NEVER seen by service
```

**Constructor patterns:**
```python
LLMConnectionError("message", original_error=exc)
LLMRateLimitError("message", retry_after_seconds=30, original_error=exc)
LLMTimeoutError("message", original_error=exc)
```

## Email Adapter ABC — `create_draft` signature (from `src/adapters/email/base.py`)

```python
class EmailAdapter(abc.ABC):
    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> DraftId:
        """Sync method — NOT async def. Wrap with asyncio.to_thread() from async service."""
```

**Return type:** `DraftId = NewType("DraftId", str)` (from `src.adapters.email.schemas`).

### Email adapter exceptions (from `src/adapters/email/exceptions.py`)

```python
class EmailAdapterError(Exception):           # base — has original_error
class AuthError(EmailAdapterError): ...       # OAuth2 invalid/expired
class RateLimitError(EmailAdapterError): ...  # 429
class EmailConnectionError(EmailAdapterError): ...  # 5xx/network
class DraftCreationError(EmailAdapterError): ...    # draft-specific failure
```

**Import from `src.adapters.email`** (package exports all via `__init__.py`).

## Draft ORM model (from `src/models/draft.py`)

```python
class DraftStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class Draft(Base, TimestampMixin):
    __tablename__ = "drafts"
    id: Mapped[uuid.UUID]               # PK, default=uuid.uuid4
    email_id: Mapped[uuid.UUID]         # FK → emails.id CASCADE, indexed
    content: Mapped[str]                # Text, not nullable
    status: Mapped[DraftStatus]         # default=PENDING, values_callable=_enum_values
    reviewer_id: Mapped[uuid.UUID | None]  # FK → users.id SET NULL
    reviewed_at: Mapped[datetime | None]
    pushed_to_provider: Mapped[bool]    # default=False
```

**No `model_used` column.** Store in `DraftResult` only. Constructor needs explicit `id=uuid.uuid4()`.

## CRMSyncRecord — what B11 can read (from `src/models/crm_sync.py`)

```python
class CRMSyncRecord(Base, TimestampMixin):
    __tablename__ = "crm_sync_records"
    contact_id: Mapped[str | None]      # ONLY usable CRM field for context
    activity_id: Mapped[str | None]
    lead_id: Mapped[str | None]
    status: Mapped[CRMSyncStatus]       # SYNCED/FAILED/SKIPPED
```

**No `metadata` JSONB column.** `_extract_crm_context()` can only populate `CRMContextData.contact_id`. Other fields (`contact_name`, `company`, `account_tier`, `recent_interactions`) will be `None`/`[]`.

## Config settings — what exists vs what to add

### Already in `config.py` (reuse — do NOT add duplicates)

```python
max_body_length: int = Field(default=4000)       # body truncation
llm_model_draft: str = Field(default="gpt-4o")
llm_temperature_draft: float = Field(default=0.7)
llm_draft_max_tokens: int = Field(default=2000)
llm_timeout_seconds: int = Field(default=30)
openai_api_key: str = Field(default="")
anthropic_api_key: str = Field(default="")
llm_fallback_model: str = Field(default="gpt-3.5-turbo")
llm_base_url: str = Field(default="")
```

### To ADD to `config.py` (after CRM Sync section, before `def get_settings()`)

```python
# Draft Generation (Cat 8: configurable defaults)
draft_push_to_gmail: bool = Field(default=False)
draft_org_system_prompt: str = Field(default="")
draft_org_tone: str = Field(default="professional")
draft_org_signature: str = Field(default="")
draft_org_prohibited_language: str = Field(default="")  # comma-separated
draft_generation_retry_max: int = Field(default=2)
```

**Map Settings → DraftGenerationConfig:**
```python
DraftGenerationConfig(
    push_to_gmail=settings.draft_push_to_gmail,
    org_context=OrgContext(
        system_prompt=settings.draft_org_system_prompt,
        tone=settings.draft_org_tone,
        signature=settings.draft_org_signature or None,
        prohibited_language=[s.strip() for s in settings.draft_org_prohibited_language.split(",") if s.strip()],
    ),
    retry_max=settings.draft_generation_retry_max,
)
```

## Service schemas (from spec — schemas are accurate, copy as-is)

```python
# src/services/schemas/draft.py

class EmailContent(BaseModel):
    sender_email: str
    sender_name: str | None = None
    subject: str
    body_snippet: str              # truncated to max_body_length — NEVER full body_plain
    received_at: str               # ISO 8601

class ClassificationContext(BaseModel):
    action: str                    # ActionCategory slug
    type: str                      # TypeCategory slug
    confidence: str                # "high" | "low"

class CRMContextData(BaseModel):
    contact_name: str | None = None
    company: str | None = None
    account_tier: str | None = None
    recent_interactions: list[str] = []    # summaries, not objects
    contact_id: str | None = None

class OrgContext(BaseModel):
    system_prompt: str
    tone: str
    signature: str | None = None
    prohibited_language: list[str] = []

class DraftContext(BaseModel):
    email_content: EmailContent
    classification: ClassificationContext
    crm_context: CRMContextData | None = None
    org_context: OrgContext
    template: str | None = None
    notes: list[str] = []

class DraftRequest(BaseModel):
    email_id: uuid.UUID
    email_content: EmailContent
    classification: ClassificationContext
    template_id: str | None = None
    push_to_gmail: bool = False

class DraftResult(BaseModel):
    email_id: uuid.UUID
    draft_id: uuid.UUID | None = None
    gmail_draft_id: str | None = None     # DraftId is NewType(str), str is compatible
    status: str                            # "generated" | "failed" | "generated_push_failed"
    model_used: str | None = None
    fallback_applied: bool = False
    error_detail: str | None = None

class DraftGenerationConfig(BaseModel):
    push_to_gmail: bool
    org_context: OrgContext
    retry_max: int
```

## Architecture overview

### DraftContextBuilder (pure-local, zero try/except — D8)

```python
class DraftContextBuilder:
    def build(self, request, crm_record, template_content, org_context) -> DraftContext:
        # 1. Extract CRM context if available (conditional, not try/except)
        # 2. Resolve template (conditional, not try/except)
        # 3. Append notes for missing data
        # 4. Return DraftContext

    def _extract_crm_context(self, record: CRMSyncRecord) -> CRMContextData:
        return CRMContextData(contact_id=record.contact_id)  # only field available

    def build_llm_prompt(self, context: DraftContext) -> str:
        # Sections: EMAIL / CLASSIFICATION / CRM CONTEXT / TEMPLATE / NOTES / INSTRUCTIONS
        # Separator: "\n\n---\n\n"
```

**Grep enforcement:** `grep -n "try\|except" src/services/draft_context.py` must be empty (or comments only).

### DraftGenerationService

```python
class DraftGenerationService:
    def __init__(self, *, llm_adapter: LLMAdapter, email_adapter: EmailAdapter, config: DraftGenerationConfig):
        self._context_builder = DraftContextBuilder()

    async def generate(self, request: DraftRequest, db: AsyncSession) -> DraftResult:
        # 1. Load CRM record from DB (optional, for context)
        # 2. Load template from DB if template_id set (placeholder for B14)
        # 3. DraftContextBuilder.build() → DraftContext (local — no try/except)
        # 4. build_llm_prompt() → str (local — no try/except)
        # 5. llm_adapter.generate_draft(prompt, system_prompt, options) → DraftText
        #    - LLMConnectionError → DRAFT_FAILED, return failed result
        #    - LLMRateLimitError → re-raise (task retries)
        #    - LLMTimeoutError → DRAFT_FAILED, return failed result
        # 6. Create Draft(content=draft_text.content, status=PENDING) → db.flush()
        # 7. COMMIT (D13) — draft persists before push
        # 8. transition_to(DRAFT_GENERATED), commit
        # 9. If push_to_gmail: asyncio.to_thread(email_adapter.create_draft, ...)
        #    - EmailAdapterError → log warning, pushed_to_provider stays False
        #    - Gmail push failure → DRAFT_GENERATED (NOT DRAFT_FAILED) per SCRATCHPAD B11
        # 10. Return DraftResult
```

## Exception strategy

| Operation | Type | Pattern |
|-----------|------|---------|
| `llm_adapter.generate_draft()` | External state | `try/except LLMConnectionError, LLMRateLimitError, LLMTimeoutError` |
| `email_adapter.create_draft()` | External state | `try/except EmailAdapterError` — failure silenced, logged |
| Draft `db.flush()` + `db.commit()` | External state | `try/except SQLAlchemyError` → DRAFT_FAILED |
| DB load CRM record | External state | `try/except SQLAlchemyError` (or let propagate) |
| `DraftContextBuilder.build()` | Local computation | Zero try/except (D8) — conditionals only |
| `build_llm_prompt()` | Local computation | Zero try/except (D8) — string assembly |
| Body truncation | Local computation | Slicing: `body_plain[:max_body_length]` — D8 |

**`LLMRateLimitError` is the ONLY exception re-raised from service** — goes to Celery task for retry.

## Celery task pattern (from `src/tasks/crm_sync_task.py`)

```python
def draft_generation_task(self: object, email_id: str) -> None:
    asyncio.run(_run_draft_generation(self, email_id))

async def _run_draft_generation(task: object, email_id_str: str) -> None:
    # Deferred imports to avoid circular imports
    # Load email, build DraftRequest, call service.generate()
    # LLMRateLimitError → task.retry(countdown=exc.retry_after_seconds or 60) from exc
    # Exception → task.retry(exc=exc) from exc
    # No state transition in task — service handles it
```

## Privacy (MANDATORY — Sec 6.5)

- `EmailContent.body_snippet` is truncated to `max_body_length` — NEVER full `body_plain`
- Logger NEVER logs `subject`, `body_plain`, `sender_email`, `snippet`, `body_snippet`
- OK to log: `email_id`, `draft_id`, `gmail_draft_id`, `model_used`, `status`

## HITL verification (mandatory grep — no auto-send)

```bash
grep -rn "send_message\|send_email\|auto_send\|send_after" \
  src/services/draft_generation.py src/services/draft_context.py src/tasks/draft_generation_task.py
# Must return EMPTY — any match = block NOT complete
```

## Test patterns

### Key scenarios

**DraftContextBuilder (5+ tests):**
1. Full context: all sources present → complete DraftContext
2. No CRM record → `crm_context=None`, notes includes "CRM context unavailable"
3. No template: `template_content=None`, `template_id` set → note about missing template
4. Both CRM and template missing → both notes present
5. Prompt does NOT contain full body — only `body_snippet`
6. `build_llm_prompt()` includes classification section

**DraftGenerationService (9+ tests):**
1. Happy path: LLM succeeds, push=False → Draft in DB, `status="generated"`, email=DRAFT_GENERATED
2. Happy path with push: Gmail succeeds → `gmail_draft_id` populated, `pushed_to_provider=True`
3. Gmail push fails → email stays DRAFT_GENERATED, `status="generated_push_failed"`
4. `LLMConnectionError` → email=DRAFT_FAILED, `draft_id=None`, `status="failed"`
5. `LLMTimeoutError` → same as connection error
6. `LLMRateLimitError` → re-raised, email stays CRM_SYNCED
7. DB error on Draft save → email=DRAFT_FAILED, `status="failed"`
8. HITL: no auto-send call path (grep check)
9. `DraftContextBuilder.build()` never raises (fuzz)

**Task (4 tests):**
1. `LLMRateLimitError` → `task.retry()` with countdown
2. Generic exception → `task.retry()`
3. Email not found → log, return
4. Success → no exception

### Mocking pattern

```python
# LLM adapter: AsyncMock
mock_llm = AsyncMock(spec=LLMAdapter)
mock_llm.generate_draft.return_value = DraftText(content="Dear Customer, ...", model_used="gpt-4o")

# Email adapter: MagicMock (sync method!)
mock_email = MagicMock(spec=EmailAdapter)
mock_email.create_draft.return_value = DraftId("gmail-draft-123")

# DB session: AsyncMock with side_effect for sequential queries
mock_db = AsyncMock()
mock_db.add = MagicMock()
mock_db.flush = AsyncMock()
mock_db.commit = AsyncMock()

# ORM models: MagicMock()
mock_email_orm = MagicMock()
mock_email_orm.state = EmailState.CRM_SYNCED
```

## Quality gates

```bash
python -m mypy src/services/schemas/draft.py src/services/draft_context.py src/services/draft_generation.py src/tasks/draft_generation_task.py
python -m ruff check src/services/draft_context.py src/services/draft_generation.py src/services/schemas/draft.py src/tasks/draft_generation_task.py
python -m ruff format src/services/ src/tasks/draft_generation_task.py --check
pytest tests/unit/test_draft_schemas.py tests/unit/test_draft_context_builder.py tests/unit/test_draft_generation_service.py tests/unit/test_draft_generation_task.py -v
pytest tests/ -q  # full suite, 0 regressions
grep -rn "send_message\|send_email\|auto_send\|send_after" src/services/draft_generation.py src/services/draft_context.py src/tasks/draft_generation_task.py  # EMPTY
grep -rn "body_plain\|body_html" src/services/draft_generation.py src/tasks/draft_generation_task.py  # EMPTY (or comments only)
grep -n "try\|except" src/services/draft_context.py  # EMPTY (or comments only)
bash scripts/validate-docs.sh
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]` at boundaries
- Contract docstrings on service class and `generate()` method
- `structlog.get_logger(__name__)`
- `from datetime import UTC, datetime` + `datetime.now(UTC)`
- Commit: `feat(draft): block-11 — draft generation service, N tests`
