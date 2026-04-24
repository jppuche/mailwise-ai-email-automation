# Block 09: Routing Service — Agent Context Handoff

> Read this INSTEAD of exploring the codebase. Full spec: `docs/specs/block-09-routing.md`.

## What to build

`src/services/` — RoutingService that orchestrates: load rules from DB → evaluate conditions via RuleEngine → compute idempotent dispatch IDs → dispatch to channel adapters → record each RoutingAction independently → transition email state. Plus RuleEngine (pure local, no I/O).

### Files to create

| File | Purpose |
|------|---------|
| `src/services/schemas/routing.py` | RoutingContext, RoutingRequest, RuleMatchResult, RoutingActionDef, RoutingResult, RuleTestResult |
| `src/services/rule_engine.py` | RuleEngine — evaluates conditions against RoutingContext. **0 try/except, 0 ORM imports, 0 adapter imports** |
| `src/services/routing.py` | RoutingService class (route + test_route) |
| `tests/unit/test_routing_schemas.py` | Schema tests |
| `tests/unit/test_rule_engine.py` | RuleEngine tests (all operators, AND logic, malformed conditions) |
| `tests/unit/test_routing_service.py` | Service tests (mocked channel adapters + DB) |
| `tests/unit/test_routing_idempotency.py` | dispatch_id determinism + skip existing dispatch |
| `tests/unit/test_routing_test_mode.py` | Dry-run guarantees (no adapter calls, no state change) |

### Files to modify

| File | Change |
|------|--------|
| `src/core/config.py` | Add `routing_vip_senders`, `routing_dashboard_base_url`, `routing_snippet_length` |

## Architecture overview

```
RoutingService.route(email_id, db)
  1. Load email from DB (must be CLASSIFIED)
  2. Load ClassificationResult DB record for email_id
  3. Load active ActionCategory + TypeCategory (for slug resolution)
  4. Build RoutingContext from email + ClassificationResult
  5. Load active routing rules from DB (ORDER BY priority DESC)
  6. RuleEngine.evaluate(context, rules) → list[RuleMatchResult]
  7. For each match, for each action:
     a. Compute dispatch_id = SHA-256[:32]("{email_id}:{rule_id}:{channel}:{destination}")
     b. Check idempotency: if RoutingAction exists with DISPATCHED → skip
     c. Build RoutingPayload (pure local)
     d. Call adapter.send_notification(payload, destination_id)
     e. Record RoutingAction (own db.commit() — D13)
     f. On channel error: record FAILED, continue to next action (Cat 6)
  8. Determine final state:
     - ≥1 DISPATCHED → ROUTED
     - All FAILED → ROUTING_FAILED
     - 0 rules matched → ROUTED (unrouted is valid, not error)
  9. Transition email state → commit
  10. Return RoutingResult
```

## DB Models needed (B01 — what B09 reads/writes)

### RoutingRule (read — conditions + actions)

```python
# src/models/routing.py

class RoutingConditions(TypedDict):
    """Single condition in JSONB conditions array."""
    field: str      # "action_category" | "type_category" | "sender_domain" | "subject_contains"
    operator: str   # "eq" | "contains" | "in" | "not_in"
    value: str | list[str]

class RoutingActions(TypedDict):
    """Single action in JSONB actions array."""
    channel: str        # "slack" | "email" | "hubspot"
    destination: str    # Channel ID, email, pipeline ID
    template_id: str | None

class RoutingRule(Base, TimestampMixin):
    id: Mapped[uuid.UUID]           # primary key
    name: Mapped[str]               # String(255)
    priority: Mapped[int]           # Integer, default=0, indexed
    is_active: Mapped[bool]         # Boolean, default=True
    conditions: Mapped[list[RoutingConditions]]  # JSONB array
    actions: Mapped[list[RoutingActions]]         # JSONB array
```

### RoutingAction (write — one per dispatch attempt)

```python
class RoutingActionStatus(StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    FAILED = "failed"
    SKIPPED = "skipped"

class RoutingAction(Base, TimestampMixin):
    id: Mapped[uuid.UUID]
    email_id: Mapped[uuid.UUID]           # FK → emails.id CASCADE
    rule_id: Mapped[uuid.UUID | None]     # FK → routing_rules.id SET NULL
    channel: Mapped[str]                  # String(50)
    destination: Mapped[str]              # String(255)
    priority: Mapped[int]                 # Integer
    status: Mapped[RoutingActionStatus]   # Enum, default=PENDING
    dispatch_id: Mapped[str | None]       # String(255) — SHA-256[:32]
    dispatched_at: Mapped[datetime | None]
    attempts: Mapped[int]                 # Integer, default=0
```

### ClassificationResult (read — B08 output)

```python
# src/models/classification.py
class ClassificationResult(Base, TimestampMixin):
    id: Mapped[uuid.UUID]
    email_id: Mapped[uuid.UUID]            # FK → emails.id
    action_category_id: Mapped[uuid.UUID]  # FK → action_categories.id
    type_category_id: Mapped[uuid.UUID]    # FK → type_categories.id
    confidence: Mapped[ClassificationConfidence]  # "high" | "low"
    raw_llm_output: Mapped[dict]           # JSONB
    fallback_applied: Mapped[bool]
    classified_at: Mapped[datetime]
```

### Email (read + state transition)

```python
# Relevant fields for B09:
email.id              # UUID
email.sender_email    # str
email.sender_name     # str | None
email.subject         # str
email.snippet         # str | None — max 500 chars
email.body_plain      # str | None — sanitized, max 4000 chars
email.state           # EmailState — must be CLASSIFIED

# State transitions for B09:
# Precondition: email.state == CLASSIFIED
# Happy path: CLASSIFIED → ROUTED
# Error path: CLASSIFIED → ROUTING_FAILED
# Unrouted (no matching rules): CLASSIFIED → ROUTED (not ROUTING_FAILED!)
```

## Channel Adapter interface (B05 — what B09 calls)

**IMPORTANT:** `send_notification` takes **two arguments**: `payload` and `destination_id` (separate parameter, NOT inside payload). The spec's `_dispatch_rule_actions` examples show only one argument — this is incorrect.

```python
class ChannelAdapter(abc.ABC):
    async def send_notification(
        self,
        payload: RoutingPayload,
        destination_id: str,     # ← separate from payload!
    ) -> DeliveryResult:
        """
        Errors raised: ValueError, ChannelAuthError, ChannelRateLimitError,
                       ChannelConnectionError, ChannelDeliveryError
        Errors silenced: None.
        """
```

### RoutingPayload (what B09 constructs, B05 consumes)

```python
# src/adapters/channel/schemas.py
class RoutingPayload(BaseModel):
    email_id: str
    subject: str
    sender: SenderInfo           # SenderInfo(email=str, name=str|None)
    classification: ClassificationInfo  # ClassificationInfo(action=str, type=str, confidence=Literal["high","low"])
    priority: Literal["urgent", "normal", "low"]
    snippet: str
    dashboard_link: str
    assigned_to: str | None = None
    timestamp: datetime

class DeliveryResult(BaseModel):
    success: bool
    message_ts: str | None = None    # Slack thread reply timestamp
    channel_id: str | None = None
    error_detail: str | None = None
```

### Channel exceptions (from `src/adapters/channel/exceptions.py`)

```python
class ChannelAdapterError(Exception):            # base — has original_error attribute
class ChannelAuthError(ChannelAdapterError):      # token invalid/revoked
class ChannelRateLimitError(ChannelAdapterError): # 429 — has retry_after_seconds
class ChannelConnectionError(ChannelAdapterError): # network/timeout
class ChannelDeliveryError(ChannelAdapterError):   # channel not found, bot not in channel
```

**Constructor pattern:** all channel exceptions use keyword args:
```python
ChannelAuthError("message", original_error=exc)
ChannelRateLimitError("message", retry_after_seconds=30, original_error=exc)
```

## CRITICAL: Naming collision (carry-forward from B08)

`ClassificationResult` exists as **both** an ORM model and an adapter schema. B09 reads the **ORM** model from DB. If you also need the adapter schema, alias it:
```python
from src.models.classification import ClassificationResult  # ORM — this is what B09 reads
```

## RuleEngine (pure local — 0 try/except, 0 ORM imports, 0 adapter imports)

### Operator enums (module-level in `rule_engine.py`)

```python
class ConditionOperator(str, enum.Enum):
    EQ = "eq"
    CONTAINS = "contains"
    IN = "in"
    NOT_IN = "not_in"
    STARTS_WITH = "starts_with"
    MATCHES_DOMAIN = "matches_domain"  # wildcard: "*.company.com"

class ConditionField(str, enum.Enum):
    ACTION_CATEGORY = "action_category"
    TYPE_CATEGORY = "type_category"
    SENDER_DOMAIN = "sender_domain"
    SENDER_EMAIL = "sender_email"
    SUBJECT = "subject"
    CONFIDENCE = "confidence"
```

### Operator behavior table

| Operator | Value type | Logic |
|----------|-----------|-------|
| `eq` | `str` | `context_value == value` (case-insensitive) |
| `contains` | `str` | `value.lower() in context_value.lower()` |
| `in` | `list[str]` | `context_value.lower() in [v.lower() for v in value]` |
| `not_in` | `list[str]` | `context_value.lower() not in [v.lower() for v in value]` |
| `starts_with` | `str` | `context_value.lower().startswith(value.lower())` |
| `matches_domain` | `str` | wildcard `"*.company.com"` matches `"sub.company.com"` |

### Evaluation logic

- All conditions within a rule must match (AND logic)
- Only `is_active=True` rules are evaluated
- Rules arrive pre-sorted by `priority DESC` from DB; RuleEngine preserves order
- **All matching rules execute** — NOT "first match wins"
- Malformed condition (unknown field/operator): treated as no-match + `logger.warning()`

### RuleEngine interface

```python
class RuleEngine:
    """Evaluates routing conditions — pure local computation, no I/O.

    Takes ONLY service-layer schemas (RoutingContext) and ORM models (RoutingRule).
    Does NOT call any adapter. Does NOT write to DB.
    """

    def evaluate(
        self,
        context: RoutingContext,
        rules: list[RoutingRule],
    ) -> list[RuleMatchResult]:
        """Returns matching rules in priority order. Never raises."""
```

**Note:** RuleEngine receives `RoutingRule` ORM models (read-only) but MUST NOT import from `src.adapters.*`. The only `src.models` import is `RoutingRule` and the TypedDicts. The key enforcement is: 0 adapter imports, 0 try/except.

## Service schemas to create

```python
# src/services/schemas/routing.py

class RoutingContext(BaseModel):
    """Classification context for rule evaluation — decoupled from ORM."""
    email_id: uuid.UUID
    action_slug: str
    type_slug: str
    confidence: Literal["high", "low"]
    sender_email: str
    sender_domain: str
    subject: str
    snippet: str
    sender_name: str | None = None

class RoutingRequest(BaseModel):
    """Input to the routing service."""
    email_id: uuid.UUID

class RuleMatchResult(BaseModel):
    """A rule that matched + its actions to execute."""
    rule_id: uuid.UUID
    rule_name: str
    priority: int
    actions: list[RoutingActionDef]

class RoutingActionDef(BaseModel):
    """Action definition — decoupled from ORM RoutingActions TypedDict."""
    channel: str
    destination: str
    template_id: str | None = None

class RoutingResult(BaseModel):
    """Complete result of routing an email."""
    email_id: uuid.UUID
    rules_matched: int
    rules_executed: int
    actions_dispatched: int
    actions_failed: int
    was_routed: bool              # True if ≥1 action succeeded
    routing_action_ids: list[uuid.UUID]
    final_state: str              # "ROUTED" | "ROUTING_FAILED"

class RuleTestResult(BaseModel):
    """Dry-run result — no dispatches, no state changes."""
    context: RoutingContext
    rules_matched: list[RuleMatchResult]
    would_dispatch: list[RoutingActionDef]
    total_actions: int
    dry_run: bool = True
```

## Idempotency (dispatch_id)

```python
def _compute_dispatch_id(
    email_id: uuid.UUID,
    rule_id: uuid.UUID,
    channel: str,
    destination: str,
) -> str:
    """SHA-256[:32] of "{email_id}:{rule_id}:{channel}:{destination}".
    Pure local computation — deterministic, no try/except."""
    import hashlib
    raw = f"{email_id}:{rule_id}:{channel}:{destination}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
```

**Before dispatching each action:**
1. Query DB for existing `RoutingAction` with same `dispatch_id`
2. If exists with `status=DISPATCHED` → skip (return existing, don't call adapter)
3. If exists with `status=FAILED` → re-dispatch is legitimate (retry scenario)
4. If not found → proceed to dispatch

## Partial failure pattern (Cat 6 — D13)

**Each action commits independently. Failure in action N does NOT:**
- Revert action N-1 (already committed)
- Stop action N+1 from executing
- Prevent the email from transitioning to ROUTED (if any action succeeded)

```
Rule 1 → Action A (DISPATCHED, committed) → Action B (FAILED, committed)
Rule 2 → Action C (DISPATCHED, committed)
→ Email state: ROUTED (≥1 DISPATCHED)
```

## VIP sender priority

VIP senders loaded from `ROUTING_VIP_SENDERS` env var (comma-separated emails and `*.domain` patterns). Parsed once at service construction.

Priority determination (pure local — conditionals, no try/except):
1. VIP sender → `"urgent"` always
2. `context.action_slug == "escalate"` → `"urgent"`
3. Urgent keywords in subject → `"urgent"`
4. Rule priority ranges: 67+ = `"urgent"`, 34-66 = `"normal"`, 0-33 = `"low"`

## State final determination

```python
# Pure local computation — conditionals, no try/except
if len(matched_rules) == 0:
    new_state = EmailState.ROUTED        # Unrouted is valid, not error
elif dispatched_count > 0:
    new_state = EmailState.ROUTED        # ≥1 success
else:
    new_state = EmailState.ROUTING_FAILED # All failed
```

**Single state transition at the end** — not per-action. The final `db.commit()` for the email state is separate from per-action commits.

## Exception strategy (try-except D7/D8)

### External-state operations (try/except with specific types)

| Boundary | Exception type | Scope |
|----------|---------------|-------|
| DB: load email | `SQLAlchemyError` | Abort routing |
| DB: load classification result | `SQLAlchemyError` | Abort routing |
| DB: load routing rules | `SQLAlchemyError` | Abort routing |
| DB: check dispatch idempotency | `SQLAlchemyError` | Skip this action (can't verify → don't dispatch) |
| ChannelAdapter.send_notification | `ChannelAuthError`, `ChannelRateLimitError`, `ChannelConnectionError`, `ChannelDeliveryError` | Per-action FAILED, continue |
| DB: record RoutingAction | `SQLAlchemyError` | Log error, continue |
| DB: transition email state | `SQLAlchemyError` | Abort (but dispatches already committed) |

### Local computation (NO try/except — D8)

| Operation | Why no try/except |
|-----------|-------------------|
| `RuleEngine.evaluate()` | Pure function — conditionals only |
| `_compute_dispatch_id()` | Deterministic hash — cannot fail |
| `_build_routing_payload()` | RoutingContext already validated by Pydantic |
| `_determine_dispatch_priority()` | Conditionals on validated data |
| Final state determination | Counting dispatched/failed actions |

## RoutingService constructor pattern

Follow B08's keyword-only pattern. **Do NOT inject `llm_adapter`** — B09 doesn't use it:

```python
class RoutingService:
    def __init__(
        self,
        *,
        channel_adapters: dict[str, ChannelAdapter],
        settings: Settings,
    ) -> None:
        self._channel_adapters = channel_adapters
        self._settings = settings
        self._rule_engine = RuleEngine()
        self._vip_senders = _parse_vip_senders(settings.routing_vip_senders)
```

**Adapter lookup:** `self._channel_adapters.get(channel)` → `ValueError` if None. This enables test injection without subclassing.

## Load-bearing defaults (Cat 8) — to add to config.py

| Default | Value | Env Var | Already in config? |
|---------|-------|---------|--------------------|
| VIP senders | `""` (empty) | `ROUTING_VIP_SENDERS` | **No — add** |
| Dashboard base URL | `http://localhost:3000` | `ROUTING_DASHBOARD_BASE_URL` | **No — add** |
| Routing snippet length | `150` | `ROUTING_SNIPPET_LENGTH` | **No — add** (should match `channel_snippet_length`) |
| Max retries per action | `3` | `CELERY_MAX_RETRIES` | Yes (existing) |
| Backoff base | `60s` | `CELERY_BACKOFF_BASE` | Yes (existing) |
| Channel snippet length | `150` | `CHANNEL_SNIPPET_LENGTH` | Yes (B05) |

## Privacy (Sec 11.4 — MANDATORY)

- Logger NEVER logs `subject`, `body_plain`, `sender_email`, `snippet`
- OK to log: `email_id` (UUID), `dispatch_id`, `rule_id`, `channel`, `status`, `priority`
- `RoutingPayload` contains PII (sender email, subject, snippet) — never log the full payload object

## Hard enforcement rules (grep-verifiable exit conditions)

These **must** pass before commit:
```bash
# RuleEngine: 0 try/except, 0 adapter imports
grep "^    try:" src/services/rule_engine.py      # must return EMPTY
grep "src.adapters" src/services/rule_engine.py    # must return EMPTY

# RoutingService: channel exceptions caught with specific types (not bare except)
grep "except Exception" src/services/routing.py    # must return EMPTY
grep "except:" src/services/routing.py             # must return EMPTY

# dispatch_id uses SHA-256 (not MD5 or random)
grep "sha256" src/services/routing.py              # must MATCH
```

## Test patterns

### Test file locations (flat convention from B03-B08)

```
tests/unit/test_routing_schemas.py
tests/unit/test_rule_engine.py
tests/unit/test_routing_service.py
tests/unit/test_routing_idempotency.py
tests/unit/test_routing_test_mode.py
```

**NOTE:** Spec says `tests/services/routing/` — IGNORE this. Use `tests/unit/` (flat convention established in B03).

### Key test scenarios

**RuleEngine:**
1. Single condition `eq` match → rule in results
2. `contains` operator → case-insensitive substring match
3. `in` operator → value list membership
4. `not_in` operator → exclusion match
5. `starts_with` operator → prefix match
6. `matches_domain` → wildcard domain matching
7. Multiple conditions (AND logic) → all must match
8. Inactive rule → excluded from results
9. Unknown field/operator → treated as no-match (no exception)
10. Empty rules list → empty results
11. Priority order preserved in output

**Idempotency:**
1. Same `(email_id, rule_id, channel, destination)` → same `dispatch_id`
2. Different inputs → different `dispatch_id`
3. Existing DISPATCHED action → skip adapter call, return existing
4. Existing FAILED action → re-dispatch allowed

**Routing Service:**
1. Happy path: CLASSIFIED email + 1 matching rule → ROUTED, 1 RoutingAction
2. Multiple matching rules → all executed (not first-match-wins)
3. No matching rules → ROUTED (unrouted), 0 RoutingActions
4. Partial failure: 2 rules, 1 fails → ROUTED (≥1 success)
5. All actions fail → ROUTING_FAILED
6. VIP sender → priority elevated to "urgent"
7. Email not CLASSIFIED → InvalidStateTransitionError
8. Channel adapter not found → ValueError for that action, others continue

**Test mode (dry-run):**
1. Matching rules returned in result
2. `adapter.send_notification` never called (mock `assert_not_called()`)
3. No `RoutingAction` created in DB
4. Email state unchanged

### Mocking pattern for tests

```python
# Mock channel adapter
mock_adapter = AsyncMock(spec=ChannelAdapter)
mock_adapter.send_notification.return_value = DeliveryResult(
    success=True, message_ts="1234567890.123456", channel_id="C123"
)

# Inject via constructor
service = RoutingService(
    channel_adapters={"slack": mock_adapter},
    settings=mock_settings,
)
```

## Existing code patterns to follow (from B07/B08)

- Constructor injection: `__init__(*, adapters, settings)` keyword-only
- `structlog.get_logger(__name__)` for logging
- Per-item isolation in batch/multi-action processing
- Independent commits per action (not transaction-per-batch)
- `mapped_column(default=uuid.uuid4)` is INSERT-time only → explicit `id=uuid.uuid4()` in constructor calls
- `from src.models.email import Email, EmailState` for state machine
- `from src.core.exceptions import InvalidStateTransitionError` for state guard

## Open questions from SCRATCHPAD (resolve during implementation)

- `frozenset[str]` vs `set[str]` for VIP senders → use `frozenset` (immutable after construction, Cat 3)
- Spec includes `llm_adapter` in constructor → DROP it (B09 doesn't use LLM)
- Spec's `send_notification(payload)` → actually `send_notification(payload, destination_id)` (B05 ABC)
- Spec's test dir `tests/services/routing/` → use `tests/unit/` (flat convention)

## Quality gates (must pass before commit)

```bash
python -m mypy src/services/routing.py src/services/rule_engine.py src/services/schemas/routing.py
python -m ruff check src/services/ && python -m ruff format src/services/ --check
pytest tests/unit/test_routing_schemas.py -v
pytest tests/unit/test_rule_engine.py -v
pytest tests/unit/test_routing_service.py -v
pytest tests/unit/test_routing_idempotency.py -v
pytest tests/unit/test_routing_test_mode.py -v
pytest tests/ -q  # full non-integration suite
# Enforcement greps:
grep "^    try:" src/services/rule_engine.py && echo "FAIL: try in rule_engine" || echo "OK"
grep "src.adapters" src/services/rule_engine.py && echo "FAIL: adapter import in rule_engine" || echo "OK"
grep "except Exception" src/services/routing.py && echo "FAIL: bare except in routing" || echo "OK"
grep "sha256" src/services/routing.py || echo "FAIL: no sha256 in routing"
bash scripts/validate-docs.sh
```

## Style rules

- snake_case files/vars/functions, PascalCase classes
- Type hints on public functions, no `dict[str, Any]` at boundaries
- Contract docstrings: Preconditions, Guarantees, Errors raised, Errors silenced
- `structlog.get_logger(__name__)` — no `# type: ignore` needed
- Commit: `feat(routing): block-09 — routing service, N tests`
