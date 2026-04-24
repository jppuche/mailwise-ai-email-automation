# Bloque 7: Ingestion Service

## Objetivo

Implementar `IngestionService` que orquesta el ciclo completo de ingestion de emails: fetch desde
el Email adapter, deduplicacion contra el registro de mensajes procesados, sanitizacion via
`src/core/sanitizer.py`, almacenamiento en DB con estado `FETCHED`, y transicion a `SANITIZED` —
con thread awareness (extrae `thread_id`, marca solo el mensaje mas reciente de cada thread para
clasificacion). Cada email se procesa de forma independiente: un fallo no detiene el batch
(pre-mortem Cat 6). Las transiciones de estado estan forzadas via el enum de DB (pre-mortem Cat 1).

## Dependencias

- Bloque 0 (Foundation): `src/core/sanitizer.py` disponible; `src/core/config.py` con settings
  de polling; `src/core/logging.py` con PII policy (ID-only).
- Bloque 1 (Database + Models): modelo `Email` con `EmailState` enum DB; session factories
  async (FastAPI) y sync (Celery); metodo `email.transition_to(state)` que fuerza validez.
- Bloque 3 (Email Adapter): `EmailAdapter` ABC + `GmailAdapter` disponibles; `EmailMessage`
  Pydantic model; jerarquia de excepciones `EmailAdapterError`.

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/services/ingestion.py` — `IngestionService` clase con metodos:
  `ingest_batch`, `_deduplicate`, `_sanitize_and_store`, `_acquire_poll_lock`,
  `_release_poll_lock`. Dependency injection del `EmailAdapter` en constructor.
- `src/services/schemas/ingestion.py` — Dataclasses tipados: `IngestionResult` (resultado
  por email individual), `IngestionBatchResult` (resultado del batch completo).
  Sin `dict[str, Any]` en ninguna firma.
- `src/tasks/ingestion_task.py` — Tarea Celery `ingest_emails_task` que instancia
  `IngestionService` y llama `ingest_batch`. Maneja `IngestionBatchResult` como resultado
  tipado almacenado en DB/Redis (Directiva D3 — no via Celery result backend).
- `src/core/config.py` — Modificar: agregar settings de ingestion (`INGESTION_BATCH_SIZE`,
  `INGESTION_POLL_INTERVAL_SECONDS`, `INGESTION_LOCK_TTL_SECONDS`,
  `INGESTION_LOCK_KEY_PREFIX`). Defaults configurables via env.

### Frontend (frontend-worker)

- Ninguno en este bloque — el ingestion service es backend puro. El dashboard que muestra
  emails ingresados se implementa en el bloque de UI de bandeja.

### Tests (Inquisidor)

- `tests/services/test_ingestion_service.py` — Tests unitarios de `IngestionService` con
  `EmailAdapter` mockeado y DB de test. Cubre: batch normal, deduplicacion (mensaje ya
  procesado es saltado), fallo aislado (un email falla, resto procesados), batch vacio,
  thread awareness (solo mas reciente marcado para clasificacion), lock previene concurrencia.
- `tests/services/test_ingestion_schemas.py` — Validacion de `IngestionResult` y
  `IngestionBatchResult`; verifica que los campos estadisticos (total, ingested, skipped,
  failed) son consistentes entre si.
- `tests/tasks/test_ingestion_task.py` — Test de la tarea Celery con `IngestionService`
  mockeado; verifica que `IngestionBatchResult` se persiste en DB y no via result backend.

## Skills aplicables

- **try-except** (CRITICO): Este servicio cruza tres boundaries externos: Email adapter
  (external-state), DB queries de dedup (external-state), y DB writes de almacenamiento
  (external-state). La sanitizacion es local computation (condicionales). El patron de
  aislamiento por email (un fallo no mata el batch) requiere try/except por elemento.
- **tighten-types** (ALTO): `IngestionResult` y `IngestionBatchResult` son dataclasses tipados
  — no dicts ni `Any`. La tarea Celery almacena el resultado en DB/Redis, no lo retorna via
  `AsyncResult.get()`. Aplicar al definir schemas antes de implementar el servicio.
- **pre-mortem** (ALTO): Cat 1 (state ordering: FETCHED→SANITIZED via `transition_to` en el
  modelo — no por convencion). Cat 6 (non-atomic: commit por email individual, no por batch).
  Cat 8 (batch_size, poll_interval, lock_ttl son load-bearing). Cat 3 (thread_id es str, no
  campo derivado — extraer explicitamente, no asumir presencia).

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Esquemas tipados de resultado (schemas/ingestion.py)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class IngestionSkipReason(Enum):
    """Razon por la que un email fue saltado durante ingestion."""
    DUPLICATE = "duplicate"              # provider_message_id ya en DB
    THREAD_NOT_NEWEST = "thread_not_newest"  # mensaje mas antiguo en thread activo


class IngestionFailureReason(Enum):
    """Razon de fallo de un email individual en el batch."""
    ADAPTER_ERROR = "adapter_error"      # EmailAdapterError durante fetch
    DB_ERROR = "db_error"                # SQLAlchemyError durante store
    SANITIZER_ERROR = "sanitizer_error"  # Error en sanitizer (no deberia ocurrir — es local)


@dataclass(frozen=True)
class IngestionResult:
    """Resultado del procesamiento de un email individual."""
    email_id: str | None               # DB ID asignado (None si fallo antes de store)
    provider_message_id: str           # ID del proveedor (Gmail message_id)
    success: bool
    skip_reason: IngestionSkipReason | None = None
    failure_reason: IngestionFailureReason | None = None
    error_detail: str | None = None    # str(exception) para debugging; nunca PII


@dataclass
class IngestionBatchResult:
    """Resultado del batch completo de ingestion."""
    account_id: str                    # ID de la cuenta de email procesada
    batch_start: datetime
    batch_end: datetime
    total_fetched: int                 # mensajes obtenidos del adapter
    ingested: int                      # almacenados exitosamente en DB
    skipped: int                       # duplicados + thread_not_newest
    failed: int                        # errores individuales
    results: list[IngestionResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Proporcion de mensajes procesados exitosamente (ingested / total_fetched)."""
        if self.total_fetched == 0:
            return 1.0
        return self.ingested / self.total_fetched
```

## Flujo de ingestion (IngestionService.ingest_batch)

```
1. Adquirir lock distribuido en Redis (previene polls concurrentes en la misma cuenta)
   → Si lock no disponible: retornar IngestionBatchResult vacio (otro worker ya ejecutando)

2. Llamar EmailAdapter.fetch_new_messages(since=last_poll_at, limit=INGESTION_BATCH_SIZE)
   → try/except EmailAdapterError (external-state)
   → Si falla: release lock, re-raise (no hay mensajes que procesar)

3. Para cada EmailMessage en el batch:
   a. Verificar deduplicacion: query DB por provider_message_id
      → try/except SQLAlchemyError (external-state)
      → Si ya existe: append IngestionResult(skip_reason=DUPLICATE), continuar
   b. Extraer thread_id del mensaje
      → Local computation (condicional — si campo ausente, thread_id=None)
   c. Determinar si es el mensaje mas reciente del thread
      → DB query por thread_id (external-state: try/except SQLAlchemyError)
      → Si no es el mas reciente: append IngestionResult(skip_reason=THREAD_NOT_NEWEST), continuar
   d. Sanitizar: sanitizer.sanitize(email.body_plain or "")
      → Local computation — SIN try/except (Directiva D8; si falla es bug, no runtime error)
   e. Persistir en DB con estado FETCHED
      → try/except SQLAlchemyError (external-state)
      → Commit individual (pre-mortem Cat 6: commit por email, no por batch)
   f. Transicion de estado FETCHED → SANITIZED via email.transition_to(EmailState.SANITIZED)
      → Modelo fuerza validez; si falla es InvalidStateTransitionError (bug — no capturar)
      → Commit individual

4. Release lock
5. Actualizar last_poll_at en DB para la cuenta
6. Retornar IngestionBatchResult con estadisticas completas
```

## Patron de try/except en ingestion.py (directiva D7)

### Boundary: Email Adapter (external-state)

```python
try:
    messages = await self._email_adapter.fetch_new_messages(
        since=last_poll_at,
        limit=settings.ingestion_batch_size,
    )
except EmailAdapterError as exc:
    logger.error("Email fetch failed", extra={"account_id": account_id, "error": str(exc)})
    raise  # fallo total del batch — no hay mensajes que procesar
```

### Boundary: DB deduplicacion (external-state, aislado por email)

```python
try:
    existing = await session.execute(
        select(Email).where(Email.provider_message_id == msg.provider_message_id)
    )
    if existing.scalar_one_or_none() is not None:
        results.append(IngestionResult(
            email_id=None,
            provider_message_id=msg.provider_message_id,
            success=False,
            skip_reason=IngestionSkipReason.DUPLICATE,
        ))
        continue
except SQLAlchemyError as exc:
    logger.error("Dedup check failed", extra={"message_id": msg.provider_message_id, "error": str(exc)})
    results.append(IngestionResult(
        email_id=None,
        provider_message_id=msg.provider_message_id,
        success=False,
        failure_reason=IngestionFailureReason.DB_ERROR,
        error_detail=str(exc),
    ))
    continue  # fallo aislado — procesar siguiente mensaje
```

### Sanitizacion: local computation (NO try/except — Directiva D8)

```python
# Sanitizacion es deterministica y local — fallo aqui es un bug, no error de runtime
sanitized_body = sanitizer.sanitize(msg.body_plain or "")
sanitized_snippet = sanitizer.sanitize(msg.snippet or "")[:settings.email_snippet_length]
```

### Transicion de estado (NO try/except — fallo es bug)

```python
# Modelo fuerza estado valido — si InvalidStateTransitionError aqui, hay un bug de logica
email_record.transition_to(EmailState.FETCHED)
await session.commit()  # commit independiente (pre-mortem Cat 6)

email_record.transition_to(EmailState.SANITIZED)
await session.commit()  # commit independiente
```

## Lock distribuido (prevenir polls concurrentes)

```python
LOCK_KEY = f"{settings.ingestion_lock_key_prefix}:{account_id}"
LOCK_TTL = settings.ingestion_lock_ttl_seconds  # default 300s

async def _acquire_poll_lock(self, account_id: str) -> bool:
    """Intenta adquirir lock en Redis. Retorna True si adquirido, False si ya existe."""
    # SET NX EX — atomico en Redis (no necesita try/except — es local computation sobre Redis)
    acquired = await self._redis.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL)
    return acquired is not None
```

El lock evita que el scheduler lance dos polls simultaneos si el anterior tarda mas que el
intervalo de polling. TTL es safety net — si el worker muere, el lock expira y el siguiente
poll puede proceder.

## Thread awareness

- `thread_id` se extrae del campo `EmailMessage.thread_id` (str | None del adapter).
- Si `thread_id` es None: el mensaje no pertenece a thread conocido — se procesa normalmente.
- Si `thread_id` no es None: query DB por `thread_id` para encontrar el mensaje mas reciente
  ya almacenado con ese thread.
- Si el mensaje actual es mas antiguo que el mas reciente en DB: marcado como
  `THREAD_NOT_NEWEST` y saltado (almacenado pero no enviado a clasificacion).
- Si el mensaje actual es el mas reciente o el primero del thread: procesado normalmente.
- El campo `Email.is_thread_root` (bool) marca si es el mensaje principal del thread.
- **Invariante:** solo un mensaje por thread tiene `classify_next=True` en cualquier momento.

## Tarea Celery (ingestion_task.py — Directiva D3)

```python
@celery_app.task(
    name="tasks.ingest_emails",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def ingest_emails_task(self: Task, account_id: str) -> None:
    """
    Tarea Celery de ingestion. Resultado tipado almacenado en DB — no via result backend.
    top-level except Exception permitido aqui (handler de Celery, Directiva D7 excepcion).
    """
    try:
        # Session sync para Celery (dual session factory pattern)
        with sync_session_factory() as session:
            service = IngestionService(
                email_adapter=get_email_adapter(account_id, session),
                redis=get_redis_client(),
                session=session,
            )
            result: IngestionBatchResult = run_async(service.ingest_batch(account_id))

        # Persistir IngestionBatchResult en DB (no via Celery result backend — Directiva D3)
        _persist_batch_result(result)

    except Exception as exc:  # top-level handler — permitido en Celery (D7)
        logger.error("Ingestion task failed", extra={"account_id": account_id, "error": str(exc)})
        raise self.retry(exc=exc)
```

## Defaults load-bearing (Cat 8 pre-mortem)

| Default | Valor | Env Var | Consecuencia si incorrecto |
|---------|-------|---------|---------------------------|
| Batch size | `50` emails/poll | `INGESTION_BATCH_SIZE` | Demasiado alto: timeout de Gmail API. Demasiado bajo: lag creciente en inbox activo |
| Poll interval | `300` s (5 min) | `INGESTION_POLL_INTERVAL_SECONDS` | Demasiado bajo: rate limit de Gmail. Demasiado alto: latencia de clasificacion inaceptable |
| Lock TTL | `300` s | `INGESTION_LOCK_TTL_SECONDS` | Demasiado bajo: lock expira antes de que termine el poll → polls concurrentes. Demasiado alto: lock fantasma bloquea todos los polls si el worker muere |
| Snippet length | `200` chars | `EMAIL_SNIPPET_LENGTH` | Demasiado largo: PII en notificaciones. Demasiado corto: contexto insuficiente para previsualizacion |

## Estructura de archivos esperada

```
src/services/
├── ingestion.py                  # IngestionService (orquestacion)
└── schemas/
    └── ingestion.py              # IngestionResult, IngestionBatchResult (dataclasses)

src/tasks/
└── ingestion_task.py             # ingest_emails_task (Celery)
```

## Criterios de exito (deterministicos)

### Calidad de codigo

- [ ] `ruff check src/services/ingestion.py src/services/schemas/ingestion.py src/tasks/ingestion_task.py` — 0 violaciones
- [ ] `ruff format ... --check` — 0 diferencias
- [ ] `mypy src/services/ src/tasks/ingestion_task.py` — 0 errores de tipo

### Tipos (tighten-types — Directiva D1/D3)

- [ ] `IngestionResult` y `IngestionBatchResult` son `@dataclass(frozen=True)` o `@dataclass` — no `dict[str, Any]`
- [ ] `IngestionService.ingest_batch` retorna `IngestionBatchResult` — no `dict`
- [ ] `IngestionSkipReason` y `IngestionFailureReason` son Enum — no strings libres
- [ ] Tarea Celery no usa `AsyncResult.get()` para recuperar resultados — resultado en DB
- [ ] `IngestionBatchResult` persiste en DB como registro tipado, no en Celery result backend

### Manejo de excepciones (try-except — Directivas D7/D8)

- [ ] `fetch_new_messages` en try/except con `EmailAdapterError` (external-state)
- [ ] Cada dedup check en try/except con `SQLAlchemyError` aislado (external-state por email)
- [ ] Cada DB write en try/except con `SQLAlchemyError` aislado (external-state por email)
- [ ] Sanitizacion sin try/except — es computacion local deterministica
- [ ] `transition_to(EmailState.FETCHED)` sin try/except — fallo es bug de logica, no error de runtime
- [ ] `transition_to(EmailState.SANITIZED)` sin try/except — idem
- [ ] Top-level de la tarea Celery tiene `except Exception` — unico punto permitido (D7)
- [ ] Sin `except Exception` desnudo en metodos del servicio

### Comportamiento funcional (Sec 3.1-3.5)

- [ ] Batch de 3 emails: 1 duplicado, 1 exitoso, 1 fallo de DB → `ingested=1, skipped=1, failed=1`
- [ ] Mismo `provider_message_id` procesado dos veces → segundo es `DUPLICATE`, no crea registro nuevo
- [ ] Thread con 3 mensajes: solo el mas reciente tiene `classify_next=True`
- [ ] Poll concurrente prevenido: segundo llamado a `ingest_batch` con lock activo retorna resultado vacio
- [ ] Cada email tiene commit individual — verificar que fallo en email N no hace rollback de email N-1
- [ ] `last_poll_at` actualizado en DB al completar batch (incluso si hubo fallos parciales)
- [ ] Estado `FETCHED` y luego `SANITIZED` en dos commits separados — verificable en test

### Pre-mortem (Cat 1, 6, 8)

- [ ] Transiciones de estado via `email.transition_to()` — no asignacion directa `email.state = ...` (Cat 1)
- [ ] Commit por email individual — no commit al final del batch (Cat 6)
- [ ] `INGESTION_BATCH_SIZE` default `50` cargado desde config — no hardcodeado (Cat 8)
- [ ] `INGESTION_LOCK_TTL_SECONDS` default `300` cargado desde config — no hardcodeado (Cat 8)
- [ ] `thread_id` extraido explicitamente de `EmailMessage.thread_id` — no derivado por convencion (Cat 3)

### PII en logs (Sec 11.4)

- [ ] Logger en `ingestion.py` nunca loggea `subject`, `body_plain`, `from_address`, ni `snippet`
- [ ] Solo `account_id`, `email_id` (DB ID), `provider_message_id` en logs estructurados

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Orden de implementacion sugerido para minimizar re-trabajo:**
1. `src/services/schemas/ingestion.py` — dataclasses de resultado, sin dependencias
2. `src/services/ingestion.py` — servicio (depende de schemas, Email adapter ABC, DB models)
3. `src/tasks/ingestion_task.py` — tarea Celery (depende del servicio)
4. `src/core/config.py` — agregar settings de ingestion

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**
1. `mypy src/services/ src/tasks/ingestion_task.py` — tipos primero
2. `ruff check src/services/ src/tasks/ingestion_task.py && ruff format --check ...` — lint
3. `pytest tests/services/test_ingestion_schemas.py -v` — schemas antes del servicio
4. `pytest tests/services/test_ingestion_service.py -v` — servicio completo con mocks
5. `pytest tests/tasks/test_ingestion_task.py -v` — tarea Celery con servicio mockeado
6. `pytest tests/services/ tests/tasks/ -v` — suite completa

**Consultas requeridas antes de implementar:**
- Consultar Inquisidor para confirmar patron de lock distribuido en Redis con `asyncio` —
  `SET NX EX` es correcto para lock atomico, pero confirmar comportamiento en caso de
  excepcion antes del `release` (context manager pattern recomendado).
- Consultar Inquisidor para confirmar que `@dataclass(frozen=True)` en `IngestionResult`
  es correcto vs `frozen=False` — impacto en mutabilidad durante construccion del batch.

**Verificacion critica (no automatizable):** Revisar manualmente que ningun log statement
en `ingestion.py` contenga campos de PII. Sentinel ejecuta revision de PII policy (Sec 11.4)
y confirma que el lock TTL no puede crear condiciones de race en el scheduler antes de marcar
COMPLETO.
