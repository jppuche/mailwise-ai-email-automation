# Bloque 11: Draft Generation Service

## Objetivo

Implementar `DraftGenerationService` que construye contexto multi-fuente (email + clasificacion +
CRM + org context + template), llama al LLM adapter para generar un borrador, persiste el draft
en DB con estado `pending`, y opcionalmente lo sube a Gmail como borrador — con HITL como
restriccion arquitectonica absoluta: el sistema NUNCA envia emails por su cuenta.

## Dependencias

- Bloque 1 (Models): `Draft`, `DraftStatus`, `Email`, `EmailState`
- Bloque 4 (LLM Adapter): `LLMAdapter` ABC, `DraftText`, `DraftOptions`,
  excepciones `LLMAdapterError`, `LLMConnectionError`, `LLMRateLimitError`, `LLMTimeoutError`
- Bloque 3 (Email Adapter): `EmailAdapter` ABC, `DraftId`,
  excepcion `EmailAdapterError`
- Bloque 10 (CRM Sync Service): `CRMSyncRecord` — fuente opcional de contexto CRM
- Bloque 9 (Routing Service): genera `RoutingAction` con `generate_draft: true` — trigger

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/services/draft_generation.py` — `DraftGenerationService`: orquesta la generacion,
  persiste el draft, controla el push opcional a Gmail, transiciona `EmailState`
- `src/services/draft_context.py` — `DraftContextBuilder`: ensambla el contexto LLM desde
  las 5 fuentes; operacion local pura (sin I/O propio)
- `src/services/schemas/draft.py` — Pydantic models: `DraftRequest`, `DraftResult`,
  `DraftContext`, `OrgContext`, `CRMContextData`, `DraftGenerationConfig`
- `src/tasks/draft_generation_task.py` — Tarea Celery: carga contexto desde DB, llama al
  service, maneja retries, escribe resultado
- `src/core/config.py` — Modificar: agregar settings de generacion
  (`DRAFT_PUSH_TO_GMAIL`, `DRAFT_ORG_SYSTEM_PROMPT`, `DRAFT_ORG_TONE`,
  `DRAFT_ORG_PROHIBITED_LANGUAGE`, `DRAFT_GENERATION_RETRY_MAX`)

### Frontend (frontend-worker)

- N/A — la cola de revision de drafts y la UI de revision son responsabilidad de B13
  (Draft Review API + Dashboard). Este bloque es exclusivamente backend.

### Tests (Inquisidor)

- `tests/services/test_draft_generation_service.py` — Casos: draft con contexto completo
  (email + clasificacion + CRM + org + template), draft sin CRM context (CRM no configurado
  o sync no completado), draft sin template (routing rule sin template_id), fallo de LLM
  (DRAFT_FAILED sin perder el request), fallo de Gmail push (draft existe en DB aunque
  Gmail falle), verificacion de HITL (no existe ningun codigo path que llame a
  `send_email()` desde este servicio)
- `tests/services/test_draft_context_builder.py` — Casos: contexto completo con las 5
  fuentes, contexto sin CRM (campo `crm_context=None`), contexto sin template
  (campo `template=None`), prompt resultante no contiene body completo (solo snippet),
  contexto incluye nota "CRM context unavailable" cuando CRM es None
- `tests/tasks/test_draft_generation_task.py` — Retry ante `LLMRateLimitError`, no-retry
  ante fallo de Gmail push, estado `DRAFT_GENERATED` cuando LLM ok y Gmail falla

## Skills aplicables

- **tighten-types** (CRITICO): `DraftGenerationService` consume `LLMAdapter` (retorna
  `DraftText`) y `EmailAdapter` (retorna `DraftId`). Ningun dict raw escapa. `DraftContext`
  es un Pydantic BaseModel — el `DraftContextBuilder` produce tipos concretos, no strings
  concatenados ad-hoc. Aplicar en planificacion (definir `DraftContext` antes de implementar
  el builder) y en revision (mypy en modo estricto).
- **try-except** (CRITICO): Llamada al LLM adapter es external state (try/except). Push a
  Gmail es external state (try/except — fallo aceptable). Assembly del contexto es local
  computation (condicionales, no try/except). Renderizado de templates es local computation
  (condicionales). Ver "Patron de try/except" abajo.
- **pre-mortem Cat 6** (CRITICO): Draft stored en DB first, Gmail push second. Si Gmail
  falla, el draft existe en el sistema (fuente primaria). El reviewer puede aprobar y hacer
  push manual desde el dashboard. Ningun fallo de push debe resultar en perdida de draft.
- **pre-mortem Cat 4** (ALTO): Shape del contexto que el LLM espera es una precondicion
  implicita. Documentar explicitamente el formato del prompt en el builder — sin asumir que
  el LLM maneja cualquier estructura de entrada.
- **pre-mortem Cat 8** (ALTO): `DRAFT_ORG_SYSTEM_PROMPT`, `DRAFT_ORG_TONE`,
  `DRAFT_PUSH_TO_GMAIL`, `DRAFT_GENERATION_RETRY_MAX` son load-bearing. Ver tabla abajo.
- **contract-docstrings** (MEDIO): `DraftGenerationService.generate()` documenta las 5
  fuentes de contexto, la garantia HITL (no-send path), errores surfaceados vs silenciados.

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## HITL — Restriccion Arquitectonica Absoluta (Sec 7.1)

**El sistema NUNCA envia emails. Esta restriccion no es configurable.**

Implicaciones arquitectonicas concretas:

```python
# PROHIBIDO: no existe este metodo en DraftGenerationService
async def send_draft(self, draft_id: uuid.UUID) -> None: ...

# PROHIBIDO: no existe este campo en DraftGenerationConfig
auto_send_after_hours: int  # <- NUNCA

# PROHIBIDO: no existe esta logica en ningun Celery task de este bloque
if draft.status == DraftStatus.PENDING and hours_since_creation > threshold:
    await email_adapter.send(...)  # <- NUNCA

# CORRECTO: el service solo llama a create_draft (borrador en Gmail), nunca a send
await email_adapter.create_draft(to=..., subject=..., body=draft_content)
```

La unica interaccion con el email adapter en este bloque es `create_draft()`. El metodo
`send_message()` (si existe en el adapter) no se importa ni se llama desde este servicio.

**El reviewer inicia el envio** desde su cliente de email (Gmail) o desde el dashboard
(accion futura, B13). El sistema no tiene mecanismo de envio automatico — ni con umbral
de confianza, ni con timeout, ni con aprobacion implicita.

## Contratos de metodo (contract-docstrings — 4 preguntas)

### `DraftGenerationService.generate(request: DraftRequest, db: AsyncSession) -> DraftResult`

```
Preconditions:
  - request.email_id: UUID del email en estado CRM_SYNCED o ROUTED
    (ROUTED si CRM sync no esta configurado para esta regla)
  - request.email_content.subject: str no vacio
  - request.email_content.body_snippet: str no vacio (truncado a LLM_BODY_TRUNCATION_CHARS)
  - LLM adapter inicializado con configuracion valida
  - Email adapter inicializado si request.push_to_gmail=True

Errors raised on violation:
  - ValueError si request.email_id no corresponde a un Email en DB
  - InvalidStateTransitionError si el email no esta en estado compatible

External state errors (clasificados por degradacion aceptable):
  - LLMConnectionError, LLMRateLimitError, LLMTimeoutError: draft no generado → DRAFT_FAILED
  - EmailAdapterError (push a Gmail): draft existe en DB, push fallido — estado sigue siendo
    DRAFT_GENERATED (no es DRAFT_FAILED) porque el draft principal existe
  - SQLAlchemyError (al guardar draft): propagada — no hay draft, transicion a DRAFT_FAILED

Silenced errors:
  - CRM context unavailable (CRMSyncRecord no existe o status=FAILED): silenciado, genera
    draft sin CRM context, incluye nota "CRM context unavailable" en el prompt
  - Template no encontrado para template_id: silenciado, genera sin template
  - Gmail push failure: silenciado, loggea warning, draft existe en DB como fuente primaria
```

### `DraftContextBuilder.build(request: DraftRequest, crm_record: CRMSyncRecord | None) -> DraftContext`

```
Preconditions:
  - request.email_content.body_snippet: truncado a LLM_BODY_TRUNCATION_CHARS (caller trunca)
  - Si crm_record es None: genera contexto valido sin datos CRM

Errors raised on violation:
  - Ninguno — el builder nunca lanza; retorna siempre un DraftContext valido

External state errors:
  - Ninguno — el builder es operacion local pura (sin I/O)

Silenced errors:
  - Todos los fallos de assembly son fallos de datos opcionales (CRM, template) — se omiten
    del contexto silenciosamente; DraftContext.notes documenta las omisiones
```

## Esquemas Pydantic (schemas/draft.py)

```python
from __future__ import annotations
import uuid
from pydantic import BaseModel


class EmailContent(BaseModel):
    """Contenido del email original incluido en el contexto de generacion."""
    sender_email: str
    sender_name: str | None = None
    subject: str
    body_snippet: str    # truncado a LLM_BODY_TRUNCATION_CHARS — nunca el body completo
    received_at: str     # ISO 8601 — solo para contexto temporal en el prompt


class ClassificationContext(BaseModel):
    """Resultado de clasificacion incluido en el contexto."""
    action: str          # slug de ActionCategory
    type: str            # slug de TypeCategory
    confidence: str      # "high" | "low"


class CRMContextData(BaseModel):
    """
    Datos CRM disponibles para enriquecer el draft.
    Todos los campos son opcionales — CRM puede estar sin configurar o sync fallido.
    """
    contact_name: str | None = None
    company: str | None = None
    account_tier: str | None = None     # ej: "enterprise", "startup", "free"
    recent_interactions: list[str] = [] # ultimas N interacciones (resumen, no body)
    contact_id: str | None = None       # para trazabilidad, no incluido en el prompt


class OrgContext(BaseModel):
    """
    Contexto organizacional para el prompt. Cargado desde configuracion (D14).
    Nunca hardcodeado en el service.
    """
    system_prompt: str         # DRAFT_ORG_SYSTEM_PROMPT
    tone: str                  # DRAFT_ORG_TONE (ej: "professional", "friendly")
    signature: str | None = None   # DRAFT_ORG_SIGNATURE
    prohibited_language: list[str] = []  # DRAFT_ORG_PROHIBITED_LANGUAGE (lista separada por coma)


class DraftContext(BaseModel):
    """
    Contexto completo ensamblado para la llamada al LLM.
    Generado por DraftContextBuilder — es la entrada tipada al LLM adapter.
    """
    email_content: EmailContent
    classification: ClassificationContext
    crm_context: CRMContextData | None = None   # None si CRM no disponible
    org_context: OrgContext
    template: str | None = None                  # template de respuesta si configurado
    notes: list[str] = []                        # notas del builder (ej: "CRM context unavailable")


class DraftRequest(BaseModel):
    """Input para DraftGenerationService.generate()."""
    email_id: uuid.UUID
    email_content: EmailContent
    classification: ClassificationContext
    template_id: str | None = None     # ID de template en tabla de configuracion
    push_to_gmail: bool = False        # DRAFT_PUSH_TO_GMAIL (default: False)


class DraftResult(BaseModel):
    """
    Resultado de DraftGenerationService.generate().
    draft_id es None si la generacion fallo (DRAFT_FAILED).
    gmail_draft_id es None si push no solicitado o fallo el push.
    """
    email_id: uuid.UUID
    draft_id: uuid.UUID | None = None         # ID del Draft en nuestra DB
    gmail_draft_id: str | None = None         # DraftId de Gmail si push exitoso
    status: str                               # "generated" | "failed" | "generated_push_failed"
    model_used: str | None = None             # que modelo genero el draft
    fallback_applied: bool = False            # si el LLM fallback fue activado
    error_detail: str | None = None


class DraftGenerationConfig(BaseModel):
    """Configuracion de generacion leida desde Settings. Nunca hardcodeada."""
    push_to_gmail: bool                       # DRAFT_PUSH_TO_GMAIL (default: False)
    org_context: OrgContext                   # construido desde DRAFT_ORG_*
    retry_max: int                            # DRAFT_GENERATION_RETRY_MAX (default: 2)
```

## DraftContextBuilder (draft_context.py)

El builder es una clase de utilidad con un unico metodo publico. Es operacion local pura:
no hace I/O, no llama a la DB, no llama al LLM. Su entrada es el `DraftRequest` mas el
`CRMSyncRecord` opcional. Su salida es un `DraftContext` siempre valido.

```python
class DraftContextBuilder:
    """
    Ensambla DraftContext desde multiples fuentes.
    Operacion local pura — sin I/O, sin try/except (directiva D8).
    Si una fuente es None o invalida, la omite silenciosamente y registra nota.
    """

    def build(
        self,
        request: DraftRequest,
        crm_record: CRMSyncRecord | None,
        template_content: str | None,
        org_context: OrgContext,
    ) -> DraftContext:
        notes: list[str] = []

        # CRM context — opcional, sin try/except (local computation)
        crm_context: CRMContextData | None = None
        if crm_record is not None and crm_record.contact_id is not None:
            crm_context = self._extract_crm_context(crm_record)
        else:
            notes.append("CRM context unavailable — generating without contact data")

        # Template — opcional, sin try/except
        template: str | None = None
        if template_content is not None:
            template = template_content
        elif request.template_id is not None:
            notes.append(f"Template '{request.template_id}' not found — generating without template")

        return DraftContext(
            email_content=request.email_content,
            classification=request.classification,
            crm_context=crm_context,
            org_context=org_context,
            template=template,
            notes=notes,
        )

    def _extract_crm_context(self, record: CRMSyncRecord) -> CRMContextData:
        """
        Extrae CRMContextData del record. Operacion local — condicionales, no try/except.
        Si un campo no esta disponible, retorna None para ese campo.
        """
        return CRMContextData(
            contact_id=record.contact_id,
            # Los campos enriquecidos (name, company, tier) vienen del CRM adapter
            # en el momento del sync y se guardan en CRMSyncRecord.metadata JSONB.
            # Si no estan presentes, quedan como None.
        )

    def build_llm_prompt(self, context: DraftContext) -> str:
        """
        Construye el prompt final para el LLM desde DraftContext.
        Operacion local pura — formato documentado (Cat 4 pre-mortem).

        Formato del prompt:
        1. Datos del email: remitente, asunto, snippet del body
        2. Clasificacion: action y type
        3. Contexto CRM (si disponible): nombre, empresa, tier, interacciones recientes
        4. Template de respuesta (si disponible)
        5. Notas del builder (si aplican)
        6. Instruccion de generacion: tono, longitud sugerida, placeholder policy
        """
        sections: list[str] = []

        sections.append(
            f"EMAIL TO RESPOND TO:\n"
            f"From: {context.email_content.sender_name or ''} "
            f"<{context.email_content.sender_email}>\n"
            f"Subject: {context.email_content.subject}\n"
            f"Received: {context.email_content.received_at}\n\n"
            f"Content:\n{context.email_content.body_snippet}"
        )

        sections.append(
            f"CLASSIFICATION:\n"
            f"Action required: {context.classification.action}\n"
            f"Email type: {context.classification.type}\n"
            f"Confidence: {context.classification.confidence}"
        )

        if context.crm_context is not None:
            crm_lines = ["CRM CONTEXT:"]
            if context.crm_context.contact_name:
                crm_lines.append(f"Contact name: {context.crm_context.contact_name}")
            if context.crm_context.company:
                crm_lines.append(f"Company: {context.crm_context.company}")
            if context.crm_context.account_tier:
                crm_lines.append(f"Account tier: {context.crm_context.account_tier}")
            if context.crm_context.recent_interactions:
                crm_lines.append("Recent interactions:")
                for interaction in context.crm_context.recent_interactions:
                    crm_lines.append(f"  - {interaction}")
            sections.append("\n".join(crm_lines))

        if context.template is not None:
            sections.append(f"RESPONSE TEMPLATE (adapt as needed):\n{context.template}")

        if context.notes:
            sections.append("NOTES:\n" + "\n".join(f"- {n}" for n in context.notes))

        sections.append(
            f"INSTRUCTIONS:\n"
            f"- Tone: {context.org_context.tone}\n"
            f"- Address the sender by name if available\n"
            f"- Acknowledge specific content from their email (not generic)\n"
            f"- Use [INSERT SPECIFIC DETAIL] placeholders for facts you cannot confirm\n"
            f"- NEVER invent facts, dates, prices, or commitments\n"
            f"- Include signature if provided\n"
            + (f"- Prohibited language: {', '.join(context.org_context.prohibited_language)}\n"
               if context.org_context.prohibited_language else "")
        )

        return "\n\n---\n\n".join(sections)
```

**Invariante del builder:** El prompt resultante NUNCA incluye el body completo del email —
solo `body_snippet`, que ya fue truncado a `LLM_BODY_TRUNCATION_CHARS` por el caller antes
de construir `EmailContent`. Esto es una garantia del tipo: el campo se llama `body_snippet`,
no `body` ni `body_plain`, lo que hace explicita la expectativa de truncacion.

## Patron de try/except en draft_generation.py (directiva D7)

```python
async def generate(
    self,
    request: DraftRequest,
    db: AsyncSession,
) -> DraftResult:
    # Assembly de contexto: operacion local pura — sin try/except (D8)
    crm_record = await self._load_crm_record(request.email_id, db)
    template_content = await self._load_template(request.template_id, db)
    context = self._context_builder.build(
        request=request,
        crm_record=crm_record,
        template_content=template_content,
        org_context=self._config.org_context,
    )
    prompt = self._context_builder.build_llm_prompt(context)

    # Llamada al LLM: external state — try/except con tipos especificos (D7)
    draft_text: DraftText
    try:
        draft_text = await self._llm_adapter.generate_draft(
            prompt=prompt,
            system_prompt=self._config.org_context.system_prompt,
            options=DraftOptions(),
        )
    except LLMConnectionError as exc:
        await self._transition_email(request.email_id, EmailState.DRAFT_FAILED, db)
        return DraftResult(
            email_id=request.email_id,
            status="failed",
            error_detail=f"LLM connection error: {exc}",
        )
    except LLMRateLimitError:
        # No guarda DRAFT_FAILED — el task Celery reintentara con backoff
        raise
    except LLMTimeoutError as exc:
        await self._transition_email(request.email_id, EmailState.DRAFT_FAILED, db)
        return DraftResult(
            email_id=request.email_id,
            status="failed",
            error_detail=f"LLM timeout: {exc}",
        )

    # Persistencia del draft en DB: external state — try/except (D7)
    draft: Draft
    try:
        draft = Draft(
            email_id=request.email_id,
            content=draft_text.content,
            status=DraftStatus.PENDING,
        )
        db.add(draft)
        await db.flush()  # obtener draft.id antes del commit
    except SQLAlchemyError as exc:
        await self._transition_email(request.email_id, EmailState.DRAFT_FAILED, db)
        return DraftResult(
            email_id=request.email_id,
            status="failed",
            error_detail=f"DB error saving draft: {exc}",
        )

    # Commit independiente (D13): draft existe en DB antes del push a Gmail
    await db.commit()

    # Transicion de estado (D10: via transition_to, no asignacion directa)
    await self._transition_email(request.email_id, EmailState.DRAFT_GENERATED, db)

    # Push a Gmail: external state, fallo aceptable — D7
    gmail_draft_id: str | None = None
    push_failed = False
    if request.push_to_gmail:
        try:
            gmail_draft_id = await self._email_adapter.create_draft(
                to=request.email_content.sender_email,
                subject=f"Re: {request.email_content.subject}",
                body=draft_text.content,
                in_reply_to=None,  # thread reply en B12 si se requiere
            )
        except EmailAdapterError as exc:
            # Fallo de push: draft existe en DB (fuente primaria) — no es DRAFT_FAILED
            logger.warning(
                "Gmail draft push failed — draft saved locally",
                extra={"email_id": str(request.email_id), "error": str(exc)},
            )
            push_failed = True

    return DraftResult(
        email_id=request.email_id,
        draft_id=draft.id,
        gmail_draft_id=gmail_draft_id,
        status="generated_push_failed" if push_failed else "generated",
        model_used=draft_text.model_used,
        fallback_applied=draft_text.fallback_applied,
    )
```

**Clasificacion de operaciones (D7 vs D8):**

| Operacion | Tipo | Patron |
|-----------|------|--------|
| LLM adapter.generate_draft | External state | try/except con LLMConnectionError, LLMRateLimitError, LLMTimeoutError |
| EmailAdapter.create_draft (push) | External state | try/except con EmailAdapterError |
| CRMSyncRecord load (DB) | External state | try/except para SQLAlchemyError |
| Draft save (DB) | External state | try/except para SQLAlchemyError |
| DraftContextBuilder.build() | Local computation | Sin try/except — condicionales |
| build_llm_prompt() | Local computation | Sin try/except — string assembly |
| Template rendering | Local computation | Sin try/except — condicionales |
| Snippet truncation (en el caller) | Local computation | Slicing directo |

## Transicion de estado (D10)

```
CRM_SYNCED → DRAFT_GENERATED   (camino principal: CRM sync completado)
ROUTED → DRAFT_GENERATED       (cuando CRM sync no configurado para esta regla)
CRM_SYNCED → DRAFT_FAILED      (fallo de LLM connection/timeout, o fallo de DB)
ROUTED → DRAFT_FAILED          (mismos fallos en el camino alternativo)
DRAFT_FAILED → CRM_SYNCED      (recovery: retry desde CRM_SYNCED)
DRAFT_FAILED → ROUTED          (recovery: retry si el estado previo era ROUTED)
```

**Fallo de push a Gmail:** El estado es `DRAFT_GENERATED` (no `DRAFT_FAILED`) porque el
draft existe como fuente primaria en nuestra DB. El campo `DraftResult.status` es
`"generated_push_failed"` para que el dashboard lo diferencie, pero el pipeline continua
normalmente.

## Tarea Celery (draft_generation_task.py)

```python
@celery_app.task(
    bind=True,
    max_retries=settings.draft_generation_retry_max,
    default_retry_delay=60,
)
def draft_generation_task(self, email_id: str) -> None:
    """
    Top-level Celery task. El unico `except Exception` aceptable esta aqui (D7).
    """
    with SyncSessionLocal() as db:
        try:
            email = db.get(Email, uuid.UUID(email_id))
            if email is None:
                logger.error("Email not found for draft generation", extra={"email_id": email_id})
                return

            request = _build_draft_request(email, db)
            service = DraftGenerationService(
                llm_adapter=get_llm_adapter(),
                email_adapter=get_email_adapter(),
                config=get_draft_config(),
            )
            result = service.generate(request, db)
            # Transicion de estado ya ocurrio dentro del service

        except LLMRateLimitError as exc:
            raise self.retry(
                exc=exc,
                countdown=getattr(exc, "retry_after_seconds", None) or 60,
            )
        except Exception as exc:
            logger.exception(
                "Unexpected error in draft_generation_task",
                extra={"email_id": email_id},
            )
            raise self.retry(exc=exc)
```

## Atributos de calidad del draft (Sec 7.3)

El `build_llm_prompt()` enforce estos atributos via instrucciones explicitas al LLM:

| Atributo | Implementacion |
|----------|---------------|
| Dirigirse al remitente por nombre | Instruccion en prompt + `sender_name` en `EmailContent` |
| Reconocer contenido especifico | Snippet del email original incluido en el prompt |
| Tono organizacional | `OrgContext.tone` en el prompt, configurable via env |
| Contexto CRM natural | `CRMContextData` formateado en seccion dedicada del prompt |
| No alucinacion de hechos | Instruccion explicita: `[INSERT SPECIFIC DETAIL]` para datos inciertos |
| Longitud apropiada | Guia en instrucciones; no hardcodeada — LLM decide segun contenido |

**Nota sobre idioma (Sec 10.5):** El system prompt debe incluir instruccion de idioma de la
organizacion. Si el email llega en un idioma diferente, el LLM genera en el idioma
configurado en `OrgContext.system_prompt` y puede incluir nota sobre el idioma original.
Esta logica vive en el system prompt de la org, no en codigo.

## Edge cases documentados (Sec 10.5)

| Escenario | Comportamiento |
|-----------|----------------|
| CRM context no disponible | `DraftContextBuilder` omite seccion CRM, agrega nota "CRM context unavailable". Draft generado sin CRM data. |
| Template no encontrado | Nota "Template not found" en `DraftContext.notes`. Draft generado sin template. |
| Placeholder no rellenable | LLM genera `[INSERT PRICING]` o similar. Reviewer completa en dashboard. |
| Draft inapropiado | HITL lo captura. Reviewer rechaza/edita. El rechazo se loggea para feedback loop (B16). |
| Email en idioma diferente | System prompt de la org define el idioma de respuesta. LLM maneja el switch. |
| LLM fallback aplicado | `DraftText.fallback_applied=True`. `DraftResult.fallback_applied=True`. Visible en dashboard. |

## Defaults load-bearing (Cat 8 pre-mortem)

| Default | Valor | Env Var | Consecuencia si incorrecto |
|---------|-------|---------|---------------------------|
| `push_to_gmail` | `False` | `DRAFT_PUSH_TO_GMAIL` | `True` por defecto: todos los drafts van a Gmail aunque el reviewer no lo espere. `False`: reviewer solo ve en dashboard hasta aprobar |
| `org_system_prompt` | `""` | `DRAFT_ORG_SYSTEM_PROMPT` | Vacio: el LLM usa su comportamiento default sin contexto organizacional. Critico para tono y calidad |
| `org_tone` | `"professional"` | `DRAFT_ORG_TONE` | Tono incorrecto para la cultura de la empresa impacta calidad del draft |
| `prohibited_language` | `[]` | `DRAFT_ORG_PROHIBITED_LANGUAGE` | Vacio: ningun lenguaje bloqueado. Lista incorrecta: bloquea terminos necesarios |
| `retry_max` | `2` | `DRAFT_GENERATION_RETRY_MAX` | `0`: ningun retry en fallo transitorio de LLM. `5+`: demasiados reintentos si el LLM tiene outage |
| LLM body truncation | heredado de B4 | `LLM_BODY_TRUNCATION_CHARS` | Definido en B4; el servicio trunca el body antes de construir `EmailContent` |

## Estructura de archivos esperada

```
src/services/
├── draft_generation.py           # DraftGenerationService
├── draft_context.py              # DraftContextBuilder
└── schemas/
    └── draft.py                  # DraftRequest, DraftResult, DraftContext, OrgContext, etc.

src/tasks/
└── draft_generation_task.py      # Tarea Celery + _build_draft_request helper
```

## Criterios de exito (deterministicos)

- [ ] `DraftGenerationService.generate()` produce un `Draft` con `status=PENDING` en DB
  cuando el LLM responde exitosamente
- [ ] `Draft.content` nunca esta vacio tras una generacion exitosa
- [ ] Fallo de Gmail push: estado del email es `DRAFT_GENERATED` (no `DRAFT_FAILED`),
  `DraftResult.status == "generated_push_failed"`, draft existe en DB
- [ ] Fallo de LLM (connection/timeout): estado del email transiciona a `DRAFT_FAILED`,
  `DraftResult.draft_id == None`
- [ ] `LLMRateLimitError` NO transiciona a `DRAFT_FAILED` — el task reintenta con backoff
- [ ] No existe ningun codigo path que llame a `email_adapter.send_message()` o equivalente
  desde este servicio (verificable via grep en el modulo)
- [ ] No existe `auto_send` ni `send_after_timeout` en ninguna configuracion, clase, o tarea
  de este bloque
- [ ] Draft con CRM context: prompt incluye nombre del contacto, empresa, account tier
- [ ] Draft sin CRM context: `DraftContext.notes` incluye `"CRM context unavailable"`,
  prompt no incluye seccion CRM vacia
- [ ] Draft sin template: generado correctamente, nota en `DraftContext.notes`
- [ ] `DraftContextBuilder.build()` nunca lanza — retorna `DraftContext` valido en todos los casos
- [ ] `body_snippet` en `EmailContent` esta truncado a `LLM_BODY_TRUNCATION_CHARS` —
  `body_plain` completo no aparece en el prompt
- [ ] Instruccion de placeholder `[INSERT SPECIFIC DETAIL]` presente en el prompt generado
- [ ] Transicion de estado via `email.transition_to()` (nunca asignacion directa)
- [ ] Commit independiente antes del push a Gmail (D13): si Gmail falla, el draft persiste
- [ ] Todos los defaults cargados desde env vars via `DraftGenerationConfig`; ninguno hardcodeado
- [ ] `ruff check src/services/draft_generation.py src/services/draft_context.py src/tasks/draft_generation_task.py` — 0 violaciones
- [ ] `mypy src/services/draft_generation.py src/services/draft_context.py src/services/schemas/draft.py src/tasks/draft_generation_task.py` — 0 errores
- [ ] `pytest tests/services/test_draft_generation_service.py -v` — todos los scenarios pasan
- [ ] `pytest tests/services/test_draft_context_builder.py -v` — 5 fuentes + ausencia de CRM/template
- [ ] `pytest tests/tasks/test_draft_generation_task.py -v` — retry/no-retry behavior verificado

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**
1. `mypy src/services/schemas/draft.py` — schemas primero; base de tipos para todo lo demas
2. `mypy src/services/draft_context.py` — builder sin I/O depende solo de schemas
3. `mypy src/services/draft_generation.py` — service depende de builder + schemas
4. `mypy src/tasks/draft_generation_task.py` — task es el ultimo nivel
5. `ruff check src/services/draft_generation.py src/services/draft_context.py src/services/schemas/draft.py src/tasks/draft_generation_task.py && ruff format --check src/services/ src/tasks/draft_generation_task.py`
6. `pytest tests/services/test_draft_context_builder.py -v` — builder antes del service
7. `pytest tests/services/test_draft_generation_service.py -v` — service completo
8. `pytest tests/tasks/test_draft_generation_task.py -v` — retry behavior

**Verificacion critica de HITL (no automatizable):**

Antes de marcar el bloque COMPLETO, ejecutar:

```bash
grep -rn "send_message\|send_email\|auto_send\|send_after" src/services/draft_generation.py src/services/draft_context.py src/tasks/draft_generation_task.py
```

El resultado debe estar vacio. Si aparece cualquier match, el bloque NO esta completo —
independientemente de que todos los tests pasen.

**Consultas requeridas antes de implementar:**
- Consultar Inquisidor para confirmar el tipo correcto de `recent_interactions` en
  `CRMContextData`: `list[str]` (resumenes) vs `list[InteractionRecord]` con BaseModel
  dedicado — impacto en tighten-types D1 y en la integracion con el CRM adapter (B6).
- Consultar Sentinel para revisar el manejo de `DRAFT_ORG_SYSTEM_PROMPT` desde env var —
  este valor es user-supplied y podria contener instrucciones que modifiquen el comportamiento
  del LLM de forma no esperada (prompt injection desde configuracion).
