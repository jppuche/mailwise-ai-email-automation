# Bloque 14: REST API Config & Analytics

## Objetivo

Implementar los routers de configuracion (categorias, ejemplos few-shot, feedback) e
integraciones (email, canales, CRM, LLM), las consultas de analytics con agregacion en DB,
y el endpoint de logs del sistema — extendiendo la API core de B13 con las rutas de
administracion y observabilidad del sistema.

## Dependencias

- Bloque 1 (Models): `ActionCategory`, `TypeCategory`, `FewShotExample`,
  `ClassificationFeedback`, `IntegrationConfig`, `SystemLog`, `EmailState`, `EmailAction`
- Bloque 2 (Auth): `require_admin`, `require_reviewer` dependencias FastAPI — todas las rutas
  de config son admin-only; analytics es Reviewer-accesible
- Bloque 13 (API Core): `app` FastAPI montado, `AsyncSession` dependency, registro de routers
  base; B14 extiende registrando sus 4 nuevos routers

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/api/routers/categories.py` — `APIRouter` para CRUD de `ActionCategory` y
  `TypeCategory` con reorden, mas CRUD de `FewShotExample` y listado de
  `ClassificationFeedback`. Todos admin-only excepto GET (Reviewer-accesible).
- `src/api/routers/integrations.py` — `APIRouter` para status, configuracion y test de
  conexion de los 4 tipos de integracion: email (Gmail), canales (Slack), CRM (HubSpot),
  LLM (LiteLLM). Todos admin-only.
- `src/api/routers/analytics.py` — `APIRouter` para las 4 consultas de analytics con
  agregacion en DB y exportacion CSV en streaming. Reviewer-accesible.
- `src/api/routers/logs.py` — `APIRouter` para lectura paginada y filtrada de `SystemLog`.
  Admin-only.
- `src/api/schemas/categories.py` — Pydantic models: `ActionCategoryCreate`,
  `ActionCategoryUpdate`, `ActionCategoryResponse`, `TypeCategoryCreate`,
  `TypeCategoryUpdate`, `TypeCategoryResponse`, `ReorderRequest`, `FewShotExampleCreate`,
  `FewShotExampleUpdate`, `FewShotExampleResponse`, `FeedbackListResponse`,
  `FeedbackItem`.
- `src/api/schemas/integrations.py` — Pydantic models: `IntegrationStatus`,
  `EmailIntegrationConfig`, `EmailIntegrationUpdate`, `ChannelIntegrationConfig`,
  `ChannelIntegrationUpdate`, `CRMIntegrationConfig`, `CRMIntegrationUpdate`,
  `LLMIntegrationConfig`, `LLMIntegrationUpdate`, `ConnectionTestResult`.
- `src/api/schemas/analytics.py` — Pydantic models: `DateRangeFilter`, `VolumeDataPoint`,
  `VolumeResponse`, `DistributionItem`, `ClassificationDistributionResponse`,
  `AccuracyResponse`, `RoutingChannelStat`, `RoutingResponse`.
- `src/api/schemas/logs.py` — Pydantic models: `LogEntry`, `LogFilter`, `LogListResponse`.
- `src/services/category_service.py` — Logica de negocio para CRUD de categorias con
  verificacion de FK antes de delete. Separa la validacion de negocio del router.
- `src/services/analytics_service.py` — Consultas SQL via SQLAlchemy (GROUP BY, COUNT,
  DATE_TRUNC) — nunca computacion Python sobre listas. Produce streaming CSV.
- `src/services/integration_service.py` — Lee/escribe `IntegrationConfig`, llama al adapter
  correspondiente para `test_connection()`, mapea resultado a `ConnectionTestResult`.
- `src/core/config.py` — Modificar: agregar settings de analytics
  (`ANALYTICS_MAX_DATE_RANGE_DAYS`, `ANALYTICS_CSV_CHUNK_SIZE`,
  `ANALYTICS_DEFAULT_TIMEZONE`).

### Frontend (frontend-worker)

- N/A — este bloque es exclusivamente backend. Los routers de B14 son consumidos por la
  UI de B15+ (Integration Settings page, Classification Config page, Analytics page).

### Tests (Inquisidor)

- `tests/api/test_categories_router.py` — CRUD completo de ActionCategory y TypeCategory:
  create, read, update, delete exitoso, delete bloqueado por FK (409), reorder, list
  ordenado por display_order. CRUD de FewShotExample. Lista de feedback. Verificacion de
  roles: admin puede todo, reviewer no puede POST/PUT/DELETE (403).
- `tests/api/test_integrations_router.py` — GET status para los 4 adapters, PUT config,
  POST test exitoso, POST test fallido (adapter error mapeado a ConnectionTestResult con
  success=False). Verificacion de que credenciales no aparecen en respuesta.
- `tests/api/test_analytics_router.py` — Volume con rango de fechas, distribution con
  datos reales agregados, accuracy con feedback real, routing stats. CSV export: respuesta
  es StreamingResponse con Content-Type text/csv, headers correctos.
- `tests/api/test_logs_router.py` — Lista paginada, filtro por nivel, filtro por fecha.

## Skills aplicables

- **tighten-types** (CRITICO): Todos los schemas de request/response son Pydantic BaseModel.
  Ningun `dict[str, Any]` en ninguna firma de router, service o schema. `IntegrationConfig`
  almacena JSONB en DB — la extraccion del JSONB ocurre dentro del `integration_service`,
  nunca en el router. El router solo conoce los schemas de `src/api/schemas/`.
  `AnalyticsService` retorna `VolumeResponse` tipado, no rows de DB crudos.
  Aplicar en planificacion (definir schemas antes de implementar servicios) y revision
  (mypy estricto sobre todo el modulo).
- **pre-mortem Cat 3** (ALTO): Los slugs de categoria son la fuente de verdad del sistema
  de clasificacion. El endpoint DELETE debe verificar via FK constraint o query explicita
  que no existe ninguna `ClassificationResult` referenciando esa categoria antes de
  eliminarla. Devolver 409 con `affected_email_count` — no eliminar silenciosamente.
  Ver seccion "Category deletion guard" abajo.
- **pre-mortem Cat 8** (ALTO): Los settings de integracion (temperatura LLM, intervalo de
  polling, etc.) son load-bearing. Valores incorrectos en PUT /api/integrations/llm pueden
  degradar la calidad de clasificacion o causar timeouts. Ver tabla de defaults abajo.
- **try-except** (CRITICO): Operaciones externas en integration_service.test_connection()
  son external-state — try/except con tipos de excepcion especificos mapeados a
  `ConnectionTestResult`. Queries a DB en analytics_service son external-state —
  try/except SQLAlchemyError. CRUD de categorias en category_service es external-state —
  try/except SQLAlchemyError. Construccion del query SQL de analytics es local computation
  — condicionales, no try/except. Serializar CSV es local computation — condicionales.

## Type Decisions

| Tipo | Kind | Justificacion |
|------|------|---------------|
| `ActionCategoryCreate` | Pydantic BaseModel | Boundary de API (request body de POST) — validacion de campo en entrada |
| `ActionCategoryResponse` | Pydantic BaseModel | Boundary de API (response body) — serializado a JSON por FastAPI |
| `ActionCategoryUpdate` | Pydantic BaseModel | Campos opcionales (partial update semantics) — `model_config = ConfigDict(extra="forbid")` |
| `ReorderRequest` | Pydantic BaseModel | Lista de UUIDs con nuevo display_order — validada en boundary |
| `FewShotExampleCreate` | Pydantic BaseModel | Boundary de API — contiene email_snippet, action_slug, type_slug |
| `FeedbackItem` | Pydantic BaseModel | Representation read-only de `ClassificationFeedback` — solo GET |
| `IntegrationStatus` | Pydantic BaseModel | Respuesta de GET /api/integrations/* — connected: bool, last_synced, error_detail |
| `EmailIntegrationConfig` | Pydantic BaseModel | Config especifica de Gmail — oauth_configured: bool, scopes: list[str], account_email: str \| None |
| `ChannelIntegrationConfig` | Pydantic BaseModel | Config especifica por adapter — discriminated union por `adapter_type: Literal["slack", ...]` |
| `LLMIntegrationConfig` | Pydantic BaseModel | Config de LiteLLM — classify_model, draft_model, temperature_classify, temperature_draft |
| `ConnectionTestResult` | Pydantic BaseModel | Resultado de POST /test — success: bool, latency_ms: int \| None, error_detail: str \| None |
| `DateRangeFilter` | Pydantic BaseModel | Query params para analytics — start_date, end_date (ISO 8601), timezone: str |
| `VolumeDataPoint` | Pydantic BaseModel | Un punto de la serie temporal — date: str, count: int. Nunca `dict[str, Any]` |
| `DistributionItem` | Pydantic BaseModel | Un bucket del pie chart — category: str, count: int, percentage: float |
| `AccuracyResponse` | Pydantic BaseModel | Precision de clasificacion — total_classified: int, total_overridden: int, accuracy_pct: float |
| `RoutingChannelStat` | Pydantic BaseModel | Stats por canal — channel: str, dispatched: int, failed: int |
| `LogEntry` | Pydantic BaseModel | Una linea de log — id, timestamp, level, message, context: dict[str, str] |
| `LogFilter` | Pydantic BaseModel | Query params de GET /api/logs — level: str \| None, since: datetime \| None, until: datetime \| None, limit: int |

Nota sobre `LogEntry.context`: el campo `context` es `dict[str, str]` (no `dict[str, Any]`)
porque `SystemLog.context` en DB solo almacena valores string por politica de PII (IDs, no
valores de negocio). Esta es la unica excepcion documentada al patron no-dict.

## Pre-Mortem Analysis

### Cat 3 — Category deletion guard (stringly-typed)

El slug de una categoria es referenciado por `ClassificationResult.action_category_id` y
`ClassificationResult.type_category_id` via FK. Si se elimina una categoria referenciada,
las clasificaciones existentes quedan inconsistentes.

**Patron incorrecto:** Confiar en que el motor de DB lanzara `IntegrityError` y mapearlo a 409.
Esto depende del driver y del tipo de FK constraint — comportamiento distinto entre SQLite
(tests) y PostgreSQL (prod).

**Patron correcto:** Query explicita antes de DELETE:

```python
async def delete_action_category(
    self,
    category_id: uuid.UUID,
    db: AsyncSession,
) -> DeleteResult:
    """
    Precondition: category_id existe en DB.
    Raises: CategoryInUseError si hay clasificaciones referenciando esta categoria.
    """
    # Query explicita — computo sobre estado externo (try/except)
    try:
        affected_count: int = await db.scalar(
            select(func.count(ClassificationResult.id)).where(
                ClassificationResult.action_category_id == category_id
            )
        )
    except SQLAlchemyError as exc:
        raise DatabaseError(f"Failed to check category usage: {exc}") from exc

    if affected_count > 0:
        raise CategoryInUseError(
            category_id=category_id,
            affected_email_count=affected_count,
        )

    # La eliminacion solo ocurre si affected_count == 0
    try:
        category = await db.get(ActionCategory, category_id)
        await db.delete(category)
        await db.commit()
    except SQLAlchemyError as exc:
        raise DatabaseError(f"Failed to delete category: {exc}") from exc

    return DeleteResult(deleted=True)
```

El router mapea `CategoryInUseError` a HTTP 409:

```python
@router.delete("/api/categories/actions/{category_id}")
async def delete_action_category(
    category_id: uuid.UUID,
    service: CategoryService = Depends(get_category_service),
    _: User = Depends(require_admin),
) -> DeletedResponse:
    try:
        result = await service.delete_action_category(category_id, db)
    except CategoryInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "category_in_use",
                "affected_email_count": exc.affected_email_count,
                "message": f"Cannot delete: {exc.affected_email_count} classifications reference this category. Deactivate instead.",
            },
        )
    return DeletedResponse(deleted=result.deleted)
```

La alternativa de **desactivar** (is_active=False) siempre esta disponible via
`PUT /api/categories/actions/{id}` con `{"is_active": false}` — las clasificaciones
historicas permanecen validas.

### Cat 8 — Load-bearing defaults de integracion

| Default | Valor | Env Var | Consecuencia si incorrecto |
|---------|-------|---------|---------------------------|
| `temperature_classify` | `0.1` | `LLM_TEMPERATURE_CLASSIFY` | Alto: clasificaciones inconsistentes entre ejecuciones del mismo email. Bajo (0): sin variacion, puede fallar edge cases creativos. |
| `temperature_draft` | `0.7` | `LLM_TEMPERATURE_DRAFT` | Alto: drafts erraticos. Bajo: drafts roboticos. |
| `polling_interval_minutes` | `5` | `GMAIL_POLL_INTERVAL_MINUTES` | Muy bajo: quota agotada de Gmail API. Muy alto: emails urgentes llegan tarde. |
| `analytics_max_date_range_days` | `365` | `ANALYTICS_MAX_DATE_RANGE_DAYS` | Alto: queries de analytics sobre 3+ anos en DB grande generan timeouts. |
| `analytics_csv_chunk_size` | `1000` | `ANALYTICS_CSV_CHUNK_SIZE` | Alto: CSV export carga todo en memoria (OOM en exports grandes). |
| `analytics_default_timezone` | `"UTC"` | `ANALYTICS_DEFAULT_TIMEZONE` | Timezone incorrecto: graficas de volumen muestran datos del dia equivocado para usuarios en otras zonas. |

Los valores de integracion (temperatura LLM, scopes OAuth) configurados via
`PUT /api/integrations/llm` se validan en el schema Pydantic (rangos de temperatura 0.0-2.0).
El `integration_service` rechaza valores fuera de rango antes de persistirlos.

## Contratos de metodo (contract-docstrings — 4 preguntas)

### `CategoryService.delete_action_category(category_id, db) -> DeleteResult`

```
Preconditions:
  - category_id: UUID de una ActionCategory existente en DB
  - db: AsyncSession con transaccion activa

Errors raised on violation:
  - ValueError si category_id no existe (404 en el router)
  - CategoryInUseError si hay clasificaciones referenciando la categoria (409 en el router)

External state errors:
  - SQLAlchemyError al hacer el count query: re-raised como DatabaseError
  - SQLAlchemyError al hacer el DELETE: re-raised como DatabaseError

Silenced errors:
  - Ninguno — delete es una operacion destructiva; todos los fallos son visibles
```

### `AnalyticsService.get_volume(filter, db) -> VolumeResponse`

```
Preconditions:
  - filter.end_date >= filter.start_date
  - filter.end_date - filter.start_date <= ANALYTICS_MAX_DATE_RANGE_DAYS dias
  - filter.timezone es un timezone string valido (pytz/zoneinfo)

Errors raised on violation:
  - ValueError si date range invalido (400 en el router)

External state errors:
  - SQLAlchemyError al ejecutar el query agregado: re-raised al router (500)

Silenced errors:
  - Ningun dia sin emails: incluido como data point con count=0 (fecha presente, count cero)
    para que las graficas muestren gaps de actividad, no huecos en la serie temporal
```

### `IntegrationService.test_connection(adapter_type, db) -> ConnectionTestResult`

```
Preconditions:
  - adapter_type: "email" | "slack" | "crm" | "llm"
  - Configuracion del adapter existe en DB (IntegrationConfig)

Errors raised on violation:
  - ValueError si adapter_type desconocido (400 en el router)
  - ConfigurationMissingError si IntegrationConfig no existe para el adapter (422 en el router)

External state errors (todos silenciados en ConnectionTestResult):
  - EmailAdapterError → ConnectionTestResult(success=False, error_detail=...)
  - ChannelAdapterError → ConnectionTestResult(success=False, error_detail=...)
  - CRMAdapterError → ConnectionTestResult(success=False, error_detail=...)
  - LLMAdapterError → ConnectionTestResult(success=False, error_detail=...)

Silenced errors:
  - Todos los errores del adapter son capturados y traducidos a ConnectionTestResult.
    El endpoint POST /test siempre retorna 200 OK con success: bool.
    NUNCA propaga la excepcion del adapter como HTTP 500 — un test fallido es un resultado,
    no una excepcion del sistema.
```

## Esquemas Pydantic

### categories.py

```python
from __future__ import annotations
import uuid
from pydantic import BaseModel, ConfigDict, field_validator


class ActionCategoryBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    slug: str
    description: str | None = None
    is_active: bool = True
    color_hex: str | None = None   # para UI badges ("#4f46e5")


class ActionCategoryCreate(ActionCategoryBase):
    pass


class ActionCategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    color_hex: str | None = None
    # slug es inmutable post-creacion (otras entidades lo referencian por slug)


class ActionCategoryResponse(ActionCategoryBase):
    id: uuid.UUID
    display_order: int
    model_config = ConfigDict(from_attributes=True)


class ReorderRequest(BaseModel):
    """Lista ordenada de IDs: el indice en la lista define el nuevo display_order."""
    ordered_ids: list[uuid.UUID]

    @field_validator("ordered_ids")
    @classmethod
    def must_be_nonempty(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if not v:
            raise ValueError("ordered_ids must not be empty")
        return v


# TypeCategory — misma estructura que ActionCategory
class TypeCategoryCreate(ActionCategoryBase):
    pass

class TypeCategoryUpdate(ActionCategoryUpdate):
    pass

class TypeCategoryResponse(ActionCategoryResponse):
    pass


class FewShotExampleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_snippet: str       # snippet del email de ejemplo (truncado a 500 chars)
    action_slug: str         # slug de ActionCategory — validado contra DB en el service
    type_slug: str           # slug de TypeCategory
    rationale: str | None = None   # explicacion para el LLM


class FewShotExampleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_snippet: str | None = None
    action_slug: str | None = None
    type_slug: str | None = None
    rationale: str | None = None


class FewShotExampleResponse(FewShotExampleCreate):
    id: uuid.UUID
    model_config = ConfigDict(from_attributes=True)


class FeedbackItem(BaseModel):
    """Representacion read-only de una correccion de clasificacion."""
    id: uuid.UUID
    email_id: uuid.UUID
    original_action: str
    original_type: str
    corrected_action: str
    corrected_type: str
    reviewer_note: str | None = None
    created_at: str   # ISO 8601
    model_config = ConfigDict(from_attributes=True)


class FeedbackListResponse(BaseModel):
    items: list[FeedbackItem]
    total: int
    page: int
    page_size: int


class DeletedResponse(BaseModel):
    deleted: bool
```

### integrations.py

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class IntegrationStatus(BaseModel):
    """Estado actual de una integracion."""
    connected: bool
    last_synced: str | None = None     # ISO 8601
    error_detail: str | None = None    # ultimo error si connected=False
    adapter_type: str


class EmailIntegrationConfig(BaseModel):
    """Config de Gmail — expone estado, nunca credenciales."""
    oauth_configured: bool
    account_email: str | None = None
    scopes: list[str] = []
    poll_interval_minutes: int


class EmailIntegrationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poll_interval_minutes: int | None = Field(default=None, ge=1, le=60)
    # OAuth se configura via flujo OAuth separado, no via este endpoint


class SlackChannelConfig(BaseModel):
    adapter_type: Literal["slack"]
    workspace: str | None = None
    default_channel: str | None = None
    bot_configured: bool


class ChannelIntegrationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    adapter_type: Literal["slack"]
    default_channel: str | None = None


class CRMIntegrationConfig(BaseModel):
    crm_type: Literal["hubspot"]
    api_key_configured: bool
    portal_id: str | None = None
    auto_create_contacts: bool


class CRMIntegrationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_create_contacts: bool | None = None
    # api_key se actualiza via endpoint separado (POST /api/integrations/crm/credentials)


class LLMIntegrationConfig(BaseModel):
    provider: str                  # "openai" | "anthropic" | "ollama"
    classify_model: str
    draft_model: str
    temperature_classify: float
    temperature_draft: float
    api_key_configured: bool


class LLMIntegrationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classify_model: str | None = None
    draft_model: str | None = None
    temperature_classify: float | None = Field(default=None, ge=0.0, le=2.0)
    temperature_draft: float | None = Field(default=None, ge=0.0, le=2.0)
    # api_key via endpoint dedicado


class ConnectionTestResult(BaseModel):
    """Resultado de un test de conexion. Siempre 200 OK — success=False es un resultado valido."""
    success: bool
    latency_ms: int | None = None
    error_detail: str | None = None
    adapter_type: str
```

### analytics.py

```python
from __future__ import annotations
from pydantic import BaseModel, field_validator
from datetime import date


class DateRangeFilter(BaseModel):
    start_date: date
    end_date: date
    timezone: str = "UTC"

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, v: date, info: ...) -> date:
        if "start_date" in info.data and v < info.data["start_date"]:
            raise ValueError("end_date must be >= start_date")
        return v


class VolumeDataPoint(BaseModel):
    date: str     # "YYYY-MM-DD" — no datetime, para evitar tz ambiguity en JSON
    count: int


class VolumeResponse(BaseModel):
    data_points: list[VolumeDataPoint]
    total_emails: int
    start_date: str
    end_date: str


class DistributionItem(BaseModel):
    category: str         # slug de la categoria
    display_name: str     # nombre legible
    count: int
    percentage: float


class ClassificationDistributionResponse(BaseModel):
    actions: list[DistributionItem]
    types: list[DistributionItem]
    total_classified: int


class AccuracyResponse(BaseModel):
    total_classified: int
    total_overridden: int
    accuracy_pct: float    # (1 - overridden/classified) * 100
    period_start: str
    period_end: str


class RoutingChannelStat(BaseModel):
    channel: str
    dispatched: int
    failed: int
    success_rate: float   # dispatched / (dispatched + failed)


class RoutingResponse(BaseModel):
    channels: list[RoutingChannelStat]
    total_dispatched: int
    total_failed: int
    unrouted_count: int
```

### logs.py

```python
from __future__ import annotations
import uuid
from datetime import datetime
from pydantic import BaseModel, Field


class LogEntry(BaseModel):
    id: uuid.UUID
    timestamp: datetime
    level: str           # "INFO" | "WARNING" | "ERROR"
    source: str          # "ingestion" | "classification" | "routing" | "crm_sync" | "draft" | "auth"
    message: str
    email_id: uuid.UUID | None = None   # referencia al email si aplica (solo ID, no contenido)
    context: dict[str, str] = {}        # datos de contexto — valores son str (politica PII)
    model_config = ...


class LogFilter(BaseModel):
    level: str | None = None
    source: str | None = None
    since: datetime | None = None
    until: datetime | None = None
    email_id: uuid.UUID | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class LogListResponse(BaseModel):
    items: list[LogEntry]
    total: int
    limit: int
    offset: int
```

## Patron de try/except en la capa de servicios (directiva D7)

### category_service.py — operaciones CRUD

```python
# CORRECTO: try/except por operacion de DB (estado externo)
async def create_action_category(
    self,
    data: ActionCategoryCreate,
    db: AsyncSession,
) -> ActionCategoryResponse:
    # Verificar slug unico (estado externo — try/except)
    try:
        existing = await db.scalar(
            select(ActionCategory).where(ActionCategory.slug == data.slug)
        )
    except SQLAlchemyError as exc:
        raise DatabaseError(f"Failed to check slug uniqueness: {exc}") from exc

    if existing is not None:   # computo local — condicional, no try/except
        raise SlugConflictError(slug=data.slug)

    # Persistir (estado externo — try/except)
    try:
        category = ActionCategory(**data.model_dump())
        db.add(category)
        await db.commit()
        await db.refresh(category)
    except SQLAlchemyError as exc:
        await db.rollback()
        raise DatabaseError(f"Failed to create category: {exc}") from exc

    return ActionCategoryResponse.model_validate(category)
```

### analytics_service.py — queries de agregacion

```python
# CORRECTO: query SQL con agregacion en DB, no en Python
async def get_volume(
    self,
    filter: DateRangeFilter,
    db: AsyncSession,
) -> VolumeResponse:
    # Validacion de rango (computo local — condicional, no try/except)
    delta = (filter.end_date - filter.start_date).days
    if delta > settings.analytics_max_date_range_days:
        raise ValueError(f"Date range exceeds maximum of {settings.analytics_max_date_range_days} days")

    # Query de agregacion en DB (estado externo — try/except)
    try:
        rows = await db.execute(
            select(
                func.date_trunc("day", Email.received_at).label("day"),
                func.count(Email.id).label("count"),
            )
            .where(
                Email.received_at >= filter.start_date,
                Email.received_at <= filter.end_date,
            )
            .group_by(text("day"))
            .order_by(text("day"))
        )
    except SQLAlchemyError as exc:
        raise DatabaseError(f"Analytics query failed: {exc}") from exc

    data_points = [
        VolumeDataPoint(date=str(row.day.date()), count=row.count)
        for row in rows
    ]
    return VolumeResponse(
        data_points=data_points,
        total_emails=sum(dp.count for dp in data_points),
        start_date=str(filter.start_date),
        end_date=str(filter.end_date),
    )
```

### analytics_service.py — CSV export (streaming)

```python
# CORRECTO: StreamingResponse con generador — no carga todos los rows en memoria
async def stream_csv_export(
    self,
    filter: DateRangeFilter,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    """
    Generador para StreamingResponse.
    Produce chunks de ANALYTICS_CSV_CHUNK_SIZE filas.
    Operacion de DB es external-state; cada fetch es try/except.
    """
    yield "id,received_at,action_category,type_category,state,was_overridden\n"

    offset = 0
    chunk_size = settings.analytics_csv_chunk_size

    while True:
        try:
            rows = await db.execute(
                select(Email, ClassificationResult)
                .join(ClassificationResult, isouter=True)
                .where(
                    Email.received_at >= filter.start_date,
                    Email.received_at <= filter.end_date,
                )
                .order_by(Email.received_at)
                .offset(offset)
                .limit(chunk_size)
            )
        except SQLAlchemyError as exc:
            # En un generador no podemos propagar HTTP 500 bien —
            # loggear y terminar el stream
            logger.error("CSV export query failed", extra={"offset": offset, "error": str(exc)})
            return

        result_rows = rows.all()
        if not result_rows:
            break

        for email, classification in result_rows:
            # Serializar fila (computo local — condicionales, no try/except)
            action = classification.action_category.slug if classification else ""
            type_ = classification.type_category.slug if classification else ""
            overridden = "yes" if (classification and classification.was_overridden) else "no"
            yield f"{email.id},{email.received_at.isoformat()},{action},{type_},{email.state.value},{overridden}\n"

        offset += chunk_size
```

### integration_service.py — test de conexion

```python
async def test_connection(
    self,
    adapter_type: str,
    db: AsyncSession,
) -> ConnectionTestResult:
    """
    GARANTIA: siempre retorna ConnectionTestResult. Nunca lanza excepcion al caller.
    Los errores del adapter son parte del resultado, no excepciones del sistema.
    """
    import time

    config = await self._load_config(adapter_type, db)
    adapter = self._build_adapter(adapter_type, config)

    start = time.monotonic()
    try:
        await adapter.test_connection()
        latency_ms = int((time.monotonic() - start) * 1000)
        return ConnectionTestResult(
            success=True,
            latency_ms=latency_ms,
            adapter_type=adapter_type,
        )
    except EmailAdapterError as exc:
        return ConnectionTestResult(success=False, error_detail=str(exc), adapter_type=adapter_type)
    except ChannelAdapterError as exc:
        return ConnectionTestResult(success=False, error_detail=str(exc), adapter_type=adapter_type)
    except CRMAdapterError as exc:
        return ConnectionTestResult(success=False, error_detail=str(exc), adapter_type=adapter_type)
    except LLMAdapterError as exc:
        return ConnectionTestResult(success=False, error_detail=str(exc), adapter_type=adapter_type)
```

## Estructura de endpoints (resumen)

```
GET    /api/categories/actions              — list (Reviewer+)
POST   /api/categories/actions              — create (Admin)
GET    /api/categories/actions/{id}         — get (Reviewer+)
PUT    /api/categories/actions/{id}         — update (Admin)
DELETE /api/categories/actions/{id}         — delete con FK guard (Admin)
PUT    /api/categories/actions/reorder      — reorder display_order (Admin)

GET    /api/categories/types                — list (Reviewer+)
POST   /api/categories/types               — create (Admin)
GET    /api/categories/types/{id}           — get (Reviewer+)
PUT    /api/categories/types/{id}           — update (Admin)
DELETE /api/categories/types/{id}           — delete con FK guard (Admin)
PUT    /api/categories/types/reorder        — reorder display_order (Admin)

GET    /api/classification/examples         — list (Admin)
POST   /api/classification/examples         — create (Admin)
PUT    /api/classification/examples/{id}    — update (Admin)
DELETE /api/classification/examples/{id}    — delete (Admin)

GET    /api/classification/feedback         — list paginada (Admin)

GET    /api/integrations/email              — status + config (Admin)
PUT    /api/integrations/email              — update config (Admin)
POST   /api/integrations/email/test         — test conexion (Admin)

GET    /api/integrations/channels           — list de adapters (Admin)
PUT    /api/integrations/channels/{adapter} — update config (Admin)
POST   /api/integrations/channels/{adapter}/test — test conexion (Admin)

GET    /api/integrations/crm                — status + config (Admin)
PUT    /api/integrations/crm                — update config (Admin)
POST   /api/integrations/crm/test           — test conexion (Admin)

GET    /api/integrations/llm                — status + config (Admin)
PUT    /api/integrations/llm                — update config (Admin)
POST   /api/integrations/llm/test           — test conexion (Admin)

GET    /api/analytics/volume                — serie temporal (Reviewer+)
GET    /api/analytics/classification-distribution — pie charts (Reviewer+)
GET    /api/analytics/accuracy              — % override (Reviewer+)
GET    /api/analytics/routing               — stats por canal (Reviewer+)
GET    /api/analytics/export                — CSV streaming (Admin) [Tier 2]

GET    /api/logs                            — logs paginados y filtrados (Admin)
```

## Estructura de archivos esperada

```
src/api/
├── routers/
│   ├── categories.py       # CRUD ActionCategory + TypeCategory + FewShotExample + Feedback
│   ├── integrations.py     # Status + config + test de los 4 adapters
│   ├── analytics.py        # 4 queries + CSV export
│   └── logs.py             # Logs paginados
└── schemas/
    ├── categories.py       # ActionCategory*, TypeCategory*, FewShotExample*, Feedback*
    ├── integrations.py     # IntegrationStatus, *Config, *Update, ConnectionTestResult
    ├── analytics.py        # DateRangeFilter, Volume*, Distribution*, Accuracy*, Routing*
    └── logs.py             # LogEntry, LogFilter, LogListResponse

src/services/
├── category_service.py     # CategoryService: CRUD + FK guard + reorder
├── analytics_service.py    # AnalyticsService: queries agregadas + CSV streaming
└── integration_service.py  # IntegrationService: config R/W + test_connection()
```

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Criterios de exito (deterministicos)

- [ ] `ActionCategory` CRUD completo — create, read, update, delete exitoso, reorder
- [ ] `TypeCategory` CRUD completo — mismas operaciones que ActionCategory
- [ ] DELETE de categoria referenciada por `ClassificationResult` retorna HTTP 409 con
  `affected_email_count` en el body — verificable con test que inserta clasificacion y luego
  intenta eliminar la categoria
- [ ] DELETE de categoria no referenciada retorna HTTP 200 con `{"deleted": true}`
- [ ] `is_active=false` via PUT desactiva la categoria sin eliminarla — no afecta clasificaciones existentes
- [ ] `FewShotExample` CRUD completo — create, read, update, delete
- [ ] `GET /api/classification/feedback` retorna lista paginada con `total`, `page`, `page_size`
- [ ] GET /api/integrations/* — respuesta nunca incluye API keys, tokens, o credenciales en texto plano
- [ ] `ConnectionTestResult.success=False` retorna HTTP 200 (no 500) — el test fallido es un resultado valido
- [ ] `ConnectionTestResult` incluye `latency_ms` cuando `success=True`
- [ ] `GET /api/analytics/volume` con rango de 30 dias retorna 30 data points (uno por dia, count=0 en dias sin emails)
- [ ] Analytics queries usan GROUP BY en SQL — 0 bucles Python sobre listas de emails para calcular agregados (verificable via EXPLAIN ANALYZE en test de integracion)
- [ ] `GET /api/analytics/export` retorna `StreamingResponse` con `Content-Type: text/csv` y header `Content-Disposition: attachment; filename=...`
- [ ] CSV export no carga todos los emails en memoria — usa generador con chunks de `ANALYTICS_CSV_CHUNK_SIZE`
- [ ] `GET /api/logs` soporta filtros: `level`, `source`, `since`, `until`, `email_id`
- [ ] Todos los endpoints de config son admin-only (403 para Reviewer en POST/PUT/DELETE)
- [ ] Endpoints de analytics son accesibles para Reviewer (200 OK)
- [ ] `LogEntry.context` nunca contiene subjects, sender names o body content — solo IDs y slugs
- [ ] `DateRangeFilter` rechaza rango mayor a `ANALYTICS_MAX_DATE_RANGE_DAYS` con HTTP 422
- [ ] `LLMIntegrationUpdate.temperature_classify` rechaza valores fuera de [0.0, 2.0] con HTTP 422
- [ ] `ruff check src/api/routers/categories.py src/api/routers/integrations.py src/api/routers/analytics.py src/api/routers/logs.py` — 0 violaciones
- [ ] `mypy src/api/routers/ src/api/schemas/ src/services/category_service.py src/services/analytics_service.py src/services/integration_service.py` — 0 errores
- [ ] `pytest tests/api/test_categories_router.py tests/api/test_integrations_router.py tests/api/test_analytics_router.py tests/api/test_logs_router.py -v` — todos pasan

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**

1. `mypy src/api/schemas/categories.py src/api/schemas/integrations.py src/api/schemas/analytics.py src/api/schemas/logs.py` — schemas primero; todos los servicios y routers dependen de ellos
2. `mypy src/services/category_service.py src/services/analytics_service.py src/services/integration_service.py` — servicios dependen de schemas
3. `mypy src/api/routers/categories.py src/api/routers/integrations.py src/api/routers/analytics.py src/api/routers/logs.py` — routers son el ultimo nivel
4. `ruff check src/api/routers/ src/api/schemas/ src/services/category_service.py src/services/analytics_service.py src/services/integration_service.py && ruff format --check src/api/routers/ src/api/schemas/ src/services/`
5. `pytest tests/api/test_categories_router.py -v` — CRUD + FK guard primero (nucleo del bloque)
6. `pytest tests/api/test_integrations_router.py -v` — test_connection semantics
7. `pytest tests/api/test_analytics_router.py -v` — queries + CSV export
8. `pytest tests/api/test_logs_router.py -v`

**Verificaciones criticas (no automatizables):**

```bash
# Verificar que ningun router retorna credenciales en texto plano
grep -rn "api_key\|token\|password\|secret" src/api/schemas/integrations.py
# El resultado debe mostrar solo campos booleanos (*_configured: bool)
# Ningun campo debe ser str con nombre de credencial

# Verificar que analytics_service no tiene bucles Python sobre listas de emails
grep -rn "for email in\|for row in emails\|\.all()" src/services/analytics_service.py
# Si aparece un .all() seguido de un for loop para calcular agregados: FALLO
# Los agregados deben venir de GROUP BY en SQL

# Verificar que CSV export usa generador (no carga en memoria)
grep -n "yield" src/services/analytics_service.py
# Debe haber al menos 2 yields (header + body)
```

**Consultas requeridas antes de implementar:**

- Consultar Inquisidor para confirmar el tipo correcto del campo `context` en `LogEntry`:
  `dict[str, str]` (valores solo string para PII compliance) vs `dict[str, str | int | uuid.UUID]`
  — impacto en mypy strictness y en la serialization layer de `SystemLog`.
- Consultar Sentinel para revisar que el endpoint `PUT /api/integrations/llm` (que acepta
  `classify_model` y `draft_model` como strings libres) no puede usarse para redirigir
  las llamadas LLM a endpoints arbitrarios controlados por el atacante. El `integration_service`
  debe validar contra una lista de modelos permitidos configurada en `settings`.
