# Bloque 12: Pipeline & Scheduler

## Objetivo

Implementar el pipeline Celery completo que conecta los cinco servicios (B7-B11) en una cadena
de tareas tipada, mas el scheduler APScheduler corriendo en su propio contenedor con lock Redis
que previene polls concurrentes. Cada etapa hace commit independiente; un fallo en la etapa N
no revierte la etapa N-1. Los resultados de las tareas se almacenan en DB/Redis con dataclasses
tipados — nunca via Celery result backend (`AsyncResult.get()` retorna `Any`).

## Dependencias

- Bloque 1 (Models): `Email`, `EmailState`, `VALID_TRANSITIONS`, session factories async + sync
- Bloque 7 (Ingestion Service): `IngestionService`, `IngestionBatchResult`
- Bloque 8 (Classification Service): `ClassificationService`, `ClassificationResult` (service schema)
- Bloque 9 (Routing Service): `RoutingService`, `RoutingResult`
- Bloque 10 (CRM Sync Service): `CRMSyncService`, `CRMSyncResult`
- Bloque 11 (Draft Generation Service): `DraftGenerationService`, `DraftResult`
- Redis (`src/adapters/redis_client.py`): para lock del scheduler y almacenamiento de resultados

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/tasks/celery_app.py` — Configuracion del app Celery: broker Redis, backend Redis,
  serializer JSON, timezone UTC, task autodiscover. Configurables via Settings (D14).
- `src/tasks/result_types.py` — Dataclasses tipados de resultado para las 5 tareas:
  `IngestResult`, `ClassifyResult`, `RouteResult`, `CRMSyncResult`, `DraftResult`.
  Ninguno hereda de `dict`. Ninguno tiene campo `Any`.
- `src/tasks/pipeline.py` — Definicion del pipeline completo: funcion `run_pipeline` que
  construye la chain Celery, y las 5 tareas: `ingest_task`, `classify_task`, `route_task`,
  `crm_sync_task`, `draft_task`. Cada tarea llama a su servicio correspondiente.
- `src/scheduler/main.py` — Entry point APScheduler para el contenedor dedicado. Configura
  scheduler, registra jobs, inicia loop. Sin imports de `src/api/` (contenedor separado).
- `src/scheduler/jobs.py` — `poll_email_accounts_job`: itera cuentas activas, adquiere lock
  Redis por `account_id`, envia `ingest_task` a la cola Celery, libera lock. Lock TTL = intervalo
  de polling.
- `src/core/config.py` — Modificar: agregar settings de pipeline
  (`CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `PIPELINE_POLL_INTERVAL_SECONDS`,
  `PIPELINE_SCHEDULER_LOCK_KEY_PREFIX`, `PIPELINE_SCHEDULER_LOCK_TTL_SECONDS`,
  `PIPELINE_INGEST_MAX_RETRIES`, `PIPELINE_CLASSIFY_MAX_RETRIES`,
  `PIPELINE_ROUTE_MAX_RETRIES`, `PIPELINE_CRM_MAX_RETRIES`, `PIPELINE_DRAFT_MAX_RETRIES`,
  `PIPELINE_BACKOFF_BASE_SECONDS`)

### Frontend (frontend-worker)

- N/A — este bloque es exclusivamente backend. El estado del pipeline visible en el dashboard
  es responsabilidad de B13 (API endpoints de email y health check).

### Tests (Inquisidor)

- `tests/tasks/test_pipeline_chain.py` — Chain completa con todos los servicios mockeados:
  email pasa por las 5 etapas, cada etapa recibe el resultado correcto de la anterior, estado
  final `DRAFT_GENERATED` (o `ROUTED` si CRM/draft no configurados).
- `tests/tasks/test_pipeline_partial_failure.py` — Fallo en cada etapa individual: fallo en
  classify_task no revierte ingest_task (email permanece en DB con estado `SANITIZED`),
  fallo en route_task no revierte classify_task (clasificacion preservada), etc. Un test
  por etapa de fallo.
- `tests/tasks/test_pipeline_result_types.py` — Verificar que `IngestResult`, `ClassifyResult`,
  `RouteResult`, `CRMSyncResult`, `DraftResult` son dataclasses tipados sin campos `Any`.
  Verificar que ningun task usa `AsyncResult.get()`.
- `tests/scheduler/test_poll_job.py` — `poll_email_accounts_job`: lock previene envio doble,
  lock TTL correcto, lock se libera incluso si `ingest_task.delay()` lanza excepcion,
  accounts inactivas no son polleadas.
- `tests/scheduler/test_scheduler_lock.py` — Lock distribuido Redis: acquisition exitosa,
  segundo intento retorna False, expiración de TTL libera lock, crash-safety (lock expira).

## Skills aplicables

- **pre-mortem** (CRITICO): Aplicado en la seccion "Pre-Mortem Analysis" abajo. Cat 1
  (ordering: tareas de la chain deben ejecutarse en orden especifico), Cat 6 (non-atomic:
  cada tarea hace commit independiente), Cat 8 (defaults de polling y retry son load-bearing),
  Cat 9 (lifecycle de lock Redis y conexiones Celery).
- **try-except** (CRITICO): Ver "Exception Strategy" abajo. Cada tarea cruza boundaries
  externos (DB, servicios). Construccion de la chain es computo local.
- **tighten-types** (CRITICO): Ver "Type Decisions" abajo. `AsyncResult.get()` retorna `Any`
  — prohibido. Resultados de tareas via dataclasses tipados en DB/Redis (D3).
- **contract-docstrings** (ALTO): `run_pipeline` documenta precondicion de estado inicial,
  garantia de commit independiente, y semantica de cadena opcional (CRM/draft condicionales).

## Pre-Mortem Analysis

### Fragility: Reordenamiento accidental de tareas en la chain

- **Category:** Cat 1 (implicit ordering)
- **What breaks:** Si `classify_task` se ejecuta antes de que `ingest_task` haya hecho commit
  del estado `SANITIZED`, la query del email en `classify_task` encontrara estado `FETCHED`
  y fallara la precondicion de `ClassificationService`. Si `route_task` se ejecuta antes de
  `classify_task`, el email estara en estado `SANITIZED` y `RoutingService` levantara
  `InvalidStateTransitionError`. Los errores son confusos porque no dicen "wrong order" sino
  "invalid state transition".
- **Hardening:** La chain se construye en un unico lugar (`run_pipeline` en `pipeline.py`).
  Cada tarea verifica el estado esperado del email al inicio (precondicion explicita, no
  convencion). El orden es: `ingest_task` → `classify_task` → `route_task` →
  `crm_sync_task` (condicional) → `draft_task` (condicional). Insertar una tarea nueva entre
  etapas existentes requiere actualizar las precondiciones de la tarea siguiente — forzado por
  `email.transition_to()` que valida contra `VALID_TRANSITIONS` del modelo.

### Fragility: Scheduler lanza dos polls antes de que expire el lock

- **Category:** Cat 9 (implicit resource lifecycle)
- **What breaks:** Si `PIPELINE_SCHEDULER_LOCK_TTL_SECONDS < PIPELINE_POLL_INTERVAL_SECONDS`,
  el lock expira antes de que el siguiente poll este programado. Si el poll anterior todavia
  esta procesando (batch grande, lentitud de Gmail API), el lock ya expiro y el siguiente
  scheduler tick adquiere el lock y envia otro `ingest_task` para la misma cuenta. Resultado:
  dos workers procesando el mismo inbox en paralelo, duplicados en DB (mitigados por
  deduplicacion de B7 pero con costo de DB writes extra y logs confusos).
- **Hardening:** `PIPELINE_SCHEDULER_LOCK_TTL_SECONDS` debe ser >= `PIPELINE_POLL_INTERVAL_SECONDS`.
  Default: ambos `300`. El job de scheduler verifica explicitamente que TTL == intervalo de
  polling al arrancar (assertion en `main.py`). Lock TTL se setea en `SET NX EX` atomico —
  no hay race entre check y set.

### Fragility: Fallo de commit en etapa N-1 con etapa N ya encolada

- **Category:** Cat 6 (non-atomic)
- **What breaks:** Si `classify_task` hace flush del `ClassificationResult` a DB pero el
  commit falla (timeout de PostgreSQL), y en ese mismo momento `route_task` ya fue encolada
  como continuacion de la chain, `route_task` intentara leer un `ClassificationResult` que
  no existe en DB. Resultado: `route_task` falla con "classification not found" y el email
  queda en estado `CLASSIFIED` sin clasificacion accesible.
- **Hardening:** Cada tarea hace commit completo antes de encolar la siguiente. La chain
  Celery no usa `link` (que encola automaticamente): cada tarea, al completar exitosamente,
  llama explicitamente a `next_task.delay(email_id)`. Si el commit falla, `next_task.delay`
  nunca se llama. El email queda en estado previo y puede ser reintentado desde el dashboard
  (B13 `POST /api/emails/{id}/retry`).

### Fragility: Celery task result backend acumula resultados sin TTL

- **Category:** Cat 9 (implicit resource lifecycle)
- **What breaks:** Si el result backend de Celery se configura con Redis y `result_expires=None`
  (default en algunas versiones), los resultados se acumulan indefinidamente en Redis. En
  produccion con alto volumen (1000+ emails/dia), esto agota memoria Redis en semanas.
  La configuracion de broker y backend desde la misma URL de Redis complica la separacion
  de namespaces.
- **Hardening:** `CELERY_RESULT_EXPIRES` configurado via env (default `3600` segundos).
  Los resultados de negocio no van al result backend — van a DB (D3). El result backend
  solo almacena metadata de tareas para Flower/monitoring. Si el backend Redis falla, las
  tareas siguen ejecutandose (el backend no es critico para el flujo de negocio).

### Fragility: Chain entera cancelada si CRM/draft no configurados en routing rule

- **Category:** Cat 1 (implicit ordering) + Cat 8 (load-bearing defaults)
- **What breaks:** `crm_sync_task` y `draft_task` son condicionales — solo se ejecutan si la
  `RoutingAction` incluye `crm_sync: true` o `generate_draft: true`. Si el codigo de decision
  de "ejecutar o no" vive en la chain (Celery `chord`/`group`) en lugar de dentro de la tarea,
  el flag se evalua en tiempo de construccion de la chain con datos que pueden no estar
  disponibles. Si el routing no ha completado cuando la chain se construye, el flag es `False`
  por default y CRM/draft nunca corren aunque la regla lo indique.
- **Hardening:** La decision de ejecutar `crm_sync_task` / `draft_task` vive DENTRO de
  `route_task`, despues de que el routing ha completado. `route_task` lee `RoutingResult.actions`
  e invoca `crm_sync_task.delay(email_id)` y/o `draft_task.delay(email_id)` condicionalmente.
  No hay `chord`/`group` condicional en tiempo de construccion de la chain. La chain inicial es:
  `ingest_task` → `classify_task` → `route_task`. Las bifurcaciones las decide `route_task`.

## Exception Strategy

| Operacion | Externa/Local | Mecanismo | Tipos de Excepcion | Handler |
|-----------|--------------|-----------|-------------------|---------|
| `IngestionService.ingest_batch()` | Externa (DB + Gmail) | try/except en el servicio | `EmailAdapterError`, `SQLAlchemyError` | Aislado por email; fallo total aborta tarea |
| `ClassificationService.classify()` | Externa (LLM + DB) | try/except en el servicio | `LLMConnectionError`, `LLMRateLimitError`, `SQLAlchemyError` | `LLMRateLimitError` → retry con backoff; otros → `CLASSIFICATION_FAILED` |
| `RoutingService.route()` | Externa (Slack/channel + DB) | try/except en el servicio | `ChannelAdapterError`, `SQLAlchemyError` | Por `RoutingAction` individual; fallo parcial aceptable |
| `CRMSyncService.sync()` | Externa (HubSpot + DB) | try/except en el servicio | `CRMAuthError`, `CRMRateLimitError`, `CRMAdapterError` | `CRMAuthError` → no retry; rate limit → retry con backoff |
| `DraftGenerationService.generate()` | Externa (LLM + Gmail + DB) | try/except en el servicio | `LLMRateLimitError`, `LLMConnectionError`, `EmailAdapterError` | `LLMRateLimitError` → retry; otros → `DRAFT_FAILED` |
| Construccion de `Signature` Celery | Local | Condicional | N/A | Si `email_id` es None, no se construye la chain |
| Evaluacion de flags condicionales (`crm_sync`, `draft`) | Local | Condicional | N/A | `if routing_result.requires_crm_sync` — sin try/except |
| `redis.set(lock_key, ...)` SET NX EX | Externa (Redis) | try/except | `redis.RedisError` | Log warning, skip poll para esta cuenta; no re-raise |
| `redis.delete(lock_key)` release | Externa (Redis) | try/except en `finally` | `redis.RedisError` | Log warning; lock expira por TTL como fallback |
| Top-level de cada Celery task | N/A | `except Exception` | `Exception` | Unico punto permitido por D7; log + retry con backoff |
| `ingest_task.delay(account_id)` (enqueue) | Externa (Redis broker) | try/except | `redis.RedisError`, `kombu.exceptions.OperationalError` | Log error; scheduler continua con siguiente cuenta |

**Regla critica:** El `try` block que envuelve la llamada al servicio debe ser lo mas estrecho
posible — solo la llamada al metodo, no la construccion de parametros. Los parametros se
construyen fuera del `try` con condicionales.

**Top-level pattern (el unico `except Exception` aceptable):**

```python
@celery_app.task(bind=True, max_retries=settings.pipeline_classify_max_retries)
def classify_task(self: Task, email_id: str) -> None:
    try:
        with sync_session_factory() as db:
            # Carga del email: DB query — external state
            try:
                email = db.get(Email, uuid.UUID(email_id))
            except SQLAlchemyError as exc:
                logger.error("DB error loading email", extra={"email_id": email_id})
                raise self.retry(exc=exc)

            if email is None:
                logger.error("Email not found", extra={"email_id": email_id})
                return  # no retry — email eliminado

            # Llamada al servicio: external state (LLM + DB)
            try:
                result = ClassificationService(...).classify(email.id, db)
            except LLMRateLimitError as exc:
                raise self.retry(
                    exc=exc,
                    countdown=getattr(exc, "retry_after_seconds", None)
                    or settings.pipeline_backoff_base_seconds,
                )

            # Encolar siguiente tarea: condicional local, sin try/except para la decision
            if result.success:
                route_task.delay(email_id)

    except Exception as exc:  # top-level: el unico except Exception permitido (D7)
        logger.exception("Unexpected error in classify_task", extra={"email_id": email_id})
        raise self.retry(exc=exc)
```

## Type Decisions

| Tipo | Kind | Justification |
|------|------|---------------|
| `IngestResult` | `@dataclass(frozen=True)` | Resultado de ingest_task; inmutable tras construccion; almacenado en DB. Sin `Any`. |
| `ClassifyResult` | `@dataclass(frozen=True)` | Resultado de classify_task; contiene `email_id`, `success`, `action`, `type`, `confidence`. |
| `RouteResult` | `@dataclass(frozen=True)` | Resultado de route_task; contiene `email_id`, `actions_dispatched`, `actions_failed`. |
| `CRMSyncResult` | `@dataclass(frozen=True)` | Resultado de crm_sync_task; contiene `email_id`, `contact_id`, `activity_id`, `status`. |
| `DraftResult` | `@dataclass(frozen=True)` | Resultado de draft_task; contiene `email_id`, `draft_id`, `status`. |
| `PipelineRunRecord` | `SQLAlchemy Mapped model` | Registro en DB de cada ejecucion del pipeline para un `email_id`. Almacena resultados serializados de cada etapa. |
| `TaskStatus` | `Enum` | `PENDING`, `RUNNING`, `SUCCESS`, `FAILED`, `RETRYING` — estado de cada etapa del pipeline visible en dashboard. |
| `CeleryConfig` | `Pydantic BaseModel` | Configuracion del app Celery: broker_url, result_backend, task_serializer, timezone. Construido desde Settings. |
| `SchedulerLockKey` | `NewType("SchedulerLockKey", str)` | Distingue semanticamente el lock key del scheduler de otros keys Redis. |

**Prohibido en este bloque:**
- `AsyncResult.get()` — retorna `Any`. Los resultados de negocio van a DB.
- `dict[str, Any]` en firmas de tareas o funciones de pipeline.
- `celery.canvas.chain` construida con `link_error` que pasa `dict` raw al handler.

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Configuracion de la chain Celery

La chain es lineal en su nucleo; `route_task` bifurca a tareas opcionales:

```
[scheduler] -> ingest_task(account_id)
                    |
              classify_task(email_id)     <- encolada por ingest_task al completar
                    |
              route_task(email_id)        <- encolada por classify_task al completar
                    |
          +---------+---------+
          |                   |
    crm_sync_task        draft_task       <- ambas condicionales; route_task decide
    (si regla lo pide)  (si regla lo pide)
```

**Diseno de la bifurcacion:** `route_task` inspecciona `RoutingResult.actions` y llama
`crm_sync_task.delay(email_id)` y/o `draft_task.delay(email_id)` si los flags estan activos
en al menos una `RoutingAction`. Las tareas opcionales son independientes entre si: ambas
pueden ejecutarse en paralelo sin dependencia de orden.

**Invariante:** Solo un `classify_task`, `route_task`, `crm_sync_task`, y `draft_task` por
`email_id` estan activos al mismo tiempo. Garantizado por el modelo de estado del email
(un email en estado `CLASSIFYING` no puede tener otro `classify_task` valido para el mismo ID
porque la precondicion de estado fallaria).

## Scheduler APScheduler (scheduler/main.py + jobs.py)

El contenedor scheduler no importa nada de `src/api/`. Es un proceso Python independiente que:

1. Carga `Settings` desde env vars.
2. Instancia `AsyncIOScheduler` de APScheduler.
3. Registra `poll_email_accounts_job` con `IntervalTrigger(seconds=settings.pipeline_poll_interval_seconds)`.
4. Conecta al mismo Redis (como cliente para locks) y envia tareas a la cola Celery.
5. Nunca instancia `FastAPI` ni sesiones async de SQLAlchemy directamente.

```python
# scheduler/jobs.py

async def poll_email_accounts_job() -> None:
    """
    Itera todas las EmailAccount activas y encola ingest_task para cada una.
    Lock Redis por account_id previene polls concurrentes en la misma cuenta.

    Preconditions:
      - Redis accesible
      - Al menos una EmailAccount activa en DB
    External state errors:
      - RedisError en adquisicion de lock: skip cuenta, log warning, continuar con siguiente
      - SQLAlchemyError al cargar cuentas: abortar job, log error
      - RedisError al enviar tarea a broker: log error, skip cuenta
    Silenced:
      - Lock ya tomado (otro worker aun procesando): retorno silencioso, sin warning excesivo
    """
    try:
        accounts = await _load_active_accounts()
    except SQLAlchemyError as exc:
        logger.error("Failed to load active accounts for polling", extra={"error": str(exc)})
        return

    for account in accounts:
        lock_key = SchedulerLockKey(
            f"{settings.pipeline_scheduler_lock_key_prefix}:{account.id}"
        )
        acquired = False
        try:
            acquired = await redis_client.set(
                lock_key, "1", nx=True, ex=settings.pipeline_scheduler_lock_ttl_seconds
            )
        except redis.RedisError as exc:
            logger.warning(
                "Redis lock acquisition failed — skipping account",
                extra={"account_id": str(account.id), "error": str(exc)},
            )
            continue

        if not acquired:
            # Otro worker ya procesando esta cuenta — silencioso (esperado)
            continue

        try:
            ingest_task.delay(str(account.id))
        except (redis.RedisError, kombu.exceptions.OperationalError) as exc:
            logger.error(
                "Failed to enqueue ingest_task",
                extra={"account_id": str(account.id), "error": str(exc)},
            )
            # Liberar lock — la tarea no fue encolada
            try:
                await redis_client.delete(lock_key)
            except redis.RedisError:
                pass  # Lock expirara por TTL; no hay doble procesamiento
```

**Nota sobre el lock en el scheduler vs en IngestionService (B7):** B7 tambien tiene un lock
Redis en `IngestionService._acquire_poll_lock`. Ambos locks son necesarios y complementarios:
el lock del scheduler previene que multiples `ingest_task` sean encoladas para la misma cuenta
(producer-side); el lock del servicio previene que dos workers Celery ejecuten el servicio
concurrentemente si la tarea fue encolada dos veces de todas formas (consumer-side).

## Defaults load-bearing (Cat 8 pre-mortem)

| Default | Valor | Env Var | Consecuencia si incorrecto |
|---------|-------|---------|---------------------------|
| Poll interval | `300` s | `PIPELINE_POLL_INTERVAL_SECONDS` | Demasiado bajo: rate limit Gmail + saturacion de cola Celery. Demasiado alto: latencia de clasificacion inaceptable para usuarios |
| Scheduler lock TTL | `300` s | `PIPELINE_SCHEDULER_LOCK_TTL_SECONDS` | Debe ser >= poll interval. Si es menor: polls concurrentes. Si es mucho mayor: cuenta bloqueada tras crash de worker por horas |
| Ingest max retries | `3` | `PIPELINE_INGEST_MAX_RETRIES` | `0`: ningun retry si Gmail tiene spike transitorio. `10+`: emails atascados en retry loop llenan la cola |
| Classify max retries | `3` | `PIPELINE_CLASSIFY_MAX_RETRIES` | `0`: sin retry en LLM rate limit — clasifaciones perdidas. `5+`: LLM outage puede bloquear la cola por horas |
| Route max retries | `2` | `PIPELINE_ROUTE_MAX_RETRIES` | `0`: notificacion perdida si Slack tiene momentos de inactividad. `5+`: mensajes duplicados en Slack si el problema es idempotencia |
| CRM max retries | `3` | `PIPELINE_CRM_MAX_RETRIES` | Similar a classify; `CRMAuthError` no debe retentarse independientemente de este valor |
| Draft max retries | `2` | `PIPELINE_DRAFT_MAX_RETRIES` | Similar a classify pero con menor impacto; HITL compensa |
| Backoff base | `60` s | `PIPELINE_BACKOFF_BASE_SECONDS` | Demasiado bajo: hammer al servicio externo en fallo. Demasiado alto: email tarda horas en clasificarse tras un fallo transitorio |
| Celery result TTL | `3600` s | `CELERY_RESULT_EXPIRES` | `None`: Redis acumula resultados indefinidamente hasta OOM |
| Broker URL | `redis://redis:6379/0` | `CELERY_BROKER_URL` | Debe apuntar a Redis correcto; `localhost` falla en Docker Compose |
| Result backend URL | `redis://redis:6379/1` | `CELERY_RESULT_BACKEND` | DB distinta al broker evita interferencia entre metadata de tareas y mensajes de cola |

## Contratos de metodo

### `run_pipeline(email_id: uuid.UUID) -> None`

```
Preconditions:
  - email_id: UUID valido de un Email en DB en estado SANITIZED o superior
  - Celery broker (Redis) accesible

Errors raised on violation:
  - No levanta — encola classify_task.delay(str(email_id)). Si el broker no es accesible,
    kombu.exceptions.OperationalError propagada al caller.

External state errors:
  - Broker Redis inaccesible: OperationalError — el caller (scheduler job) loggea y continua

Silenced errors:
  - Ninguno en run_pipeline mismo. Cada tarea maneja sus propios errores.

Note: run_pipeline NO es una tarea Celery — es una funcion Python que construye y envia
la chain. La atomicidad de "la chain completa" no existe — cada tarea es independiente.
```

## Estructura de archivos esperada

```
src/tasks/
├── celery_app.py          # Celery app instance + configuracion
├── result_types.py        # IngestResult, ClassifyResult, RouteResult, CRMSyncResult, DraftResult
└── pipeline.py            # run_pipeline + 5 task definitions

src/scheduler/
├── __init__.py
├── main.py                # APScheduler entry point
└── jobs.py                # poll_email_accounts_job + _load_active_accounts
```

## Criterios de exito (deterministicos)

### Calidad de codigo

- [ ] `ruff check src/tasks/ src/scheduler/` — 0 violaciones
- [ ] `ruff format src/tasks/ src/scheduler/ --check` — 0 diferencias
- [ ] `mypy src/tasks/ src/scheduler/` — 0 errores de tipo

### Tipos (tighten-types — Directiva D1/D3)

- [ ] `IngestResult`, `ClassifyResult`, `RouteResult`, `CRMSyncResult`, `DraftResult` son
  `@dataclass(frozen=True)` — verificable via `grep -n "frozen=True" src/tasks/result_types.py`
- [ ] Ninguna firma en `pipeline.py` tiene `dict[str, Any]` o `Any` — verificable via mypy estricto
- [ ] `AsyncResult.get()` no aparece en ningun archivo de `src/tasks/` —
  verificable via `grep -rn "AsyncResult.get\|\.get()" src/tasks/`
- [ ] Resultados de tareas almacenados en `PipelineRunRecord` DB model — no via result backend
- [ ] `CeleryConfig` construido desde `Settings` (Pydantic BaseModel) — no desde dict

### Manejo de excepciones (try-except — Directivas D7/D8)

- [ ] Cada tarea tiene exactamente un `except Exception` en el top-level — el unico permitido (D7)
- [ ] `LLMRateLimitError` en classify_task: retry con `countdown` configurado, sin `CLASSIFICATION_FAILED`
- [ ] `CRMAuthError` en crm_sync_task: NO trigger retry — log + return (no hammer credenciales invalidas)
- [ ] Construccion de Celery `Signature` sin try/except — computo local (D8)
- [ ] Evaluacion de flags `crm_sync`/`draft` en route_task sin try/except — condicionales (D8)
- [ ] Lock Redis en `finally` block o context manager — garantia de release ante exception

### Pipeline funcional (Sec 3.1-3.5)

- [ ] Email procesado completamente: estado final `DRAFT_GENERATED` si todas las reglas lo requieren
- [ ] Email procesado sin CRM/draft: estado final `ROUTED` — chain termina en route_task
- [ ] Fallo en classify_task: email permanece en `SANITIZED` (estado de ingest), no `CLASSIFIED`
- [ ] Fallo en route_task: email permanece en `CLASSIFIED`, ClassificationResult existe en DB
- [ ] Fallo en crm_sync_task: email permanece en `ROUTED`, RoutingActions existen en DB
- [ ] Retry de classify_task ante `LLMRateLimitError`: countdown >= `PIPELINE_BACKOFF_BASE_SECONDS`
- [ ] `run_pipeline(email_id)` encola `classify_task` sin retornar resultado (fire-and-forget)

### Scheduler (APScheduler + Redis lock)

- [ ] Scheduler corre en contenedor dedicado: `src/scheduler/main.py` es el entry point del Dockerfile
- [ ] No importa nada de `src/api/` — verificable via `grep -rn "from src.api" src/scheduler/`
- [ ] Lock adquirido antes de encolar `ingest_task`, liberado despues — no puede quedar lock huerfano
  en flujo normal
- [ ] Segundo llamado al job con lock activo: no encola segunda tarea (verificable en test)
- [ ] Lock TTL configurado via `PIPELINE_SCHEDULER_LOCK_TTL_SECONDS` — no hardcodeado
- [ ] Crash de worker: lock expira por TTL, siguiente poll procede normalmente
- [ ] Assertion en `main.py`: `lock_ttl >= poll_interval` al arrancar (fail-fast en misconfiguracion)

### Pre-mortem (Cat 1, 6, 8, 9)

- [ ] Orden de tareas no modificable sin cambiar precondiciones de estado en cada tarea (Cat 1)
- [ ] Cada tarea hace su propio commit antes de encolar la siguiente (Cat 6) — verificable en test
  de fallo parcial: email N-1 persiste cuando N falla
- [ ] Todos los defaults de pipeline en `Settings` — `grep -n "300\|60\|3600" src/tasks/pipeline.py`
  no retorna ninguna constante hardcodeada (Cat 8)
- [ ] Lock Redis liberado en `finally` o context manager en todos los code paths (Cat 9)

### PII en logs (Sec 11.4)

- [ ] Ningun log statement en `pipeline.py` o `jobs.py` contiene `subject`, `from_address`,
  `body_plain`, o `snippet` — solo `email_id` y `account_id`

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**

1. `mypy src/tasks/result_types.py` — dataclasses tipados, sin dependencias
2. `mypy src/tasks/celery_app.py` — configuracion Celery desde Settings
3. `mypy src/tasks/pipeline.py` — 5 tareas + run_pipeline
4. `mypy src/scheduler/jobs.py src/scheduler/main.py` — scheduler
5. `ruff check src/tasks/ src/scheduler/ && ruff format --check src/tasks/ src/scheduler/`
6. `pytest tests/tasks/test_pipeline_result_types.py -v` — tipos antes de comportamiento
7. `pytest tests/scheduler/test_scheduler_lock.py -v` — lock antes del job completo
8. `pytest tests/tasks/test_pipeline_chain.py -v` — chain completa con servicios mockeados
9. `pytest tests/tasks/test_pipeline_partial_failure.py -v` — fallo por etapa
10. `pytest tests/scheduler/test_poll_job.py -v` — job completo

**Verificaciones criticas (no automatizables):**

```bash
# D3: AsyncResult.get() prohibido
grep -rn "AsyncResult\|\.get()" src/tasks/
# Resultado esperado: vacio (excepto comentarios)

# D14: sin constantes hardcodeadas de tiempo/conteo en pipeline
grep -n "300\|3600\|60\b" src/tasks/pipeline.py src/scheduler/jobs.py
# Resultado esperado: vacio (todos los valores vienen de settings.*)

# D7: except Exception solo en top-level de tareas
grep -n "except Exception" src/tasks/pipeline.py
# Resultado esperado: exactamente 5 matches (uno por tarea)
```

**Consultas requeridas antes de implementar:**

- Consultar Inquisidor para confirmar el patron correcto de bifurcacion condicional en Celery:
  llamadas a `.delay()` dentro de `route_task` vs Celery `chord`/`group` — confirmar que la
  decision condicional dentro de la tarea es la forma correcta para evitar race conditions.
- Consultar Sentinel para revisar la configuracion de `CELERY_RESULT_BACKEND` compartiendo
  Redis con el broker — confirmar separacion de DB indices (broker en `/0`, backend en `/1`)
  es suficiente o se requiere namespace adicional.
