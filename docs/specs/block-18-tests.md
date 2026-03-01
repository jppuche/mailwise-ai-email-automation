# Bloque 18: Test Suite

## Objetivo

Implementar los tests E2E del pipeline completo (email FETCHED → COMPLETED a traves de las
7 etapas), tests de integracion cross-block (API + pipeline juntos), y un analisis de gaps de
cobertura con tests focalizados para alcanzar >70% en `src/`. Este bloque NO escribe tests
unitarios por bloque — esos son escritos por Inquisidor durante la implementacion de cada bloque
(B0-B17). B18 cubre exclusivamente lo que ningun bloque individual puede cubrir: la cadena
completa de extremo a extremo y los gaps de cobertura residuales.

## Dependencias

- Bloque 12 (Pipeline): `ingest_task`, `classify_task`, `route_task`, `crm_sync_task`,
  `draft_task`, `run_pipeline`, `IngestResult`, `ClassifyResult`, `RouteResult`,
  `CRMSyncResult`, `DraftResult`, `PipelineRunRecord`
- Bloque 13 (API Core): todos los routers, `exception_handlers.py`, health endpoint
- Bloque 14 (API Config & Analytics): category management, routing rule CRUD,
  integration config, analytics endpoints
- Bloque 7 (Ingestion): `IngestionService` — para setup de email en estado FETCHED
- Bloque 8 (Classification): `ClassificationService`, `ClassificationResult`
- Bloque 9 (Routing): `RoutingService`, `RoutingRule`, `RoutingAction`
- Bloque 10 (CRM Sync): `CRMSyncService`
- Bloque 11 (Draft Generation): `DraftGenerationService`
- Bloque 1 (Models): `Email`, `EmailState`, `Draft`, `DraftStatus`, `EmailAccount`
- Bloque 2 (Auth): `AuthService`, JWT fixtures
- Todos los adapters (B3-B6): mocked en tests E2E

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/core/logging.py` — Si aun no existe: structured JSON logging para todos los tests.
  Si ya existe (creado en B19): no modificar aqui.

### Frontend (frontend-worker)

- N/A — Este bloque es backend-only. Los tests Playwright E2E del dashboard se especifican
  en B17 (frontend worker escribe sus propios tests durante implementacion).

### Tests (Inquisidor)

- `tests/conftest.py` — Fixtures compartidas de sesion: DB de test (PostgreSQL en Docker),
  Redis de test, `async_client` (httpx AsyncClient contra FastAPI app), factories
  importadas de `tests/factories.py`, mocked adapters registrados via DI override.
- `tests/factories.py` — factory-boy factories para todos los modelos del dominio.
  Ver seccion "Factory Definitions" abajo.
- `tests/e2e/conftest.py` — Fixtures E2E adicionales: mocked adapter stubs con respuestas
  realistas, email de muestra representando cada combinacion de clasificacion.
- `tests/e2e/test_pipeline_e2e.py` — Test principal: email pasa por todos los estados
  FETCHED → SANITIZED → CLASSIFIED → ROUTED → CRM_SYNCED → DRAFT_GENERATED → COMPLETED.
  Verificacion de estado, datos persistidos, y resultados por etapa.
- `tests/e2e/test_pipeline_partial_failure.py` — Fallo en cada etapa N: verificar que
  N-1 esta comprometido en DB, error state registrado, retry restaura progresion.
  Un escenario de fallo por cada una de las 5 tareas Celery.
- `tests/e2e/test_api_pipeline_integration.py` — API trigger de pipeline: POST a
  `/api/emails/{id}/retry` envia `run_pipeline`, estado cambia en DB, polling de
  `/api/emails/{id}` refleja estado final.
- `tests/e2e/test_draft_workflow.py` — Draft approve/reject/reassign E2E: draft aprobado
  llama al adapter de email con el contenido correcto; draft rechazado queda en
  `DRAFT_REJECTED`; reassign cambia destinatario y vuelve a `DRAFT_PENDING`.
- `tests/e2e/test_config_changes.py` — Cambios de configuracion afectan pipeline:
  cambiar categoria en `/api/categories` refleja en siguiente clasificacion; nueva
  regla de routing en `/api/routing-rules` activa en siguiente routing.
- `tests/coverage/` — Directorio para tests de gap-fill generados despues del analisis de
  cobertura. Nombres de archivo por modulo: `test_gap_<module_name>.py`. Estos archivos
  no son parte del spec estatico — se generan dinamicamente post-analisis.

## Skills aplicables

- **alignment-chart** (CRITICO): Aplicado en la seccion "Alignment Chart Analysis" abajo.
  Categorizar cada tipo de test por posicion (Lawful Good / Chaotic Good / Neutral / Evil)
  y derivar reglas de calidad concretas. Prohibir tests "Evil" via criterios de exit.
- **tighten-types** (ALTO): Fixtures de tests deben ser completamente tipadas — sin
  `dict[str, Any]` en firmas de factory methods ni en parametros de fixtures. Los mocked
  adapters retornan los mismos tipos tipados que los adapters reales.
- **try-except** (ALTO): Tests de excepcion verifican tipos especificos de excepcion, no
  `Exception` generico. `pytest.raises(SpecificError)` en todos los tests de error path.
- **pre-mortem** (MEDIO): Ver "Pre-Mortem Analysis" abajo. Cat 6 (non-atomic) es el
  concern principal — verificar que commits independientes por etapa son testables.

## Alignment Chart Analysis

El alignment-chart skill categoriza funciones/tests por correctitud y colaboracion:
- **Lawful Good:** Correcto Y fuerza a los vecinos a ser correctos. Un test Lawful Good
  atrapa bugs reales Y su mensaje de fallo identifica la causa exacta.
- **Chaotic Good:** Correcto pero tolerante. Funciona en aislamiento, puede perder fallos
  de integracion.
- **Neutral:** Patron ambiguo. Dificil de decir si es un problema.
- **Evil:** Donde viven los bugs. Tests que pasan pero no verifican lo que dicen verificar.

| Tipo de test | Alineacion | Razon | Riesgo si prolifera |
|---|---|---|---|
| E2E pipeline (todas las etapas) | **Lawful Good** | Valida la cadena completa; un fallo de etapa N falla el test y el mensaje identifica que etapa fallo | Alto costo de setup; justificado por valor maximo |
| E2E fallo parcial por etapa | **Lawful Good** | Verifica que N-1 persiste cuando N falla — el contrato de independencia de etapas (D13) | Sin este test, D13 es convencion no verificada |
| Integracion cross-block API+pipeline | **Lawful Good** | Verifica la interaccion real entre capa API y capa de tareas; falla si el DI no esta correcto | Puede ser lento; usar con selectividad |
| Tests unitarios de servicios (B7-B11) | **Chaotic Good** | Rapidos, aislados, buenos para TDD. No detectan problemas de integracion entre servicios | Pueden dar falsa confianza si los mocks no reflejan contratos reales |
| Tests de adapters con mock externo | **Neutral** | El mock puede divergir del API real. Pasan aunque el contrato del API externo cambie | Deben complementarse con tests de contrato (no en scope de B18) |
| `assert response.status_code == 200` sin verificar body | **Evil** | Pasa aunque el body este vacio, malformado, o tenga datos de otro email | **PROHIBIDO** — ver reglas de calidad abajo |
| `assert result is not None` como unica asercion | **Evil** | Pasa aunque `result` sea un objeto completamente incorrecto | **PROHIBIDO** |
| `pytest.raises(Exception)` sin tipo especifico | **Evil** | Pasa aunque se lance un tipo de excepcion completamente diferente al esperado | **PROHIBIDO** |
| Mocks verificados solo por existencia, no por args | **Neutral** → **Evil** | Mock que existe pero no verifica args: el servicio podia llamar al adapter con datos erroneos | Siempre usar `mock.assert_called_once_with(...)` |

### Reglas de calidad derivadas del alignment-chart (aplicadas como criterios de exit)

1. **Todo test de API DEBE verificar el body de la respuesta**, no solo el status code.
   `assert response.json()["id"] == str(email.id)` — no solo `assert response.status_code == 200`.

2. **Todo test de excepcion DEBE especificar el tipo exacto.**
   `pytest.raises(LLMRateLimitError)` — no `pytest.raises(Exception)`.

3. **Todo test de transicion de estado DEBE verificar estado anterior Y estado posterior.**
   ```python
   assert email_before.state == EmailState.CLASSIFIED
   await trigger_route_task(email_id)
   assert email_after.state == EmailState.ROUTED
   ```

4. **Todo mock de adapter DEBE verificar que fue llamado con los argumentos correctos.**
   ```python
   mock_slack.send_notification.assert_called_once_with(
       destination=expected_channel,
       payload=expected_payload,
   )
   ```

5. **Prohibido `assert True`, `assert result is not None` como unica asercion.**
   Si un test solo puede afirmar "algo retorno", el test no esta verificando ningun contrato.

6. **Tests E2E DEBEN verificar datos en DB, no solo respuestas HTTP.**
   Despues de un pipeline completo: `SELECT * FROM emails WHERE id = ?` y verificar
   `state`, `classification_result`, `routing_actions`, `draft_id`.

## Pre-Mortem Analysis

### Fragility: Estado de DB compartido entre tests contamina resultados

- **Category:** Cat 6 (non-atomic) + Cat 1 (implicit ordering)
- **What breaks:** Si los tests E2E no limpian la DB entre ejecuciones, emails de un test
  aparecen en queries de otro test. Tests de cobertura de analiticas cuentan emails de otros
  tests. Fallo intermitente: pasa en aislamiento, falla en suite completa.
- **Hardening:** Cada test E2E corre en una transaccion que se rollback al finalizar
  (patron `session.begin_nested()` o fixture `db_rollback`). Para tests que requieren
  commits reales (E2E de pipeline que usa Celery sync): usar DB separada por test class
  con `CREATE/DROP SCHEMA`. `conftest.py` implementa el patron correcto y lo documenta.

### Fragility: Mocked adapters divergen de contratos reales con el tiempo

- **Category:** Cat 10 (version-coupled)
- **What breaks:** Los adapters de Gmail, Slack, HubSpot, LiteLLM se mockean en los tests
  E2E. Si el adapter real cambia su firma (B3-B6 son actualizados) pero el mock en
  `conftest.py` no se actualiza, los tests E2E siguen pasando con el mock viejo. El bug
  real solo se descubre en produccion.
- **Hardening:** Los mocked adapters en `conftest.py` deben implementar los mismos
  Protocols/ABCs que los adapters reales. Si el adapter real cambia su firma y el ABC
  cambia, mypy fallara en el mock porque el mock no cumple el Protocol. Esto convierte
  el problema de "mock divergente silencioso" en un error de typecheck.

### Fragility: Tests E2E lentos bloquean el CI en cada PR

- **Category:** Cat 8 (load-bearing defaults)
- **What breaks:** Un test E2E de pipeline completo puede tardar 10-30s si las tareas
  Celery corren con workers reales. Si hay 20+ tests E2E, el CI tarda >10 minutos.
  Los developers dejan de correr el suite.
- **Hardening:** Los tests E2E usan Celery en modo `CELERY_TASK_ALWAYS_EAGER=True` (tasks
  ejecutadas sincrono en el mismo proceso, sin worker externo). Esto mantiene la cobertura
  de integracion sin la latencia de workers reales. El valor de `CELERY_TASK_ALWAYS_EAGER`
  es configurable via env var de test — nunca hardcodeado en el codigo de produccion.

### Fragility: Cobertura se reporta pero no se verifica en CI

- **Category:** Cat 8 (load-bearing defaults)
- **What breaks:** `pytest --cov` genera reporte pero si nadie lo verifica, la cobertura
  puede caer por debajo del 70% silenciosamente tras agregar codigo no testeado en B13-B17.
- **Hardening:** `pytest --cov=src --cov-fail-under=70` en el gate de CI. El comando falla
  si la cobertura cae por debajo del umbral. El umbral es configurable via `pyproject.toml`
  `[tool.pytest.ini_options]` — no hardcodeado en scripts.

## Factory Definitions

Todas las factories heredan de `factory.Factory` (sync) o `factory.alchemy.SQLAlchemyModelFactory`
(para modelos con DB). Firmas completamente tipadas — sin `dict[str, Any]`.

```python
# tests/factories.py

class EmailFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Email

    id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    account_id: uuid.UUID = factory.LazyFunction(uuid.uuid4)
    gmail_message_id: str = factory.Sequence(lambda n: f"msg_{n:06d}")
    subject: str = factory.Faker("sentence", nb_words=6)
    from_address: str = factory.Faker("email")
    state: EmailState = EmailState.FETCHED
    received_at: datetime = factory.LazyFunction(datetime.utcnow)
    # Nota: subject/from_address estan en factories para test data setup.
    # Nunca aparecen en logs de produccion (PII policy B0).


class ClassificationResultFactory(SQLAlchemyModelFactory):
    class Meta:
        model = ClassificationResult  # SQLAlchemy model, no el dataclass del adapter

    email_id: uuid.UUID = factory.SubFactory(EmailFactory, state=EmailState.CLASSIFIED)
    action_category_id: int = factory.SelfAttribute("..action_category.id")
    type_category_id: int = factory.SelfAttribute("..type_category.id")
    confidence: float = factory.Faker("pyfloat", min_value=0.7, max_value=1.0)
    classified_at: datetime = factory.LazyFunction(datetime.utcnow)


class RoutingRuleFactory(SQLAlchemyModelFactory):
    class Meta:
        model = RoutingRule

    name: str = factory.Sequence(lambda n: f"Rule {n}")
    priority: int = factory.Sequence(lambda n: n * 10)
    is_active: bool = True
    conditions: dict = factory.LazyFunction(lambda: {"action_category": "support"})


class RoutingActionFactory(SQLAlchemyModelFactory):
    class Meta:
        model = RoutingAction

    rule_id: int = factory.SubFactory(RoutingRuleFactory)
    channel: str = "slack"
    destination: str = factory.Faker("slug")
    generate_draft: bool = False
    crm_sync: bool = False


class DraftFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Draft

    email_id: uuid.UUID = factory.SubFactory(EmailFactory)
    body: str = factory.Faker("paragraphs", nb=2, as_text=True)
    status: DraftStatus = DraftStatus.PENDING
    created_at: datetime = factory.LazyFunction(datetime.utcnow)


class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User

    email: str = factory.Faker("email")
    hashed_password: str = factory.LazyFunction(lambda: AuthService.hash_password("test_password"))
    role: UserRole = UserRole.REVIEWER
    is_active: bool = True
```

## E2E Pipeline Test: Diseno detallado

### test_pipeline_e2e.py — Happy path completo

```python
async def test_email_full_pipeline_happy_path(
    db: AsyncSession,
    redis_client: Redis,
    mock_gmail_adapter: MockGmailAdapter,
    mock_slack_adapter: MockSlackAdapter,
    mock_hubspot_adapter: MockHubSpotAdapter,
    mock_llm_adapter: MockLLMAdapter,
    email_factory: EmailFactory,
    routing_rule_factory: RoutingRuleFactory,
) -> None:
    """
    E2E: Email FETCHED → SANITIZED → CLASSIFIED → ROUTED → CRM_SYNCED →
         DRAFT_GENERATED → COMPLETED.

    Verifica:
    1. Cada transicion de estado ocurre en orden (D10)
    2. Datos de cada etapa persisten en DB antes de la siguiente etapa (D13)
    3. Adapters llamados con argumentos correctos (alignment-chart regla 4)
    4. Estado final COMPLETED con todos los sub-records presentes
    """
    # Setup: email en estado FETCHED, regla con crm_sync=True y generate_draft=True
    email = await email_factory.create(state=EmailState.FETCHED)
    rule = await routing_rule_factory.create_with_actions(
        crm_sync=True, generate_draft=True
    )

    # Act: ejecutar pipeline completo (Celery en modo eager)
    run_pipeline(email.id)

    # Assert: estado final
    await db.refresh(email)
    assert email.state == EmailState.COMPLETED  # no solo "not FETCHED"

    # Assert: ClassificationResult existe en DB con campos reales
    classification = await db.get(ClassificationResult, email.id)
    assert classification is not None
    assert classification.confidence > 0.0
    assert classification.action_category_id is not None  # no solo "exists"

    # Assert: RoutingAction ejecutada y registrada
    routing_actions = await db.scalars(
        select(RoutingAction).where(RoutingAction.email_id == email.id)
    )
    actions = routing_actions.all()
    assert len(actions) == 1
    assert actions[0].dispatched_at is not None

    # Assert: Draft generado
    draft = await db.scalar(select(Draft).where(Draft.email_id == email.id))
    assert draft is not None
    assert draft.status == DraftStatus.PENDING
    assert len(draft.body) > 0  # no solo "exists"

    # Assert: PipelineRunRecord con todos los resultados de etapa
    run_record = await db.scalar(
        select(PipelineRunRecord).where(PipelineRunRecord.email_id == email.id)
    )
    assert run_record is not None
    assert run_record.ingest_result is not None
    assert run_record.classify_result is not None
    assert run_record.route_result is not None
    assert run_record.crm_sync_result is not None
    assert run_record.draft_result is not None

    # Assert: adapters llamados con args correctos (alignment-chart regla 4)
    mock_slack_adapter.send_notification.assert_called_once()
    call_kwargs = mock_slack_adapter.send_notification.call_args.kwargs
    assert call_kwargs["destination"] == rule.actions[0].destination

    mock_hubspot_adapter.upsert_contact.assert_called_once()
    mock_llm_adapter.classify.assert_called_once()
    mock_llm_adapter.generate_draft.assert_called_once()
```

### test_pipeline_partial_failure.py — Fallo por etapa

Cinco scenarios, uno por tarea. Patron comun:

```python
async def test_classify_task_failure_preserves_ingest_result(
    db: AsyncSession,
    mock_llm_adapter: MockLLMAdapter,
    email_factory: EmailFactory,
) -> None:
    """
    Fallo en classify_task:
    - Email permanece en DB (SANITIZED, no rollback)
    - ClassificationResult NO existe en DB (no commit parcial)
    - PipelineRunRecord registra classify_result.success=False
    - Email puede ser reintentado desde API
    """
    email = await email_factory.create(state=EmailState.FETCHED)
    mock_llm_adapter.classify.side_effect = LLMConnectionError("LLM unavailable")

    # ingest_task debe completar (SANITIZED comprometido)
    ingest_task(str(email.id))

    await db.refresh(email)
    assert email.state == EmailState.SANITIZED  # ingest exitoso, no revertido (D13)

    # classify_task debe fallar
    with pytest.raises(LLMConnectionError):  # tipo especifico, no Exception
        classify_task(str(email.id))

    # ClassificationResult no existe — fallo antes del commit
    classification = await db.scalar(
        select(ClassificationResult).where(ClassificationResult.email_id == email.id)
    )
    assert classification is None  # no "assert result is None or ..."

    # Estado del email: no avanzado por encima de SANITIZED
    await db.refresh(email)
    assert email.state == EmailState.SANITIZED
```

## Mocked Adapters: estructura

Los mocked adapters implementan los mismos ABCs/Protocols que los adapters reales.
mypy verifica que los mocks cumplen los contratos (hardening Cat 10).

```python
# tests/e2e/conftest.py

class MockGmailAdapter:
    """Implements EmailAdapter Protocol. Verified by mypy via Protocol check."""

    async def fetch_messages(
        self, account_id: uuid.UUID, max_results: int
    ) -> list[RawEmailMessage]:
        return [_make_sample_raw_email()]

    async def send_draft(self, draft_id: str, body: str) -> SentMessageId:
        return SentMessageId("mock_sent_id_001")

    async def test_connection(self) -> bool:
        return True


class MockLLMAdapter:
    """Implements LLMAdapter Protocol."""

    def classify(
        self, prompt: ClassifyPrompt
    ) -> AdapterClassificationResult:
        return AdapterClassificationResult(
            action_category="support",
            type_category="question",
            confidence=0.92,
            reasoning="Mock classification",
        )

    def generate_draft(self, context: DraftContext) -> DraftText:
        return DraftText(
            body="Mock draft body for testing purposes.",
            subject="Re: Mock Subject",
        )
```

## Analisis de gaps de cobertura: proceso

Despues de completar B0-B17 y sus tests por bloque:

```bash
# Paso 1: ejecutar suite completa con reporte de cobertura
pytest --cov=src --cov-report=term-missing --cov-report=html:htmlcov/ -q

# Paso 2: identificar modulos por debajo del 70%
# La salida term-missing muestra lineas no cubiertas por modulo

# Paso 3: para cada modulo bajo 70%:
# - Identificar que tipo de path no esta cubierto (error paths, edge cases, config variations)
# - Escribir test minimo que cubre ese path
# - Re-ejecutar cobertura para confirmar mejora

# Paso 4: verificar umbral global
pytest --cov=src --cov-fail-under=70
```

Prioridades de gap-fill (por impacto):
1. Error paths en servicios (LLMConnectionError, CRMAuthError, etc.) — alta probabilidad
   de que los tests por bloque cubran happy path pero no todos los errores
2. Configuracion alternativa — tests con settings no-default (modelo LLM diferente,
   retry counts alternativos)
3. Edge cases de sanitizacion — emails con adjuntos, emails sin body, encoding no-ASCII
4. Paginacion en API — primera pagina, ultima pagina, pagina vacia, pagina fuera de rango

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Criterios de exito (deterministicos)

### Calidad de codigo

- [ ] `ruff check tests/` — 0 violaciones
- [ ] `ruff format tests/ --check` — 0 diferencias
- [ ] `mypy tests/` — 0 errores de tipo (mocked adapters cumplen Protocols)

### Cobertura (target >70%)

- [ ] `pytest --cov=src --cov-fail-under=70` — sale con codigo 0
- [ ] HTML coverage report generado en `htmlcov/` — inspeccionable post-run

### E2E pipeline (test_pipeline_e2e.py)

- [ ] Happy path: email pasa por TODOS los estados en orden: FETCHED → SANITIZED →
  CLASSIFIED → ROUTED → CRM_SYNCED → DRAFT_GENERATED → COMPLETED
- [ ] Happy path: `ClassificationResult`, `RoutingAction`, `Draft`, `PipelineRunRecord`
  existen en DB con campos no-nulos al finalizar
- [ ] Happy path: mocked adapters verificados con `assert_called_once_with(...)` — no solo
  con `assert_called()`
- [ ] Fallo en ingest_task: email queda en estado FETCHED, sin SANITIZED state, sin crash
  en las tareas siguientes (no se encolan)
- [ ] Fallo en classify_task: email en SANITIZED, sin ClassificationResult en DB
- [ ] Fallo en route_task: email en CLASSIFIED, ClassificationResult existe, sin RoutingAction
- [ ] Fallo en crm_sync_task: email en ROUTED, RoutingActions existen, sin CRM record
- [ ] Fallo en draft_task: email en ROUTED o CRM_SYNCED, sin Draft en DB
- [ ] Retry tras fallo: despues de reparar el mock y llamar a la tarea de nuevo, el email
  avanza correctamente al estado siguiente

### Integracion cross-block (test_api_pipeline_integration.py)

- [ ] `POST /api/emails/{id}/retry`: retorna 202, email en DB cambia a estado de procesamiento
- [ ] `GET /api/emails/{id}`: despues del pipeline, retorna estado COMPLETED con
  classification y draft en el body (no solo status 200)
- [ ] Draft approve workflow: `POST /api/drafts/{id}/approve` llama al adapter de email con
  el body del draft — verificado via mock con `assert_called_once_with`
- [ ] Draft reject workflow: `POST /api/drafts/{id}/reject` cambia estado a `DRAFT_REJECTED`
  — verificado en DB, no solo en respuesta HTTP
- [ ] Category creation via API se refleja en clasificacion del siguiente email (integracion
  B14 → B8)

### Reglas de calidad alignment-chart (Evil tests prohibidos)

- [ ] **Ninguna** asercion `assert response.status_code == 200` sin asercion sobre el body
  en el mismo test — verificable via `grep -rn "status_code == 200" tests/` seguido de
  inspeccion manual de que cada match tiene asercion de body en las 5 lineas siguientes
- [ ] **Ninguna** asercion `assert result is not None` o `assert True` como unica asercion
  en un test — verificable via `grep -rn "assert .* is not None$\|assert True$" tests/`
- [ ] **Ningun** `pytest.raises(Exception)` sin tipo especifico — verificable via
  `grep -rn "raises(Exception)" tests/` — resultado esperado: vacio
- [ ] **Ningun** mock verificado solo con `assert_called()` sin `assert_called_with` o
  `assert_called_once_with` — verificable via `grep -rn "\.assert_called()" tests/e2e/`

### Tipos (tighten-types — Directiva D1)

- [ ] Todos los metodos de factory tienen firmas tipadas — `mypy tests/factories.py` — 0 errores
- [ ] Mocked adapters en conftest.py implementan Protocols verificables por mypy — si el
  ABC/Protocol de B3-B6 cambia su firma, mypy falla en el mock antes de que falle el test
- [ ] Sin `dict[str, Any]` en firmas de fixtures de `conftest.py` —
  `grep -rn "dict\[str, Any\]" tests/conftest.py` — resultado esperado: vacio

### Manejo de excepciones (try-except — D7/D8)

- [ ] Tests de error path usan `pytest.raises(SpecificErrorType)` — nunca `Exception` base
- [ ] Tests de retry verifican que `self.retry()` fue llamado (mock del metodo `retry` de Celery)
- [ ] Tests de `CRMAuthError` verifican que no se llama a `self.retry()` (no-retry semantics B10)

### PII en fixtures de test

- [ ] Datos de factories con `from_address` y `subject` no aparecen en assertions de logs.
  Los tests de logging solo verifican `email_id` — nunca `from_address`, `subject`, o `body`.
  Verificable via `grep -rn "from_address\|subject\|body_plain" tests/e2e/` — 0 matches
  en assertions de logs.

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**

1. `mypy tests/factories.py` — factories tipadas, sin dependencias complejas
2. `mypy tests/conftest.py` — fixtures y mocked adapters cumplen Protocols
3. `ruff check tests/ && ruff format --check tests/`
4. `pytest tests/e2e/test_pipeline_e2e.py::test_email_full_pipeline_happy_path -v`
   — happy path antes de failure scenarios
5. `pytest tests/e2e/test_pipeline_partial_failure.py -v` — un test por etapa de fallo
6. `pytest tests/e2e/test_api_pipeline_integration.py -v` — cross-block integration
7. `pytest tests/e2e/test_draft_workflow.py -v` — draft approve/reject/reassign
8. `pytest tests/e2e/test_config_changes.py -v` — config changes affect pipeline
9. `pytest --cov=src --cov-report=term-missing -q` — coverage report para identificar gaps
10. Analizar reporte, escribir tests de gap-fill en `tests/coverage/`
11. `pytest --cov=src --cov-fail-under=70` — gate final de cobertura

**Verificaciones criticas (no automatizables):**

```bash
# Evil tests prohibidos: sin status_code-only assertions
grep -rn "status_code == 200" tests/e2e/
# Inspeccion manual: cada match debe tener asercion de body en lineas adyacentes

# Evil tests prohibidos: sin pytest.raises(Exception) generico
grep -rn "raises(Exception)" tests/
# Resultado esperado: vacio

# Evil tests prohibidos: sin assert is not None como unica asercion
grep -rn "assert .* is not None$" tests/e2e/
# Resultado esperado: vacio o matches con aserciones adicionales en el mismo test

# Mocked adapters cumplen Protocol (verificado por mypy, pero confirmar explicitamente)
mypy tests/e2e/conftest.py --strict

# PII policy: datos de test no en assertions de logs
grep -rn "from_address\|body_plain\|sender_name" tests/e2e/
# Resultado esperado: vacio en assertions de logs (puede aparecer en setup de factories)
```

**Consultas requeridas antes de implementar:**

- Consultar Inquisidor para confirmar el patron correcto de DB isolation en tests E2E que
  usan Celery eager mode + commits reales: `begin_nested()` rollback vs schema-per-test-class.
- Consultar Inquisidor para el patron de fixtures de factory-boy con SQLAlchemy 2.0 async:
  `SQLAlchemyModelFactory` con `AsyncSession` requiere configuracion especial.
- Consultar Sentinel para revisar que `CELERY_TASK_ALWAYS_EAGER=True` en tests no introduce
  diferencias de comportamiento de seguridad vs modo worker real (especialmente para
  exception handling en top-level handlers).

---

## Amendments (post-implementation review)

> **Date:** 2026-03-02 | **Scope:** Deltas between spec assumptions and codebase after B00-B13 implementation.
> Cross-cutting deltas referenced by ID — see below.

### Cross-cutting deltas

| ID | Spec assumption | Codebase reality | Source |
|----|-----------------|-------------------|--------|
| X1 | `Email.received_at` | `Email.date` | `src/models/email.py:105` |
| X2 | `Email.from_address` | `Email.sender_email` | `src/models/email.py:98` |
| X3 | `Draft.body` | `Draft.content` | `src/models/draft.py:47` |
| X4 | `User.email` | `User.username` | `src/models/user.py:42` |
| X6 | `EmailAccount` model | Does NOT exist — `Email.account` is `str` | `src/models/email.py:96` |
| X7 | `PipelineRunRecord` model | Does NOT exist anywhere in ORM | grep across `src/models/` |

### Delta table

| # | Category | Spec says | Codebase reality | Resolution |
|---|----------|-----------|-------------------|------------|
| 1 | Model | `PipelineRunRecord` used for E2E assertions (X7) | No such model exists | Verify pipeline via Email state transitions + child records (`ClassificationResult`, `RoutingAction`, `Draft`) |
| 2 | Factory | `EmailFactory.account_id: UUID` | `Email.account: str` (X6) | Use `account: str` in factory |
| 3 | Factory | `EmailFactory.gmail_message_id` | `Email.provider_message_id` (`src/models/email.py:101`) | Rename to `provider_message_id` |
| 4 | Factory | `EmailFactory.from_address` (X2) | `Email.sender_email` | Rename to `sender_email` |
| 5 | Factory | `EmailFactory.received_at` (X1) | `Email.date` | Rename to `date` |
| 6 | Factory | `ClassificationResultFactory.confidence: float` | `ClassificationConfidence` enum: `HIGH`/`LOW` (`src/models/classification.py:16`) | Use enum values, not float |
| 7 | Factory | `ClassificationResultFactory.*_category_id: int` | Type: `UUID` (all FK columns are UUID) | Use `uuid.UUID` |
| 8 | Factory | `RoutingActionFactory.generate_draft: bool` | Field does NOT exist on `RoutingAction` — it's in `RoutingRule.actions` JSONB (`src/models/routing.py:62`) | Remove from factory |
| 9 | Factory | `RoutingActionFactory.crm_sync: bool` | Same — not on `RoutingAction` model | Remove from factory |
| 10 | Factory | `DraftFactory.body` (X3) | `Draft.content` | Rename to `content` |
| 11 | Factory | `UserFactory.email` (X4) | `User.username` | Rename to `username` |
| 12 | Factory | `UserFactory.hashed_password` via `AuthService.hash_password()` | Auth uses `bcrypt` directly — passlib incompatible with bcrypt>=4.2 on Python 3.14 (`src/services/auth_service.py`) | Use `bcrypt.hashpw()` |
| 13 | Dep | `EmailAccount` model referenced in factories/tests (X6) | Does NOT exist | Remove all references — use `Email.account: str` |
| 14 | Type | `CRMSyncResult` | Actual: `CRMSyncTaskResult` (`src/tasks/result_types.py:46`) | Use actual name |
| 15 | Type | `DraftResult` | Actual: `DraftTaskResult` (`src/tasks/result_types.py:59`) | Use actual name |
| 16 | Import | `from src.tasks import ingest_task, ...` | `src/tasks/__init__.py` is empty — tasks live in individual modules | Import from `src.tasks.ingestion_task`, `src.tasks.classify_task`, etc. |
| 17 | Mock | `MockGmailAdapter.test_connection()` returns `bool` | All 4 adapters return `ConnectionTestResult` dataclass (`src/adapters/*/base.py`) | Match real return type |
| 18 | Mock | `MockLLMAdapter.classify()` shown as sync | Actual `classify()` is `async` (`src/adapters/llm/base.py`) | Use `async def` |
| 19 | Pattern | `ingest_task(str(email.id))` — direct call | Celery tasks: use `task.run()` for testing (bypasses dispatch, per CLAUDE.md learned pattern) | Use `task.run()` |
| 20 | State | `DRAFT_REJECTED` email state | No such `EmailState`; `DraftStatus.REJECTED` is on Draft model (`src/models/draft.py:20`) | Email stays `DRAFT_GENERATED`; assert `draft.status == DraftStatus.REJECTED` |
| 21 | Mock | Mock adapters as simple classes | Real adapters use `_ensure_connected()` + `assert self._client is not None` pattern | Use `connected_adapter` fixture pattern: set `_connected = True` directly (per B06 learned pattern) |
