# Bloque 4: LLM Adapter (LiteLLM)

## Objetivo

Implementar `LLMAdapter` ABC y `LiteLLMAdapter` concreto que retornan tipos `ClassificationResult` y `DraftText` — nunca `ModelResponse` raw — con parser de output y capa de validacion con fallback documentado.

## Dependencias

- Bloque 1 (Foundation: src layout, pyproject.toml, configuracion base, modelos SQLAlchemy)

## Archivos a crear/modificar

### Backend (backend-worker)

- `src/adapters/llm/__init__.py` — Re-exporta `LLMAdapter`, `LiteLLMAdapter`, `ClassificationResult`, `DraftText`
- `src/adapters/llm/base.py` — `LLMAdapter` ABC con firmas completamente tipadas (FOUNDATION.md Sec 9.5)
- `src/adapters/llm/litellm_adapter.py` — `LiteLLMAdapter` implementacion concreta; toda extraccion de `ModelResponse` ocurre aqui
- `src/adapters/llm/schemas.py` — Pydantic models: `ClassificationResult`, `DraftText`, `LLMConfig`, `ClassifyOptions`, `DraftOptions`, `ConnectionTestResult`
- `src/adapters/llm/parser.py` — Parser de output LLM: extraccion de JSON, normalizacion de casing, fallback path; operacion local (sin try/except — condicionales)
- `src/adapters/llm/exceptions.py` — Jerarquia de excepciones: `LLMAdapterError`, `LLMConnectionError`, `LLMRateLimitError`, `LLMTimeoutError`, `OutputParseError`

### Frontend (frontend-worker)

- N/A — este bloque es exclusivamente backend

### Tests (Inquisidor)

- `tests/adapters/llm/test_litellm_adapter.py` — Contrato del adapter con mocks de LiteLLM; nunca llama a API real
- `tests/adapters/llm/test_parser.py` — Casos edge del parser: JSON puro, wrapped en markdown, texto extra, thinking-mode tags, casing incorrecto, campos faltantes, fallback path
- `tests/adapters/llm/test_schemas.py` — Validacion Pydantic de `ClassificationResult` y `ClassifyOptions`

## Skills aplicables

- **tighten-types** (CRITICO): El adapter es el boundary exacto donde `ModelResponse` dinamico se convierte en tipos estaticos. Aplicar en planificacion (definir firmas antes de implementar), implementacion (verificar que nada de `dict[str, Any]` escape), y revision (mypy en modo estricto).
- **contract-docstrings** (CRITICO): Cada metodo del ABC requiere las 4 preguntas: preconditions, errors raised on violation, external state errors, silenced errors. Consultar antes de escribir docstrings.
- **try-except** (ALTO): Clasificacion exacta de operaciones. LLM API calls = external state (try/except con tipos especificos). Parsing de output = local computation (condicionales, no try/except). Consultar al definir los bloques try/except en `litellm_adapter.py`.
- **pre-mortem** (ALTO): Cat 4 (unstated preconditions sobre shape del output LLM) y Cat 8 (load-bearing defaults de temperatura/tokens). Consultar al disenar el parser y la tabla de defaults.

## Candidate Tools

No candidate tool dependencies — exit conditions achievable without candidates.

## Contratos de metodo (contract-docstrings — 4 preguntas)

### `LLMAdapter.classify(prompt, system_prompt, options) -> ClassificationResult`

```
Preconditions:
  - prompt: str no vacio; debe contener contenido de email sanitizado (SanitizedText)
  - system_prompt: str no vacio; debe incluir definiciones de categorias validas
  - options.allowed_actions: list[str] no vacia
  - options.allowed_types: list[str] no vacia
  - options.temperature en [0.0, 1.0]

Errors raised on violation:
  - ValueError si prompt o system_prompt estan vacios
  - ValueError si allowed_actions o allowed_types estan vacios

External state errors:
  - LLMConnectionError: proveedor LLM inalcanzable (red, DNS)
  - LLMRateLimitError: proveedor retorna 429; incluye retry_after_seconds si disponible
  - LLMTimeoutError: llamada supera LLM_TIMEOUT_SECONDS (default 30s)

Silenced errors:
  - OutputParseError: capturado internamente -> retorna ClassificationResult con
    fallback_applied=True, confidence="low", action="inform", type="notification"
  - El caller detecta el fallback via campo fallback_applied
  - raw_llm_output siempre se preserva para debugging
```

### `LLMAdapter.generate_draft(prompt, system_prompt, options) -> DraftText`

```
Preconditions:
  - prompt: str no vacio; debe contener contenido de email + contexto de routing
  - system_prompt: str no vacio; debe definir tono y estilo esperado
  - options.temperature en [0.0, 1.0]

Errors raised on violation:
  - ValueError si prompt o system_prompt estan vacios

External state errors:
  - LLMConnectionError: proveedor inalcanzable
  - LLMRateLimitError: proveedor retorna 429
  - LLMTimeoutError: llamada supera LLM_TIMEOUT_SECONDS

Silenced errors:
  - Ninguno — fallos en generacion de draft se surfacean al caller
  - No existe fallback seguro para texto libre; el caller decide reintentar o escalar
```

### `LLMAdapter.test_connection() -> ConnectionTestResult`

```
Preconditions:
  - LLMConfig valido cargado (model, api_key o base_url segun proveedor)

Errors raised on violation:
  - Ninguno — retorna ConnectionTestResult con success=False y error_detail

External state errors:
  - Capturados internamente -> ConnectionTestResult(success=False, error_detail=str(e))

Silenced errors:
  - Todos — este metodo nunca lanza; siempre retorna ConnectionTestResult
```

## Esquemas Pydantic (schemas.py)

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, field_validator


class ClassificationResult(BaseModel):
    """Resultado tipado de clasificacion LLM. Nunca expone ModelResponse raw."""
    action: str          # validado contra allowed_actions en options
    type: str            # validado contra allowed_types en options
    confidence: Literal["high", "low"]
    raw_llm_output: str  # siempre preservado para debugging y auditoria
    fallback_applied: bool = False


class DraftText(BaseModel):
    """Draft generado por LLM. Branded para distinguir de str raw."""
    content: str
    model_used: str      # que modelo genero este draft (trazabilidad)
    fallback_applied: bool = False


class ClassifyOptions(BaseModel):
    allowed_actions: list[str]  # no empty — validado en adapter
    allowed_types: list[str]    # no empty — validado en adapter
    temperature: float = 0.1   # LLM_CLASSIFY_TEMPERATURE
    max_tokens: int = 500       # LLM_CLASSIFY_MAX_TOKENS
    model: str | None = None    # override; usa LLMConfig.classify_model si None


class DraftOptions(BaseModel):
    temperature: float = 0.7   # LLM_DRAFT_TEMPERATURE
    max_tokens: int = 2000     # LLM_DRAFT_MAX_TOKENS
    model: str | None = None   # override; usa LLMConfig.draft_model si None


class LLMConfig(BaseModel):
    classify_model: str        # LLM_CLASSIFY_MODEL — cheap, temp 0.1
    draft_model: str           # LLM_DRAFT_MODEL — capable, temp 0.7
    fallback_model: str        # LLM_FALLBACK_MODEL — para thinking-mode failures
    api_key: str | None = None # LLM_API_KEY (Anthropic/OpenAI); None para Ollama
    base_url: str | None = None  # LLM_BASE_URL para Ollama/custom endpoints
    timeout_seconds: int = 30  # LLM_TIMEOUT_SECONDS


class ConnectionTestResult(BaseModel):
    success: bool
    model_used: str
    latency_ms: int
    error_detail: str | None = None
```

## Parser de output LLM (parser.py)

### Suposiciones documentadas sobre shape del output (Cat 4 pre-mortem)

El parser DEBE manejar todos estos casos sin lanzar excepciones — solo retorna `None` en fallo para que el adapter aplique el fallback:

| # | Caso | Ejemplo | Estrategia |
|---|------|---------|------------|
| 1 | JSON puro | `{"action":"reply","type":"support"}` | json.loads directo |
| 2 | JSON en code block markdown | ` ```json\n{...}\n``` ` | Regex strip de ` ```[json]? ` |
| 3 | Texto explicativo antes/despues del JSON | `"Based on...\n{...}\nTherefore..."` | Regex para extraer primer objeto `{...}` |
| 4 | Casing incorrecto en valores | `{"action":"Reply","type":"SUPPORT"}` | `.lower()` antes de validar |
| 5 | Thinking-mode tags antes del JSON | `<think>...</think>\n{...}` | Strip de `<think>...</think>` con regex |
| 6 | Campos extra ignorados | `{"action":"reply","type":"support","explanation":"..."}` | Pydantic `model_config = ConfigDict(extra="ignore")` |
| 7 | Nombres de clave alternativos | `{"category":"support","intent":"reply"}` | Mapping de aliases conocidos |

### Logica del parser (local computation — condicionales, NO try/except)

```python
def parse_classification(
    raw: str,
    allowed_actions: list[str],
    allowed_types: list[str],
) -> ClassificationResult | None:
    """
    Extrae ClassificationResult de output LLM raw.
    Retorna None si el parsing falla — el adapter aplica el fallback.
    NUNCA lanza excepciones (operacion local, condicionales).
    """
    text = _strip_thinking_tags(raw)
    text = _strip_markdown_fences(text)
    json_str = _extract_json_object(text)

    if json_str is None:
        return None

    data = _safe_json_loads(json_str)
    if data is None:
        return None

    action = _resolve_field(data, ["action", "intent", "category"])
    type_ = _resolve_field(data, ["type", "email_type", "classification"])

    if action is None or type_ is None:
        return None

    action = action.lower()
    type_ = type_.lower()

    if action not in allowed_actions or type_ not in allowed_types:
        return None

    return ClassificationResult(
        action=action,
        type=type_,
        confidence="high",
        raw_llm_output=raw,
        fallback_applied=False,
    )
```

**Invariante del parser:** Si `parse_classification` retorna `None`, el caller (adapter) produce el fallback. El parser nunca decide el fallback — solo reporta exito o fallo.

## Defaults load-bearing (Cat 8 pre-mortem)

| Default | Valor | Env Var | Consecuencia si incorrecto |
|---------|-------|---------|---------------------------|
| Classification temperature | `0.1` | `LLM_CLASSIFY_TEMPERATURE` | Demasiado alto: clasificaciones inconsistentes entre emails identicos |
| Draft temperature | `0.7` | `LLM_DRAFT_TEMPERATURE` | Demasiado bajo: drafts roboticos. Demasiado alto: alucinacion de hechos |
| Classification max tokens | `500` | `LLM_CLASSIFY_MAX_TOKENS` | Demasiado bajo: JSON truncado, OutputParseError garantizado |
| Draft max tokens | `2000` | `LLM_DRAFT_MAX_TOKENS` | Demasiado bajo: drafts incompletos |
| LLM timeout | `30` s | `LLM_TIMEOUT_SECONDS` | Demasiado bajo: timeouts en emails complejos o red lenta |
| Fallback model | `gpt-3.5-turbo` | `LLM_FALLBACK_MODEL` | No-op si mismo modelo con thinking-mode — fallback no funciona |
| Body truncation | `4000` chars | `LLM_BODY_TRUNCATION_CHARS` | Demasiado alto: excede context window; demasiado bajo: clasificacion sin contexto |

Todos los defaults se cargan desde `LLMConfig` via `src/core/config.py` (pydantic-settings). Ningun valor hardcodeado en el adapter.

## Estructura de archivos esperada

```
src/adapters/llm/
├── __init__.py           # re-exporta LLMAdapter, LiteLLMAdapter, schemas publicos
├── base.py               # LLMAdapter ABC
├── litellm_adapter.py    # LiteLLMAdapter (toda extraccion de ModelResponse aqui)
├── schemas.py            # ClassificationResult, DraftText, LLMConfig, etc.
├── parser.py             # parse_classification(), helpers privados
└── exceptions.py         # LLMAdapterError y subclases
```

## Jerarquia de excepciones (exceptions.py)

```python
class LLMAdapterError(Exception):
    """Base para todos los errores del LLM adapter."""

class LLMConnectionError(LLMAdapterError):
    """Proveedor LLM inalcanzable (red, DNS, endpoint incorrecto)."""

class LLMRateLimitError(LLMAdapterError):
    """Proveedor retorno 429. retry_after_seconds puede ser None."""
    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds

class LLMTimeoutError(LLMAdapterError):
    """Llamada supero LLM_TIMEOUT_SECONDS."""

class OutputParseError(LLMAdapterError):
    """El output del LLM no pudo ser parseado a ClassificationResult.
    Solo para logging interno — el adapter aplica fallback, no relanza."""
    def __init__(self, message: str, raw_output: str) -> None:
        super().__init__(message)
        self.raw_output = raw_output
```

## Patron de try/except en litellm_adapter.py (directiva D7)

```python
async def classify(
    self,
    prompt: str,
    system_prompt: str,
    options: ClassifyOptions,
) -> ClassificationResult:
    # Validacion de preconditions (local — condicionales, no try/except)
    if not prompt:
        raise ValueError("prompt must not be empty")
    if not options.allowed_actions:
        raise ValueError("allowed_actions must not be empty")

    # Llamada externa — try/except con tipos especificos (directiva D7)
    try:
        response = await litellm.acompletion(
            model=options.model or self._config.classify_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=options.temperature,
            max_tokens=options.max_tokens,
            timeout=self._config.timeout_seconds,
        )
    except litellm.exceptions.RateLimitError as exc:
        raise LLMRateLimitError(str(exc)) from exc
    except litellm.exceptions.Timeout as exc:
        raise LLMTimeoutError(str(exc)) from exc
    except litellm.exceptions.APIConnectionError as exc:
        raise LLMConnectionError(str(exc)) from exc

    # Extraccion de ModelResponse (nunca expuesta fuera del adapter)
    raw_output: str = response.choices[0].message.content or ""

    # Parsing — operacion local (condicionales, directiva D8)
    result = parse_classification(raw_output, options.allowed_actions, options.allowed_types)

    if result is None:
        # Fallback documentado (Cat 4 pre-mortem)
        logger.warning("LLM output parse failed, applying fallback", extra={"raw": raw_output[:200]})
        return ClassificationResult(
            action="inform",
            type="notification",
            confidence="low",
            raw_llm_output=raw_output,
            fallback_applied=True,
        )

    return result
```

## Criterios de exito (deterministicos)

- [ ] `LLMAdapter` ABC importable; contiene exactamente 3 metodos con firmas completamente tipadas
- [ ] `LiteLLMAdapter` implementa todos los metodos del ABC sin `dict[str, Any]` en ninguna firma publica
- [ ] `ModelResponse` de LiteLLM nunca escapa del modulo `litellm_adapter.py` — verificado por mypy
- [ ] `ClassificationResult.fallback_applied` es `True` cuando el parser retorna `None`
- [ ] Parser maneja los 7 casos documentados de shape de output LLM (tests individuales por caso)
- [ ] Fallback path produce `ClassificationResult` valida con `confidence="low"` y `action="inform"`
- [ ] Todos los defaults (temperatura, tokens, timeout) cargados desde env vars via `LLMConfig`; ninguno hardcodeado
- [ ] Contract-docstrings presentes en los 3 metodos del ABC (formato 4 preguntas)
- [ ] Jerarquia de excepciones: `LLMAdapterError` base + 4 subclases especificas
- [ ] `ruff check src/adapters/llm/` — 0 violaciones
- [ ] `mypy src/adapters/llm/` — 0 errores
- [ ] Todos los tests de adapter pasan con mocks (sin llamadas a API real)
- [ ] Typecheck: 0 errores en modo estricto mypy para este modulo

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**
1. `mypy src/adapters/llm/` — si falla, corregir tipos antes de cualquier otro gate
2. `ruff check src/adapters/llm/ && ruff format --check src/adapters/llm/` — si falla, corregir lint
3. `pytest tests/adapters/llm/test_parser.py -v` — 7 casos edge mas fallback
4. `pytest tests/adapters/llm/test_litellm_adapter.py -v` — contrato completo con mocks
5. `pytest tests/adapters/llm/ -v` — suite completa del modulo

**Verificacion critica (no automatizable):** Revisar manualmente que ninguna firma publica contenga `ModelResponse`, `dict[str, Any]`, o retornos sin anotar. Inquisidor ejecuta esta revision via tighten-types antes de marcar COMPLETO.
