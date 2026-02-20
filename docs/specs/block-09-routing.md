# Bloque 9: Routing Service

## Objetivo

Evaluar reglas de routing en orden de prioridad contra emails clasificados, despachar a los channel adapters correspondientes con dispatch IDs idempotentes, registrar cada `RoutingAction` de forma independiente, y gestionar fallos parciales sin revertir despachos ya exitosos.

## Dependencias

- B1 (Database Models): `RoutingRule`, `RoutingAction`, `RoutingActionStatus`, `RoutingConditions`, `RoutingActions`, `EmailState` — schema completo disponible
- B5 (Channel Adapter): `ChannelAdapter`, `SlackAdapter`, `RoutingPayload`, `DeliveryResult`, `ChannelAdapterError` y subclases — boundary tipado disponible
- B8 (Classification Service): emails en estado `CLASSIFIED` con `ClassificationResult` DB record; `ActionCategoryDef`, `TypeCategoryDef`

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/services/routing.py` — `RoutingService`: orquesta carga de reglas, evaluacion via `RuleEngine`, construccion de `RoutingPayload`, despacho a adapters, persistencia independiente de cada `RoutingAction`, y transicion de estado del email
- `src/services/rule_engine.py` — `RuleEngine`: evalua condiciones de `RoutingRule` contra un `RoutingContext`; operacion local pura (sin I/O); retorna lista de reglas que hacen match
- `src/services/schemas/routing.py` — Pydantic models del servicio: `RoutingContext`, `RoutingRequest`, `RuleMatchResult`, `RoutingResult`, `RuleTestResult`
- `src/services/schemas/__init__.py` — Re-exporta schemas del paquete services (modificar si ya existe)

### Frontend (frontend-worker)

N/A — este bloque es exclusivamente backend. El endpoint de rule testing (`POST /api/v1/routing/test`) se expone en B13 (API de routing).

### Tests (Inquisidor)

- `tests/services/routing/test_routing_service.py` — Contrato completo del servicio: match de una regla, match de multiples reglas, sin match (unrouted), fallo parcial de canal (una regla falla, otra exito), VIP escalation, estado final correcto
- `tests/services/routing/test_rule_engine.py` — Evaluacion de condiciones: `eq`, `contains`, `in`, `not_in`; condiciones multiples (AND); regla inactiva excluida; prioridad preservada en resultado; entrada sin reglas activas
- `tests/services/routing/test_idempotency.py` — `dispatch_id` deterministico: mismo `(email_id, rule_id, channel, destination)` produce mismo hash. Segundo despacho del mismo dispatch_id retorna `RoutingAction` existente sin crear duplicado
- `tests/services/routing/test_rule_test_mode.py` — Dry-run retorna reglas que matchean sin crear `RoutingAction` ni llamar al adapter; estado del email no cambia

## Skills aplicables

- **tighten-types** (CRITICO): `RoutingPayload` de B5 es el tipo de boundary entre el servicio y el adapter. El `RuleEngine` recibe `RoutingContext` (Pydantic model del servicio) y retorna `list[RuleMatchResult]` — sin `dict[str, Any]` en ninguna firma. `RoutingConditions` y `RoutingActions` son TypedDict de B1 — el `RuleEngine` los recibe pero los itera con acceso tipado. Aplicar en planificacion y revision mypy estricto.
- **try-except** (CRITICO): Clasificacion exacta. Carga de reglas desde DB = estado externo (try/except `SQLAlchemyError`). Despacho al channel adapter = estado externo (try/except `ChannelAdapterError`). Evaluacion de condiciones de reglas = computo local (condicionales, sin try/except). Calculo de `dispatch_id` = computo local (hash deterministico, sin try/except). Determinacion de prioridad = computo local (condicionales, sin try/except). Consultar skill al definir cada bloque.
- **pre-mortem** (ALTO): Cat 6 (non-atomic: cada `RoutingAction` es un commit independiente; fallo en regla N no revierte regla N-1 ya despachada). Cat 1 (ordering: reglas evaluadas una vez por email en orden de prioridad determinista; loops imposibles por diseno). Cat 8 (load-bearing defaults: max reintentos, base de backoff, canal de fallback). Cat 3 (stringly-typed: condiciones de routing con operadores definidos como constantes, no strings libres).
- **contract-docstrings** (ALTO): `RoutingService.route()` debe documentar precondicion de estado (CLASSIFIED), garantia de no-reversion de despachos exitosos, y semantica de estado final (ROUTED si >= 1 exitoso, ROUTING_FAILED si todos fallan).

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Contratos de metodo (contract-docstrings — 4 preguntas)

### `RoutingService.route(email_id, db) -> RoutingResult`

```
Preconditions:
  - Email con email_id existe en DB con state=CLASSIFIED
  - ClassificationResult DB record existe para email_id
  - Al menos un ChannelAdapter registrado en el servicio

Errors raised on violation:
  - ValueError si email_id no existe
  - InvalidStateTransitionError si email.state != CLASSIFIED

External state errors:
  - SQLAlchemyError al cargar reglas — aborta routing completamente; email permanece en CLASSIFIED
  - ChannelAdapterError por regla individual — registrado en RoutingAction como FAILED;
    routing continua con las demas reglas (D13)

Silenced errors:
  - Ninguno — todos los fallos de canal se registran en RoutingAction.status=FAILED
    y son visibles en el dashboard
```

### `RoutingService.test_route(context, db) -> RuleTestResult`

```
Preconditions:
  - context.action_slug pertenece a un ActionCategory activo
  - context.type_slug pertenece a un TypeCategory activo

Errors raised on violation:
  - ValueError si slugs no son reconocibles

External state errors:
  - SQLAlchemyError al cargar reglas — relanzado al caller (endpoint API)

Silenced errors:
  - Ninguno — modo de prueba, el caller espera resultado completo o excepcion
```

### `RuleEngine.evaluate(context, rules) -> list[RuleMatchResult]`

```
Preconditions:
  - context es RoutingContext valido (Pydantic valida en construccion)
  - rules es list[RoutingRule] (puede ser vacia)

Errors raised on violation:
  - Ninguno — operacion local pura

External state errors:
  - Ninguno — sin I/O

Silenced errors:
  - Reglas con condiciones malformadas (campo desconocido, operador desconocido):
    silenciadas con log warning — la regla se trata como no-match
    RAZON: reglas malformadas no deben derribar el pipeline de un email
```

## Esquemas del servicio (schemas/routing.py)

```python
from __future__ import annotations
import uuid
from typing import Literal
from pydantic import BaseModel


class RoutingContext(BaseModel):
    """
    Contexto completo de clasificacion para evaluacion de reglas.
    Construido por RoutingService a partir del email + ClassificationResult DB.
    El RuleEngine solo conoce RoutingContext — nunca modelos SQLAlchemy.
    """
    email_id: uuid.UUID
    action_slug: str              # slug de ActionCategory
    type_slug: str                # slug de TypeCategory
    confidence: Literal["high", "low"]
    sender_email: str
    sender_domain: str
    subject: str
    snippet: str                  # para incluir en RoutingPayload
    sender_name: str | None = None


class RoutingRequest(BaseModel):
    """Entrada al servicio de routing."""
    email_id: uuid.UUID


class RuleMatchResult(BaseModel):
    """Una regla que hizo match + acciones a ejecutar."""
    rule_id: uuid.UUID
    rule_name: str
    priority: int
    actions: list[RoutingActionDef]


class RoutingActionDef(BaseModel):
    """Definicion de una accion de routing — desacoplada del modelo ORM."""
    channel: str                  # "slack" | "email" | "hubspot"
    destination: str              # channel ID, email, pipeline ID
    template_id: str | None = None


class RoutingResult(BaseModel):
    """Resultado completo del routing de un email."""
    email_id: uuid.UUID
    rules_matched: int
    rules_executed: int
    actions_dispatched: int
    actions_failed: int
    was_routed: bool              # True si al menos 1 action tuvo exito
    routing_action_ids: list[uuid.UUID]
    final_state: str              # "ROUTED" | "ROUTING_FAILED" | "UNROUTED"


class RuleTestResult(BaseModel):
    """Resultado del dry-run de routing — ningun despacho real ocurre."""
    context: RoutingContext
    rules_matched: list[RuleMatchResult]
    would_dispatch: list[RoutingActionDef]
    total_actions: int
    dry_run: bool = True
```

## Motor de reglas (rule_engine.py)

### Operadores soportados

Los operadores son constantes del modulo — no strings magic en la logica de evaluacion:

```python
class ConditionOperator(str, enum.Enum):
    EQ = "eq"
    CONTAINS = "contains"
    IN = "in"
    NOT_IN = "not_in"
    STARTS_WITH = "starts_with"
    MATCHES_DOMAIN = "matches_domain"  # sender_domain con soporte wildcard "*.company.com"
```

### Campos evaluables

```python
class ConditionField(str, enum.Enum):
    ACTION_CATEGORY = "action_category"  # compara con context.action_slug
    TYPE_CATEGORY = "type_category"      # compara con context.type_slug
    SENDER_DOMAIN = "sender_domain"      # compara con context.sender_domain
    SENDER_EMAIL = "sender_email"        # compara con context.sender_email
    SUBJECT_CONTAINS = "subject"         # compara con context.subject
    CONFIDENCE = "confidence"            # compara con context.confidence
```

### Logica de evaluacion (operacion local pura — sin try/except)

Las condiciones de una `RoutingRule` son una lista — todas deben cumplirse (AND implicito).

```python
class RuleEngine:
    def evaluate(
        self,
        context: RoutingContext,
        rules: list[RoutingRule],
    ) -> list[RuleMatchResult]:
        """
        Invariants:
          - Solo evalua reglas con is_active=True
          - Retorna resultados en el mismo orden de prioridad de entrada
          - Regla con condicion malformada: log warning, tratada como no-match
        Guarantees:
          - Retorna lista (puede ser vacia); nunca lanza excepcion
        Errors: ninguno
        State transitions: ninguna
        """
        results: list[RuleMatchResult] = []
        for rule in rules:
            if not rule.is_active:
                continue
            if self._rule_matches(context, rule):
                results.append(
                    RuleMatchResult(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        priority=rule.priority,
                        actions=[
                            RoutingActionDef(
                                channel=a["channel"],
                                destination=a["destination"],
                                template_id=a.get("template_id"),
                            )
                            for a in rule.actions
                        ],
                    )
                )
        return results

    def _rule_matches(self, context: RoutingContext, rule: RoutingRule) -> bool:
        """Todas las condiciones de la regla deben cumplirse (AND)."""
        for condition in rule.conditions:
            if not self._condition_matches(context, condition):
                return False
        return True

    def _condition_matches(
        self,
        context: RoutingContext,
        condition: RoutingConditions,
    ) -> bool:
        """Computo local — condicionales, sin try/except.
        Condicion malformada (campo/operador desconocido): retorna False + log warning."""
        field = condition.get("field")
        operator = condition.get("operator")
        value = condition.get("value")

        if field not in ConditionField.__members__.values():
            logger.warning("Unknown condition field", extra={"field": field})
            return False
        if operator not in ConditionOperator.__members__.values():
            logger.warning("Unknown condition operator", extra={"operator": operator})
            return False

        context_value = self._get_context_value(context, field)
        return self._apply_operator(context_value, operator, value)
```

### Tabla de operadores

| Operador | Tipo de value | Logica |
|----------|---------------|--------|
| `eq` | `str` | `context_value == value` (case-insensitive) |
| `contains` | `str` | `value.lower() in context_value.lower()` |
| `in` | `list[str]` | `context_value.lower() in [v.lower() for v in value]` |
| `not_in` | `list[str]` | `context_value.lower() not in [v.lower() for v in value]` |
| `starts_with` | `str` | `context_value.lower().startswith(value.lower())` |
| `matches_domain` | `str` | soporte wildcard: `"*.company.com"` matchea `"subdomain.company.com"` |

## Determinacion de prioridad (computo local)

La prioridad de despacho se determina en este orden (sin try/except — condicionales):

```python
def _determine_dispatch_priority(
    context: RoutingContext,
    rule_priority: int,
    vip_senders: frozenset[str],
) -> Literal["urgent", "normal", "low"]:
    """Computo local — condicionales deterministicos."""
    # 1. VIP sender (Tier 2): maxima prioridad siempre
    if context.sender_email.lower() in vip_senders:
        return "urgent"
    if any(context.sender_domain.endswith(d) for d in _vip_domains(vip_senders)):
        return "urgent"

    # 2. Classification-based: action urgente siempre es urgent
    if context.action_slug == "urgent":
        return "urgent"

    # 3. Keyword escalation en subject
    URGENT_KEYWORDS = frozenset({"urgent", "asap", "immediately", "legal", "security breach"})
    if any(kw in context.subject.lower() for kw in URGENT_KEYWORDS):
        return "urgent"

    # 4. Rule priority map: 0-33=low, 34-66=normal, 67+=urgent
    if rule_priority >= 67:
        return "urgent"
    if rule_priority >= 34:
        return "normal"
    return "low"
```

Las `URGENT_KEYWORDS` son constantes en el modulo — no strings magic dispersos.

## Idempotencia de despacho (Sec 3.5)

```python
def _compute_dispatch_id(
    email_id: uuid.UUID,
    rule_id: uuid.UUID,
    channel: str,
    destination: str,
) -> str:
    """
    Hash deterministico para idempotencia de despacho.
    Computo local — condicionales, sin try/except.
    Mismo input siempre produce mismo dispatch_id.
    """
    import hashlib
    raw = f"{email_id}:{rule_id}:{channel}:{destination}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
```

Antes de cada despacho, el servicio verifica si ya existe un `RoutingAction` con ese `dispatch_id`. Si existe con `status=DISPATCHED`, se omite el despacho y se retorna el `RoutingAction` existente. Si existe con `status=FAILED`, se reintenta (el retry Celery generara el mismo `dispatch_id`, lo que esta bien — es una re-ejecucion legitima).

## Patron de fallo parcial (pre-mortem Cat 6 — D13)

```python
async def _dispatch_rule_actions(
    self,
    context: RoutingContext,
    match: RuleMatchResult,
    email: Email,
    db: AsyncSession,
) -> list[uuid.UUID]:
    """
    Despacha todas las acciones de una regla.
    Cada accion es independiente: fallo en accion N no detiene accion N+1.
    Cada RoutingAction hace su propio commit (D13).
    """
    action_ids: list[uuid.UUID] = []

    for action_def in match.actions:
        dispatch_id = _compute_dispatch_id(
            context.email_id, match.rule_id, action_def.channel, action_def.destination
        )

        # Verificar idempotencia (estado externo — try/except)
        try:
            existing = await self._find_existing_dispatch(dispatch_id, db)
        except SQLAlchemyError as exc:
            logger.error("Failed to check dispatch idempotency", extra={"dispatch_id": dispatch_id, "error": str(exc)})
            continue  # No despachar si no podemos verificar idempotencia

        if existing is not None and existing.status == RoutingActionStatus.DISPATCHED:
            logger.info("Skipping already dispatched action", extra={"dispatch_id": dispatch_id})
            action_ids.append(existing.id)
            continue

        # Construir RoutingPayload (computo local — sin try/except)
        payload = self._build_routing_payload(context, action_def, match)

        # Despacho al adapter (estado externo — try/except especifico)
        adapter = self._get_adapter(action_def.channel)
        try:
            delivery_result = await adapter.send_notification(payload)
        except ChannelAuthError as exc:
            await self._record_routing_action(db, context, match, action_def, dispatch_id, failed=True, error=str(exc))
            logger.error("Channel auth error — check adapter credentials", extra={"channel": action_def.channel, "error": str(exc)})
            continue  # No lanzar — fallo parcial es aceptable (Cat 6)
        except ChannelRateLimitError as exc:
            await self._record_routing_action(db, context, match, action_def, dispatch_id, failed=True, error=str(exc))
            logger.warning("Channel rate limited", extra={"retry_after": exc.retry_after_seconds})
            continue
        except ChannelConnectionError as exc:
            await self._record_routing_action(db, context, match, action_def, dispatch_id, failed=True, error=str(exc))
            continue
        except ChannelDeliveryError as exc:
            await self._record_routing_action(db, context, match, action_def, dispatch_id, failed=True, error=str(exc))
            continue

        # Persistir exito (estado externo — try/except)
        try:
            action_id = await self._record_routing_action(
                db, context, match, action_def, dispatch_id,
                failed=False, message_ts=delivery_result.message_ts
            )
            await db.commit()  # D13: commit por accion individual
            action_ids.append(action_id)
        except SQLAlchemyError as exc:
            logger.error("Failed to persist routing action", extra={"error": str(exc)})

    return action_ids
```

## Estado final del email (pre-mortem Cat 1 — D10)

```
Email state despues del routing:

  Al menos 1 RoutingAction con status=DISPATCHED  →  ROUTED
  Todas las RoutingActions con status=FAILED      →  ROUTING_FAILED
  Sin reglas matching (unrouted)                  →  ROUTED
    (el email aparece en dashboard bajo "unrouted" — esto es un estado valido,
     no un error; el reviewer puede enrutar manualmente)
```

La transicion de estado es exactamente una — al final del routing completo, no por accion individual. Si hay 0 reglas activas, el email transiciona a `ROUTED` igualmente (unrouted es un caso de negocio, no un error de pipeline).

```python
# Al final de RoutingService.route() — computo local para determinar estado final
dispatched_count = sum(1 for a in all_actions if a.status == RoutingActionStatus.DISPATCHED)
failed_count = sum(1 for a in all_actions if a.status == RoutingActionStatus.FAILED)

if len(matched_rules) == 0:
    # Sin reglas: unrouted — sigue siendo ROUTED (no ROUTING_FAILED)
    new_state = EmailState.ROUTED
elif dispatched_count > 0:
    new_state = EmailState.ROUTED
else:
    new_state = EmailState.ROUTING_FAILED

email.transition_to(new_state)
await db.commit()  # D13: commit de transicion de estado independiente
```

## VIP sender priority (Tier 2)

La lista VIP se carga desde `ROUTING_VIP_SENDERS` (env var, lista separada por comas de emails y dominios). Tambien puede estar en una tabla `VipSender` futura — por ahora env var es suficiente para Tier 2.

```
ROUTING_VIP_SENDERS=ceo@company.com,*.board.company.com,vip@partner.com
```

La carga de VIP senders ocurre una vez al iniciar el servicio (no por email). El servicio debe recargar si la configuracion cambia — en Phase N esto se hace via reinicio del worker (aceptable para Tier 2).

## Rule testing mode (Tier 2)

```python
async def test_route(
    self,
    context: RoutingContext,
    db: AsyncSession,
) -> RuleTestResult:
    """
    Dry-run del motor de reglas.
    GARANTIA: No crea RoutingAction, no llama a ningun adapter, no cambia estado del email.
    Util para que el usuario valide reglas antes de activarlas.
    """
    # Carga de reglas (estado externo — try/except)
    try:
        rules = await self._load_active_rules(db)
    except SQLAlchemyError as exc:
        raise SQLAlchemyError(f"Failed to load routing rules: {exc}") from exc

    # Evaluacion (computo local — sin try/except)
    matches = self._rule_engine.evaluate(context, rules)

    would_dispatch: list[RoutingActionDef] = [
        action
        for match in matches
        for action in match.actions
    ]

    return RuleTestResult(
        context=context,
        rules_matched=matches,
        would_dispatch=would_dispatch,
        total_actions=len(would_dispatch),
    )
```

## Construccion de RoutingPayload (computo local)

El `RoutingPayload` (B5) se construye a partir del `RoutingContext` y `RuleMatchResult`. Es computo local — condicionales, sin try/except. La funcion `_build_routing_payload()` vive en `routing.py` como metodo privado del servicio.

```python
def _build_routing_payload(
    self,
    context: RoutingContext,
    action_def: RoutingActionDef,
    match: RuleMatchResult,
) -> RoutingPayload:
    """Computo local — sin try/except. RoutingContext valido garantiza no-fallo."""
    from src.adapters.channel.schemas import (
        RoutingPayload, SenderInfo, ClassificationInfo, Destination
    )
    from datetime import datetime, timezone

    priority = _determine_dispatch_priority(
        context, match.priority, self._vip_senders
    )

    return RoutingPayload(
        email_id=str(context.email_id),
        subject=context.subject,
        sender=SenderInfo(email=context.sender_email, name=context.sender_name),
        classification=ClassificationInfo(
            action=context.action_slug,
            type=context.type_slug,
            confidence=context.confidence,
        ),
        priority=priority,
        snippet=context.snippet[:self._config.routing_snippet_length],
        dashboard_link=f"{self._config.dashboard_base_url}/emails/{context.email_id}",
        timestamp=datetime.now(timezone.utc),
    )
```

## Defaults load-bearing (Cat 8 pre-mortem)

| Default | Valor | Env Var | Consecuencia si incorrecto |
|---------|-------|---------|---------------------------|
| Max reintentos por accion | `3` | `ROUTING_MAX_RETRIES` | Muy alto: spammea el canal durante outage. Muy bajo: fallos transitorios no se recuperan |
| Backoff base | `60` s | `ROUTING_BACKOFF_BASE_SECONDS` | Muy bajo: rate-limit inmediato en Slack. Muy alto: emails urgentes llegan tarde |
| Canal de fallback | `""` (ninguno) | `ROUTING_FALLBACK_CHANNEL` | Sin configurar: emails sin canal valido desaparecen silenciosamente |
| Snippet de routing | `150` chars | `ROUTING_SNIPPET_LENGTH` | Debe coincidir con `CHANNEL_SNIPPET_LENGTH` de B5; inconsistencia visual |
| Dashboard base URL | `http://localhost:3000` | `ROUTING_DASHBOARD_BASE_URL` | URL incorrecta: botones "View in Dashboard" en Slack llevan a 404 |
| VIP senders | `""` (vacio) | `ROUTING_VIP_SENDERS` | Sin configurar: prioridad VIP nunca aplica — aceptable como default |
| Keywords de escalado | constantes en codigo | `ROUTING_URGENT_KEYWORDS` (futuro) | Por ahora hardcoded como `frozenset` — D14: mover a config en Phase N |

## Estructura de archivos esperada

```
src/services/
├── routing.py              # RoutingService
├── rule_engine.py          # RuleEngine (puro, sin I/O)
└── schemas/
    ├── __init__.py
    ├── classification.py   # de B8
    └── routing.py          # RoutingContext, RoutingResult, RuleTestResult, etc.
```

## Notas de integracion con B5 (ChannelAdapter)

El `RoutingService` registra adapters por nombre de canal:

```python
class RoutingService:
    def __init__(
        self,
        llm_adapter: LLMAdapter,  # no usado en routing, pero inyectado para future B10
        channel_adapters: dict[str, ChannelAdapter],
        config: RoutingConfig,
    ) -> None:
        self._channel_adapters = channel_adapters
        ...

    def _get_adapter(self, channel: str) -> ChannelAdapter:
        adapter = self._channel_adapters.get(channel)
        if adapter is None:
            raise ValueError(f"No adapter registered for channel '{channel}'")
        return adapter
```

`channel_adapters` se inyecta como dependencia en el startup de FastAPI y en las tareas Celery. El servicio no instancia adapters — solo los usa. Esto permite swapping de adapters en tests sin subclasificar el servicio.

## Criterios de exito (deterministicos)

- [ ] `RoutingService.route()` acepta email en estado `CLASSIFIED` y retorna `RoutingResult` tipado sin `dict[str, Any]` en ninguna firma publica
- [ ] `RuleEngine.evaluate()` retorna reglas en el mismo orden de prioridad en que se recibieron (las reglas ya vienen ordenadas por `ORDER BY priority DESC` desde DB)
- [ ] Multiples reglas que hacen match todas ejecutan — no "first match wins"
- [ ] Email sin ninguna regla matching transiciona a `ROUTED` con `final_state="UNROUTED"` (no `ROUTING_FAILED`)
- [ ] `dispatch_id` para `(email_id, rule_id, channel, destination)` identico produce mismo hash en ejecuciones distintas
- [ ] Segundo despacho con mismo `dispatch_id` y `status=DISPATCHED` es omitido sin llamar al adapter
- [ ] Fallo de channel adapter en regla 1 no detiene la regla 2 — ambas `RoutingAction` creadas
- [ ] Email con todas las acciones fallidas transiciona a `ROUTING_FAILED`
- [ ] Email con al menos 1 accion exitosa transiciona a `ROUTED`
- [ ] `test_route()` no crea `RoutingAction`, no llama adapter, no cambia `email.state` — verificable por mock `assert_not_called()`
- [ ] VIP sender eleva prioridad a `"urgent"` independientemente de la clasificacion
- [ ] `RuleEngine` no tiene try/except — 0 bloques try en `rule_engine.py` (verificable con grep), excepto el handler de campo/operador desconocido que usa condicionales
- [ ] Contract-docstring presente en `RoutingService.route()` y `RuleEngine.evaluate()` con las 4 secciones
- [ ] `RoutingConfig` carga todos los defaults desde env vars via pydantic-settings — ningun valor hardcodeado en el servicio
- [ ] `ruff check src/services/routing.py src/services/rule_engine.py` — 0 violaciones
- [ ] `mypy src/services/routing.py src/services/rule_engine.py src/services/schemas/routing.py` — 0 errores
- [ ] Todos los tests pasan sin llamadas reales a channel adapters ni DB de produccion

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**
1. `mypy src/services/routing.py src/services/rule_engine.py src/services/schemas/routing.py` — si falla, corregir tipos antes de cualquier otro gate
2. `ruff check src/services/routing.py src/services/rule_engine.py src/services/schemas/ && ruff format --check src/services/routing.py src/services/rule_engine.py src/services/schemas/` — si falla, corregir lint
3. `pytest tests/services/routing/test_rule_engine.py -v` — todos los operadores, condiciones AND, regla inactiva, campo desconocido
4. `pytest tests/services/routing/test_idempotency.py -v` — hash deterministico, skip de dispatch existente
5. `pytest tests/services/routing/test_rule_test_mode.py -v` — dry-run garantias
6. `pytest tests/services/routing/test_routing_service.py -v` — contrato completo con mocks de adapter y DB
7. `pytest tests/services/routing/ -v` — suite completa del modulo

**Verificaciones criticas (no automatizables):**
- Revisar manualmente que `rule_engine.py` no tiene imports de `src.models.*` ni de `src.adapters.*` — el motor de reglas solo conoce `RoutingContext` y los TypedDicts de B1
- Verificar que cada `await db.commit()` en `_dispatch_rule_actions()` es independiente por accion (no un commit al final del loop)
- Inquisidor ejecuta revision via tighten-types: confirmar que `RoutingConditions` TypedDict de B1 y `RoutingActionDef` Pydantic del servicio son claramente distinguibles en el codigo
- Verificar que la tabla de operadores esta completa y cada operador tiene test individual en `test_rule_engine.py`
