# Bloque 1: Database Models & Migrations

## Objetivo

Definir todos los modelos SQLAlchemy 2.0 con EmailState como DB enum, categorias de clasificacion respaldadas por DB con FK validation, y la migracion inicial de Alembic que crea el schema completo.

## Dependencias

- B0 (Project Scaffolding) — requiere `src/core/config.py` para `database_url`, paquete `src/` instalable, Dockerfile funcional.

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/models/base.py` — `Base` declarativa con `DeclarativeBase`. Mixin `TimestampMixin` (created_at, updated_at con `onupdate`). UUID primary keys via `uuid.uuid4` como default del servidor Python (no `gen_random_uuid()` para portabilidad de tests).
- `src/models/email.py` — Modelo `Email` mapeando Appendix B.1. Ver "Email Model" abajo.
- `src/models/category.py` — Modelos `ActionCategory` y `TypeCategory`. Ver "Category Models" abajo.
- `src/models/classification.py` — Modelo `ClassificationResult`. Ver "Classification Model" abajo.
- `src/models/routing.py` — Modelos `RoutingRule` y `RoutingAction`. Ver "Routing Models" abajo.
- `src/models/draft.py` — Modelo `Draft`. Ver "Draft Model" abajo.
- `src/models/user.py` — Modelo `User` con `UserRole` enum. Ver "User Model" abajo.
- `src/models/crm_sync.py` — Modelo `CRMSyncRecord`. Ver "CRM Sync Model" abajo.
- `src/models/feedback.py` — Modelo `ClassificationFeedback`. Ver "Feedback Model" abajo.
- `src/models/__init__.py` — Re-exporta todos los modelos para que Alembic pueda importarlos con `from src.models import *`.
- `src/core/database.py` — Dual session factories: `AsyncSessionLocal` (FastAPI) + `SyncSessionLocal` (Celery). `get_async_db()` como dependency de FastAPI. `get_sync_db()` como context manager para tareas.
- `alembic.ini` — Config de Alembic apuntando a `alembic/` como script_location. `sqlalchemy.url` sobreescrito en `env.py` desde `Settings`.
- `alembic/env.py` — Importa `Base` de `src.models`, usa `Settings` para URL de DB. Configura `target_metadata = Base.metadata`. Soporte para migraciones async (asyncpg).
- `alembic/versions/001_initial_schema.py` — Migracion generada que crea todas las tablas, enums, indices, y constraints. Incluye datos seed para `ActionCategory` y `TypeCategory`.

### Frontend (frontend-worker)

N/A — este bloque es backend-only. Los tipos generados (OpenAPI → TypeScript) ocurren en B2 (Auth API).

### Tests (Inquisidor)

- `tests/models/__init__.py` — Vacio.
- `tests/models/test_email_state.py` — Verifica EmailState: transiciones validas pasan, transiciones invalidas lanzan `InvalidStateTransitionError`. Cubre todos los estados y todas las transiciones prohibidas.
- `tests/models/test_models_import.py` — Smoke test: todos los modelos importan sin error. Verifica que `Base.metadata.tables` contiene todas las tablas esperadas.
- `tests/models/test_migrations.py` — Usa `alembic upgrade head` + `alembic downgrade base` en DB de test. Verifica que upgrade es idempotente y downgrade limpia correctamente.
- `tests/models/test_categories_seed.py` — Verifica que los datos seed de ActionCategory y TypeCategory estan presentes tras la migracion. Verifica slugs canonicos de FOUNDATION.md Sec 4.2 y 4.3.

## Skills aplicables

- **pre-mortem (Cat 1 — implicit ordering):** Las transiciones del state machine deben ser forzadas por codigo, no por convencion. Si cualquier servicio puede escribir `email.state = EmailState.CLASSIFIED` sin pasar por `SANITIZED`, el pipeline se corrompe silenciosamente. La validacion vive en el modelo, no en el servicio.
- **pre-mortem (Cat 3 — stringly-typed):** Las categorias de clasificacion como columnas `VARCHAR` libres (sin FK) permiten que un LLM alucinado escriba `"URGENTE"` en lugar de `"urgent"` y pase validacion de DB. FK a `ActionCategory.id` y `TypeCategory.id` hace esto imposible a nivel de constraint.
- **tighten-types (D1):** `Mapped[type]` en todos los campos. JSONB fields tipados con `TypedDict` especificos — `RecipientData`, `AttachmentData`, `RoutingConditions`, `RoutingActions`. Ningun campo JSONB es `dict[str, Any]` en la firma del modelo.
- **tighten-types (D3):** `ClassificationResult` (modelo DB) es distinto de `ClassificationResult` (dataclass del LLM adapter). El modelo DB almacena el resultado; el dataclass del adapter transporta el resultado entre el adapter y el servicio. No confundir los dos.
- **contract-docstrings (D5-D6):** El modelo `Email` documenta la transicion de estado como contrato: precondiciones para cada transicion, postcondiciones garantizadas, y errores que se lanzan si la precondicion falla.

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

| Tool | Tier | Status | How it applies |
|------|------|--------|----------------|
| mcp-scan | 1 | Installed | Gate de seguridad — no aplica en este bloque de modelos/migraciones |

## EmailState Enum y State Machine (pre-mortem Cat 1)

### Estados

```python
import enum

class EmailState(str, enum.Enum):
    # Happy path
    FETCHED = "FETCHED"
    SANITIZED = "SANITIZED"
    CLASSIFIED = "CLASSIFIED"
    ROUTED = "ROUTED"
    CRM_SYNCED = "CRM_SYNCED"
    DRAFT_GENERATED = "DRAFT_GENERATED"
    COMPLETED = "COMPLETED"
    RESPONDED = "RESPONDED"

    # Error states
    CLASSIFICATION_FAILED = "CLASSIFICATION_FAILED"
    ROUTING_FAILED = "ROUTING_FAILED"
    CRM_SYNC_FAILED = "CRM_SYNC_FAILED"
    DRAFT_FAILED = "DRAFT_FAILED"
```

### Transiciones validas

```python
VALID_TRANSITIONS: dict[EmailState, frozenset[EmailState]] = {
    EmailState.FETCHED: frozenset({EmailState.SANITIZED}),
    EmailState.SANITIZED: frozenset({EmailState.CLASSIFIED, EmailState.CLASSIFICATION_FAILED}),
    EmailState.CLASSIFIED: frozenset({EmailState.ROUTED, EmailState.ROUTING_FAILED}),
    EmailState.ROUTED: frozenset({EmailState.CRM_SYNCED, EmailState.CRM_SYNC_FAILED}),
    EmailState.CRM_SYNCED: frozenset({EmailState.DRAFT_GENERATED, EmailState.DRAFT_FAILED}),
    EmailState.DRAFT_GENERATED: frozenset({EmailState.COMPLETED}),
    EmailState.COMPLETED: frozenset({EmailState.RESPONDED}),
    EmailState.RESPONDED: frozenset(),  # Terminal

    # Recovery paths desde estados de error
    EmailState.CLASSIFICATION_FAILED: frozenset({EmailState.SANITIZED}),  # Retry desde SANITIZED
    EmailState.ROUTING_FAILED: frozenset({EmailState.CLASSIFIED}),        # Retry desde CLASSIFIED
    EmailState.CRM_SYNC_FAILED: frozenset({EmailState.ROUTED}),           # Retry desde ROUTED
    EmailState.DRAFT_FAILED: frozenset({EmailState.CRM_SYNCED}),          # Retry desde CRM_SYNCED
}
```

### Metodo de transicion (en modelo `Email`)

```python
def transition_to(self, new_state: EmailState) -> None:
    """
    Invariants: self.state es el estado actual del email en DB.
    Guarantees: Si la transicion es valida, self.state = new_state.
    Errors: Lanza InvalidStateTransitionError si la transicion no esta en VALID_TRANSITIONS.
    State transitions: Actualiza self.state. El commit a DB es responsabilidad del caller.
    """
    allowed = VALID_TRANSITIONS.get(self.state, frozenset())
    if new_state not in allowed:
        raise InvalidStateTransitionError(
            f"Cannot transition Email {self.id} from {self.state} to {new_state}. "
            f"Allowed: {allowed}"
        )
    self.state = new_state
```

`InvalidStateTransitionError` es una excepcion de dominio definida en `src/core/exceptions.py`.

**D10 enforcement:** El campo `state` en DB es un PostgreSQL ENUM type (no VARCHAR), creado por Alembic con `sa.Enum(EmailState, name='emailstate', create_type=True)`. La DB rechaza valores fuera del enum incluso si el codigo Python falla en validar.

## Email Model (Appendix B.1)

```python
from typing import TypedDict
import uuid
import datetime
import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB, UUID

class RecipientData(TypedDict):
    email: str
    name: str
    type: str  # "to" | "cc" | "bcc"

class AttachmentData(TypedDict):
    filename: str
    mime_type: str
    size_bytes: int
    attachment_id: str

class Email(Base, TimestampMixin):
    __tablename__ = "emails"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_message_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, unique=True)
    thread_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True, index=True)
    account: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)
    sender_email: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    recipients: Mapped[list[RecipientData]] = mapped_column(JSONB, nullable=False, default=list)
    subject: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    body_plain: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    snippet: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    date: Mapped[datetime.datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    attachments: Mapped[list[AttachmentData]] = mapped_column(JSONB, nullable=False, default=list)
    provider_labels: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    state: Mapped[EmailState] = mapped_column(
        sa.Enum(EmailState, name="emailstate", create_type=True),
        nullable=False,
        default=EmailState.FETCHED,
        index=True,
    )
    processed_at: Mapped[datetime.datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    # Indices
    __table_args__ = (
        sa.Index("ix_emails_state_date", "state", "date"),
        sa.Index("ix_emails_account_state", "account", "state"),
    )
```

## Category Models (pre-mortem Cat 3)

Las categorias se almacenan en DB — no son enums Python hardcodeados — para ser configurables en runtime sin deploy.

```python
class ActionCategory(Base, TimestampMixin):
    """Capa 1: Que accion requiere el email (ej: 'urgent', 'reply', 'archive')"""
    __tablename__ = "action_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    is_fallback: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)


class TypeCategory(Base, TimestampMixin):
    """Capa 2: Que tipo de email es (ej: 'customer_support', 'sales_inquiry', 'spam')"""
    __tablename__ = "type_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    description: Mapped[str] = mapped_column(sa.Text, nullable=False, default="")
    is_fallback: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    display_order: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
```

### Datos seed (FOUNDATION.md Sec 4.2 y 4.3)

Incluidos en `alembic/versions/001_initial_schema.py` como `op.bulk_insert()` al final de `upgrade()`.

**ActionCategory seeds (Capa 1 — 4 categorias):**

| slug | name | is_fallback |
|------|------|-------------|
| `urgent` | Urgent — Requires Immediate Attention | False |
| `reply_needed` | Reply Needed — Standard Response Required | False |
| `informational` | Informational — No Action Required | False |
| `unknown` | Unknown — Fallback Category | True |

**TypeCategory seeds (Capa 2 — 10 categorias):**

| slug | name | is_fallback |
|------|------|-------------|
| `customer_support` | Customer Support Request | False |
| `sales_inquiry` | Sales Inquiry / Lead | False |
| `billing` | Billing / Payment | False |
| `technical` | Technical Issue / Bug Report | False |
| `partnership` | Partnership / Business Development | False |
| `hr_internal` | HR / Internal Communication | False |
| `legal_compliance` | Legal / Compliance | False |
| `marketing_promo` | Marketing / Promotional | False |
| `spam_automated` | Spam / Automated Message | False |
| `other` | Other — Fallback Type | True |

## Classification Model (Appendix B.2)

```python
class ClassificationResult(Base, TimestampMixin):
    """
    Resultado de clasificacion LLM para un email.
    NOTA: No confundir con el dataclass ClassificationResult del LLM adapter
    (src/adapters/llm/types.py). Este es el modelo de persistencia.
    """
    __tablename__ = "classification_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("action_categories.id"), nullable=False
    )
    type_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("type_categories.id"), nullable=False
    )
    confidence: Mapped[ClassificationConfidence] = mapped_column(
        sa.Enum(ClassificationConfidence, name="classificationconfidence", create_type=True),
        nullable=False,
    )
    raw_llm_output: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fallback_applied: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    classified_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

class ClassificationConfidence(str, enum.Enum):
    HIGH = "high"
    LOW = "low"
```

## Routing Models (Appendix B.3)

```python
class RoutingConditions(TypedDict):
    """Estructura de condiciones de routing almacenadas en JSONB."""
    field: str          # "action_category" | "type_category" | "sender_domain" | "subject_contains"
    operator: str       # "eq" | "contains" | "in" | "not_in"
    value: str | list[str]

class RoutingActions(TypedDict):
    """Estructura de acciones de routing almacenadas en JSONB."""
    channel: str        # "slack" | "email" | "hubspot"
    destination: str    # Channel ID, email address, pipeline ID
    template_id: str | None

class RoutingRule(Base, TimestampMixin):
    __tablename__ = "routing_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0, index=True)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
    conditions: Mapped[list[RoutingConditions]] = mapped_column(JSONB, nullable=False)
    actions: Mapped[list[RoutingActions]] = mapped_column(JSONB, nullable=False)


class RoutingAction(Base, TimestampMixin):
    """Registro de una accion de routing ejecutada (o intentada) para un email."""
    __tablename__ = "routing_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("routing_rules.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(sa.String(50), nullable=False)
    destination: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    priority: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[RoutingActionStatus] = mapped_column(
        sa.Enum(RoutingActionStatus, name="routingactionstatus", create_type=True),
        nullable=False,
        default=RoutingActionStatus.PENDING,
    )
    dispatch_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    dispatched_at: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)

class RoutingActionStatus(str, enum.Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    FAILED = "failed"
    SKIPPED = "skipped"
```

## Draft Model

```python
class DraftStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class Draft(Base, TimestampMixin):
    __tablename__ = "drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[DraftStatus] = mapped_column(
        sa.Enum(DraftStatus, name="draftstatus", create_type=True),
        nullable=False,
        default=DraftStatus.PENDING,
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime.datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    pushed_to_provider: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
```

## User Model

```python
class UserRole(str, enum.Enum):
    ADMIN = "admin"
    REVIEWER = "reviewer"

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(sa.String(100), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        sa.Enum(UserRole, name="userrole", create_type=True),
        nullable=False,
        default=UserRole.REVIEWER,
    )
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True)
```

## CRM Sync Model

```python
class CRMSyncStatus(str, enum.Enum):
    SYNCED = "synced"
    FAILED = "failed"
    SKIPPED = "skipped"

class CRMSyncRecord(Base, TimestampMixin):
    __tablename__ = "crm_sync_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    activity_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    lead_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
    status: Mapped[CRMSyncStatus] = mapped_column(
        sa.Enum(CRMSyncStatus, name="crmsyncstatus", create_type=True),
        nullable=False,
    )
    synced_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
```

## Feedback Model

```python
class ClassificationFeedback(Base, TimestampMixin):
    """
    Feedback de reviewer sobre clasificacion incorrecta.
    Usado por el Tier 2 feedback loop (B16) para fine-tuning de prompts.
    """
    __tablename__ = "classification_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("action_categories.id"), nullable=False
    )
    original_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("type_categories.id"), nullable=False
    )
    corrected_action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("action_categories.id"), nullable=False
    )
    corrected_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("type_categories.id"), nullable=False
    )
    corrected_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False
    )
    corrected_at: Mapped[datetime.datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
```

## Database Session Factories

`src/core/database.py` implementa dual session factories (patron establecido en DECISIONS.md para Celery + FastAPI):

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from collections.abc import AsyncGenerator
from src.core.config import get_settings

def _build_async_engine():
    settings = get_settings()
    return create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)

def _build_sync_engine():
    settings = get_settings()
    return create_engine(settings.database_url_sync, echo=False, pool_pre_ping=True)

async_engine = _build_async_engine()
sync_engine = _build_sync_engine()

AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False)
SyncSessionLocal = sessionmaker(sync_engine, expire_on_commit=False)


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency. Uso: db: AsyncSession = Depends(get_async_db)"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

**D13 (non-atomic stages):** Cada etapa del pipeline hace `session.commit()` independiente. El `get_async_db()` hace commit al final del request. Las tareas Celery usan `SyncSessionLocal` con commit explicito al final de cada etapa — no al final de la cadena completa.

## Alembic Configuration

`alembic/env.py` pattern para async:

```python
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
from src.models import Base  # Importa todos los modelos via __init__.py
from src.core.config import get_settings

config = context.config
settings = get_settings()

# Override sqlalchemy.url desde Settings (no hardcoded en alembic.ini)
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

def run_migrations_online() -> None:
    connectable = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    # ... migracion async standard pattern
```

`alembic.ini`: `script_location = alembic`. La URL de DB NO se configura en alembic.ini — se sobreescribe desde Settings en env.py para evitar duplicacion de configuracion (D14).

## TypedDict Policy (tighten-types D1)

Todos los campos JSONB de modelos tienen TypedDict asociado en el mismo archivo del modelo. Regla: si un campo es `Mapped[dict]` o `Mapped[list]`, DEBE tener su TypedDict que documente la estructura esperada. Esto no impide que la DB guarde estructuras diferentes (JSONB es schema-less), pero documenta el contrato y permite que mypy verifique los write paths.

| Modelo | Campo JSONB | TypedDict |
|--------|-------------|-----------|
| Email | recipients | `list[RecipientData]` |
| Email | attachments | `list[AttachmentData]` |
| Email | provider_labels | `list[str]` (no TypedDict necesario) |
| RoutingRule | conditions | `list[RoutingConditions]` |
| RoutingRule | actions | `list[RoutingActions]` |
| ClassificationResult | raw_llm_output | `dict` (raw output — sin TypedDict, intencional: es el output crudo del LLM antes de parsear) |

## Criterios de exito (deterministicos)

- [ ] Typecheck: `mypy src/` reporta 0 errores
- [ ] Lint: `ruff check .` reporta 0 violaciones
- [ ] Format: `ruff format --check .` sin diffs
- [ ] Tests: `pytest tests/models/` todos pasan
- [ ] Migration up: `alembic upgrade head` crea las 9 tablas: `emails`, `action_categories`, `type_categories`, `classification_results`, `routing_rules`, `routing_actions`, `drafts`, `users`, `crm_sync_records`, `classification_feedback`
- [ ] Migration down: `alembic downgrade base` elimina todas las tablas y enums sin error
- [ ] Migration idempotente: `alembic upgrade head` ejecutado dos veces no falla
- [ ] DB enums creados: `emails.state` es PostgreSQL ENUM (no VARCHAR) — verificable via `\d emails` en psql
- [ ] Importacion de modelos: `from src.models.email import Email, EmailState` funciona
- [ ] Importacion de modelos: `from src.models.category import ActionCategory, TypeCategory` funciona
- [ ] Importacion de modelos: todos los 9 modelos importan desde `src.models` (via `__init__.py`)
- [ ] State machine — transicion valida: `email.transition_to(EmailState.SANITIZED)` desde `FETCHED` actualiza `email.state`
- [ ] State machine — transicion invalida: `email.transition_to(EmailState.CLASSIFIED)` desde `FETCHED` lanza `InvalidStateTransitionError`
- [ ] State machine — estado terminal: `email.transition_to(cualquier_estado)` desde `RESPONDED` lanza `InvalidStateTransitionError`
- [ ] Seed data — ActionCategory: 4 categorias presentes post-migracion, exactamente 1 con `is_fallback=True` (slug=`unknown`)
- [ ] Seed data — TypeCategory: 10 categorias presentes post-migracion, exactamente 1 con `is_fallback=True` (slug=`other`)
- [ ] FK enforcement: insertar `ClassificationResult` con `action_category_id` invalido lanza `IntegrityError` de DB
- [ ] Dual session: `from src.core.database import get_async_db, SyncSessionLocal` importa sin error
- [ ] mypy `Mapped[]`: ningun modelo usa anotaciones de tipo pre-SA2.0 (`Column(String)` sin `Mapped`) — verificado por mypy

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Notas de iteracion:**
- Si `alembic upgrade head` falla con `can't adapt type 'EmailState'`: verificar que `sa.Enum(EmailState, name="emailstate", create_type=True)` esta presente en la columna, no solo `sa.String`.
- Si mypy falla con `dict[str, Any]` en campo JSONB: agregar el TypedDict correspondiente segun la tabla "TypedDict Policy" arriba.
- Si `alembic downgrade base` falla con `enum type still referenced`: las migraciones de downgrade deben eliminar las tablas antes que los tipos enum. Verificar el orden de `op.drop_table()` vs `op.execute("DROP TYPE ...")`.
- Si el test de FK enforcement falla: verificar que el constraint `ondelete` esta configurado en el `ForeignKey()`, no solo en el modelo SQLAlchemy.
- Si la migracion async falla con `greenlet_spawn`: usar el pattern `run_sync` de Alembic para migraciones async (ver documentacion de Alembic async migrations).
