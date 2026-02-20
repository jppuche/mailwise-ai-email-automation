# Bloque 13: REST API Core

## Objetivo

Implementar el nucleo de la API REST: routers delgados para email CRUD, clasificaciones,
reglas de routing, revision de drafts, auth, y health check. Cada endpoint tiene modelos
Pydantic tipados para request y response — sin `dict` pass-through. La capa API es thin:
los routers delegan al service layer (B7-B11) via FastAPI dependency injection. OpenAPI
se genera automaticamente desde los tipos (differentiator del portfolio). Tiempo de
respuesta < 500ms para operaciones CRUD (Sec 12.1).

## Dependencias

- Bloque 1 (Models): `Email`, `EmailState`, `Draft`, `DraftStatus`, `RoutingRule`, enums
- Bloque 2 (Auth): `AuthService`, `get_current_user`, JWT validation, roles `Admin`/`Reviewer`
- Bloque 7 (Ingestion Service): `IngestionService` — para `POST /emails/{id}/retry`
- Bloque 8 (Classification Service): `ClassificationService` — para reclassify + feedback
- Bloque 9 (Routing Service): `RoutingService` — para rule management + test
- Bloque 10 (CRM Sync Service): `CRMSyncService` — para estado CRM en email detail
- Bloque 11 (Draft Generation Service): `DraftGenerationService` — para approve workflow
- Bloque 12 (Pipeline): `run_pipeline` — para retry desde el dashboard
- Todos los adapters (B3, B4, B5, B6): health check agrega estado de cada adapter

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/api/main.py` — FastAPI app: CORS, lifespan (startup/shutdown adapters), registro de
  routers, exception handlers globales. Sin logica de negocio.
- `src/api/routers/emails.py` — 4 endpoints de email: lista paginada + filtros, detalle
  completo, retry, reclassify.
- `src/api/routers/routing_rules.py` — 6 endpoints: CRUD completo + reorder + test.
- `src/api/routers/drafts.py` — 5 endpoints: lista, detalle, approve, reject, reassign.
- `src/api/routers/health.py` — 1 endpoint: health check agregado.
- `src/api/routers/auth.py` — 4 endpoints: login, refresh, logout, me. Delegados a B2
  `AuthService` — no hay logica de auth en el router.
- `src/api/schemas/emails.py` — `EmailListItem`, `EmailListResponse`, `EmailDetailResponse`,
  `EmailFilter`, `PaginationParams`, `RetryRequest`, `ReclassifyRequest`.
- `src/api/schemas/routing.py` — `RoutingRuleCreate`, `RoutingRuleUpdate`,
  `RoutingRuleResponse`, `RoutingRuleReorderRequest`, `RuleTestRequest`, `RuleTestResponse`.
- `src/api/schemas/drafts.py` — `DraftListItem`, `DraftListResponse`, `DraftDetailResponse`,
  `DraftApproveResponse`, `DraftRejectRequest`, `DraftReassignRequest`.
- `src/api/schemas/common.py` — `PaginatedResponse[T]`, `ErrorResponse`, `HealthResponse`,
  `AdapterHealthItem`.
- `src/api/schemas/auth.py` — `LoginRequest`, `LoginResponse`, `RefreshRequest`,
  `RefreshResponse`, `UserMeResponse`. (Puede existir ya en B2; si existe, importar no duplicar.)
- `src/api/dependencies.py` — FastAPI `Depends` factories: `get_db`, `get_current_user`,
  `require_admin`, `get_ingestion_service`, `get_classification_service`,
  `get_routing_service`, `get_crm_sync_service`, `get_draft_service`.
- `src/api/exception_handlers.py` — Mapa de excepciones de dominio a HTTP status codes:
  `InvalidStateTransitionError` → 409, `NotFoundError` → 404, `ValidationError` → 422,
  `PermissionDeniedError` → 403.

### Frontend (frontend-worker)

- N/A en este bloque — el frontend consume esta API. La integracion frontend/API se especifica
  en el bloque de Dashboard (B14+). Sin embargo, el OpenAPI spec generado
  automaticamente en `/docs` y `/openapi.json` es el contrato de integracion.

### Tests (Inquisidor)

- `tests/api/test_emails_router.py` — Lista paginada (con y sin filtros), detalle completo,
  retry (encola pipeline), reclassify (invoca service), auth requerida (401 sin token),
  Reviewer no puede reclassify (403).
- `tests/api/test_routing_rules_router.py` — CRUD completo, reorder (prioridad cambia),
  test mode (retorna reglas que matchean sin side effects), Admin-only para create/update/delete.
- `tests/api/test_drafts_router.py` — Lista con filtro de status, detalle con email original
  side-by-side, approve (invoca push a Gmail), reject, reassign (cambia reviewer). Reviewer
  puede approve/reject su draft; no puede aprobar draft asignado a otro.
- `tests/api/test_health_router.py` — Health OK (todos adapters up), degraded (un adapter
  down), status codes correctos (200 OK, 207 degraded).
- `tests/api/test_auth_router.py` — Login exitoso, token invalido (401), refresh exitoso,
  logout revoca token, me retorna usuario correcto.
- `tests/api/test_pagination.py` — offset/limit validos, offset mayor al total (lista vacia),
  limit = 0 rechazado (422), limit > max rechazado (422).

## Skills aplicables

- **tighten-types** (CRITICO): Ver "Type Decisions" abajo. Cada endpoint tiene request y
  response tipados via Pydantic BaseModel. `PaginatedResponse[T]` es un generic tipado.
  Enums para filtros (no strings libres). Sin `dict` en ninguna firma de endpoint.
- **try-except** (MEDIO): Los routers NO tienen try/except — delegan a los services, y los
  errores de dominio son mapeados a HTTP codes en `exception_handlers.py`. El unico try/except
  en la capa API es en la funcion de lifespan (startup/shutdown de adapters).
- **pre-mortem Cat 11** (ALTO): Filtros de email y condiciones de routing como enums
  respaldados por DB — no strings libres que el frontend puede enviar arbitrariamente.
- **contract-docstrings** (MEDIO): Endpoints de draft workflow documentan precondiciones
  de estado (approve solo si `status=pending`) y garantias de HITL.

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Diseno de endpoints

### Emails

```
GET  /api/v1/emails
     Query: page (int, default 1), page_size (int, default 20, max 100)
            status (EmailState | None), action (str | None), type (str | None)
            priority (PriorityLevel | None), sender (str | None)
            date_from (datetime | None), date_to (datetime | None)
     Response: PaginatedResponse[EmailListItem]
     Auth: Reviewer | Admin
     Note: sender filter busca por LIKE '%sender%' usando pg_trgm index — no exact match

GET  /api/v1/emails/{email_id}
     Response: EmailDetailResponse (incluye classification, routing_actions, crm_sync, draft)
     Auth: Reviewer | Admin
     Note: campos opcionales son None si la etapa no fue ejecutada todavia

POST /api/v1/emails/{email_id}/retry
     Body: RetryRequest (reason: str | None)
     Response: RetryResponse (queued: bool, message: str)
     Auth: Admin only
     Note: llama run_pipeline(email_id); encola classify_task si email esta en SANITIZED+
     Precondition: email en estado CLASSIFICATION_FAILED, ROUTING_FAILED, CRM_FAILED, o DRAFT_FAILED

POST /api/v1/emails/{email_id}/reclassify
     Body: ReclassifyRequest (reason: str | None)
     Response: ReclassifyResponse (queued: bool)
     Auth: Admin only
     Note: resetea clasificacion y encola classify_task — solo para emails ya CLASSIFIED+
```

### Classifications

```
GET  /api/v1/emails/{email_id}/classification
     Response: ClassificationDetailResponse
     Auth: Reviewer | Admin

POST /api/v1/emails/{email_id}/classification/feedback
     Body: ClassificationFeedbackRequest (correct_action: str, correct_type: str, notes: str | None)
     Response: FeedbackResponse (recorded: bool)
     Auth: Reviewer | Admin
     Note: guarda feedback en ClassificationFeedback tabla (B8) para el feedback loop
```

### Routing Rules

```
GET    /api/v1/routing-rules
       Response: list[RoutingRuleResponse] (ordenado por priority ASC)
       Auth: Admin only

POST   /api/v1/routing-rules
       Body: RoutingRuleCreate
       Response: RoutingRuleResponse (201)
       Auth: Admin only

GET    /api/v1/routing-rules/{rule_id}
       Response: RoutingRuleResponse
       Auth: Admin only

PUT    /api/v1/routing-rules/{rule_id}
       Body: RoutingRuleUpdate
       Response: RoutingRuleResponse
       Auth: Admin only

DELETE /api/v1/routing-rules/{rule_id}
       Response: 204 No Content
       Auth: Admin only

PUT    /api/v1/routing-rules/reorder
       Body: RoutingRuleReorderRequest (ordered_ids: list[uuid.UUID])
       Response: list[RoutingRuleResponse] (en nuevo orden)
       Auth: Admin only
       Note: reasigna priority field (1..N) segun el orden de ordered_ids

POST   /api/v1/routing-rules/test
       Body: RuleTestRequest (email_content, classification, sender)
       Response: RuleTestResponse (matching_rules: list[RuleTestMatch])
       Auth: Admin only
       Note: dry-run — no crea RoutingAction ni llama al channel adapter
```

### Drafts

```
GET  /api/v1/drafts
     Query: status (DraftStatus | None), reviewer_id (uuid | None), page, page_size
     Response: PaginatedResponse[DraftListItem]
     Auth: Reviewer | Admin
     Note: Reviewer ve solo drafts asignados a si mismo (o sin asignar)
           Admin ve todos los drafts

GET  /api/v1/drafts/{draft_id}
     Response: DraftDetailResponse (draft + email original side-by-side)
     Auth: Reviewer | Admin
     Precondition: Draft existe; Reviewer solo puede ver su propio draft

POST /api/v1/drafts/{draft_id}/approve
     Body: DraftApproveRequest (push_to_gmail: bool = True, notes: str | None)
     Response: DraftApproveResponse (draft_id, gmail_draft_id | None, approved_at)
     Auth: Reviewer | Admin
     Precondition: draft.status == PENDING; reviewer asignado al draft (o Admin)
     Note: HITL — solo pushea a Gmail como borrador, NUNCA envia

POST /api/v1/drafts/{draft_id}/reject
     Body: DraftRejectRequest (reason: str)
     Response: 204 No Content
     Auth: Reviewer | Admin
     Precondition: draft.status == PENDING; reviewer asignado

POST /api/v1/drafts/{draft_id}/reassign
     Body: DraftReassignRequest (reviewer_id: uuid.UUID, reason: str | None)
     Response: DraftDetailResponse (con nuevo reviewer)
     Auth: Admin only
```

### Auth

```
POST /api/v1/auth/login
     Body: LoginRequest (email, password)
     Response: LoginResponse (access_token, refresh_token, token_type, expires_in)
     Auth: none

POST /api/v1/auth/refresh
     Body: RefreshRequest (refresh_token)
     Response: RefreshResponse (access_token, expires_in)
     Auth: none (el refresh token es la credencial)

POST /api/v1/auth/logout
     Response: 204 No Content
     Auth: Bearer token (cualquier rol)
     Note: invalida el refresh token en Redis

GET  /api/v1/auth/me
     Response: UserMeResponse (id, email, role, created_at)
     Auth: Bearer token (cualquier rol)
```

### Health

```
GET  /api/v1/health
     Response: HealthResponse (status: "ok" | "degraded", adapters: list[AdapterHealthItem])
     Auth: none (monitoring tools necesitan acceder sin auth)
     Note: status "degraded" si cualquier adapter falla; HTTP 200 siempre (no 503)
           para evitar que load balancers remuevan el pod por un adapter externo
     Adapters verificados: gmail, slack, hubspot, llm, database, redis
```

## Esquemas Pydantic (tighten-types — D1)

```python
# src/api/schemas/common.py

from __future__ import annotations
from typing import Generic, TypeVar
import uuid
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Response paginado generico. Usado en lista de emails y drafts."""
    items: list[T]
    total: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    pages: int  # ceil(total / page_size)

    model_config = {"arbitrary_types_allowed": True}


class ErrorResponse(BaseModel):
    """Response de error estandarizado. Todas las excepciones usan este formato."""
    error: str               # codigo legible por maquina: "not_found", "invalid_state", etc.
    message: str             # descripcion legible por humano
    detail: str | None = None  # stack trace o informacion adicional (solo en modo debug)


class AdapterHealthItem(BaseModel):
    """Estado de un adapter individual en el health check."""
    name: str                # "gmail", "slack", "hubspot", "llm", "database", "redis"
    status: str              # "ok" | "degraded" | "unavailable"
    latency_ms: int | None = None
    error: str | None = None  # descripcion del error si status != "ok"


class HealthResponse(BaseModel):
    """Response del health check agregado."""
    status: str              # "ok" | "degraded"
    adapters: list[AdapterHealthItem]
    version: str             # version de la app desde Settings
```

```python
# src/api/schemas/emails.py

from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, Field
from src.models.email import EmailState  # enum del modelo DB (B1)
from src.models.classification import ClassificationResult as ClassificationDBModel  # B1


class PaginationParams(BaseModel):
    """Parametros de paginacion. Compartido por lista de emails y drafts."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class EmailFilter(BaseModel):
    """Filtros opcionales para lista de emails."""
    status: EmailState | None = None
    action: str | None = None         # slug de ActionCategory
    type: str | None = None           # slug de TypeCategory
    priority: str | None = None       # "high" | "normal" | "low"
    sender: str | None = None         # partial match via pg_trgm
    date_from: datetime | None = None
    date_to: datetime | None = None


class ClassificationSummary(BaseModel):
    """Clasificacion resumida para lista de emails."""
    action: str
    type: str
    confidence: str  # "high" | "low"
    is_fallback: bool


class EmailListItem(BaseModel):
    """Item de email en lista paginada. Sin body completo (PII policy)."""
    id: uuid.UUID
    subject: str
    sender_email: str
    sender_name: str | None
    received_at: datetime
    state: EmailState
    snippet: str              # LLM_SNIPPET_LENGTH chars (B0 sanitizer)
    classification: ClassificationSummary | None  # None si no clasificado aun


class RoutingActionSummary(BaseModel):
    """Accion de routing resumida para detalle de email."""
    id: uuid.UUID
    channel: str
    destination: str
    status: str  # RoutingActionStatus slug
    dispatched_at: datetime | None


class CRMSyncSummary(BaseModel):
    """Estado CRM resumido para detalle de email."""
    status: str         # CRMSyncStatus slug
    contact_id: str | None
    activity_id: str | None
    synced_at: datetime | None


class DraftSummary(BaseModel):
    """Draft resumido para detalle de email."""
    id: uuid.UUID
    status: str         # DraftStatus slug
    model_used: str | None
    created_at: datetime


class EmailDetailResponse(BaseModel):
    """Detalle completo de un email con todas las etapas del pipeline."""
    id: uuid.UUID
    subject: str
    sender_email: str
    sender_name: str | None
    received_at: datetime
    state: EmailState
    snippet: str
    thread_id: str | None
    classification: ClassificationSummary | None
    routing_actions: list[RoutingActionSummary]
    crm_sync: CRMSyncSummary | None
    draft: DraftSummary | None
    created_at: datetime
    updated_at: datetime


class RetryRequest(BaseModel):
    """Request para retry manual de un email fallido."""
    reason: str | None = None


class RetryResponse(BaseModel):
    queued: bool
    message: str
    email_id: uuid.UUID


class ReclassifyRequest(BaseModel):
    reason: str | None = None


class ReclassifyResponse(BaseModel):
    queued: bool
    email_id: uuid.UUID


class ClassificationFeedbackRequest(BaseModel):
    correct_action: str = Field(min_length=1)
    correct_type: str = Field(min_length=1)
    notes: str | None = None


class FeedbackResponse(BaseModel):
    recorded: bool
    feedback_id: uuid.UUID
```

```python
# src/api/schemas/routing.py

from __future__ import annotations
import uuid
from pydantic import BaseModel, Field


class RoutingConditionSchema(BaseModel):
    """Una condicion de una regla de routing. Mapeada desde RoutingConditions TypedDict (B1)."""
    field: str     # "action", "type", "priority", "sender_domain"
    operator: str  # "eq", "contains", "in", "not_in"
    value: str | list[str]


class RoutingActionSchema(BaseModel):
    """Una accion de una regla de routing. Mapeada desde RoutingActions TypedDict (B1)."""
    channel: str              # "slack"
    destination: str          # Slack channel ID
    crm_sync: bool = False
    generate_draft: bool = False
    template_id: str | None = None


class RoutingRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    is_active: bool = True
    conditions: list[RoutingConditionSchema] = Field(min_length=1)
    actions: list[RoutingActionSchema] = Field(min_length=1)
    # priority asignada por el servicio (siguiente disponible) — no en el request


class RoutingRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None
    conditions: list[RoutingConditionSchema] | None = None
    actions: list[RoutingActionSchema] | None = None


class RoutingRuleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    priority: int
    conditions: list[RoutingConditionSchema]
    actions: list[RoutingActionSchema]
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601


class RoutingRuleReorderRequest(BaseModel):
    """ordered_ids define el nuevo orden de prioridad: indice 0 = prioridad 1 (mas alta)."""
    ordered_ids: list[uuid.UUID] = Field(min_length=1)


class RuleTestEmailInput(BaseModel):
    """Input de email de prueba para el test de reglas."""
    subject: str
    sender_email: str
    sender_domain: str  # extraido en el servicio si no se provee
    action: str         # como si ya estuviera clasificado
    type: str
    priority: str


class RuleTestRequest(BaseModel):
    email: RuleTestEmailInput


class RuleTestMatch(BaseModel):
    rule_id: uuid.UUID
    rule_name: str
    priority: int
    matched_conditions: list[str]  # descripcion legible de condiciones que matchearon


class RuleTestResponse(BaseModel):
    matching_rules: list[RuleTestMatch]
    total_rules_evaluated: int
    note: str = "Dry-run: no side effects. No RoutingAction created."
```

```python
# src/api/schemas/drafts.py

from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel


class DraftListItem(BaseModel):
    id: uuid.UUID
    email_id: uuid.UUID
    email_subject: str
    email_sender: str
    status: str            # DraftStatus slug
    reviewer_id: uuid.UUID | None
    created_at: datetime


class EmailForDraftReview(BaseModel):
    """
    Email original incluido en el detalle del draft para revision side-by-side.
    Solo campos necesarios para revision — no body completo (PII policy).
    """
    id: uuid.UUID
    subject: str
    sender_email: str
    sender_name: str | None
    snippet: str
    received_at: datetime
    classification: ClassificationSummary  # importado de emails.py


class DraftDetailResponse(BaseModel):
    id: uuid.UUID
    content: str               # contenido del draft generado por LLM
    status: str
    model_used: str | None
    fallback_applied: bool
    reviewer_id: uuid.UUID | None
    email: EmailForDraftReview  # email original para revision side-by-side
    created_at: datetime
    updated_at: datetime


class DraftApproveRequest(BaseModel):
    push_to_gmail: bool = True
    notes: str | None = None


class DraftApproveResponse(BaseModel):
    draft_id: uuid.UUID
    approved: bool
    gmail_draft_id: str | None  # None si push_to_gmail=False o si fallo el push
    approved_at: datetime
    note: str | None            # "Gmail push failed — draft saved locally" si aplica


class DraftRejectRequest(BaseModel):
    reason: str


class DraftReassignRequest(BaseModel):
    reviewer_id: uuid.UUID
    reason: str | None = None
```

## Patron de exception handlers (thin router — D7 aplicado)

Los routers NO tienen try/except. Las excepciones de dominio son capturadas en
`exception_handlers.py` y mapeadas a HTTP responses:

```python
# src/api/exception_handlers.py

from fastapi import Request
from fastapi.responses import JSONResponse
from src.core.exceptions import (
    NotFoundError,
    InvalidStateTransitionError,
    PermissionDeniedError,
    DuplicateResourceError,
)
from src.api.schemas.common import ErrorResponse


async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(error="not_found", message=str(exc)).model_dump(),
    )


async def invalid_state_handler(request: Request, exc: InvalidStateTransitionError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=ErrorResponse(
            error="invalid_state_transition",
            message=str(exc),
        ).model_dump(),
    )


async def permission_denied_handler(request: Request, exc: PermissionDeniedError) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content=ErrorResponse(error="forbidden", message=str(exc)).model_dump(),
    )


async def duplicate_resource_handler(request: Request, exc: DuplicateResourceError) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=ErrorResponse(error="duplicate_resource", message=str(exc)).model_dump(),
    )
```

```python
# src/api/main.py (fragmento — registro de handlers)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: inicializar adapters
    try:
        await initialize_adapters()
    except Exception as exc:
        # Unico except Exception en la capa API — es un handler de lifespan (D7)
        logger.exception("Adapter initialization failed", extra={"error": str(exc)})
        raise  # Si los adapters no inician, la app no debe arrancar

    yield

    # Shutdown: cleanup
    await teardown_adapters()


app = FastAPI(
    title="mailwise API",
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,  # D14: configurable, no hardcoded
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(NotFoundError, not_found_handler)
app.add_exception_handler(InvalidStateTransitionError, invalid_state_handler)
app.add_exception_handler(PermissionDeniedError, permission_denied_handler)
app.add_exception_handler(DuplicateResourceError, duplicate_resource_handler)

# Routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(emails_router, prefix="/api/v1/emails", tags=["emails"])
app.include_router(routing_rules_router, prefix="/api/v1/routing-rules", tags=["routing"])
app.include_router(drafts_router, prefix="/api/v1/drafts", tags=["drafts"])
app.include_router(health_router, prefix="/api/v1", tags=["health"])
```

## Patron de router delgado (thin router — arquitectura)

Los routers SOLO hacen:
1. Validar el request via Pydantic (automatico por FastAPI)
2. Extraer dependencias via `Depends`
3. Llamar al service
4. Retornar el response schema

```python
# src/api/routers/emails.py (fragmento)

@router.get("/{email_id}", response_model=EmailDetailResponse)
async def get_email_detail(
    email_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # cualquier rol autenticado
) -> EmailDetailResponse:
    # Router es thin: sin try/except, sin logica de negocio
    email = await email_query_service.get_email_detail(email_id, db)
    return _to_email_detail_response(email)  # funcion de mapeo local, no service call


@router.post("/{email_id}/retry", response_model=RetryResponse)
async def retry_email(
    email_id: uuid.UUID,
    body: RetryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),  # Admin only
) -> RetryResponse:
    await pipeline_service.retry_email(email_id, body.reason, db)
    return RetryResponse(queued=True, message="Pipeline retry queued", email_id=email_id)
```

## Health check (Sec 12.1 — < 500ms)

El health check hace `test_connection()` en cada adapter con timeout de 200ms cada uno.
Los adapters se verifican en paralelo (asyncio.gather). Si uno falla, el status general
es "degraded" pero el HTTP status es siempre 200 (no 503).

```python
# src/api/routers/health.py

@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    results = await asyncio.gather(
        _check_adapter("gmail", gmail_adapter),
        _check_adapter("slack", slack_adapter),
        _check_adapter("hubspot", hubspot_adapter),
        _check_adapter("llm", llm_adapter),
        _check_adapter("database", db_adapter),
        _check_adapter("redis", redis_adapter),
        return_exceptions=True,
    )
    adapters = [r if isinstance(r, AdapterHealthItem) else _error_item(r) for r in results]
    overall = "ok" if all(a.status == "ok" for a in adapters) else "degraded"
    return HealthResponse(status=overall, adapters=adapters, version=settings.app_version)


async def _check_adapter(name: str, adapter: Any) -> AdapterHealthItem:
    start = time.monotonic()
    try:
        await asyncio.wait_for(adapter.test_connection(), timeout=0.2)
        latency_ms = int((time.monotonic() - start) * 1000)
        return AdapterHealthItem(name=name, status="ok", latency_ms=latency_ms)
    except asyncio.TimeoutError:
        return AdapterHealthItem(name=name, status="degraded", error="timeout")
    except Exception as exc:
        return AdapterHealthItem(name=name, status="unavailable", error=str(exc))
```

**Nota sobre `Any` en `_check_adapter`:** El parametro `adapter: Any` es aceptable aqui
porque `test_connection()` es el unico metodo llamado y esta definido en el ABC de cada
adapter. Alternativa mas precisa: `adapter: HasTestConnection` (Protocol), recomendada si
Inquisidor confirma que todos los adapters implementan el mismo ABC.

## Type Decisions

| Tipo | Kind | Justification |
|------|------|---------------|
| `PaginatedResponse[T]` | `BaseModel Generic[T]` | Reutilizable para emails y drafts. Generic evita duplicacion. FastAPI soporta modelos genericos en OpenAPI. |
| `EmailListItem` | `BaseModel` | Boundary API: validacion Pydantic al serializar desde ORM. Sin `from_orm` — mapeo explicito. |
| `EmailDetailResponse` | `BaseModel` | Boundary API: incluye sub-modelos anidados (todos tipados). Sin `dict` en ningun nivel. |
| `EmailFilter` | `BaseModel` | Query params como modelo tipado. FastAPI los extrae de query string automaticamente. |
| `PaginationParams` | `BaseModel` | Compartido por todos los endpoints paginados. Propiedad `offset` es computo local (no tighten-types critico). |
| `RoutingRuleCreate` | `BaseModel` | Request body con validacion (min_length en conditions y actions). |
| `RoutingConditionSchema` | `BaseModel` | Reemplaza `dict[str, Any]` del TypedDict interno (B1). En el boundary API, necesitamos Pydantic, no TypedDict. |
| `ErrorResponse` | `BaseModel` | Todos los errores usan este schema. Mapeado en `exception_handlers.py`. |
| `AdapterHealthItem` | `BaseModel` | Resultado tipado del health check por adapter. `status` es `str` en lugar de `Enum` porque los valores son pocos y claramente documentados. |
| `EmailState` | `Enum` (B1) | Importado del modelo DB — reutilizado en filtros de API. No redefinido. |
| `DraftStatus` | `Enum` (B1) | Importado del modelo DB — reutilizado como filtro de drafts. |
| `ClassificationSummary` | `BaseModel` | Sub-modelo anidado en `EmailListItem` y `DraftDetailResponse`. Definido en `schemas/emails.py`, importado en `schemas/drafts.py`. |

**Prohibido en este bloque:**
- `dict[str, Any]` en cualquier firma de endpoint o schema
- `response_model=None` en endpoints que retornan datos — todos tienen `response_model` explicito
- `Any` en campo de BaseModel (usar `Union` explicito o modelo especifico)
- `from __future__ import annotations` rompe `model_rebuild()` en algunos generics — verificar con mypy

## Autorizacion (B2 integration)

```
Rol Admin:    acceso a todo — emails, rules, drafts, auth endpoints
Rol Reviewer: GET emails, GET drafts (propios), POST approve/reject/feedback
              NO puede: crear/modificar routing rules, retry/reclassify, ver drafts de otros
```

```python
# src/api/dependencies.py

async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise PermissionDeniedError("Admin role required")
    return current_user


async def require_draft_access(
    draft_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Draft:
    """Verifica que el usuario tiene acceso al draft (propio o Admin)."""
    draft = await db.get(Draft, draft_id)
    if draft is None:
        raise NotFoundError(f"Draft {draft_id} not found")
    if current_user.role != UserRole.ADMIN and draft.reviewer_id != current_user.id:
        raise PermissionDeniedError("Access to this draft is not allowed")
    return draft
```

## Defaults load-bearing (Cat 8 pre-mortem)

| Default | Valor | Env Var | Consecuencia si incorrecto |
|---------|-------|---------|---------------------------|
| Max page_size | `100` items | `API_MAX_PAGE_SIZE` | Demasiado alto: query DB tarda > 500ms. Demasiado bajo: frontend necesita muchas paginas para cargar tabla completa |
| Default page_size | `20` items | `API_DEFAULT_PAGE_SIZE` | Afecta percepcion de velocidad del dashboard inicial |
| Health check timeout por adapter | `200` ms | `API_HEALTH_ADAPTER_TIMEOUT_MS` | Demasiado bajo: falsos "degraded" en adapters lentos. Demasiado alto: health endpoint tarda > 500ms y falla SLO |
| CORS origins | `["http://localhost:5173"]` | `API_CORS_ALLOWED_ORIGINS` | `["*"]` en produccion expone la API a cualquier origen — critico para seguridad |
| App version | `"0.1.0"` | `APP_VERSION` | Visible en health check y OpenAPI spec — debe actualizarse en cada release |

## Estructura de archivos esperada

```
src/api/
├── main.py                      # FastAPI app + lifespan + CORS + routers
├── dependencies.py              # Depends factories: get_db, auth, services
├── exception_handlers.py        # Mapa excepciones dominio → HTTP codes
├── routers/
│   ├── __init__.py
│   ├── auth.py                  # /auth/* (delega a B2 AuthService)
│   ├── emails.py                # /emails/* + /emails/{id}/classification/*
│   ├── routing_rules.py         # /routing-rules/*
│   ├── drafts.py                # /drafts/*
│   └── health.py                # /health
└── schemas/
    ├── __init__.py
    ├── common.py                # PaginatedResponse[T], ErrorResponse, HealthResponse
    ├── auth.py                  # Login/Refresh/Logout/Me schemas
    ├── emails.py                # EmailListItem, EmailDetailResponse, EmailFilter, etc.
    ├── routing.py               # RoutingRuleCreate/Update/Response, RuleTest*
    └── drafts.py                # DraftListItem, DraftDetailResponse, Approve/Reject/Reassign
```

## Criterios de exito (deterministicos)

### Calidad de codigo

- [ ] `ruff check src/api/` — 0 violaciones
- [ ] `ruff format src/api/ --check` — 0 diferencias
- [ ] `mypy src/api/` — 0 errores de tipo

### Tipos (tighten-types — D1)

- [ ] Ningun endpoint tiene `response_model=None` cuando retorna datos — verificable via
  `grep -n "response_model=None" src/api/routers/*.py` → vacio
- [ ] Ningun schema tiene campo `Any` — verificable via
  `grep -n ": Any\|dict\[str, Any\]" src/api/schemas/*.py` → vacio (excepto comentario explicativo en health)
- [ ] `PaginatedResponse[EmailListItem]` y `PaginatedResponse[DraftListItem]` pasan mypy estricto
- [ ] `EmailFilter` y `PaginationParams` son `BaseModel` con todos los campos tipados
- [ ] `RoutingConditionSchema` no tiene campos `dict` — reemplaza el TypedDict interno de B1

### Autorizacion

- [ ] `GET /api/v1/emails` con token invalido → 401
- [ ] `GET /api/v1/emails` con token de Reviewer → 200
- [ ] `POST /api/v1/routing-rules` con token de Reviewer → 403
- [ ] `POST /api/v1/emails/{id}/retry` con token de Reviewer → 403
- [ ] `POST /api/v1/drafts/{id}/approve` con Reviewer que no es el asignado → 403
- [ ] `GET /api/v1/health` sin token → 200 (no auth requerida)

### Paginacion y filtros

- [ ] `GET /api/v1/emails?page=1&page_size=5` con 12 emails en DB → `items` len=5, `total=12`, `pages=3`
- [ ] `GET /api/v1/emails?page_size=0` → 422 (validacion Pydantic)
- [ ] `GET /api/v1/emails?page_size=101` → 422 (supera max)
- [ ] `GET /api/v1/emails?status=CLASSIFIED` → solo emails en estado CLASSIFIED
- [ ] `GET /api/v1/emails?sender=acme` → emails donde sender_email LIKE '%acme%'

### Endpoints funcionales

- [ ] `GET /api/v1/emails/{id}` con email en estado ROUTED → `routing_actions` no vacio, `crm_sync=None` si no configurado
- [ ] `POST /api/v1/emails/{id}/retry` con email en CLASSIFICATION_FAILED → `queued=True`
- [ ] `POST /api/v1/emails/{id}/retry` con email en CLASSIFIED (estado no fallido) → 409 `invalid_state_transition`
- [ ] `GET /api/v1/routing-rules` → lista ordenada por priority ASC
- [ ] `PUT /api/v1/routing-rules/reorder` con 3 reglas reordenadas → priorities reasignadas 1, 2, 3
- [ ] `POST /api/v1/routing-rules/test` → response tiene `note` con texto de dry-run
- [ ] `POST /api/v1/drafts/{id}/approve` con `push_to_gmail=false` → `gmail_draft_id=None`
- [ ] `GET /api/v1/health` con todos adapters up → `status="ok"`
- [ ] `GET /api/v1/health` con un adapter down → `status="degraded"`, HTTP 200

### OpenAPI

- [ ] `GET /docs` accesible y carga Swagger UI
- [ ] `GET /openapi.json` retorna spec valido (sin campos `null` en schemas de modelos)
- [ ] Todos los endpoints tienen `tags` correctos en el spec
- [ ] `PaginatedResponse[EmailListItem]` aparece como schema nombrado en el spec (no inline)

### Thin router (arquitectura)

- [ ] Ningun router file tiene `try/except` fuera del health check `_check_adapter` —
  verificable via `grep -n "try:" src/api/routers/*.py` → solo `health.py`
- [ ] Ningun router importa directamente desde `src/adapters/` — todo via services/dependencies
- [ ] `main.py` no tiene logica de negocio — solo configuracion de app

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**

1. `mypy src/api/schemas/` — schemas antes de routers; base de tipos para todo lo demas
2. `mypy src/api/dependencies.py src/api/exception_handlers.py` — infraestructura de la API
3. `mypy src/api/routers/` — routers dependen de schemas y dependencies
4. `mypy src/api/main.py` — entry point depende de todo lo anterior
5. `ruff check src/api/ && ruff format --check src/api/`
6. `pytest tests/api/test_auth_router.py -v` — auth antes del resto (base de seguridad)
7. `pytest tests/api/test_pagination.py -v` — paginacion antes de endpoints de datos
8. `pytest tests/api/test_emails_router.py -v`
9. `pytest tests/api/test_routing_rules_router.py -v`
10. `pytest tests/api/test_drafts_router.py -v`
11. `pytest tests/api/test_health_router.py -v`
12. `pytest tests/api/ -v` — suite completa

**Verificaciones criticas (no automatizables):**

```bash
# Thin router: sin try/except en routers (excepto health)
grep -n "try:" src/api/routers/emails.py src/api/routers/routing_rules.py \
    src/api/routers/drafts.py src/api/routers/auth.py
# Resultado esperado: vacio

# Sin dict[str, Any] en schemas
grep -rn "dict\[str, Any\]\|: Any" src/api/schemas/
# Resultado esperado: vacio (o solo en comentarios explicativos)

# Sin response_model=None en endpoints de datos
grep -n "response_model=None" src/api/routers/
# Resultado esperado: vacio

# CORS origin no es wildcard en config default
grep -n 'CORS_ALLOWED_ORIGINS.*\*' src/core/config.py
# Resultado esperado: vacio (wildcard solo aceptable como override explicito en dev)
```

**Consultas requeridas antes de implementar:**

- Consultar Inquisidor para confirmar si `PaginatedResponse[T]` como Generic BaseModel
  es compatible con FastAPI OpenAPI codegen en la version de Pydantic v2 usada — algunos
  generics Pydantic v2 requieren `model_rebuild()` explicito para aparecer como schemas
  nombrados en el spec.
- Consultar Sentinel para revisar la configuracion de CORS en `main.py` — confirmar que
  `settings.cors_allowed_origins` como lista configurable desde env es suficiente para el
  modelo de seguridad SPA, o si se requiere validacion adicional de origen en endpoints
  sensibles (Sec 11.3).
- Consultar Inquisidor para confirmar el tipo correcto del parametro `adapter` en
  `_check_adapter`: `Any` vs `Protocol` con metodo `test_connection()` — impacto en
  tighten-types D1 y en la capacidad de mockear el health check en tests.
