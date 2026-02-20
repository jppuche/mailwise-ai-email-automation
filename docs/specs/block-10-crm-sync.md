# Bloque 10: CRM Sync Service

## Objetivo

Implementar `CRMSyncService` que ejecuta la cadena de operaciones CRM (lookup de contacto,
creacion de contacto, log de actividad, creacion de lead, actualizacion de campos) con cola de
reintento independiente, idempotencia garantizada por DB, y `CRMSyncRecord` que registra el
estado parcial de cada operacion — sin `dict[str, Any]` en ninguna firma publica.

## Dependencias

- Bloque 1 (Models): `CRMSyncRecord`, `CRMSyncStatus`, `Email`, `EmailState`, `VALID_TRANSITIONS`
- Bloque 6 (CRM Adapter): `CRMAdapter` ABC, schemas `ContactLookupResult`, `ContactRecord`,
  `ActivityRecord`, `LeadRecord`, excepciones `CRMAuthError`, `CRMRateLimitError`,
  `CRMAdapterError`
- Bloque 9 (Routing Service): genera `RoutingAction` completada que puede incluir
  `crm_sync: true` en el payload de la regla — trigger de este servicio

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/services/crm_sync.py` — `CRMSyncService`: orquesta la cadena completa de operaciones
  CRM, gestiona idempotencia, controla estado parcial, transiciona `EmailState`
- `src/services/schemas/crm_sync.py` — Pydantic models: `CRMSyncRequest`, `CRMSyncResult`,
  `CRMOperationStatus`, `CRMSyncConfig`
- `src/tasks/crm_sync_task.py` — Tarea Celery: carga request desde DB, llama al service,
  maneja retries con backoff, escribe resultado
- `src/core/config.py` — Modificar: agregar settings de CRM sync
  (`CRM_AUTO_CREATE_CONTACTS`, `CRM_ACTIVITY_SNIPPET_LENGTH`, `CRM_SYNC_RETRY_MAX`,
  `CRM_SYNC_BACKOFF_BASE_SECONDS`)

### Frontend (frontend-worker)

- N/A — este bloque es exclusivamente backend. El estado CRM visible en el dashboard es
  responsabilidad del bloque de la API de emails (B12).

### Tests (Inquisidor)

- `tests/services/test_crm_sync_service.py` — Suite completa del service: sync exitoso
  (todos los ops), fallo parcial (contact creado pero activity falla), fallo de auth
  (sync pausado, no reintentado), rate limit (backoff, cola pendiente), idempotencia
  (segundo sync del mismo email no duplica en CRM), snippet truncado a `CRM_ACTIVITY_SNIPPET_LENGTH`
- `tests/tasks/test_crm_sync_task.py` — Tarea Celery: retry con backoff ante error transitorio,
  auth failure no dispara retry, resultado escrito en `CRMSyncRecord` tras exito/fallo

## Skills aplicables

- **tighten-types** (CRITICO): `CRMSyncService` consume `CRMAdapter` tipado — ninguna firma
  acepta `dict[str, Any]`. `CRMSyncResult` es Pydantic BaseModel con campos nulables para
  operaciones no ejecutadas. El campo `operations` de `CRMSyncResult` es `list[CRMOperationStatus]`,
  no `dict`. Aplicar en planificacion (definir schemas antes del service) y en revision (mypy
  estricto sobre el modulo completo).
- **try-except** (CRITICO): Cada operacion CRM es external-state independiente. El patron
  correcto es un try/except por operacion — no un bloque try que envuelva la cadena entera.
  Cada operacion que falla registra su error y permite que las siguientes se ejecuten. Ver
  "Patron de try/except" abajo.
- **pre-mortem Cat 6** (CRITICO): La cadena de operaciones CRM es inherentemente no atomica.
  Si activity logging falla, el contacto ya creado es valido y no debe revertirse. El diseño
  debe hacer explicita esta semantica via `CRMSyncRecord` con campos nulables por operacion.
- **pre-mortem Cat 8** (ALTO): `CRM_AUTO_CREATE_CONTACTS`, `CRM_ACTIVITY_SNIPPET_LENGTH`,
  `CRM_SYNC_RETRY_MAX`, `CRM_SYNC_BACKOFF_BASE_SECONDS` son todos load-bearing. Ver tabla
  de defaults abajo.
- **contract-docstrings** (MEDIO): `CRMSyncService.sync()` documenta precondiciones (email
  en estado ROUTED), garantias de retorno, errores surfaceados, y errores silenciados (field
  mapping errors se silencian por diseno).

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Contratos de metodo (contract-docstrings — 4 preguntas)

### `CRMSyncService.sync(request: CRMSyncRequest, db: Session) -> CRMSyncResult`

```
Preconditions:
  - request.email_id: UUID del email en estado ROUTED (o CRM_SYNC_FAILED para retry)
  - request.sender_email: str no vacio — clave de lookup de contacto
  - db: sesion sincrona de SQLAlchemy (Celery usa SyncSessionLocal)
  - CRM adapter conectado (inicializado con credenciales validas)

Errors raised on violation:
  - ValueError si request.email_id no corresponde a un Email en DB
  - InvalidStateTransitionError si email no esta en estado compatible (ROUTED o CRM_SYNC_FAILED)

External state errors (por operacion individual — no colapsa la cadena):
  - CRMAuthError: propagada inmediatamente — pausa el sync, no reintenta
  - CRMRateLimitError: propagada inmediatamente — caller (task) decide backoff
  - CRMAdapterError: registrada en CRMOperationStatus.error, cadena continua

Silenced errors:
  - Field mapping error (local computation): loggeado, campo saltado, sync continua
  - Operacion completada en sync previo: skip silencioso (idempotencia), no relanza
```

### `CRMSyncService._execute_contact_lookup(sender_email: str) -> ContactLookupResult | None`

```
Preconditions:
  - sender_email: str no vacio con formato email valido

Errors raised on violation:
  - Ninguno — retorna None si el lookup falla

External state errors:
  - CRMAuthError, CRMRateLimitError, CRMAdapterError: propagadas al caller (sync())

Silenced errors:
  - Ningun contacto encontrado: retorna None (no es un error)
  - Multiples contactos encontrados: usa el primero, loggea ambiguedad (Sec 6.4)
```

## Esquemas Pydantic (schemas/crm_sync.py)

```python
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class CRMSyncConfig(BaseModel):
    """Configuracion de sync leida desde Settings. Nunca hardcodeada en el service."""
    auto_create_contacts: bool      # CRM_AUTO_CREATE_CONTACTS (default: False)
    activity_snippet_length: int    # CRM_ACTIVITY_SNIPPET_LENGTH (default: 200)
    retry_max: int                  # CRM_SYNC_RETRY_MAX (default: 3)
    backoff_base_seconds: int       # CRM_SYNC_BACKOFF_BASE_SECONDS (default: 60)


class CRMSyncRequest(BaseModel):
    """
    Input para CRMSyncService.sync(). Contiene todo el contexto necesario para
    ejecutar la cadena de operaciones CRM sin queries adicionales al email.
    """
    email_id: uuid.UUID
    sender_email: str
    sender_name: str | None = None
    subject: str
    snippet: str                          # primeros CRM_ACTIVITY_SNIPPET_LENGTH chars
    classification_action: str            # slug de ActionCategory (ej: "reply_needed")
    classification_type: str              # slug de TypeCategory (ej: "sales_inquiry")
    received_at: datetime
    create_lead: bool = False             # true si la routing rule especifica lead creation
    field_updates: dict[str, str] = {}    # campo CRM → valor; empty si no hay field updates


class CRMOperationStatus(BaseModel):
    """Estado de una operacion individual dentro del sync."""
    operation: Literal[
        "contact_lookup",
        "contact_create",
        "activity_log",
        "lead_create",
        "field_update",
    ]
    success: bool
    crm_id: str | None = None        # ID del recurso creado/actualizado en CRM
    skipped: bool = False            # True si idempotencia aplicada (ya existia)
    error: str | None = None         # Mensaje de error si success=False y skipped=False


class CRMSyncResult(BaseModel):
    """
    Resultado de CRMSyncService.sync(). Refleja estado parcial de la cadena.
    contact_id/activity_id/lead_id son None si la operacion no se ejecuto o fallo.
    Permite al dashboard mostrar estado de sincronizacion granular.
    """
    email_id: uuid.UUID
    contact_id: str | None = None     # HubSpot contact ID si lookup o create exitoso
    activity_id: str | None = None    # HubSpot engagement ID si log exitoso
    lead_id: str | None = None        # HubSpot deal ID si lead creation exitoso
    operations: list[CRMOperationStatus]
    overall_success: bool             # True solo si todas las operaciones requeridas pasaron
    paused_for_auth: bool = False     # True si CRMAuthError detecto credenciales invalidas
```

**Nota de tipos:** `field_updates: dict[str, str]` en `CRMSyncRequest` es una excepcion
documentada a la regla de no-dict en boundaries: la clave es `str` (nombre de campo CRM) y
el valor es `str` (valor a escribir). No es `dict[str, Any]` — ambos extremos son `str`.
La regla D1 de tighten-types no se viola porque el dict tiene tipos precisos en ambos lados.

## Patron de try/except por operacion (directiva D7)

El principio central de este servicio es que cada operacion CRM se ejecuta en su propio
bloque try/except. No existe un try que envuelva la cadena completa.

```python
async def sync(
    self,
    request: CRMSyncRequest,
    db: AsyncSession,
) -> CRMSyncResult:
    operations: list[CRMOperationStatus] = []
    contact_id: str | None = None
    activity_id: str | None = None
    lead_id: str | None = None

    # Verificar idempotencia: si ya existe un sync exitoso para este email, skip
    existing = await self._load_existing_sync(request.email_id, db)
    if existing and existing.status == CRMSyncStatus.SYNCED:
        return self._build_result_from_record(existing, request.email_id)

    # --- Operacion 1: Contact lookup (external state) ---
    try:
        lookup = await self._crm_adapter.lookup_contact(request.sender_email)
        contact_id = lookup.contact_id if lookup else None
        operations.append(CRMOperationStatus(
            operation="contact_lookup",
            success=True,
            crm_id=contact_id,
        ))
    except CRMAuthError:
        # Auth failure: no reintentar, pausar sync, propagar al caller (task)
        await self._record_sync(request, operations, contact_id, None, None, db)
        raise  # task Celery NO hara retry ante CRMAuthError
    except CRMRateLimitError:
        await self._record_sync(request, operations, contact_id, None, None, db)
        raise  # task Celery hara backoff y retry
    except CRMAdapterError as exc:
        operations.append(CRMOperationStatus(
            operation="contact_lookup",
            success=False,
            error=str(exc),
        ))
        # Contacto no encontrado ni creado — no tiene sentido continuar con activity log

    # --- Operacion 2: Contact create (solo si lookup fallo y auto_create habilitado) ---
    if contact_id is None and self._config.auto_create_contacts:
        try:
            created = await self._crm_adapter.create_contact(
                email=request.sender_email,
                name=request.sender_name,
            )
            contact_id = created.contact_id
            operations.append(CRMOperationStatus(
                operation="contact_create",
                success=True,
                crm_id=contact_id,
            ))
        except CRMAuthError:
            await self._record_sync(request, operations, contact_id, None, None, db)
            raise
        except CRMRateLimitError:
            await self._record_sync(request, operations, contact_id, None, None, db)
            raise
        except CRMAdapterError as exc:
            operations.append(CRMOperationStatus(
                operation="contact_create",
                success=False,
                error=str(exc),
            ))

    # --- Operacion 3: Activity log (solo si tenemos contact_id) ---
    if contact_id is not None:
        try:
            activity = await self._crm_adapter.log_activity(
                contact_id=contact_id,
                subject=request.subject,
                snippet=request.snippet[: self._config.activity_snippet_length],
                classification_action=request.classification_action,
                classification_type=request.classification_type,
                received_at=request.received_at,
            )
            activity_id = activity.activity_id
            operations.append(CRMOperationStatus(
                operation="activity_log",
                success=True,
                crm_id=activity_id,
            ))
        except CRMAuthError:
            await self._record_sync(request, operations, contact_id, activity_id, None, db)
            raise
        except CRMRateLimitError:
            await self._record_sync(request, operations, contact_id, activity_id, None, db)
            raise
        except CRMAdapterError as exc:
            operations.append(CRMOperationStatus(
                operation="activity_log",
                success=False,
                error=str(exc),
            ))
            # contact_id sigue valido — el contacto existe aunque el activity fallo

    # --- Operacion 4: Lead create (condicional) ---
    if request.create_lead and contact_id is not None:
        try:
            lead = await self._crm_adapter.create_lead(
                contact_id=contact_id,
                subject=request.subject,
                classification_type=request.classification_type,
            )
            lead_id = lead.lead_id
            operations.append(CRMOperationStatus(
                operation="lead_create",
                success=True,
                crm_id=lead_id,
            ))
        except CRMAuthError:
            await self._record_sync(request, operations, contact_id, activity_id, lead_id, db)
            raise
        except CRMRateLimitError:
            await self._record_sync(request, operations, contact_id, activity_id, lead_id, db)
            raise
        except CRMAdapterError as exc:
            operations.append(CRMOperationStatus(
                operation="lead_create",
                success=False,
                error=str(exc),
            ))

    # --- Operacion 5: Field updates (local mapping + external write) ---
    for field_name, field_value in request.field_updates.items():
        # Resolucion del campo CRM: local computation — condicional, no try/except (D8)
        crm_field = self._resolve_crm_field(field_name)
        if crm_field is None:
            logger.warning(
                "Unknown field mapping, skipping",
                extra={"field": field_name, "email_id": str(request.email_id)},
            )
            operations.append(CRMOperationStatus(
                operation="field_update",
                success=False,
                error=f"Unknown field mapping: {field_name}",
            ))
            continue  # campo desconocido: loggea y salta; no falla el sync

        if contact_id is not None:
            try:
                await self._crm_adapter.update_contact_field(
                    contact_id=contact_id,
                    field=crm_field,
                    value=field_value,
                )
                operations.append(CRMOperationStatus(
                    operation="field_update",
                    success=True,
                    crm_id=contact_id,
                ))
            except CRMAuthError:
                await self._record_sync(
                    request, operations, contact_id, activity_id, lead_id, db
                )
                raise
            except CRMRateLimitError:
                await self._record_sync(
                    request, operations, contact_id, activity_id, lead_id, db
                )
                raise
            except CRMAdapterError as exc:
                operations.append(CRMOperationStatus(
                    operation="field_update",
                    success=False,
                    error=str(exc),
                ))

    # Commit independiente (D13) — estado parcial persiste aunque el pipeline falle despues
    record = await self._record_sync(
        request, operations, contact_id, activity_id, lead_id, db
    )
    return self._build_result(request.email_id, record, operations)
```

**Clasificacion de operaciones (try-except D7 vs D8):**

| Operacion | Tipo | Patron |
|-----------|------|--------|
| CRM API call (lookup, create, log) | External state | try/except con tipos especificos |
| Idempotency check (DB query) | External state | try/except para SQLAlchemyError |
| Field mapping resolution | Local computation | Condicional (`if crm_field is None`) |
| Snippet truncation | Local computation | Slicing directo, sin try/except |
| `CRMSyncRecord` write | External state | try/except para SQLAlchemyError |

## Idempotencia (Sec 6.3)

La idempotencia se verifica al inicio del sync via query DB, no via llamada al CRM:

```python
async def _load_existing_sync(
    self, email_id: uuid.UUID, db: AsyncSession
) -> CRMSyncRecord | None:
    try:
        result = await db.execute(
            select(CRMSyncRecord)
            .where(CRMSyncRecord.email_id == email_id)
            .order_by(CRMSyncRecord.synced_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    except SQLAlchemyError as exc:
        logger.error(
            "Idempotency check failed",
            extra={"email_id": str(email_id), "error": str(exc)},
        )
        return None  # Sin record previo: continuar con sync normal
```

Si existe un `CRMSyncRecord` con `status=SYNCED` para el email, el sync retorna el resultado
existente sin llamar al CRM. Si el record previo tiene `status=FAILED`, el retry procede.

**Duplicados en CRM (Sec 6.4):** Si `lookup_contact` retorna multiples contactos para el
mismo email, se usa el primero y se loggea la ambiguedad. El servicio NO mergea contactos —
eso es responsabilidad del administrador del CRM.

## Tarea Celery (crm_sync_task.py)

```python
@celery_app.task(
    bind=True,
    max_retries=settings.crm_sync_retry_max,
    default_retry_delay=settings.crm_sync_backoff_base_seconds,
)
def crm_sync_task(self, email_id: str) -> None:
    """
    Top-level Celery task. Unico punto donde `except Exception` es aceptable (D7).
    Construye el request, delega al service, maneja retries.
    """
    with SyncSessionLocal() as db:
        try:
            email = db.get(Email, uuid.UUID(email_id))
            if email is None:
                logger.error("Email not found for CRM sync", extra={"email_id": email_id})
                return

            request = _build_crm_sync_request(email, db)
            service = CRMSyncService(crm_adapter=get_crm_adapter(), config=get_crm_config())
            result = service.sync(request, db)

            # Transicion de estado (D10: via transition_to, no asignacion directa)
            if result.overall_success:
                email.transition_to(EmailState.CRM_SYNCED)
            else:
                email.transition_to(EmailState.CRM_SYNC_FAILED)
            db.commit()  # Commit independiente (D13)

        except CRMAuthError as exc:
            # Auth failure: NO reintentar (credenciales invalidas hasta que se renueven)
            logger.error(
                "CRM auth failure — pausing sync",
                extra={"email_id": email_id, "error": str(exc)},
            )
            # Actualizar estado sin retry
            with SyncSessionLocal() as db2:
                email2 = db2.get(Email, uuid.UUID(email_id))
                if email2:
                    email2.transition_to(EmailState.CRM_SYNC_FAILED)
                    db2.commit()
            # No raise: no queremos que Celery haga retry
            return

        except CRMRateLimitError as exc:
            # Rate limit: backoff con retry
            raise self.retry(
                exc=exc,
                countdown=exc.retry_after_seconds or self.default_retry_delay,
            )

        except Exception as exc:
            # Top-level handler (unico except Exception permitido por D7)
            logger.exception(
                "Unexpected error in crm_sync_task",
                extra={"email_id": email_id},
            )
            raise self.retry(exc=exc)
```

## Transicion de estado (D10)

```
ROUTED → CRM_SYNCED       (todas las operaciones requeridas completadas)
ROUTED → CRM_SYNC_FAILED  (auth failure, o todas las operaciones fallaron)
CRM_SYNC_FAILED → ROUTED  (recovery path: retry reinicia desde ROUTED)
```

La transicion se hace siempre via `email.transition_to(new_state)` — nunca via asignacion
directa `email.state = ...`. Esto garantiza que `VALID_TRANSITIONS` en B01 sea el arbitro.

**Comportamiento de fallo parcial:**
- Contact creado + activity log fallido: `CRMSyncRecord.contact_id` poblado,
  `activity_id=None`. Estado: `CRM_SYNC_FAILED`. El dashboard muestra sincronizacion parcial.
- En retry: idempotencia detecta el contacto existente (via lookup), salta creation,
  reintenta solo activity log.

## Privacidad de datos (Sec 6.5)

```python
# CORRECTO: solo snippet configurado, no el body completo
snippet=request.snippet[: self._config.activity_snippet_length],

# CORRECTO: subject y metadatos de clasificacion
subject=request.subject,
classification_action=request.classification_action,

# PROHIBIDO: body_plain, body_html nunca se envian al CRM
# body_plain=email.body_plain  <- NUNCA
```

El `CRMSyncRequest` no tiene campo `body_plain` ni `body_html` — imposible por construccion
enviar el body completo al CRM. El snippet se genera en el servicio de routing (B9) antes de
construir el request, respetando `CRM_ACTIVITY_SNIPPET_LENGTH`.

## Defaults load-bearing (Cat 8 pre-mortem)

| Default | Valor | Env Var | Consecuencia si incorrecto |
|---------|-------|---------|---------------------------|
| `auto_create_contacts` | `False` | `CRM_AUTO_CREATE_CONTACTS` | `True`: crea contacto para cualquier remitente, incluso spam. `False`: solo sync si contacto ya existe |
| `activity_snippet_length` | `200` chars | `CRM_ACTIVITY_SNIPPET_LENGTH` | Demasiado largo: riesgo de PII exposure (Sec 6.5). Demasiado corto: sin contexto util en CRM |
| `retry_max` | `3` | `CRM_SYNC_RETRY_MAX` | `1`: no tolera fallos transitorios. `10+`: reintentos excesivos en CRM caido |
| `backoff_base_seconds` | `60` | `CRM_SYNC_BACKOFF_BASE_SECONDS` | `5`: martilla la API en rate-limit. `600+`: delay excesivo en sync |

Todos los defaults se cargan desde `src/core/config.py` (pydantic-settings). Ningun valor
hardcodeado en `crm_sync.py` ni en `crm_sync_task.py`.

## Estructura de archivos esperada

```
src/services/
├── crm_sync.py                   # CRMSyncService
└── schemas/
    └── crm_sync.py               # CRMSyncRequest, CRMSyncResult, CRMOperationStatus, CRMSyncConfig

src/tasks/
└── crm_sync_task.py              # Tarea Celery + _build_crm_sync_request helper
```

## Criterios de exito (deterministicos)

- [ ] `CRMSyncService.sync()` ejecuta la cadena completa de 5 operaciones en orden
- [ ] Cada operacion CRM tiene su propio bloque try/except — no hay un try que envuelva la
  cadena completa
- [ ] `CRMAuthError` pausa el sync y NO dispara retry en la tarea Celery
- [ ] `CRMRateLimitError` dispara backoff con retry en la tarea Celery
- [ ] `CRMAdapterError` en una operacion intermedia no cancela las operaciones posteriores
  (fallo de activity_log no cancela lead_create si contact_id es valido)
- [ ] Fallo de activity logging con contact_id valido: `CRMSyncRecord.contact_id` poblado,
  `CRMSyncRecord.activity_id=None` — el record refleja el estado parcial
- [ ] Segundo sync del mismo email (SYNCED) retorna el resultado existente sin llamar al CRM
- [ ] `body_plain` y `body_html` nunca aparecen en ninguna llamada al CRM adapter
- [ ] Snippet truncado a `CRM_ACTIVITY_SNIPPET_LENGTH` antes de enviarse al CRM
- [ ] Field mapping error (campo desconocido) loggea el error y salta el campo — no falla el sync
- [ ] Multiples contactos en lookup: usa el primero, loggea ambiguedad, no lanza
- [ ] Transicion de estado via `email.transition_to()` (nunca asignacion directa)
- [ ] Commit independiente por sync (D13): el record persiste aunque la transicion de estado falle
- [ ] Todos los defaults cargados desde env vars via `CRMSyncConfig`; ninguno hardcodeado
- [ ] `ruff check src/services/crm_sync.py src/tasks/crm_sync_task.py` — 0 violaciones
- [ ] `mypy src/services/crm_sync.py src/services/schemas/crm_sync.py src/tasks/crm_sync_task.py` — 0 errores
- [ ] `pytest tests/services/test_crm_sync_service.py -v` — todos los scenarios pasan
- [ ] `pytest tests/tasks/test_crm_sync_task.py -v` — retry/no-retry behavior verificado

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**
1. `mypy src/services/schemas/crm_sync.py` — schemas primero; errores de tipo aqui
   invalidan todo lo demas
2. `mypy src/services/crm_sync.py` — service depende de schemas
3. `mypy src/tasks/crm_sync_task.py` — task depende de service
4. `ruff check src/services/crm_sync.py src/services/schemas/crm_sync.py src/tasks/crm_sync_task.py && ruff format --check src/services/ src/tasks/crm_sync_task.py` — lint post-tipos
5. `pytest tests/services/test_crm_sync_service.py -v` — logica de negocio completa
6. `pytest tests/tasks/test_crm_sync_task.py -v` — comportamiento de retry

**Verificacion critica (no automatizable):** Revisar manualmente que ningun campo del
`CRMSyncRequest` ni ninguna llamada al adapter incluya `body_plain` o `body_html`.
Inquisidor ejecuta revision via tighten-types confirmando ausencia de `dict[str, Any]`
en todas las firmas publicas antes de marcar COMPLETO.

**Consultas requeridas antes de implementar:**
- Consultar Inquisidor para confirmar que `field_updates: dict[str, str]` en `CRMSyncRequest`
  es la representacion correcta o si debe ser `list[FieldUpdate]` con BaseModel dedicado
  (impacto en mypy strictness).
- Consultar Sentinel para revisar el patron de manejo de `CRMAuthError` en la tarea Celery —
  especificamente la decision de no hacer retry ante auth failure (riesgo de silenciar un
  problema de configuracion critico).
