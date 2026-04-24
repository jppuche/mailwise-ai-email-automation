# Bloque 3: Email Adapter (Gmail)

## Objetivo

Definir el `EmailAdapter` ABC y su implementacion concreta `GmailAdapter` con OAuth2, fetch de
mensajes nuevos con deduplicacion, creacion de borradores, gestion de etiquetas y test de
conexion — todo con firmas completamente tipadas, docstrings de contrato en formato 4-preguntas
y manejo estructurado de errores de la API de Gmail.

## Dependencias

- Bloque 0 (Foundation): estructura `src/adapters/`, pyproject.toml con deps de Google SDK
- Bloque 1 (Database + Models): modelo `Email` definido en SQLAlchemy (para saber que campos
  debe producir `EmailMessage`); campo `gmail_message_id` disponible para deduplicacion

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/adapters/email/__init__.py` — Exports publicos: `EmailAdapter`, `GmailAdapter`,
  `EmailMessage`, `ConnectionStatus`, `ConnectionTestResult`, `DraftId`, `Label`,
  `EmailCredentials` y toda la jerarquia de excepciones.
- `src/adapters/email/base.py` — `EmailAdapter` ABC con 7 metodos abstractos. Cada metodo
  tiene docstring de contrato en formato 4-preguntas. Firmas completamente tipadas sin
  `dict[str, Any]`.
- `src/adapters/email/gmail.py` — `GmailAdapter(EmailAdapter)` implementacion concreta.
  Maneja construccion del servicio Google API, refresh de tokens OAuth2, paginacion de
  resultados, extraccion de mensajes desde threads, y parse de cabeceras MIME.
- `src/adapters/email/schemas.py` — Modelos Pydantic: `EmailMessage`, `EmailCredentials`,
  `ConnectionStatus`, `ConnectionTestResult`, `DraftId`, `Label`. TypedDicts para estructuras
  anidadas: `RecipientData`, `AttachmentData`. Todos matchean Appendix B.1.
- `src/adapters/email/exceptions.py` — Jerarquia de excepciones propia: `EmailAdapterError`
  (base), `AuthError`, `RateLimitError`, `EmailConnectionError`, `FetchError`,
  `DraftCreationError`, `LabelError`. Cada tipo tiene campo `original_error: Exception | None`.
- `src/core/config.py` — Modificar: agregar settings de Gmail (`GMAIL_MAX_RESULTS`,
  `GMAIL_CREDENTIALS_FILE`, `GMAIL_TOKEN_FILE`). Defaults configurables via env.

### Frontend (frontend-worker)

_(Bloque 3 es backend puro — ningun archivo frontend. El dashboard de configuracion de cuenta
de email se implementa en un bloque posterior.)_

- Ninguno en este bloque.

### Tests (Inquisidor)

- `tests/unit/test_email_schemas.py` — Validacion de que `EmailMessage` acepta y rechaza
  campos correctamente; que `RecipientData` y `AttachmentData` serializan a JSONB-compatible
  dict; que `DraftId` es str no vacio.
- `tests/unit/test_gmail_parsing.py` — Tests unitarios para la logica de parse de cabeceras
  MIME (de/para/subject/date) y extraccion de body (plain text fallback si html presente).
  Sin llamadas a la API real. Input: dicts de respuesta Gmail raw (fixtures).
- `tests/contract/test_email_adapter_contract.py` — Suite de tests de contrato contra el ABC.
  Usa `MockEmailAdapter` que implementa todos los metodos. Verifica que cualquier implementacion
  concreta satisface: retorna tipos correctos, lanza excepciones correctas ante inputs invalidos,
  no expone `dict[str, Any]` en ningun retorno.
- `tests/integration/test_gmail_adapter.py` — Tests de integracion con Gmail API mockeada
  (unittest.mock para `googleapiclient.discovery.build`). Cubre: fetch_new_messages con batch
  de mensajes, manejo de 401 → AuthError, manejo de 429 → RateLimitError, parse failure en un
  mensaje no mata el batch, create_draft construye MIME correcto.

## Skills aplicables

- **tighten-types:** Aplicar antes y durante la implementacion. Cada metodo del ABC tiene firma
  completamente tipada. `EmailMessage` es Pydantic `BaseModel` — nunca `dict`. Los dicts raw de
  la respuesta Gmail se parsean *dentro* del adapter y nunca salen de `gmail.py`. TypedDicts
  para `RecipientData` y `AttachmentData` (estructuras anidadas en campos JSONB). Return type
  de `fetch_new_messages` es `list[EmailMessage]`, no `list[Any]`.
- **contract-docstrings:** Aplicar en la definicion del ABC (`base.py`). Cada metodo documenta
  las 4 preguntas: precondiciones, errores por violacion de precondicion, errores de estado
  externo, errores silenciados. Ver tabla completa en seccion Criterios de exito.
- **try-except:** Aplicar durante la implementacion de `gmail.py`. Cada llamada a la API de
  Google es external-state: try/except con tipos especificos. Parse de mensajes individuales:
  try/except por mensaje (fallo aislado, batch continua). Validacion de argumentos: condicionales,
  no try/except. Ver tabla completa en seccion Criterios de exito.
- **pre-mortem:** Aplicar en revision antes de cerrar el bloque. Verificar Cat 4 (threads vs
  mensajes), Cat 8 (GMAIL_MAX_RESULTS como default configurable), Cat 10 (version pinning de
  google-api-python-client).

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Criterios de exito (deterministicos)

### Calidad de codigo

- [ ] `ruff check src/adapters/email/` — 0 violaciones
- [ ] `ruff format src/adapters/email/ --check` — 0 diferencias
- [ ] `mypy src/adapters/email/` — 0 errores de tipo

### Tipos (tighten-types — Directiva D1)

- [ ] Sin `dict[str, Any]` en ningun metodo publico de `base.py` ni `gmail.py`
- [ ] `fetch_new_messages` retorna `list[EmailMessage]` donde `EmailMessage` es Pydantic `BaseModel`
- [ ] `create_draft` retorna `DraftId` (type alias de `str` o `NewType`) — no `str` desnudo ni `dict`
- [ ] `get_labels` retorna `list[Label]` donde `Label` es Pydantic `BaseModel`
- [ ] `connect` retorna `ConnectionStatus` (Pydantic `BaseModel`)
- [ ] `test_connection` retorna `ConnectionTestResult` (Pydantic `BaseModel`)
- [ ] Respuestas raw de Gmail API (`dict` interno) nunca cruzan el boundary del adapter
- [ ] `RecipientData` y `AttachmentData` son TypedDicts con todos los campos tipados

### Contratos de metodos (contract-docstrings — 4 preguntas)

Cada metodo del ABC en `base.py` debe documentar:

**`connect(credentials: EmailCredentials) -> ConnectionStatus`**
- [ ] Precondicion documentada: `credentials` tiene `client_id`, `client_secret`, `token` (access + refresh) no vacios
- [ ] Error por violacion: `ValueError` con mensaje especifico del campo faltante
- [ ] Error de estado externo: `AuthError` (credenciales invalidas, acceso revocado)
- [ ] Errores silenciados: ninguno — todos los errores se propaganr

**`fetch_new_messages(since: datetime, limit: int) -> list[EmailMessage]`**
- [ ] Precondicion documentada: `since` es timezone-aware; `limit` en rango `[1, 500]`; adapter conectado
- [ ] Error por violacion: `ValueError("since must be timezone-aware datetime")` / `ValueError("limit must be between 1 and 500")`
- [ ] Error de estado externo: `AuthError`, `RateLimitError`, `EmailConnectionError`, `FetchError`
- [ ] Errores silenciados: parse failure de mensaje individual — loggeado con `message_id`, batch continua; caller detecta via `len(result) < limit`

**`mark_as_processed(message_id: str) -> None`**
- [ ] Precondicion documentada: `message_id` no vacio; adapter conectado
- [ ] Error por violacion: `ValueError`
- [ ] Error de estado externo: `AuthError`, `RateLimitError`, `EmailConnectionError`
- [ ] Errores silenciados: ninguno

**`create_draft(to: str, subject: str, body: str, in_reply_to: str | None) -> DraftId`**
- [ ] Precondicion documentada: `to` es email valido (formato RFC 5322 basico); `body` no vacio; adapter conectado
- [ ] Error por violacion: `ValueError`
- [ ] Error de estado externo: `AuthError`, `RateLimitError`, `EmailConnectionError`, `DraftCreationError`
- [ ] Errores silenciados: ninguno

**`get_labels() -> list[Label]`**
- [ ] Precondicion documentada: adapter conectado
- [ ] Error por violacion: `EmailAdapterError("not connected")`
- [ ] Error de estado externo: `AuthError`, `EmailConnectionError`
- [ ] Errores silenciados: ninguno

**`apply_label(message_id: str, label_id: str) -> None`**
- [ ] Precondicion documentada: `message_id` y `label_id` no vacios; adapter conectado
- [ ] Error por violacion: `ValueError`
- [ ] Error de estado externo: `AuthError`, `RateLimitError`, `LabelError`
- [ ] Errores silenciados: ninguno

**`test_connection() -> ConnectionTestResult`**
- [ ] Precondicion documentada: `credentials` cargadas (adapter inicializado)
- [ ] Error por violacion: `EmailAdapterError("credentials not loaded")`
- [ ] Error de estado externo: no lanza — captura todos y los refleja en `ConnectionTestResult.error`
- [ ] Errores silenciados: todos los errores de red/auth se capturan y se exponen en el resultado como `connected=False, error=str(e)`

### Manejo de excepciones (try-except — Directivas D7/D8)

- [ ] Cada llamada a `service.users().messages().list().execute()` esta en try/except con:
  - `googleapiclient.errors.HttpError` con manejo por `status_code` (401 → `AuthError`, 429 → `RateLimitError`, 5xx → `EmailConnectionError`, resto → `FetchError`)
  - `google.auth.exceptions.RefreshError` → `AuthError`
- [ ] Parse de cada mensaje individual en `fetch_new_messages` esta en try/except aislado:
  `except (KeyError, ValueError, ValidationError) as e` — loggea y continua con el siguiente
- [ ] Refresh de token OAuth2 en try/except: `except google.auth.exceptions.RefreshError as e: raise AuthError(...) from e`
- [ ] Sin `except Exception` desnudo en ningun metodo publico
- [ ] Validacion de argumentos (`since` timezone-aware, `limit` rango, email format) usa `if/raise ValueError`, no try/except

### Comportamiento funcional

- [ ] `fetch_new_messages` extrae mensajes individuales desde threads (Gmail retorna threads, no mensajes directos — extraccion documentada en docstring y en implementacion)
- [ ] `fetch_new_messages` usa `q: "after:{timestamp}"` en la query de Gmail para filtrado server-side
- [ ] `fetch_new_messages` maneja paginacion con `pageToken` cuando hay mas de `GMAIL_MAX_RESULTS` resultados
- [ ] `create_draft` construye mensaje MIME correctamente con `email.mime.multipart` / `email.mime.text`
- [ ] `create_draft` incluye cabecera `In-Reply-To` cuando `in_reply_to` no es None
- [ ] `mark_as_processed` agrega label `PROCESSED` (o equivalente configurado) y remueve `UNREAD`
- [ ] `test_connection` retorna `connected=True` con `account` (email address) y `scopes` cuando la conexion es exitosa

### Pre-mortem (Cat 4, 8, 10)

- [ ] Docstring de `fetch_new_messages` documenta explicitamente que Gmail API retorna threads y que la implementacion extrae el primer mensaje no-procesado de cada thread (Cat 4: precondicion no obvia)
- [ ] `GMAIL_MAX_RESULTS` tiene default `100` configurable via env var (Cat 8: default load-bearing)
- [ ] `google-api-python-client` pinned a version especifica en `pyproject.toml` con comentario de version conocida-compatible (Cat 10: version-coupled)
- [ ] `google-auth-oauthlib` pinned de igual forma (Cat 10)

### Schemas (Appendix B.1 compliance)

- [ ] `EmailMessage` tiene campos: `id`, `gmail_message_id`, `subject`, `from_address`, `to_addresses: list[RecipientData]`, `cc_addresses: list[RecipientData]`, `body_plain`, `body_html | None`, `snippet`, `received_at: datetime`, `attachments: list[AttachmentData]`, `raw_headers: dict[str, str]`
- [ ] `EmailMessage.received_at` es siempre timezone-aware (UTC)
- [ ] `RecipientData` tiene campos: `name: str | None`, `email: str`
- [ ] `AttachmentData` tiene campos: `filename: str`, `mime_type: str`, `size_bytes: int`
- [ ] `ConnectionTestResult` tiene campos: `connected: bool`, `account: str | None`, `scopes: list[str]`, `error: str | None`

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Orden de implementacion sugerido para minimizar re-trabajo:**
1. `src/adapters/email/exceptions.py` — jerarquia de errores, sin dependencias
2. `src/adapters/email/schemas.py` — contratos de datos, sin dependencias externas
3. `src/adapters/email/base.py` — ABC con docstrings de contrato completos
4. `src/adapters/email/gmail.py` — implementacion concreta (depende de los tres anteriores)
5. `src/adapters/email/__init__.py` — exports
6. `src/core/config.py` — agregar settings de Gmail

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Notas criticas de implementacion:**

1. **Gmail threads vs mensajes (Cat 4):** La API `messages.list` puede retornar thread IDs.
   Usar `format=full` con `messages.get` por cada ID para obtener el mensaje completo.
   Documentar este comportamiento en el docstring de `fetch_new_messages`.

2. **Deduplicacion:** La responsabilidad de deduplicacion (evitar re-procesar el mismo
   `gmail_message_id`) es del servicio que llama al adapter, no del adapter mismo.
   El adapter solo garantiza que `gmail_message_id` esta presente en cada `EmailMessage`.

3. **Token refresh:** El adapter debe llamar `credentials.refresh(Request())` cuando detecta
   que el token de acceso esta expirado, antes de reintentar. El token refresheado debe
   persistirse via callback o metodo abstracto `_save_credentials`.

**Consultas requeridas antes de implementar:**
- Consultar Inquisidor para confirmar firma de `fetch_new_messages` con `since: datetime`
  vs `since_timestamp: int` (epoch) — impacto en boundary types y tests.
- Consultar Sentinel para revision del flujo OAuth2 en `gmail.py` (manejo de token refresh
  y persistencia de credenciales) antes de cerrar el bloque.
