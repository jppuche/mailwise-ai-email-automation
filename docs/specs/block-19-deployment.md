# Bloque 19: Deployment & Documentation

## Objetivo

Completar la configuracion de Docker Compose con health checks en los 6 servicios, verificar
el pipeline de logging estructurado JSON con correlation IDs end-to-end, escribir la guia de
extensibilidad de adapters, y producir la documentacion de despliegue completa incluyendo
todas las variables de entorno de los 19 bloques anteriores.

## Dependencias

- Todos los bloques B0-B18: los health checks y el logging verifican la infraestructura
  completa ya implementada
- Bloque 12 (Pipeline): Celery worker + scheduler ya configurados
- Bloque 13 (API Core): `GET /api/health` ya implementado
- Bloque 15 (Frontend Shell): contenedor Nginx/Vite ya definido
- Bloque 3 (Email Adapter): `test_connection()` para health check del adapter Gmail
- Bloque 4 (LLM Adapter): `test_connection()` para health check del adapter LiteLLM
- Bloque 5 (Channel Adapter): `test_connection()` para health check del adapter Slack
- Bloque 6 (CRM Adapter): `test_connection()` para health check del adapter HubSpot

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/core/logging.py` — Configuracion de logging estructurado JSON para todos los
  servicios. `CorrelationIdFilter` inyecta `correlation_id` en cada log entry desde
  contextvariable. `PiiSanitizingFilter` verifica que ningun campo prohibido aparezca
  en los logs (ultima linea de defensa — la politica primaria esta en los servicios).
  Configurable via `LOG_LEVEL` env var (default `INFO`). Formato JSON configurable via
  `LOG_FORMAT` (`json` | `text` para desarrollo local).
- `src/core/correlation.py` — `CorrelationIdContext`: `contextvars.ContextVar` para
  correlation ID. `set_email_correlation_id(email_id: EmailId) -> None`. `get_correlation_id() -> str`.
  Importado por todos los servicios al inicio de procesar un email.
- `.env.example` — Actualizado con TODAS las variables de entorno de B0-B19.
  Organizadas por secciones: Database, Redis, Auth, Gmail, Slack, HubSpot, LLM,
  Pipeline, API, Frontend, Logging, Docker. Cada variable con descripcion inline.

### Infrastructure

- `docker-compose.yml` — Modificar: agregar health checks a los 6 servicios.
  Ver seccion "Health Checks" abajo para configuracion exacta.
- `docker-compose.prod.yml` — Nuevo: overrides de produccion. Nginx en lugar de Vite
  dev server, variables de entorno desde secrets, restart policies.
- `docker/healthchecks/` — Scripts de health check para servicios que no tienen
  health check HTTP nativo (worker, scheduler).
  - `worker-health.sh` — `celery -A src.tasks.celery_app inspect ping -d celery@$HOSTNAME`
  - `scheduler-health.sh` — Verifica proceso vivo + Redis lock TTL activo

### Documentation

- `docs/deployment.md` — Guia de despliegue completa. Ver seccion "Deployment Guide
  Structure" abajo.
- `docs/adapter-guide.md` — Guia de extensibilidad de adapters. Ver seccion "Adapter
  Guide Structure" abajo.

### Tests (Inquisidor)

- `tests/infrastructure/test_health_checks.py` — Cada servicio responde healthy tras
  `docker compose up`. Requiere Docker disponible en CI; marcado con `@pytest.mark.docker`.
- `tests/infrastructure/test_logging.py` — JSON estructurado valido, correlation IDs
  presentes, PII ausente en outputs de log.
- `tests/infrastructure/test_env_example.py` — Todas las variables referenciadas en
  `src/core/config.py` estan documentadas en `.env.example`. Test de paridad.

## Skills aplicables

- **concept-analysis** (CRITICO): Aplicado en la seccion "Concept Analysis" abajo.
  Verificar consistencia de terminologia a traves de los 20 specs, docs de despliegue,
  y guia de adapters contra el glosario de B0.
- **pre-mortem** (CRITICO): Aplicado en la seccion "Pre-Mortem Analysis" abajo.
  Cat 8 (defaults load-bearing: intervalos de health check, formato de logs, CORS origins),
  Cat 10 (version-coupled: versiones exactas de imagenes Docker).
- **contract-docstrings** (ALTO): La guia de adapters documenta contratos de los ABCs:
  invariantes de entrada, garantias de retorno, errores levantados, errores de estado
  externo, errores silenciados. El formato de contrato debe coincidir con el formato
  usado en B3-B6.
- **tighten-types** (MEDIO): `src/core/logging.py` y `src/core/correlation.py` deben
  tener firmas completamente tipadas. `CorrelationIdFilter` hereda de `logging.Filter`
  y debe tipar correctamente el metodo `filter(record: logging.LogRecord) -> bool`.

## Concept Analysis

La guia de adapters y la documentacion de despliegue deben usar los terminos canonicos del
glosario de B0. Inconsistencias encontradas durante la verificacion de los 19 specs:

### Terminos canonicos verificados

| Termino canonico | Variantes encontradas | Accion |
|---|---|---|
| `EmailAccount` | "email account", "inbox", "cuenta Gmail" | Usar `EmailAccount` en docs tecnicas; "inbox" aceptable en UI copy |
| `EmailState` | "estado del email", "email status", "pipeline state" | `EmailState` en codigo, "pipeline status" en UI, "email state" en docs tecnicas |
| `ClassificationResult` | "clasificacion", "classification", "result" | `ClassificationResult` en codigo; "classification" en docs y API; nunca solo "result" |
| `RoutingRule` | "routing rule", "regla de ruteo", "rule" | `RoutingRule` en codigo; "routing rule" en docs en ingles; nunca "rule" sin contexto |
| `RoutingAction` | "action", "routing action", "dispatch" | `RoutingAction` en codigo; "routing action" en docs; "dispatch" solo para el acto de enviar |
| `Draft` | "draft", "borrador", "draft email" | `Draft` en codigo; "draft" en docs en ingles |
| `adapter` | "adapter", "integration", "connector", "plugin" | "adapter" en codigo y docs tecnicas; "integration" en UI y docs de usuario |
| `pipeline` | "pipeline", "workflow", "chain", "process" | "pipeline" en codigo y docs tecnicas; "workflow" aceptable en docs de usuario |
| `correlation_id` | "correlation id", "trace id", "request id", "email_id" | `correlation_id` en logging; es el `email_id` en contexto de pipeline; documentar equivalencia |

### Inconsistencias a corregir en docs existentes

Estas correcciones son responsabilidad de Lorekeeper al revisar docs. El backend-worker
las anota aqui como hallazgos del analisis:

- B0 spec usa "inbox" y "email account" intercambiablemente — aclarar que `EmailAccount`
  es el termino del modelo de datos; "inbox" es coloquial para UI.
- B13 spec usa "adapters" y "integrations" en contextos tecnicos — estandarizar a "adapters"
  para referencias a codigo, "integrations" para referencias a servicios externos en docs
  de despliegue (donde el usuario final ve la terminologia).
- Guia de adapters debe abrir con un glosario mini que mapa nombres de clase a nombres
  de "integracion" visible al usuario: `GmailEmailAdapter` → "Gmail integration",
  `SlackChannelAdapter` → "Slack integration", etc.

## Pre-Mortem Analysis

### Fragility: Health check interval demasiado agresivo causa restart loop

- **Category:** Cat 8 (load-bearing defaults)
- **What breaks:** `interval=5s` en el health check del worker Celery ejecuta
  `celery inspect ping` cada 5 segundos. En contenedores lentos (startup cold, Docker
  Desktop en Windows), el comando tarda mas de 5s y el contenedor se marca unhealthy
  antes de que el worker haya terminado de iniciarse. Docker Compose reinicia el
  contenedor, creando un loop de restart.
- **Hardening:** Defaults configurables — nunca hardcodeados en `docker-compose.yml`.
  Variables: `HEALTHCHECK_INTERVAL` (default `30s`), `HEALTHCHECK_TIMEOUT` (default `10s`),
  `HEALTHCHECK_RETRIES` (default `3`), `HEALTHCHECK_START_PERIOD` (default `60s`).
  `start_period` da tiempo al contenedor para inicializar antes de que los fallos cuenten.
  Documentar el valor minimo seguro por contenedor en `docs/deployment.md`.

### Fragility: Imagenes Docker con tag mutable silenciosamente actualizan dependencias

- **Category:** Cat 10 (version-coupled)
- **What breaks:** `FROM python:3.12-slim` puede resolver a `3.12.4` hoy y `3.12.5` manana
  si se hace `docker pull`. Una actualizacion menor puede cambiar la version de OpenSSL,
  romper dependencias nativas de `psycopg2` o `cryptography`, o cambiar el comportamiento
  de `ssl`. El fallo se descubre en produccion, no en desarrollo.
- **Hardening:** Pinear versiones exactas de imagenes:
  - Python: `python:3.12.9-slim-bookworm` (patch version + distro variant exactos)
  - Node: `node:20.18-alpine3.21` (minor version + distro variant exactos)
  - PostgreSQL: `postgres:16.6-alpine` (patch version + alpine variant)
  - Redis: `redis:7.4-alpine` (minor version + alpine variant)
  - Nginx: `nginx:1.27-alpine` (minor version + alpine variant)
  Actualizar versiones solo con decision explicita y test de regresion. Versiones
  documentadas en `docs/deployment.md` como "tested combination".

### Fragility: CORS origins hardcodeados en compose no se propagan a produccion

- **Category:** Cat 8 (load-bearing defaults)
- **What breaks:** Si `CORS_ALLOWED_ORIGINS=http://localhost:5173` esta hardcodeado en
  `docker-compose.yml` bajo `environment:`, y el `docker-compose.prod.yml` no lo sobreescribe,
  el frontend de produccion (en `https://app.mailwise.example.com`) es bloqueado por CORS.
  El error es silencioso en el servidor (HTTP 200 en preflight) y solo visible en browser console.
- **Hardening:** `API_CORS_ALLOWED_ORIGINS` SIEMPRE desde `.env`, nunca hardcodeado en
  compose files. El `docker-compose.yml` referencia `${API_CORS_ALLOWED_ORIGINS}` sin default.
  Si la variable no esta en `.env`, Docker Compose lanza error al inicio (fail-fast).
  `.env.example` documenta el valor correcto para dev y la estructura esperada para prod.

### Fragility: Structured logging no activo en todos los servicios

- **Category:** Cat 8 (load-bearing defaults)
- **What breaks:** Si `src/core/logging.py` solo se importa en `src/api/main.py` pero no
  en `src/tasks/celery_app.py` ni en `src/scheduler/main.py`, los workers Celery y el
  scheduler emiten logs en formato texto plano. En produccion con log aggregation (Datadog,
  Loki), los logs de worker no son parseables. Correlation IDs no aparecen en logs de
  tareas Celery aunque si aparezcan en logs del API.
- **Hardening:** `src/core/logging.py` exporta `configure_logging()` que se llama en el
  entry point de CADA proceso: `main.py` (API), `celery_app.py` (worker), `scheduler/main.py`
  (scheduler). La configuracion usa el mismo handler y formato JSON. Verificado en
  `tests/infrastructure/test_logging.py` ejecutando cada proceso y validando el output JSON.

### Fragility: .env.example desactualizado omite variables de bloques recientes

- **Category:** Cat 8 (load-bearing defaults)
- **What breaks:** Un developer nuevo clona el repo, copia `.env.example` a `.env`,
  corre `docker compose up`, y la API falla al iniciar porque `HUBSPOT_API_TOKEN` o
  `ANALYTICS_CSV_CHUNK_SIZE` no estan en `.env.example`. El error no es obvio porque
  Pydantic Settings lanza `ValidationError` con el nombre del campo pero no dice
  "este campo deberia estar en .env.example".
- **Hardening:** `tests/infrastructure/test_env_example.py` — parsea `src/core/config.py`
  con `ast` para extraer todos los campos de `Settings` que no tienen default. Verifica
  que cada uno aparece como comentario o variable en `.env.example`. Este test falla en CI
  si alguien agrega un campo a `Settings` sin actualizar `.env.example`.

## Health Checks: Configuracion detallada

```yaml
# docker-compose.yml (fragmento — solo health checks)

services:
  db:
    image: postgres:16.6-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: ${HEALTHCHECK_INTERVAL:-30s}
      timeout: ${HEALTHCHECK_TIMEOUT:-10s}
      retries: ${HEALTHCHECK_RETRIES:-3}
      start_period: ${HEALTHCHECK_START_PERIOD:-30s}

  redis:
    image: redis:7.4-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: ${HEALTHCHECK_INTERVAL:-30s}
      timeout: ${HEALTHCHECK_TIMEOUT:-10s}
      retries: ${HEALTHCHECK_RETRIES:-3}
      start_period: ${HEALTHCHECK_START_PERIOD:-10s}

  api:
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:8000/api/health || exit 1"]
      interval: ${HEALTHCHECK_INTERVAL:-30s}
      timeout: ${HEALTHCHECK_TIMEOUT:-10s}
      retries: ${HEALTHCHECK_RETRIES:-3}
      start_period: ${HEALTHCHECK_START_PERIOD:-60s}

  worker:
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "/app/docker/healthchecks/worker-health.sh"]
      interval: ${HEALTHCHECK_INTERVAL:-30s}
      timeout: ${HEALTHCHECK_TIMEOUT:-15s}
      retries: ${HEALTHCHECK_RETRIES:-3}
      start_period: ${HEALTHCHECK_START_PERIOD:-60s}

  scheduler:
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "/app/docker/healthchecks/scheduler-health.sh"]
      interval: ${HEALTHCHECK_INTERVAL:-30s}
      timeout: ${HEALTHCHECK_TIMEOUT:-10s}
      retries: ${HEALTHCHECK_RETRIES:-3}
      start_period: ${HEALTHCHECK_START_PERIOD:-30s}

  frontend:
    depends_on:
      api:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:${FRONTEND_PORT:-5173}/ || exit 1"]
      interval: ${HEALTHCHECK_INTERVAL:-30s}
      timeout: ${HEALTHCHECK_TIMEOUT:-10s}
      retries: ${HEALTHCHECK_RETRIES:-3}
      start_period: ${HEALTHCHECK_START_PERIOD:-30s}
```

**Dependency ordering:** `db + redis → api + worker + scheduler → frontend`
Enforced via `depends_on` con `condition: service_healthy`. Un servicio no inicia si
su dependencia no paso el health check.

## Structured Logging: Diseno

### Formato JSON de log entry

```json
{
  "timestamp": "2026-02-20T14:32:01.123456Z",
  "level": "INFO",
  "component": "classification_service",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Email classified successfully",
  "extra": {
    "email_id": "550e8400-e29b-41d4-a716-446655440000",
    "action_category": "support",
    "confidence": 0.92,
    "duration_ms": 342
  }
}
```

### PII policy enforcement

Campos PROHIBIDOS en cualquier log entry (verificable via grep):
- `subject` (email subject puede contener PII)
- `from_address` (email address del remitente)
- `body_plain` o `body_html` (contenido del email)
- `sender_name` (nombre del remitente)
- `recipient_address` (destinatario)

Campos PERMITIDOS:
- `email_id` (UUID — identificador interno)
- `account_id` (UUID — cuenta de email, no direccion)
- `classification_id` (UUID)
- `draft_id` (UUID)
- `rule_id` (int)
- `action_category` (slug — no contiene PII)
- `duration_ms`, `confidence`, `retry_count` (metricas)
- `error` (string — DEBE ser pre-sanitizado en el servicio antes de loggear)

### CorrelationIdContext

```python
# src/core/correlation.py

import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str] = ContextVar(
    "correlation_id", default="no-correlation"
)


def set_email_correlation_id(email_id: uuid.UUID) -> None:
    """
    Establece el correlation_id para el email actual en el contexto de la corutina
    o tarea Celery. Llamado al inicio de cada tarea del pipeline.

    Preconditions:
      - email_id: UUID valido de un Email en DB
    External state errors: ninguno — es computo local (ContextVar)
    Silenced: ninguno
    """
    _correlation_id.set(str(email_id))


def get_correlation_id() -> str:
    """Retorna el correlation_id del contexto actual. Nunca raises."""
    return _correlation_id.get()
```

### configure_logging() — entry points

```python
# src/core/logging.py

import logging
import logging.config
from src.core.config import settings


def configure_logging() -> None:
    """
    Configura logging estructurado JSON para el proceso actual.
    Debe llamarse en el entry point de CADA proceso:
    - src/api/main.py (lifespan startup)
    - src/tasks/celery_app.py (signals.worker_init)
    - src/scheduler/main.py (antes de iniciar el scheduler)

    LOG_LEVEL: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' (default: 'INFO')
    LOG_FORMAT: 'json' | 'text' (default: 'json'; 'text' para desarrollo local)
    """
    ...
```

## Deployment Guide Structure

`docs/deployment.md` debe contener las siguientes secciones en este orden:

### 1. Prerequisitos

- Docker >= 24.0, Docker Compose >= 2.20
- API keys necesarias: Gmail OAuth2 credentials, Slack Bot Token, HubSpot Private App Token,
  LiteLLM-compatible LLM API key (OpenAI / Anthropic)
- Git para clonar el repositorio

### 2. Quick Start (5 pasos)

```bash
git clone <repo>
cd mailwise
cp .env.example .env
# Editar .env con las API keys reales (ver seccion 3)
docker compose up -d
# Esperar a que todos los servicios esten healthy (ver: docker compose ps)
# Acceder a http://localhost:5173
```

### 3. Variables de entorno (referencia completa)

Tabla con TODAS las variables de `.env.example`:

| Variable | Requerida | Default | Descripcion |
|---|---|---|---|
| `DATABASE_URL` | Si | — | PostgreSQL connection string |
| `REDIS_URL` | Si | — | Redis connection string |
| `SECRET_KEY` | Si | — | JWT signing key (256-bit random) |
| `JWT_ACCESS_TOKEN_TTL_SECONDS` | No | `900` | Access token TTL (15 min) |
| `JWT_REFRESH_TOKEN_TTL_SECONDS` | No | `604800` | Refresh token TTL (7 days) |
| `BCRYPT_ROUNDS` | No | `12` | bcrypt cost factor |
| `GMAIL_CLIENT_ID` | Si | — | OAuth2 client ID de Google Cloud |
| `GMAIL_CLIENT_SECRET` | Si | — | OAuth2 client secret de Google Cloud |
| `SLACK_BOT_TOKEN` | Si | — | Slack Bot Token (xoxb-...) |
| `HUBSPOT_API_TOKEN` | Condicional | — | HubSpot Private App Token |
| `LLM_CLASSIFY_MODEL` | No | `gpt-4o-mini` | Modelo para clasificacion |
| `LLM_DRAFT_MODEL` | No | `gpt-4o` | Modelo para generacion de drafts |
| `LLM_CLASSIFY_TEMPERATURE` | No | `0.1` | Temperatura para clasificacion |
| `LLM_DRAFT_TEMPERATURE` | No | `0.7` | Temperatura para drafts |
| `LLM_FALLBACK_MODEL` | No | `gpt-3.5-turbo` | Modelo fallback (debe diferir de classify) |
| `LLM_API_KEY` | Si | — | API key del proveedor LLM |
| `CELERY_BROKER_URL` | No | `redis://redis:6379/0` | Celery broker |
| `CELERY_RESULT_BACKEND` | No | `redis://redis:6379/1` | Celery result backend |
| `CELERY_RESULT_EXPIRES` | No | `3600` | TTL de resultados en segundos |
| `PIPELINE_POLL_INTERVAL_SECONDS` | No | `300` | Intervalo de polling (5 min) |
| `PIPELINE_SCHEDULER_LOCK_TTL_SECONDS` | No | `300` | TTL del lock del scheduler |
| `PIPELINE_INGEST_MAX_RETRIES` | No | `3` | Max retries de ingest_task |
| `PIPELINE_CLASSIFY_MAX_RETRIES` | No | `3` | Max retries de classify_task |
| `PIPELINE_ROUTE_MAX_RETRIES` | No | `2` | Max retries de route_task |
| `PIPELINE_CRM_MAX_RETRIES` | No | `3` | Max retries de crm_sync_task |
| `PIPELINE_DRAFT_MAX_RETRIES` | No | `2` | Max retries de draft_task |
| `PIPELINE_BACKOFF_BASE_SECONDS` | No | `60` | Backoff base en segundos |
| `API_CORS_ALLOWED_ORIGINS` | Si | — | Lista de origenes CORS separados por coma |
| `API_HOST` | No | `0.0.0.0` | Host del servidor API |
| `API_PORT` | No | `8000` | Puerto del servidor API |
| `LOG_LEVEL` | No | `INFO` | Nivel de logging |
| `LOG_FORMAT` | No | `json` | Formato de log (json o text) |
| `ANALYTICS_CSV_CHUNK_SIZE` | No | `100` | Chunk size para CSV streaming |
| `INGESTION_BATCH_SIZE` | No | `50` | Emails por batch de ingestor |
| `LLM_BODY_TRUNCATION_CHARS` | No | `4000` | Max chars de body enviados al LLM |
| `LLM_SNIPPET_LENGTH` | No | `200` | Chars de snippet en ClassificationResult |
| `HEALTHCHECK_INTERVAL` | No | `30s` | Intervalo de health check en Docker |
| `HEALTHCHECK_TIMEOUT` | No | `10s` | Timeout de health check en Docker |
| `HEALTHCHECK_RETRIES` | No | `3` | Reintentos de health check |
| `HEALTHCHECK_START_PERIOD` | No | `60s` | Periodo de gracia al inicio |

### 4. First-time setup

1. Crear usuario admin: `docker compose exec api python -m src.cli create-admin --email admin@example.com`
2. Configurar cuenta de email: acceder a `/admin/integrations`, conectar cuenta Gmail via OAuth2
3. Configurar LLM: agregar API key en `/admin/integrations/llm`
4. Crear categorias iniciales: usar la UI o la API `POST /api/categories`
5. Crear regla de routing por defecto: `POST /api/routing-rules`
6. Verificar health: `curl http://localhost:8000/api/health`

### 5. Consideraciones de produccion

- HTTPS: usar Nginx reverse proxy con Let's Encrypt (ver `docker-compose.prod.yml`)
- Secrets: no usar `.env` con secrets en disco — usar Docker Secrets o vault
- Backups: `pg_dump` diario del volumen de PostgreSQL
- Monitoring: `/api/health` expone estado de cada adapter; integrar con Uptime Robot o similar
- Escalado: workers Celery pueden escalar horizontalmente (agregar instancias del servicio `worker`)
- Imagen pinning: las versiones de imagen documentadas son la combinacion testeada — no cambiar sin test de regresion

### 6. Troubleshooting

| Sintoma | Causa probable | Solucion |
|---|---|---|
| API no inicia | `DATABASE_URL` invalido | Verificar que `db` esta healthy, revisar credenciales |
| Worker no conecta | `CELERY_BROKER_URL` incorrecto | Debe usar hostname de servicio Docker, no `localhost` |
| Emails no clasifican | `LLM_API_KEY` invalido | Verificar key en `/admin/integrations/llm` → test connection |
| Health check falla en worker | Worker aun iniciando | Aumentar `HEALTHCHECK_START_PERIOD` |
| CORS error en frontend | `API_CORS_ALLOWED_ORIGINS` no incluye el origen del frontend | Agregar `http://localhost:5173` a la variable |
| Scheduler no hace poll | Lock Redis activo (crash anterior) | `redis-cli DEL mailwise:scheduler:lock:*` y reiniciar scheduler |

## Adapter Guide Structure

`docs/adapter-guide.md` — Guia para agregar nuevos adapters. Organizada en 4 secciones,
una por familia de adapter. Cada seccion sigue el mismo patron de 5 pasos.

### Patron de 5 pasos por adapter

**Paso 1: Implementar el ABC**

```python
# src/adapters/email/outlook_adapter.py

from src.adapters.email.base import EmailAdapter  # ABC de B3
from src.adapters.email.schemas import RawEmailMessage, SentMessageId


class OutlookEmailAdapter(EmailAdapter):
    """
    Microsoft Outlook adapter para lectura y envio de emails.

    Invariants:
      - account_id siempre corresponde a una EmailAccount activa en DB
    Return guarantees:
      - fetch_messages: lista vacia si no hay mensajes nuevos (nunca None)
      - send_draft: SentMessageId valido si el envio es exitoso
    Errors raised:
      - EmailAdapterError: fallo de red, credenciales invalidas, rate limit
      - EmailAdapterAuthError(EmailAdapterError): token expirado (subclase especifica)
    External state errors:
      - graph.microsoft.com HTTP 429: envuelto en EmailAdapterError con retry_after_seconds
    Silenced:
      - HTTP 404 en fetch de mensaje individual: mensaje borrado por el usuario — skip silencioso
    """

    def __init__(self, client_id: str, client_secret: str, tenant_id: str) -> None:
        ...

    async def fetch_messages(
        self, account_id: uuid.UUID, max_results: int
    ) -> list[RawEmailMessage]:
        ...

    async def send_draft(self, draft_id: str, body: str) -> SentMessageId:
        ...

    async def test_connection(self) -> bool:
        ...
```

**Paso 2: Registrar en configuracion**

```python
# src/core/config.py

class Settings(BaseSettings):
    EMAIL_ADAPTER: Literal["gmail", "outlook"] = "gmail"
    # outlook-specific
    OUTLOOK_CLIENT_ID: str = ""
    OUTLOOK_CLIENT_SECRET: str = ""
    OUTLOOK_TENANT_ID: str = ""
```

**Paso 3: Agregar al factory de DI**

```python
# src/api/dependencies.py

def get_email_adapter() -> EmailAdapter:
    if settings.email_adapter == "gmail":
        return GmailEmailAdapter(...)
    if settings.email_adapter == "outlook":
        return OutlookEmailAdapter(...)
    raise ConfigurationError(f"Unknown email adapter: {settings.email_adapter}")
```

**Paso 4: Actualizar .env.example**

```bash
# Email Adapter (gmail | outlook)
EMAIL_ADAPTER=gmail
# Outlook-specific (only required if EMAIL_ADAPTER=outlook)
# OUTLOOK_CLIENT_ID=
# OUTLOOK_CLIENT_SECRET=
# OUTLOOK_TENANT_ID=
```

**Paso 5: Escribir test de integracion**

```python
# tests/adapters/email/test_outlook_adapter.py

async def test_fetch_messages_returns_raw_email_messages(
    mock_graph_api: MockGraphAPI,
) -> None:
    adapter = OutlookEmailAdapter(
        client_id="test_client",
        client_secret="test_secret",
        tenant_id="test_tenant",
    )
    messages = await adapter.fetch_messages(
        account_id=uuid.uuid4(), max_results=10
    )
    assert isinstance(messages, list)
    # Alignment-chart: verificar estructura del primer elemento, no solo que la lista existe
    if messages:
        assert isinstance(messages[0], RawEmailMessage)
        assert messages[0].gmail_message_id  # o outlook_message_id
```

### Adapters documentados en la guia

1. **Email adapter** — Ejemplo: "Adding Microsoft Outlook Email Adapter". ABC: `EmailAdapter`.
   Metodos a implementar: `fetch_messages`, `send_draft`, `test_connection`.

2. **Channel adapter** — Ejemplo: "Adding Microsoft Teams Channel Adapter". ABC: `ChannelAdapter`.
   Metodos a implementar: `send_notification`, `test_connection`.

3. **CRM adapter** — Ejemplo: "Adding Salesforce CRM Adapter". ABC: `CRMAdapter`.
   Metodos a implementar: `upsert_contact`, `log_activity`, `get_contact`, `test_connection`.

4. **LLM adapter** — Ejemplo: "Adding Ollama LLM Adapter (local)". ABC: `LLMAdapter`.
   Metodos a implementar: `classify`, `generate_draft`, `test_connection`.
   Nota especial: `classify` DEBE retornar `AdapterClassificationResult` tipado —
   nunca `ModelResponse` raw de LiteLLM (D2). La extraccion y validacion del JSON de LiteLLM
   ocurre DENTRO del adapter.

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Criterios de exito (deterministicos)

### Calidad de codigo

- [ ] `ruff check src/core/logging.py src/core/correlation.py` — 0 violaciones
- [ ] `ruff format src/core/logging.py src/core/correlation.py --check` — 0 diferencias
- [ ] `mypy src/core/logging.py src/core/correlation.py` — 0 errores de tipo

### Docker Compose health checks

- [ ] `docker compose up -d` — todos los 6 servicios alcanzan estado `healthy`
  (verificable via `docker compose ps` — columna STATUS muestra `healthy` para cada servicio)
- [ ] `docker compose ps` — columna PORTS y STATUS correctas para los 6 servicios
- [ ] Dependency ordering: `api` no inicia si `db` no esta healthy — verificable via
  `docker compose up api` sin `db` corriendo: debe esperar o fallar con mensaje claro
- [ ] Health check intervals — `grep "HEALTHCHECK_INTERVAL" docker-compose.yml` —
  no contiene valores hardcodeados; usa `${HEALTHCHECK_INTERVAL:-30s}` syntax
- [ ] Imagen versions — `grep "image:" docker-compose.yml` — todas las imagenes tienen
  version exacta con patch number: `python:3.12.9-slim-bookworm`, `node:20.18-alpine3.21`,
  `postgres:16.6-alpine`, `redis:7.4-alpine`

### Structured logging

- [ ] JSON valido: cada linea de log de `api`, `worker`, `scheduler` es parseable
  como JSON — `docker compose logs api | python -c "import sys,json; [json.loads(l) for l in sys.stdin]"`
  sin errores
- [ ] Campos requeridos presentes: `timestamp`, `level`, `component`, `correlation_id`,
  `message` en cada entry — verificable via `docker compose logs api | head -5 | python -c "..."`
- [ ] Correlation IDs: procesar un email via pipeline y verificar que el mismo `correlation_id`
  aparece en logs de `api`, `worker` (classify_task), `worker` (route_task)
- [ ] PII ausente: `docker compose logs | grep -E "from_address|body_plain|subject|sender_name"`
  — resultado esperado: vacio (o solo en logs de DEBUG con marcacion explicita)
- [ ] `configure_logging()` llamado en los 3 entry points: `grep -rn "configure_logging()"
  src/api/main.py src/tasks/celery_app.py src/scheduler/main.py` — 3 matches

### .env.example completitud

- [ ] `tests/infrastructure/test_env_example.py` — 0 fallos (todas las variables de
  `Settings` sin default documentadas en `.env.example`)
- [ ] `.env.example` organizado por secciones con comentarios: Database, Redis, Auth, Gmail,
  Slack, HubSpot, LLM, Pipeline, API, Frontend, Logging, Docker
- [ ] Cada variable en `.env.example` tiene comentario de una linea con descripcion y tipo

### Documentacion

- [ ] `docs/deployment.md` existe y contiene las 6 secciones requeridas (Prerequisitos,
  Quick Start, Variables, First-time setup, Produccion, Troubleshooting)
- [ ] `docs/adapter-guide.md` existe y contiene ejemplos para las 4 familias de adapter
  con codigo funcional (no pseudocodigo)
- [ ] `bash scripts/validate-docs.sh` — 0 errores (incluyendo los nuevos archivos)

### Concept analysis

- [ ] Terminologia en `docs/deployment.md` usa terminos canonicos: "adapter" (no
  "connector" o "plugin"), "pipeline" (no "workflow" en docs tecnicas), `EmailAccount`
  (no "inbox account" en referencias a modelo de datos)
- [ ] `docs/adapter-guide.md` abre con tabla de mapping: nombre de clase → nombre de
  "integration" visible al usuario
- [ ] Seccion de troubleshooting en deployment.md usa los mismos nombres de variable
  que aparecen en `.env.example` (sin discrepancias de naming)

### Pre-mortem (Cat 8, Cat 10)

- [ ] `HEALTHCHECK_INTERVAL` configurable: `grep -n "30s\|5s\|10s" docker-compose.yml`
  — resultado esperado: solo en forma `${HEALTHCHECK_INTERVAL:-30s}`, no hardcodeado (Cat 8)
- [ ] `API_CORS_ALLOWED_ORIGINS` no tiene default en compose: `grep "CORS" docker-compose.yml`
  — debe mostrar `${API_CORS_ALLOWED_ORIGINS}` sin valor default (Cat 8)
- [ ] Todas las imagenes tienen version con patch number: `grep "image:" docker-compose.yml |
  grep -vE "[0-9]+\.[0-9]+\.[0-9]"` — resultado esperado: vacio (Cat 10)
- [ ] `docs/deployment.md` documenta la "tested combination" de versiones de imagen (Cat 10)

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**

1. `mypy src/core/logging.py src/core/correlation.py`
2. `ruff check src/core/logging.py src/core/correlation.py`
3. `pytest tests/infrastructure/test_env_example.py -v` — paridad .env.example con Settings
4. `docker compose build` — todos los servicios buildean sin errores
5. `docker compose up -d` — todos los servicios inician
6. `docker compose ps` — todos los servicios alcanzan estado `healthy` (esperar hasta 2 min)
7. `pytest tests/infrastructure/test_logging.py -v` — JSON valido, campos requeridos
8. `pytest tests/infrastructure/test_health_checks.py -v --docker` — health checks activos
9. `bash scripts/validate-docs.sh` — 0 errores (docs completos y consistentes)

**Verificaciones criticas (no automatizables):**

```bash
# Cat 10: imagenes con version exacta
grep "image:" docker-compose.yml | grep -vE "[0-9]+\.[0-9]+\.[0-9]"
# Resultado esperado: vacio

# Cat 8: CORS no hardcodeado
grep "CORS" docker-compose.yml
# Resultado esperado: ${API_CORS_ALLOWED_ORIGINS} sin valor default inline

# Cat 8: health check intervals no hardcodeados
grep -E "interval:|timeout:|retries:" docker-compose.yml | grep -v "\${"
# Resultado esperado: vacio

# configure_logging en los 3 entry points
grep -rn "configure_logging()" src/api/main.py src/tasks/celery_app.py src/scheduler/main.py
# Resultado esperado: exactamente 3 matches

# PII en logs (verificacion post-run)
docker compose up -d && sleep 30 && docker compose logs | \
  grep -E "from_address|body_plain|subject=|sender_name"
# Resultado esperado: vacio
```

**Consultas requeridas antes de implementar:**

- Consultar Sentinel para revisar el formato JSON del structured logging: confirmar que
  `PiiSanitizingFilter` como ultima linea de defensa no introduce false positives (bloquea
  logs legitimos que contienen la palabra "subject" en un contexto tecnico no-PII).
- Consultar Inquisidor para confirmar el patron de test de paridad `.env.example` vs
  `Settings`: parsear `config.py` con `ast` vs instanciar `Settings` con env vars vacias
  y capturar `ValidationError` — cual da errores mas accionables para el developer.
