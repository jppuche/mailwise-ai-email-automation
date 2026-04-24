# Bloque 6: CRM Adapter (HubSpot)

## Objetivo

Implementar `CRMAdapter` ABC y `HubSpotAdapter` concreto con las 7 operaciones del contrato
FOUNDATION.md Sec 9.4 — sin `dict[str, Any]` en ninguna firma publica, con modelos Pydantic para
todos los datos que cruzan el boundary del adapter, y manejo estructurado de errores de la API
HubSpot que cubre auth, rate-limiting, duplicados y field mapping errors. El adapter MCP de
HubSpot fue diferido — esta implementacion via `hubspot-api-client` SDK es la ruta definitiva.

## Dependencias

- Bloque 1 (Database + Models): modelos SQLAlchemy definidos; `EmailState` disponible para
  entender que datos produce el pipeline antes de llegar al CRM adapter.

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/adapters/crm/__init__.py` — Re-exporta `CRMAdapter`, `HubSpotAdapter`, y todos los
  schemas y excepciones publicos.
- `src/adapters/crm/base.py` — `CRMAdapter` ABC con 7 metodos abstractos. Contract-docstrings
  en formato 4-preguntas en cada metodo. Firmas completamente tipadas sin `dict[str, Any]`.
- `src/adapters/crm/hubspot.py` — `HubSpotAdapter(CRMAdapter)` implementacion concreta usando
  `hubspot-api-client`. Toda extraccion de respuestas SDK ocurre aqui; los objetos del SDK
  nunca cruzan el boundary.
- `src/adapters/crm/schemas.py` — Pydantic models: `Contact`, `CreateContactData`,
  `ActivityData`, `ActivityId`, `CreateLeadData`, `LeadId`, `CRMCredentials`,
  `ConnectionStatus`, `ConnectionTestResult`.
- `src/adapters/crm/exceptions.py` — Jerarquia de excepciones: `CRMAdapterError`,
  `CRMAuthError`, `CRMRateLimitError`, `CRMConnectionError`, `DuplicateContactError`,
  `ContactNotFoundError`, `FieldNotFoundError`.
- `src/core/config.py` — Modificar: agregar settings de HubSpot (`HUBSPOT_ACCESS_TOKEN`,
  `HUBSPOT_RATE_LIMIT_PER_10S`, `HUBSPOT_ACTIVITY_SNIPPET_LENGTH`,
  `HUBSPOT_AUTO_CREATE_CONTACTS`). Defaults configurables via env.

### Frontend (frontend-worker)

- Ninguno en este bloque — el CRM adapter es backend puro. La configuracion de CRM connection
  se implementa en el bloque de settings UI.

### Tests (Inquisidor)

- `tests/adapters/crm/test_hubspot_adapter.py` — Contrato del adapter con mocks de
  `hubspot-api-client`; cubre los 7 metodos del ABC. Nunca llama a la API real de HubSpot.
- `tests/adapters/crm/test_schemas.py` — Validacion Pydantic de `Contact`, `CreateContactData`,
  `ActivityData`; verifica que campos requeridos fallan correctamente y opcionales tienen defaults.
- `tests/adapters/crm/test_exceptions.py` — Verifica jerarquia: `CRMRateLimitError` es
  `CRMAdapterError`; `retry_after_seconds` accesible como atributo.

## Skills aplicables

- **tighten-types** (CRITICO): Los objetos del SDK `hubspot-api-client` (`SimplePublicObject`,
  `ApiException`) nunca salen de `hubspot.py`. El boundary del adapter expone solo `Contact`,
  `ActivityId`, `LeadId` etc. — Pydantic BaseModel o type aliases. Aplicar en planificacion
  (schemas primero) y en revision (mypy estricto, sin `Any` inference).
- **contract-docstrings** (CRITICO): Este adapter tiene el mayor numero de metodos (7) y el
  comportamiento silenciado mas variado: `lookup_contact` silencia ambiguedad, `update_field`
  silencia `FieldNotFoundError`. Cada uno requiere las 4 preguntas completas.
- **try-except** (ALTO): Toda llamada al SDK de HubSpot es external-state (try/except con
  tipos especificos). El mapeo de objetos SDK a Pydantic es local computation (condicionales).
  La clasificacion de `ApiException` por `status` es local (condicional sobre `.status`, no
  try/except adicional).
- **pre-mortem** (MEDIO): Cat 8 (rate limit de free tier: 100 req/10s; snippet_length 200;
  auto_create_contacts flag). Cat 10 (pin de `hubspot-api-client`). Cat 3 (contact_id como
  str — HubSpot usa IDs numericos como strings; no mezclar con email como identificador).

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.
HubSpot MCP fue diferido (DECISIONS.md): full adapter via SDK es el camino definitivo.

## Contratos de metodo (contract-docstrings — 4 preguntas)

### `CRMAdapter.connect(credentials: CRMCredentials) -> ConnectionStatus`

```
Preconditions:
  - credentials.access_token: str no vacio (Private App Token de HubSpot)
  - El token debe tener scopes: crm.objects.contacts.read, crm.objects.contacts.write

Errors raised on violation:
  - ValueError si access_token esta vacio

External state errors:
  - CRMAuthError: token invalido o revocado (HTTP 401)
  - CRMConnectionError: HubSpot API inalcanzable (red, DNS, timeout)

Silenced errors:
  - Ninguno — fallo de conexion se reporta via ConnectionStatus(connected=False, error=...)
  - test_connection() usa este retorno para health checks sin lanzar
```

### `CRMAdapter.lookup_contact(email: str) -> Contact | None`

```
Preconditions:
  - email: str no vacio con formato valido (contiene "@")
  - adapter previamente conectado

Errors raised on violation:
  - ValueError si email esta vacio o no tiene formato valido

External state errors:
  - CRMAuthError: token invalido durante la llamada (HTTP 401)
  - CRMRateLimitError: HTTP 429; incluye retry_after_seconds si el header esta disponible
  - CRMConnectionError: timeout de red, DNS failure

Silenced errors:
  - Multiples matches: usar el contacto mas reciente (por createdate), loggear ambiguedad
    con contact_count. El caller no detecta ambiguedad — es una decision interna del adapter.
  - Retorna None si no se encuentra el contacto — no es un error. El caller distingue
    "no encontrado" (None) de "error de API" (excepcion).
```

### `CRMAdapter.create_contact(data: CreateContactData) -> Contact`

```
Preconditions:
  - data.email: str no vacio con formato valido
  - data.first_name y data.last_name: opcionales pero al menos uno recomendado (no forzado)
  - adapter conectado

Errors raised on violation:
  - ValueError si data.email esta vacio o sin formato

External state errors:
  - CRMAuthError: token invalido (HTTP 401)
  - CRMRateLimitError: HTTP 429
  - DuplicateContactError: HubSpot retorna HTTP 409 (contacto con ese email ya existe)
  - CRMConnectionError: fallo de red

Silenced errors:
  - Ninguno — todos los fallos se surfacean al caller (servicio decide: usar existente o abortar)
```

### `CRMAdapter.log_activity(contact_id: str, activity: ActivityData) -> ActivityId`

```
Preconditions:
  - contact_id: str no vacio (ID numerico de HubSpot como string, e.g. "12345")
  - activity.subject: str no vacio
  - activity.timestamp: datetime timezone-aware
  - activity.snippet: str truncado a HUBSPOT_ACTIVITY_SNIPPET_LENGTH antes de llamar
  - adapter conectado

Errors raised on violation:
  - ValueError si contact_id esta vacio
  - ValueError si activity.subject esta vacio
  - ValueError si activity.timestamp no es timezone-aware

External state errors:
  - CRMAuthError: token invalido (HTTP 401)
  - CRMRateLimitError: HTTP 429
  - ContactNotFoundError: contact_id no existe en HubSpot (HTTP 404)
  - CRMConnectionError: fallo de red

Silenced errors:
  - Ninguno — fallo en log_activity se surfacea; la tarea Celery decide reintento
```

### `CRMAdapter.create_lead(data: CreateLeadData) -> LeadId`

```
Preconditions:
  - data.contact_id: str no vacio (referencia valida a contacto existente)
  - data.summary: str no vacio
  - data.source: str no vacio
  - adapter conectado

Errors raised on violation:
  - ValueError si contact_id o summary o source estan vacios

External state errors:
  - CRMAuthError: token invalido (HTTP 401)
  - CRMRateLimitError: HTTP 429
  - ContactNotFoundError: contact_id referenciado no existe (HTTP 404)
  - CRMConnectionError: fallo de red

Silenced errors:
  - Ninguno — creacion de lead fallida se surfacea
```

### `CRMAdapter.update_field(contact_id: str, field: str, value: str) -> None`

```
Preconditions:
  - contact_id: str no vacio
  - field: str no vacio (nombre de propiedad en HubSpot)
  - value: str (puede ser vacio — borrar un campo es una operacion valida)
  - adapter conectado

Errors raised on violation:
  - ValueError si contact_id o field estan vacios

External state errors:
  - CRMAuthError: token invalido (HTTP 401)
  - CRMRateLimitError: HTTP 429
  - ContactNotFoundError: contact_id no existe (HTTP 404)
  - CRMConnectionError: fallo de red

Silenced errors:
  - FieldNotFoundError: la propiedad `field` no existe en el schema de HubSpot (HTTP 400
    con codigo PROPERTY_DOESNT_EXIST). Se loggea con field_name y contact_id — no se relanza.
    El caller continua con otros campos (FOUNDATION.md Sec 6.4: field mapping error → skip).
    El caller detecta la ausencia de efecto verificando el campo despues si lo necesita.
```

### `CRMAdapter.test_connection() -> ConnectionTestResult`

```
Preconditions:
  - adapter inicializado con credenciales (connect() no requiere haberse completado con exito)

Errors raised on violation:
  - Ninguno — siempre retorna ConnectionTestResult

External state errors:
  - Capturados internamente -> ConnectionTestResult(success=False, error_detail=str(e))

Silenced errors:
  - Todos — este metodo nunca lanza; disenado para health checks y UI de configuracion
```

## Esquemas Pydantic (schemas.py)

```python
from __future__ import annotations
from datetime import datetime
from typing import NewType
from pydantic import BaseModel, field_validator

# Type aliases para IDs — distincion semantica, no str desnudo
ActivityId = NewType("ActivityId", str)
LeadId = NewType("LeadId", str)


class CRMCredentials(BaseModel):
    """Credenciales para conectar al CRM adapter."""
    access_token: str  # HubSpot Private App Token


class ConnectionStatus(BaseModel):
    connected: bool
    portal_id: str | None = None       # HubSpot portal/hub ID
    account_name: str | None = None
    error: str | None = None


class ConnectionTestResult(BaseModel):
    success: bool
    portal_id: str | None = None
    latency_ms: int
    error_detail: str | None = None


class Contact(BaseModel):
    """Contacto en el CRM. Nunca expone objetos SDK de HubSpot."""
    id: str                            # ID numerico de HubSpot como str
    email: str
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateContactData(BaseModel):
    """Datos para crear un nuevo contacto."""
    email: str
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    source: str | None = None           # e.g. "mailwise-inbound"
    first_interaction_at: datetime | None = None

    @field_validator("email")
    @classmethod
    def email_must_have_at(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("email must contain '@'")
        return v


class ActivityData(BaseModel):
    """Datos para registrar una actividad en el CRM (email recibido)."""
    subject: str
    timestamp: datetime                 # timezone-aware
    classification_action: str          # e.g. "reply", "forward"
    classification_type: str            # e.g. "support", "sales"
    snippet: str                        # truncado a HUBSPOT_ACTIVITY_SNIPPET_LENGTH
    email_id: str                       # referencia al Email.id en DB local
    dashboard_link: str | None = None   # deep link (Sec 6.5: no body completo)


class CreateLeadData(BaseModel):
    """Datos para crear un lead en el CRM."""
    contact_id: str                     # referencia a contacto existente
    summary: str                        # resumen del email (no body completo)
    source: str                         # e.g. "mailwise-inbound"
    lead_status: str = "NEW"            # estado inicial configurable
```

## Patron de try/except en hubspot.py (directiva D7)

```python
async def lookup_contact(self, email: str) -> Contact | None:
    # Validacion de preconditions (local — condicionales, no try/except)
    if not email or "@" not in email:
        raise ValueError(f"Invalid email format: {email!r}")
    if not self._connected:
        raise CRMAuthError("Adapter not connected — call connect() first")

    # Llamada externa — try/except con tipos especificos (directiva D7)
    try:
        response = self._client.crm.contacts.search_api.do_search(
            public_object_search_request={
                "filterGroups": [
                    {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}
                ],
                "sorts": [{"propertyName": "createdate", "direction": "DESCENDING"}],
                "limit": 2,  # buscar 2 para detectar ambiguedad
            }
        )
    except ApiException as exc:
        _raise_from_hubspot_exc(exc)  # clasifica por exc.status y relanza tipo correcto

    # Mapeo de objeto SDK a Pydantic (local — condicionales)
    results = response.results
    if not results:
        return None

    if len(results) > 1:
        logger.warning(
            "CRM lookup returned multiple contacts",
            extra={"email_hash": _hash_email(email), "count": len(results)},
        )

    raw = results[0]
    props = raw.properties
    return Contact(
        id=raw.id,
        email=props.get("email", ""),
        first_name=props.get("firstname"),
        last_name=props.get("lastname"),
        company=props.get("company"),
        created_at=_parse_hs_datetime(props.get("createdate")),
        updated_at=_parse_hs_datetime(props.get("lastmodifieddate")),
    )
```

### Clasificacion de `ApiException` por status HTTP

```python
def _raise_from_hubspot_exc(exc: ApiException) -> None:
    """Clasifica ApiException de HubSpot y relanza como tipo especifico del adapter."""
    # Clasificacion local — condicional sobre exc.status (no try/except adicional)
    if exc.status == 401:
        raise CRMAuthError(f"HubSpot auth error: {exc.reason}") from exc
    if exc.status == 409:
        raise DuplicateContactError(f"Contact already exists: {exc.reason}") from exc
    if exc.status == 404:
        raise ContactNotFoundError(f"Contact not found: {exc.reason}") from exc
    if exc.status == 429:
        retry_after = _parse_retry_after(exc)
        raise CRMRateLimitError(f"HubSpot rate limit exceeded", retry_after_seconds=retry_after) from exc
    raise CRMConnectionError(f"HubSpot API error {exc.status}: {exc.reason}") from exc
```

### `update_field` con silenciado de `FieldNotFoundError`

```python
async def update_field(self, contact_id: str, field: str, value: str) -> None:
    if not contact_id or not field:
        raise ValueError("contact_id and field must not be empty")

    try:
        self._client.crm.contacts.basic_api.update(
            contact_id=contact_id,
            simple_public_object_input={"properties": {field: value}},
        )
    except ApiException as exc:
        # FieldNotFoundError silenciado per Sec 6.4 (log, skip, no fail)
        if exc.status == 400 and "PROPERTY_DOESNT_EXIST" in (exc.body or ""):
            logger.warning(
                "CRM field not found — skipping",
                extra={"contact_id": contact_id, "field": field},
            )
            return  # silenciado intencionalmente
        _raise_from_hubspot_exc(exc)
```

## Clasificacion de errores HubSpot por status HTTP

| HTTP status | Condicion adicional | Excepcion del adapter |
|-------------|--------------------|-----------------------|
| 401 | cualquiera | `CRMAuthError` |
| 404 | cualquiera | `ContactNotFoundError` |
| 409 | cualquiera | `DuplicateContactError` |
| 429 | cualquiera | `CRMRateLimitError` |
| 400 | body contiene `PROPERTY_DOESNT_EXIST` | `FieldNotFoundError` (silenciado en `update_field`) |
| 400 | otras condiciones | `CRMConnectionError` |
| 5xx | cualquiera | `CRMConnectionError` |
| red/timeout | N/A | `CRMConnectionError` |

## Jerarquia de excepciones (exceptions.py)

```python
class CRMAdapterError(Exception):
    """Base para todos los errores del CRM adapter."""

class CRMAuthError(CRMAdapterError):
    """Token invalido, revocado, o sin scope suficiente (HTTP 401)."""

class CRMRateLimitError(CRMAdapterError):
    """HTTP 429. retry_after_seconds puede ser None si el header no esta presente."""
    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds

class CRMConnectionError(CRMAdapterError):
    """Fallo de red, timeout, DNS, o errores 5xx de HubSpot."""

class DuplicateContactError(CRMAdapterError):
    """Intento de crear un contacto con email que ya existe (HTTP 409)."""

class ContactNotFoundError(CRMAdapterError):
    """contact_id referenciado no existe en HubSpot (HTTP 404)."""

class FieldNotFoundError(CRMAdapterError):
    """La propiedad no existe en el schema de HubSpot (HTTP 400 PROPERTY_DOESNT_EXIST).
    Silenciada en update_field per Sec 6.4 — expuesta para que callers puedan capturarla
    si necesitan saber que el campo fue omitido."""
```

## Defaults load-bearing (Cat 8 pre-mortem)

| Default | Valor | Env Var | Consecuencia si incorrecto |
|---------|-------|---------|---------------------------|
| Rate limit (free tier) | `100 req / 10 s` | `HUBSPOT_RATE_LIMIT_PER_10S` | Exceder genera 429 en cascada; tareas Celery saturan la cola de reintento |
| Activity snippet length | `200` chars | `HUBSPOT_ACTIVITY_SNIPPET_LENGTH` | Demasiado largo: PII adicional en CRM (Sec 6.5). Demasiado corto: contexto insuficiente |
| Auto-create contacts | `false` | `HUBSPOT_AUTO_CREATE_CONTACTS` | `true` sin supervision: crea contactos de spam en HubSpot |
| Lead status inicial | `"NEW"` | `HUBSPOT_DEFAULT_LEAD_STATUS` | Valor incorrecto: leads creados en estado que el equipo no monitorea |
| API timeout | `15` s | `HUBSPOT_API_TIMEOUT_SECONDS` | Demasiado bajo: timeouts falsos en red lenta. Demasiado alto: tareas Celery cuelgan |

Todos los defaults se cargan desde `src/core/config.py` (pydantic-settings). Ningun valor
hardcodeado en el adapter.

## Privacidad de datos (Sec 6.5)

- El adapter NUNCA recibe ni envia el body completo del email a HubSpot.
- `ActivityData.snippet` truncado a `HUBSPOT_ACTIVITY_SNIPPET_LENGTH` antes de llegar al adapter.
- El truncado ocurre en el servicio llamador — el adapter no trunca (no es su responsabilidad).
- El adapter loggea solo IDs, nunca subject ni snippet (PII policy, Sec 11.4).

## Estructura de archivos esperada

```
src/adapters/crm/
├── __init__.py          # re-exporta CRMAdapter, HubSpotAdapter, schemas, excepciones
├── base.py              # CRMAdapter ABC (7 metodos con contract-docstrings)
├── hubspot.py           # HubSpotAdapter (toda extraccion del SDK aqui)
├── schemas.py           # Contact, CreateContactData, ActivityData, ActivityId, etc.
└── exceptions.py        # CRMAdapterError y 6 subclases
```

## Criterios de exito (deterministicos)

### Calidad de codigo

- [ ] `ruff check src/adapters/crm/` — 0 violaciones
- [ ] `ruff format src/adapters/crm/ --check` — 0 diferencias
- [ ] `mypy src/adapters/crm/` — 0 errores de tipo

### Tipos (tighten-types — Directiva D1)

- [ ] Sin `dict[str, Any]` en ninguna firma publica de `base.py` ni `hubspot.py`
- [ ] `lookup_contact` retorna `Contact | None` (Pydantic BaseModel) — no `dict | None`
- [ ] `create_contact` retorna `Contact` — no objeto SDK
- [ ] `log_activity` retorna `ActivityId` (NewType) — no `str` desnudo ni `dict`
- [ ] `create_lead` retorna `LeadId` (NewType) — no `str` desnudo ni `dict`
- [ ] Objetos `SimplePublicObject` del SDK nunca cruzan el boundary de `hubspot.py`
- [ ] `CRMCredentials`, `ActivityData`, `CreateContactData`, `CreateLeadData` son Pydantic BaseModel

### Contratos de metodo (contract-docstrings — 4 preguntas)

- [ ] Los 7 metodos del ABC en `base.py` tienen docstrings con las 4 preguntas completas
- [ ] `lookup_contact` documenta comportamiento de multiples matches (silenciado, mas reciente)
- [ ] `update_field` documenta `FieldNotFoundError` como silenciado per Sec 6.4
- [ ] `create_contact` documenta `DuplicateContactError` como no-silenciado (caller decide)
- [ ] `test_connection` documenta silenciado de todos los errores externos

### Manejo de excepciones (try-except — Directivas D7/D8)

- [ ] Toda llamada al SDK de HubSpot en try/except con `ApiException` especifica
- [ ] `_raise_from_hubspot_exc` clasifica por `.status` con condicional (no try/except anidado)
- [ ] `update_field` silencia correctamente HTTP 400 con `PROPERTY_DOESNT_EXIST` en body
- [ ] Sin `except Exception` desnudo en ninguna firma publica
- [ ] Validacion de argumentos usa condicionales (`if not contact_id: raise ValueError`)
- [ ] Mapeo de objeto SDK a Pydantic es local computation — sin try/except en esa logica

### Comportamiento funcional (Sec 6.2 + 6.4 + 6.5)

- [ ] `lookup_contact` usa `searchApi` con filtro por email — no `getAll` + filtrado local
- [ ] Multiples matches: usa el mas reciente por `createdate`, loggea ambiguedad
- [ ] `log_activity` crea Note en HubSpot (not Task) asociada al contact_id
- [ ] `create_lead` crea Deal en HubSpot en pipeline default con estado `HUBSPOT_DEFAULT_LEAD_STATUS`
- [ ] `update_field` silencia `FieldNotFoundError` y loggea con `field_name` (sin PII)
- [ ] Snippet truncado antes de llamar al adapter (verificado via test: snippet > 200 chars en ActivityData se trunca en el servicio, no el adapter)

### Pre-mortem (Cat 3, 8, 10)

- [ ] `contact_id` tratado siempre como `str` — nunca convertido a `int` (Cat 3: stringly-typed por diseno de HubSpot)
- [ ] `HUBSPOT_ACTIVITY_SNIPPET_LENGTH` default `200` cargado desde config (Cat 8)
- [ ] `HUBSPOT_AUTO_CREATE_CONTACTS` default `false` cargado desde config (Cat 8)
- [ ] `hubspot-api-client` pinned a version especifica en `pyproject.toml` con comentario (Cat 10)

### Privacidad de datos (Sec 6.5)

- [ ] `ActivityData` no tiene campo `body` ni `body_plain` — solo `snippet`
- [ ] Logger en `hubspot.py` nunca loggea `snippet`, `subject`, ni datos del sender — solo IDs

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Orden de implementacion sugerido para minimizar re-trabajo:**
1. `src/adapters/crm/exceptions.py` — jerarquia de errores, sin dependencias
2. `src/adapters/crm/schemas.py` — contratos de datos, sin dependencias externas
3. `src/adapters/crm/base.py` — ABC con contract-docstrings completos
4. `src/adapters/crm/hubspot.py` — implementacion concreta (depende de los tres anteriores)
5. `src/adapters/crm/__init__.py` — exports
6. `src/core/config.py` — agregar settings de HubSpot

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**
1. `mypy src/adapters/crm/` — si falla, corregir tipos antes de cualquier otro gate
2. `ruff check src/adapters/crm/ && ruff format --check src/adapters/crm/` — si falla, corregir lint
3. `pytest tests/adapters/crm/test_schemas.py -v` — validacion Pydantic antes de tests de adapter
4. `pytest tests/adapters/crm/test_hubspot_adapter.py -v` — contrato completo con mocks SDK
5. `pytest tests/adapters/crm/ -v` — suite completa del modulo

**Consultas requeridas antes de implementar:**
- Consultar Sentinel para revision del patron de autenticacion con `HUBSPOT_ACCESS_TOKEN`
  (Private App Token vs OAuth2) y confirmacion de que el token no se loggea accidentalmente.
- Consultar Inquisidor para confirmar tipos de `ActivityId` y `LeadId` como `NewType` vs
  Pydantic model de un campo — impacto en mypy strict y tests de contrato.

**Verificacion critica (no automatizable):** Confirmar que la tabla de clasificacion de
`ApiException` por status esta completa. Agregar nuevos codigos de error de HubSpot a la tabla
cuando se descubran en testing de integracion. Sentinel ejecuta revision de privacidad de datos
(snippet length, PII en logs) antes de marcar COMPLETO.
