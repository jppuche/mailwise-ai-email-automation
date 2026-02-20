# Bloque 0: Project Scaffolding

## Objetivo

Establecer el paquete Python, Docker Compose (6 servicios), configuracion de entorno, toolchain de desarrollo, y el utilitario core de sanitizacion de texto.

## Dependencias

Ninguna — es el primer bloque.

## Archivos a crear/modificar

### Backend (backend-worker)

- `pyproject.toml` — Configuracion del paquete Python con todas las dependencias (FastAPI, SQLAlchemy, Celery, LiteLLM, google-api-python-client, slack-sdk, hubspot-api-client, python-jose, passlib, ruff, mypy, pytest stack). Config de ruff (line-length=100, target-version=py312, select=E,W,F,I,UP,B,SIM) y mypy (strict=true, plugins=pydantic.mypy).
- `Dockerfile` — Imagen Python 3.12-slim. Multi-stage: builder (instala deps) + runtime (copia src). Non-root user `app`. WORKDIR /app. Instala desde pyproject.toml via `pip install -e .`.
- `.env.example` — Todas las variables de entorno con valores por defecto documentados y comentarios explicativos. Cubre: DB, Redis, JWT, LLM, Gmail OAuth, Slack, HubSpot, todos los defaults de Apendice C.
- `src/__init__.py` — Vacio (marca el paquete).
- `src/core/__init__.py` — Vacio.
- `src/core/config.py` — `Settings` via Pydantic `BaseSettings`. Todos los defaults load-bearing de FOUNDATION.md Apendice C configurables via env. Ver seccion "Load-Bearing Defaults" abajo.
- `src/core/sanitizer.py` — `sanitize_email_body()` retorna `SanitizedText`. HTML stripping, remocion de Unicode invisible, truncacion. Ver seccion "Sanitizer Contract" abajo.
- `src/core/logging.py` — Structured logging (structlog). PII policy: referencias de email solo por ID, nunca subject/sender en logs.
- `src/adapters/__init__.py` — Vacio.
- `src/adapters/email/__init__.py` — Vacio.
- `src/adapters/channel/__init__.py` — Vacio.
- `src/adapters/crm/__init__.py` — Vacio.
- `src/adapters/llm/__init__.py` — Vacio.
- `src/services/__init__.py` — Vacio.
- `src/api/__init__.py` — Vacio.
- `src/models/__init__.py` — Vacio.
- `src/tasks/__init__.py` — Vacio.

### Frontend (frontend-worker)

- `Dockerfile.frontend` — Imagen Node 20-alpine. Dev stage: `npm run dev` con Vite HMR. Prod stage: `npm run build` + Nginx para servir dist/. WORKDIR /app.
- `frontend/` — Directorio raiz del proyecto React+Vite+TypeScript. Inicializado con `npm create vite@latest`. Incluye `tsconfig.json`, `vite.config.ts`, `package.json`.

### Infraestructura

- `docker-compose.yml` — 6 servicios (ver seccion "Docker Compose" abajo). Perfil `prod` por defecto.
- `docker-compose.dev.yml` — Overrides de desarrollo: hot reload en api/worker via volume mount de `./src`, DEBUG=true, Vite dev server con HMR, puertos expuestos para debugging.

### Tests (Inquisidor)

- `tests/__init__.py` — Vacio.
- `tests/core/__init__.py` — Vacio.
- `tests/core/test_config.py` — Verifica que Settings carga valores desde env, que defaults son correctos, que variables requeridas sin valor lanzan error de validacion.
- `tests/core/test_sanitizer.py` — Tests parametrizados: stripping HTML, remocion de cada rango Unicode invisible, truncacion en exactamente `max_body_length` chars, preservacion de texto limpio, tipo de retorno es `SanitizedText` (isinstance check via NewType).

## Skills aplicables

- **pre-mortem (Cat 8 — load-bearing defaults):** Todos los defaults de Apendice C deben ser configurables via env. Hardcodear `polling_interval=300` o `batch_size=50` en codigo es una bomba de tiempo operacional. Cada default tiene su env var nombrada, valor, y consecuencia de mala configuracion documentada en config.py.
- **tighten-types:** `SanitizedText = NewType("SanitizedText", str)` en el boundary del sanitizer crea un tipo de marca que mypy verifica en compile-time. `Settings` usa `BaseSettings` (Pydantic) — es el boundary del sistema con el entorno externo, requiere modelo tipado, no `dict[str, Any]`.
- **concept-analysis:** Este bloque establece el glosario de dominio canonical. Los nombres definidos aqui propagan a todos los bloques subsecuentes. Inconsistencia en nomenclatura aqui (ej. usar `message` en vez de `email`, o `tag` en vez de `category`) crea deuda conceptual en 20 bloques.
- **try-except (D8):** La inicializacion de `Settings` (lectura de env) es external-state — debe fallar explicita y claramente si variables requeridas faltan, no silenciosamente con `None`. Pydantic `BaseSettings` maneja esto via `ValidationError`, que es el comportamiento correcto.

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

| Tool | Tier | Status | How it applies |
|------|------|--------|----------------|
| mcp-scan | 1 | Installed | Gate de seguridad para cualquier dependencia externa agregada post-B0 — no aplica en este bloque de scaffolding |

## Domain Glossary (concept-analysis)

Esta seccion define nombres canonicos que TODOS los agentes y bloques subsecuentes deben usar. Inconsistencia es deuda. Si un bloque usa un nombre diferente, es un bug de nomenclatura.

| Concepto | Nombre Canonical | Nombre Prohibido | Notas |
|----------|-----------------|-----------------|-------|
| El email que entra al sistema | `Email` | `Message`, `Mail`, `EmailMessage` | Modelo SQLAlchemy, clase Pydantic |
| El acto de clasificar | `classification` | `tagging`, `labeling`, `categorization` | Proceso, no resultado |
| El resultado de clasificar | `ClassificationResult` | `Label`, `Tag`, `ClassificationOutput` | Dataclass tipado del adapter LLM |
| Clasificacion de Capa 1 (urgencia/accion) | `action_category` / `ActionCategory` | `layer1`, `action_type`, `primary_category` | FK en ClassificationResult |
| Clasificacion de Capa 2 (tipo de email) | `type_category` / `TypeCategory` | `layer2`, `email_type`, `secondary_category` | FK en ClassificationResult |
| Modulo de integracion externa | `Adapter` | `Integration`, `Connector`, `Client` | Patron Adapter (Sec 9) |
| Destino de routing (Slack, email, etc.) | `Channel` | `Destination`, `Target`, `Sink` | `ChannelAdapter` es la interfaz |
| Regla de enrutamiento | `RoutingRule` | `Rule`, `Policy`, `Filter` | Stored en DB |
| Limpieza de contenido de email | `sanitization` | `cleaning`, `preprocessing`, `normalization` | Proceso del `sanitizer.py` |
| Obtencion de emails del proveedor | `ingestion` | `fetching`, `pulling`, `importing` | Tarea Celery de B7 |
| Enrutamiento a canal destino | `routing` | `dispatching`, `forwarding`, `sending` | Tarea Celery de B9 |
| Texto sanitizado (tipo de marca) | `SanitizedText` | `CleanText`, `SafeStr`, `SanitizedStr` | `NewType("SanitizedText", str)` |
| Borrador de respuesta | `Draft` | `Reply`, `Response`, `Suggestion` | Modelo SQLAlchemy de B13 |
| Ciclo de polling de Gmail | `ingestion_cycle` | `poll_cycle`, `fetch_cycle`, `sync_cycle` | 5-min interval del scheduler |

## Load-Bearing Defaults (pre-mortem Cat 8)

Todos los siguientes defaults DEBEN ser configurables via env var. Hardcodear cualquiera de estos valores en logica de negocio es una violacion de D14.

| Default | Env Var | Valor | Consecuencia si mal configurado |
|---------|---------|-------|--------------------------------|
| Polling interval | `POLLING_INTERVAL_SECONDS` | `300` (5 min) | Demasiado bajo: rate limit Gmail API. Demasiado alto: emails llegando tarde, SLA de routing violado. |
| Batch size de ingestion | `INGESTION_BATCH_SIZE` | `50` | Demasiado alto: timeout en LLM classification por volumen. Demasiado bajo: throughput insuficiente. |
| Longitud maxima de body | `MAX_BODY_LENGTH` | `4000` | Demasiado bajo: LLM pierde contexto critico. Demasiado alto: costos LLM excesivos, latencia. |
| Longitud de snippet | `SNIPPET_LENGTH` | `200` | Afecta UI previews y logs. Demasiado largo: UI overflow. |
| JWT TTL (access token) | `JWT_ACCESS_TTL_MINUTES` | `15` | Demasiado largo: ventana de ataque si token comprometido. Demasiado corto: UX degradada por re-auth frecuente. |
| JWT TTL (refresh token) | `JWT_REFRESH_TTL_DAYS` | `7` | Afecta persistencia de sesion. |
| bcrypt rounds | `BCRYPT_ROUNDS` | `12` | Demasiado bajo: passwords brute-forceable. Demasiado alto: login lento (>1s). |
| LLM temperature (clasificacion) | `LLM_TEMPERATURE_CLASSIFY` | `0.1` | Temperatura alta: clasificaciones inconsistentes entre runs identicos. |
| LLM temperature (drafts) | `LLM_TEMPERATURE_DRAFT` | `0.7` | Temperatura baja: drafts roboticos y repetitivos. |
| Retencion de datos | `DATA_RETENTION_DAYS` | `90` | Afecta compliance y costos de storage. |
| Max reintentos de tarea Celery | `CELERY_MAX_RETRIES` | `3` | Demasiado bajo: fallas transitorias permanentes. Demasiado alto: colas saturadas. |
| Backoff base (segundos) | `CELERY_BACKOFF_BASE` | `60` | Backoff demasiado agresivo puede saturar servicios externos en recovery. |
| Modelo LLM para clasificacion | `LLM_MODEL_CLASSIFY` | `gpt-4o-mini` | Modelo mas caro: costos prohibitivos a escala. Modelo incapaz: precision de clasificacion cae. |
| Modelo LLM para drafts | `LLM_MODEL_DRAFT` | `gpt-4o` | Modelo muy barato: calidad de drafts inaceptable. |

Implementacion en `src/core/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    database_url: str = Field(..., description="PostgreSQL connection URL (async)")
    database_url_sync: str = Field(..., description="PostgreSQL connection URL (sync, for Celery)")

    # Redis
    redis_url: str = Field(default="redis://redis:6379/0")

    # JWT
    jwt_secret_key: str = Field(..., description="Secret key for JWT signing — MUST be set in production")
    jwt_algorithm: str = Field(default="HS256")
    jwt_access_ttl_minutes: int = Field(default=15)
    jwt_refresh_ttl_days: int = Field(default=7)

    # Security
    bcrypt_rounds: int = Field(default=12)
    cors_origins: list[str] = Field(default=["http://localhost:5173"])

    # Pipeline defaults (Cat 8 — all configurable)
    polling_interval_seconds: int = Field(default=300)
    ingestion_batch_size: int = Field(default=50)
    max_body_length: int = Field(default=4000)
    snippet_length: int = Field(default=200)
    data_retention_days: int = Field(default=90)

    # LLM
    llm_model_classify: str = Field(default="gpt-4o-mini")
    llm_model_draft: str = Field(default="gpt-4o")
    llm_temperature_classify: float = Field(default=0.1)
    llm_temperature_draft: float = Field(default=0.7)
    openai_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")

    # Celery
    celery_max_retries: int = Field(default=3)
    celery_backoff_base: int = Field(default=60)

    # Gmail OAuth
    gmail_client_id: str = Field(default="")
    gmail_client_secret: str = Field(default="")
    gmail_redirect_uri: str = Field(default="http://localhost:8000/api/v1/auth/gmail/callback")

    # Slack
    slack_bot_token: str = Field(default="")
    slack_signing_secret: str = Field(default="")

    # HubSpot
    hubspot_access_token: str = Field(default="")


def get_settings() -> Settings:
    return Settings()
```

## Sanitizer Contract (tighten-types + try-except D8)

`src/core/sanitizer.py` implementa:

```python
from typing import NewType

SanitizedText = NewType("SanitizedText", str)

def sanitize_email_body(
    raw_body: str,
    *,
    max_length: int,
    strip_html: bool = True,
) -> SanitizedText:
    """
    Invariants (input):
      - raw_body: str, puede ser vacio, puede contener HTML, puede contener Unicode invisible.
      - max_length: int positivo. Definido por Settings.max_body_length.

    Guarantees (output):
      - Retorna SanitizedText (str con tipo de marca).
      - Sin tags HTML si strip_html=True.
      - Sin caracteres Unicode invisibles de los rangos: U+200B-U+200F, U+2060-U+2064,
        U+E0000-U+E007F, U+FEFF (BOM), U+00AD (soft hyphen).
      - Longitud <= max_length caracteres.
      - Nunca raises — computacion local pura (D8: condicionales, no try/except).

    Errors: Ninguno — si raw_body es invalido, retorna SanitizedText("").
    Silenced: Errores de parsing HTML se silencian; se retorna texto plano del contenido.
    State transitions: Ninguna — funcion pura sin side effects.
    """
```

Implementacion usa `html.parser` (stdlib, no dependencias externas). Strip via `html.parser.HTMLParser` subclasificado. Unicode removal via `str.translate()` con tabla de remocion pre-compilada (mas eficiente que regex para rangos fijos).

**D8 aplicado:** Nunca `try/except` dentro del sanitizer. Si el HTML esta malformado, el parser de stdlib continua best-effort. Si `raw_body` es `None`, el caller debe pasarlo como `""` (la validacion ocurre en el modelo Pydantic de entrada, antes de llegar al sanitizer).

## Docker Compose Architecture

`docker-compose.yml` define 6 servicios:

| Servicio | Imagen | Puertos | Health check | Dependencias |
|----------|--------|---------|--------------|--------------|
| `db` | `postgres:16-alpine` | 5432 (interno) | `pg_isready -U ${POSTGRES_USER}` | — |
| `redis` | `redis:7-alpine` | 6379 (interno) | `redis-cli ping` | — |
| `api` | `./Dockerfile` | `8000:8000` | `GET /health` 200 OK | db, redis |
| `worker` | `./Dockerfile` | — | `celery -A src.tasks inspect ping` | db, redis |
| `scheduler` | `./Dockerfile` | — | `pgrep -f apscheduler` | db, redis, api |
| `frontend` | `./Dockerfile.frontend` | `5173:5173` (dev) / `80:80` (prod) | `wget -q --spider http://localhost/` | api |

Todos los servicios comparten network `mailwise-net`. Volumes: `postgres_data`, `redis_data`.

Variables de entorno inyectadas via `env_file: .env`. Secrets (API keys) nunca en `docker-compose.yml` directamente — siempre via `.env` (gitignored).

`docker-compose.dev.yml` overrides:
- `api`: agrega `volumes: [./src:/app/src]` para hot reload, `command: uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000`
- `worker`: agrega volume mount, `command: celery -A src.tasks.celery_app worker --loglevel=debug`
- `scheduler`: agrega volume mount
- `frontend`: expone puerto 5173, `command: npm run dev -- --host`

## Criterios de exito (deterministicos)

- [ ] Typecheck: `mypy src/` reporta 0 errores
- [ ] Lint: `ruff check .` reporta 0 violaciones
- [ ] Format: `ruff format --check .` sin diffs
- [ ] Tests: `pytest tests/core/` todos pasan
- [ ] Build: `docker compose build` exitoso para todos los servicios
- [ ] Startup: `docker compose up -d` levanta todos los servicios; `docker compose ps` muestra todos `healthy` o `running`
- [ ] Import de config: `python -c "from src.core.config import Settings; s = Settings()"` funciona con `.env` presente
- [ ] Import de sanitizer: `python -c "from src.core.sanitizer import sanitize_email_body, SanitizedText"` funciona
- [ ] Sanitizer HTML: `sanitize_email_body("<b>hello</b>", max_length=4000)` retorna `"hello"` (sin tags)
- [ ] Sanitizer Unicode: input con U+200B retorna texto sin ese caracter
- [ ] Sanitizer truncacion: input de 5000 chars con `max_length=4000` retorna exactamente 4000 chars
- [ ] Sanitizer tipo: retorno pasa `isinstance`-equivalent check; mypy verifica que `str` raw no se puede asignar donde se espera `SanitizedText` sin cast
- [ ] Load-bearing defaults: todos los 14 defaults de la tabla anterior tienen env var documentada en `.env.example`
- [ ] Domain Glossary: seccion presente en este spec, consumida y consistente con nombres usados en archivos `src/`
- [ ] PII policy: `src/core/logging.py` nunca loguea subject, sender_email, o body — solo email_id

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Notas de iteracion:**
- Si `docker compose build` falla por dependencia no disponible en PyPI: verificar nombre exacto en pyproject.toml (ej. `pydantic-settings` no `pydantic_settings`).
- Si mypy falla en `NewType`: verificar que la asignacion usa `SanitizedText(str_value)` no un cast implicito.
- Si `docker compose up` falla en healthcheck: verificar que `pg_isready` esta instalado en imagen postgres (viene incluido en `postgres:16-alpine`).
