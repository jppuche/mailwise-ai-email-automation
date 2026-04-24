# Bloque 5: Channel Adapter (Slack)

## Objetivo

Implementar `ChannelAdapter` ABC y `SlackAdapter` concreto con `AsyncWebClient` de slack-sdk, formateador Block Kit para `RoutingPayload`, y manejo estructurado de errores de API Slack — sin `dict[str, Any]` en ninguna firma publica.

## Dependencias

- Bloque 1 (Foundation: src layout, pyproject.toml, configuracion base, modelos SQLAlchemy)

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/adapters/channel/__init__.py` — Re-exporta `ChannelAdapter`, `SlackAdapter`, schemas publicos
- `src/adapters/channel/base.py` — `ChannelAdapter` ABC con firmas completamente tipadas (FOUNDATION.md Sec 9.3)
- `src/adapters/channel/slack.py` — `SlackAdapter` implementacion concreta usando `AsyncWebClient`
- `src/adapters/channel/schemas.py` — Pydantic models: `RoutingPayload`, `SenderInfo`, `ClassificationInfo`, `DeliveryResult`, `Destination`, `ConnectionStatus`, `ConnectionTestResult`, `ChannelCredentials`
- `src/adapters/channel/formatters.py` — `SlackBlockKitFormatter`: `RoutingPayload` → Slack blocks; operacion local pura
- `src/adapters/channel/exceptions.py` — Jerarquia de excepciones: `ChannelAdapterError`, `ChannelAuthError`, `ChannelRateLimitError`, `ChannelConnectionError`, `ChannelDeliveryError`

### Frontend (frontend-worker)

- N/A — este bloque es exclusivamente backend

### Tests (Inquisidor)

- `tests/adapters/channel/test_slack_adapter.py` — Contrato del adapter con `AsyncMock` de `AsyncWebClient`; cubre los 4 metodos del ABC
- `tests/adapters/channel/test_formatters.py` — `SlackBlockKitFormatter`: urgente/normal/low priority, campos opcionales (assigned_to=None), snippet truncacion
- `tests/adapters/channel/test_schemas.py` — Validacion Pydantic de `RoutingPayload` y `DeliveryResult`

## Skills aplicables

- **tighten-types** (CRITICO): `RoutingPayload` y todos los modelos anidados (`SenderInfo`, `ClassificationInfo`) deben ser Pydantic BaseModel — no dicts. El boundary del adapter no debe exponer ninguna estructura de datos de slack-sdk. Aplicar en planificacion (definir schemas antes del adapter) y revision (mypy estricto).
- **contract-docstrings** (CRITICO): Los 4 metodos del ABC requieren analisis de 4 preguntas. `send_notification` es especialmente critico: hay multiples modos de fallo de Slack que deben clasificarse (auth vs delivery vs rate-limit vs connection).
- **try-except** (ALTO): Todas las llamadas a `AsyncWebClient` son external-state. La construccion de Block Kit es local (condicionales). El manejo de `SlackApiError` requiere inspeccion del `response["error"]` para clasificar el tipo especifico de error.
- **pre-mortem** (MEDIO): Cat 8 (defaults: timeout de Slack, longitud de snippet). Cat 3 (stringly-typed: colores de prioridad como constantes, no strings magic).

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Contratos de metodo (contract-docstrings — 4 preguntas)

### `ChannelAdapter.connect(credentials) -> ConnectionStatus`

```
Preconditions:
  - credentials.bot_token: str no vacio con prefijo "xoxb-" (bot token)
  - bot_token debe tener scope chat:write para send_notification

Errors raised on violation:
  - ValueError si bot_token esta vacio o no tiene prefijo "xoxb-"

External state errors:
  - ChannelAuthError: token invalido o revocado (Slack error: "invalid_auth", "token_revoked")

Silenced errors:
  - Ninguno — fallo de conexion se reporta via ConnectionStatus(connected=False, error=...)
  - test_connection() usa este retorno para health checks sin lanzar
```

### `ChannelAdapter.send_notification(payload) -> DeliveryResult`

```
Preconditions:
  - payload.email_id: str no vacio
  - payload.classification.action: str en conjunto de actions validos
  - payload.destination.id: str no vacio (channel ID o user ID de Slack)
  - adapter previamente conectado (connect() retorno ConnectionStatus(connected=True))

Errors raised on violation:
  - ValueError si payload.destination.id esta vacio
  - ChannelAuthError si adapter no esta conectado

External state errors:
  - ChannelAuthError: "invalid_auth", "token_revoked", "missing_scope" en SlackApiError
  - ChannelRateLimitError: HTTP 429; incluye retry_after_seconds del header Retry-After
  - ChannelConnectionError: timeout de red, DNS failure
  - ChannelDeliveryError: "channel_not_found", "is_archived", "not_in_channel", "cant_invite_self"

Silenced errors:
  - Ninguno — todos los fallos de entrega se surfacean; el caller (task Celery) decide reintento
```

### `ChannelAdapter.test_connection() -> ConnectionTestResult`

```
Preconditions:
  - adapter debe haber llamado connect() al menos una vez

Errors raised on violation:
  - Ninguno — siempre retorna ConnectionTestResult

External state errors:
  - Capturados internamente -> ConnectionTestResult(success=False, error_detail=str(e))

Silenced errors:
  - Todos — este metodo nunca lanza; diseniado para health checks
```

### `ChannelAdapter.get_available_destinations() -> list[Destination]`

```
Preconditions:
  - adapter conectado con scope channels:read (publicos) y/o groups:read (privados)

Errors raised on violation:
  - Ninguno (lista vacia si no hay scope suficiente)

External state errors:
  - ChannelAuthError: token invalido durante la llamada
  - ChannelConnectionError: fallo de red

Silenced errors:
  - Canales privados donde el bot no es miembro: silenciosamente excluidos
  - Canales archivados: silenciosamente excluidos
  - El caller detecta ausencia de un canal esperado por inspeccion de la lista retornada
```

## Esquemas Pydantic (schemas.py)

```python
from __future__ import annotations
from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class SenderInfo(BaseModel):
    """Informacion del remitente del email. Nunca expone dict raw."""
    email: str
    name: str | None = None


class ClassificationInfo(BaseModel):
    """Resultado de clasificacion embebido en el payload de routing."""
    action: str
    type: str
    confidence: Literal["high", "low"]


class RoutingPayload(BaseModel):
    """
    Payload de routing completo (FOUNDATION.md Sec 5.4 + Appendix B.3).
    Este es el modelo canonico — Slack formatter y otros channels lo consumen.
    """
    email_id: str
    subject: str
    sender: SenderInfo
    classification: ClassificationInfo
    priority: Literal["urgent", "normal", "low"]
    snippet: str                  # primeros CHANNEL_SNIPPET_LENGTH chars del body
    dashboard_link: str           # deep link al email en el dashboard
    assigned_to: str | None = None
    timestamp: datetime


class Destination(BaseModel):
    """Canal o usuario de destino en el channel adapter."""
    id: str           # Slack channel ID (C...) o user ID (U...)
    name: str         # nombre legible (#general, @john)
    type: Literal["channel", "dm", "group"]


class ChannelCredentials(BaseModel):
    """Credenciales para conectar al channel adapter."""
    bot_token: str    # xoxb-... para Slack


class ConnectionStatus(BaseModel):
    connected: bool
    workspace_name: str | None = None
    bot_user_id: str | None = None
    error: str | None = None


class ConnectionTestResult(BaseModel):
    success: bool
    workspace_name: str | None = None
    latency_ms: int
    error_detail: str | None = None


class DeliveryResult(BaseModel):
    """Resultado de entrega de notificacion."""
    success: bool
    message_ts: str | None = None  # Slack message timestamp (para thread replies)
    channel_id: str | None = None
    error_detail: str | None = None
```

## Formateador Block Kit (formatters.py)

### Constantes de color por prioridad

```python
PRIORITY_COLORS: dict[str, str] = {
    "urgent": "#E01E5A",   # rojo Slack
    "normal": "#36C5F0",   # azul Slack
    "low":    "#9BA3AF",   # gris
}

PRIORITY_EMOJIS: dict[str, str] = {
    "urgent": ":red_circle:",
    "normal": ":large_blue_circle:",
    "low":    ":white_circle:",
}
```

Los colores y emojis son constantes en el modulo — no magic strings dispersos en el formatter.

### Estructura Block Kit esperada

```json
[
  {
    "type": "header",
    "text": {
      "type": "plain_text",
      "text": ":red_circle: [URGENT] Subject line here"
    }
  },
  {
    "type": "section",
    "fields": [
      {"type": "mrkdwn", "text": "*From:*\nJohn Doe <john@example.com>"},
      {"type": "mrkdwn", "text": "*Classification:*\nreply / support"},
      {"type": "mrkdwn", "text": "*Priority:*\nUrgent"},
      {"type": "mrkdwn", "text": "*Assigned to:*\n@jane"}
    ]
  },
  {
    "type": "context",
    "elements": [
      {"type": "mrkdwn", "text": "Email snippet here (truncated to 150 chars)..."}
    ]
  },
  {
    "type": "actions",
    "elements": [
      {
        "type": "button",
        "text": {"type": "plain_text", "text": "View in Dashboard"},
        "url": "https://dashboard/emails/abc123",
        "style": "primary"
      }
    ]
  }
]
```

### Invariantes del formatter (operacion local pura)

- El formatter NUNCA hace I/O ni llama a Slack API — entrada `RoutingPayload`, salida `list[dict]`
- Si `assigned_to` es `None`, el campo "Assigned to" muestra "Unassigned"
- Snippet truncado a `CHANNEL_SNIPPET_LENGTH` chars (default 150, configurable via env)
- Subject truncado a 100 chars para el header (limite de Slack `plain_text`)
- Formato de sender: `{name} <{email}>` si `name` disponible, solo `{email}` si no
- Operacion sin try/except — si `RoutingPayload` es invalido, Pydantic ya fallo antes

## Defaults load-bearing (Cat 8 pre-mortem)

| Default | Valor | Env Var | Consecuencia si incorrecto |
|---------|-------|---------|---------------------------|
| Snippet length en notificacion | `150` chars | `CHANNEL_SNIPPET_LENGTH` | Demasiado largo: mensaje Slack visualmente sobrecargado |
| Subject truncation | `100` chars | `CHANNEL_SUBJECT_MAX_LENGTH` | Limite hard de Slack en `plain_text` header |
| Slack API timeout | `10` s | `CHANNEL_SLACK_TIMEOUT_SECONDS` | Demasiado bajo: falsos timeouts en red lenta |
| Max destinations page size | `200` | `CHANNEL_DESTINATIONS_PAGE_SIZE` | Limite de Slack API en `conversations.list` es 200 |

## Patron de try/except en slack.py (directiva D7)

```python
async def send_notification(self, payload: RoutingPayload) -> DeliveryResult:
    # Validacion de preconditions (local — condicionales, no try/except)
    if not payload.destination.id:
        raise ValueError("destination.id must not be empty")
    if not self._connected:
        raise ChannelAuthError("Adapter not connected — call connect() first")

    # Construccion de bloques (local — sin try/except)
    blocks = self._formatter.build_blocks(payload)

    # Llamada externa — try/except con tipos especificos (directiva D7)
    try:
        response = await self._client.chat_postMessage(
            channel=payload.destination.id,
            blocks=blocks,
            text=f"[{payload.priority.upper()}] {payload.subject}",  # fallback para notifs
        )
    except SlackApiError as exc:
        error_code = exc.response.get("error", "unknown")
        if error_code in {"invalid_auth", "token_revoked", "missing_scope"}:
            raise ChannelAuthError(f"Slack auth error: {error_code}") from exc
        if error_code in {"channel_not_found", "is_archived", "not_in_channel"}:
            raise ChannelDeliveryError(f"Slack delivery error: {error_code}") from exc
        raise ChannelDeliveryError(f"Slack API error: {error_code}") from exc
    except asyncio.TimeoutError as exc:
        raise ChannelConnectionError("Slack API timeout") from exc
    except aiohttp.ClientConnectionError as exc:
        raise ChannelConnectionError(f"Network error: {exc}") from exc

    return DeliveryResult(
        success=True,
        message_ts=response["ts"],
        channel_id=response["channel"],
    )
```

**Clasificacion de errores `SlackApiError`:**

| Slack error code | Excepcion del adapter |
|------------------|-----------------------|
| `invalid_auth` | `ChannelAuthError` |
| `token_revoked` | `ChannelAuthError` |
| `missing_scope` | `ChannelAuthError` |
| `channel_not_found` | `ChannelDeliveryError` |
| `is_archived` | `ChannelDeliveryError` |
| `not_in_channel` | `ChannelDeliveryError` |
| `cant_invite_self` | `ChannelDeliveryError` |
| cualquier otro | `ChannelDeliveryError` (mensaje incluye codigo) |

HTTP 429 es manejado por `slack-sdk` internamente (reintentos con backoff). Si el SDK agota reintentos, lanza `SlackApiError` con `response.status_code == 429` — capturado y relanzado como `ChannelRateLimitError`.

## Jerarquia de excepciones (exceptions.py)

```python
class ChannelAdapterError(Exception):
    """Base para todos los errores del channel adapter."""

class ChannelAuthError(ChannelAdapterError):
    """Token invalido, revocado, o sin scope suficiente."""

class ChannelRateLimitError(ChannelAdapterError):
    """HTTP 429 de Slack. retry_after_seconds del header Retry-After."""
    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds

class ChannelConnectionError(ChannelAdapterError):
    """Fallo de red, timeout, DNS."""

class ChannelDeliveryError(ChannelAdapterError):
    """Canal no encontrado, archivado, bot no en canal, etc."""
```

## Estructura de archivos esperada

```
src/adapters/channel/
├── __init__.py           # re-exporta ChannelAdapter, SlackAdapter, schemas publicos
├── base.py               # ChannelAdapter ABC
├── slack.py              # SlackAdapter (AsyncWebClient, manejo de SlackApiError)
├── schemas.py            # RoutingPayload, DeliveryResult, Destination, etc.
├── formatters.py         # SlackBlockKitFormatter (pura, sin I/O)
└── exceptions.py         # ChannelAdapterError y subclases
```

## Criterios de exito (deterministicos)

- [ ] `ChannelAdapter` ABC importable; contiene exactamente 4 metodos con firmas completamente tipadas
- [ ] `SlackAdapter` implementa todos los metodos del ABC sin `dict[str, Any]` en ninguna firma publica
- [ ] `RoutingPayload`, `SenderInfo`, `ClassificationInfo` son Pydantic BaseModel — no dicts
- [ ] `SlackBlockKitFormatter.build_blocks(payload)` produce estructura Block Kit valida para los 3 niveles de prioridad
- [ ] Color-coding de prioridad: urgent=#E01E5A, normal=#36C5F0, low=#9BA3AF
- [ ] Snippet truncado a `CHANNEL_SNIPPET_LENGTH` (default 150); subject truncado a 100 chars
- [ ] `assigned_to=None` produce "Unassigned" en el bloque — sin KeyError ni campo faltante
- [ ] `SlackApiError` con codigos de auth mapeados a `ChannelAuthError`
- [ ] `SlackApiError` con codigos de delivery mapeados a `ChannelDeliveryError`
- [ ] Contract-docstrings presentes en los 4 metodos del ABC (formato 4 preguntas)
- [ ] Jerarquia de excepciones: `ChannelAdapterError` base + 4 subclases especificas
- [ ] Defaults de snippet/subject/timeout cargados desde env vars; ninguno hardcodeado en formatter o adapter
- [ ] `ruff check src/adapters/channel/` — 0 violaciones
- [ ] `mypy src/adapters/channel/` — 0 errores
- [ ] Todos los tests de adapter pasan con `AsyncMock` de `AsyncWebClient` (sin llamadas a Slack real)
- [ ] Typecheck: 0 errores en modo estricto mypy para este modulo

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**
1. `mypy src/adapters/channel/` — si falla, corregir tipos antes de cualquier otro gate
2. `ruff check src/adapters/channel/ && ruff format --check src/adapters/channel/` — si falla, corregir lint
3. `pytest tests/adapters/channel/test_formatters.py -v` — 3 prioridades + assigned_to=None + truncacion
4. `pytest tests/adapters/channel/test_slack_adapter.py -v` — contrato completo con mocks
5. `pytest tests/adapters/channel/ -v` — suite completa del modulo

**Verificacion critica (no automatizable):** Revisar manualmente que la tabla de mapeo `SlackApiError` → excepcion del adapter este completa. Agregar nuevos codigos de error de Slack a la tabla cuando se descubran en testing de integracion. Inquisidor ejecuta revision via tighten-types antes de marcar COMPLETO.
