# Bloque 17: FE — Routing Rules, Integrations, Analytics, Overview, Logs

## Objetivo

Implementar las paginas restantes del dashboard: gestor de routing rules con
drag-to-reorder, paneles de configuracion de integraciones, dashboard de overview con
charts en tiempo real, pagina de analytics con selector de rango de fechas, y visor
de logs del sistema — consumiendo exclusivamente tipos auto-generados desde el OpenAPI
spec (D4), usando recharts como libreria de graficos.

## Dependencias

- Bloque 15 (FE Shell): SPA shell, React Router, layout con sidebar, auth context,
  cliente API tipado, script de codegen OpenAPI-to-TypeScript, CSS custom properties,
  tema base. Sin B15 no existe la estructura de rutas ni los tipos generados.
- Bloque 14 (Config API): endpoints de routing rules
  (`GET /api/routing-rules`, `POST /api/routing-rules`,
  `PUT /api/routing-rules/{id}`, `DELETE /api/routing-rules/{id}`,
  `PUT /api/routing-rules/reorder`, `POST /api/routing-rules/{id}/test`),
  endpoints de integraciones
  (`GET /api/integrations`, `PUT /api/integrations/{type}`,
  `POST /api/integrations/{type}/test`),
  endpoints de analytics
  (`GET /api/analytics/summary`, `GET /api/analytics/timeseries`,
  `GET /api/analytics/export`),
  endpoints de logs
  (`GET /api/logs`),
  endpoint de health
  (`GET /api/health`).
- Bloque 16 (FE Core): componentes reutilizables `StatusIndicator`,
  `ClassificationBadge`, `ConfidenceBadge`. Los imports de B16 deben estar disponibles
  antes de implementar las paginas de B17 que los reutilizan.
- Bloque 13 (Email CRUD API): `GET /api/emails/recent-activity` o endpoint equivalente
  para el activity feed del overview.

## Archivos a crear/modificar

### Backend (backend-worker)

- N/A — este bloque es exclusivamente frontend. Si frontend descubre un contrato
  faltante durante la implementacion, abre un issue al backend-worker y usa un mock
  tipado mientras tanto.

### Frontend (frontend-worker)

**Pages (contenedores de ruta):**

- `frontend/src/pages/OverviewPage.tsx` — Contenedor de ruta para `/` (home).
  Orquesta `StatCard`, `Chart`, `ActivityFeed`, `StatusIndicator`. Polling de
  health cada 30s via `useIntegrations` (o hook dedicado). Fetch de summary via
  `useAnalytics`.
- `frontend/src/pages/RoutingRulesPage.tsx` — Contenedor de ruta para
  `/routing-rules`. Lista draggable de `RuleCard` mas boton "New Rule" que abre
  `RuleBuilder` en modal/drawer. Opcionalmente: `RuleTestPanel` (Tier 2) accesible
  desde cada `RuleCard`.
- `frontend/src/pages/IntegrationsPage.tsx` — Contenedor de ruta para
  `/integrations`. Cuatro secciones: Email, Channels, CRM, LLM. Cada seccion
  renderiza un `IntegrationPanel` especializado.
- `frontend/src/pages/AnalyticsPage.tsx` — Contenedor de ruta para `/analytics`.
  `DateRangeSelector` en la parte superior; charts debajo. Boton "Export CSV"
  (Tier 2). Fetch via `useAnalytics` con el rango seleccionado.
- `frontend/src/pages/SystemLogsPage.tsx` — Contenedor de ruta para `/logs`.
  FilterBar de logs (level, component, date range) + tabla paginada de `LogEntry`.
  Fetch via `useLogs`.

**Components (reutilizables, sin fetch propio):**

- `frontend/src/components/StatCard.tsx` — Tarjeta de metrica. Props:
  `label: string`, `value: number | string`, `delta?: number` (cambio vs periodo
  anterior), `period: 'today' | 'week' | 'month'`, `isLoading?: boolean`.
  Nunca `any`. El valor se formatea segun su tipo (numero entero, porcentaje).
- `frontend/src/components/StatusIndicator.tsx` — Punto de estado. Props:
  `status: 'ok' | 'degraded' | 'error'`, `label?: string`. CSS: verde/amarillo/rojo
  via CSS custom properties. Reutilizado por B16 (EmailDetailPage para CRM sync)
  y por OverviewPage (health de integraciones). Si B16 ya lo creo, importar desde
  la ubicacion de B16 y no duplicar.
- `frontend/src/components/Chart.tsx` — Wrapper de recharts. Props:
  `type: 'line' | 'bar' | 'pie' | 'donut'`, `data: ChartDataPoint[]`,
  `xKey: string`, `yKey: string`, `height?: number`. Encapsula la eleccion de
  recharts — ningun `import from 'recharts'` debe aparecer fuera de este componente
  (excepto en sus tests). `ChartDataPoint` es un tipo local simple:
  `type ChartDataPoint = Record<string, string | number>`.
- `frontend/src/components/RuleCard.tsx` — Tarjeta de routing rule draggable.
  Muestra: nombre, resumen de condiciones (primeras 2 como chips), resumen de
  acciones, toggle activo/inactivo. Boton "Edit" abre `RuleBuilder`. Boton "Test"
  abre `RuleTestPanel` (Tier 2). Boton "Delete" con confirmation dialog.
  Props: `rule: RoutingRule`, callbacks tipados para cada accion.
- `frontend/src/components/RuleBuilder.tsx` — Formulario modal/drawer para crear
  o editar una routing rule. Secciones: condiciones (multi-select de action,
  multi-select de type, confidence select, sender_domain pattern, subject keywords)
  y acciones (channel multi-select, priority select, assign-to input, CRM sync
  toggle, generate draft toggle). Submit llama al callback del padre — el builder
  no hace fetch directamente. Props: `rule?: RoutingRule` (undefined = modo create),
  `onSubmit: (data: RoutingRulePayload) => Promise<void>`,
  `onClose: () => void`, `availableCategories: Category[]`.
- `frontend/src/components/RuleTestPanel.tsx` — Panel Tier 2 para testear una rule
  sin despacharla. Textarea para el texto del email de muestra. Boton "Test".
  Resultado: lista de reglas que matchearian + acciones que se tomarian. Llama a
  `POST /api/routing-rules/{id}/test`. Props: `ruleId: string`.
- `frontend/src/components/IntegrationPanel.tsx` — Panel de configuracion por
  integracion. Discriminado por `type: IntegrationType`. Renderiza campos
  especificos del tipo (ej: email → polling interval; LLM → provider select +
  temperature sliders + API key; CRM → field mapping + auto-create toggle).
  Boton "Test Connection" llama a `POST /api/integrations/{type}/test` y muestra
  un toast con el resultado. Props: `integration: IntegrationConfig`,
  `onSave: (config: IntegrationConfig) => Promise<void>`.
- `frontend/src/components/DateRangeSelector.tsx` — Selector de rango. Opciones
  predefinidas: "Last 7 days", "Last 30 days", "Last 90 days", "Custom". En modo
  custom: dos date inputs (from, to). Emite `{ from: string; to: string }` en
  formato ISO 8601. Props: `value: DateRange`, `onChange: (r: DateRange) => void`.
  Tipo local `DateRange = { from: string; to: string; preset?: DatePreset }` donde
  `DatePreset = '7d' | '30d' | '90d' | 'custom'`.
- `frontend/src/components/ActivityFeed.tsx` — Lista de ultimos N eventos del
  sistema. Cada item: timestamp formateado, icono por tipo de evento, descripcion,
  email_id (si aplica, como link a EmailDetailPage). Props:
  `events: ActivityEvent[]`, `isLoading?: boolean`. Tipo `ActivityEvent` generado
  desde el spec.
- `frontend/src/components/LogEntry.tsx` — Fila de log expandible. Collapsed:
  timestamp, nivel (badge con color), componente, mensaje (truncado a 120 chars).
  Expanded: mensaje completo + stack trace (si existe). Props: `entry: LogEntry`
  (tipo generado). Expansion controlada por estado local del componente (no global).

**Hooks (logica de fetch y mutacion):**

- `frontend/src/hooks/useAnalytics.ts` — Fetch de datos de analytics. Parametros:
  `{ from: string; to: string }`. Retorna `{ summary, timeseries, isLoading, error }`.
  `exportCsv()` dispara `GET /api/analytics/export` y inicia la descarga del
  archivo via `URL.createObjectURL`. Todos los tipos derivados de generated types.
- `frontend/src/hooks/useRoutingRules.ts` — CRUD + reorder de routing rules.
  Expone `{ rules, createRule, updateRule, deleteRule, reorderRules, testRule,
  toggleActive, isLoading, error }`. `reorderRules(orderedIds: string[]): Promise<void>`
  llama a `PUT /api/routing-rules/reorder`. `testRule(id: string, emailText: string)`
  llama a `POST /api/routing-rules/{id}/test` y retorna `RoutingTestResult`.
- `frontend/src/hooks/useIntegrations.ts` — Fetch y update de configuracion de
  integraciones. Expone `{ integrations, updateIntegration, testConnection,
  isLoading, error }`. `testConnection(type: IntegrationType): Promise<ConnectionTestResult>`
  llama a `POST /api/integrations/{type}/test`. `integrations` es
  `IntegrationConfig[]` tipado desde generated types.
- `frontend/src/hooks/useLogs.ts` — Fetch paginado de logs del sistema. Parametros:
  `LogFilters` (level, component, from, to, page, pageSize). Retorna
  `{ entries: LogEntry[]; total: number; page: number; isLoading: boolean; error: Error | null }`.

### Tests (Inquisidor)

- `frontend/src/pages/__tests__/OverviewPage.test.tsx` — Render con datos mock de
  summary y timeseries; StatCards muestran los valores correctos; StatusIndicator
  verde para integraciones healthy.
- `frontend/src/pages/__tests__/RoutingRulesPage.test.tsx` — Lista de rules renderizada;
  boton "New Rule" abre RuleBuilder; submit de RuleBuilder llama a createRule; toggle
  activo/inactivo llama a updateRule.
- `frontend/src/pages/__tests__/IntegrationsPage.test.tsx` — Cuatro paneles renderizados;
  "Test Connection" en cada panel llama al endpoint correcto y muestra resultado.
- `frontend/src/pages/__tests__/AnalyticsPage.test.tsx` — Cambio de DateRangeSelector
  actualiza el fetch de timeseries; boton Export descarga el archivo.
- `frontend/src/pages/__tests__/SystemLogsPage.test.tsx` — Filtro por level actualiza
  query; expand de LogEntry muestra stack trace; paginacion funciona.
- `frontend/src/components/__tests__/RuleBuilder.test.tsx` — Modo create: formulario
  vacio; modo edit: formulario pre-poblado con los datos de la rule; submit llama a
  onSubmit con `RoutingRulePayload` tipado.
- `frontend/src/components/__tests__/Chart.test.tsx` — Cada tipo de chart (line, bar,
  pie) renderiza sin errores con datos mock; no hay imports de recharts fuera del
  componente.
- `frontend/src/components/__tests__/RuleTestPanel.test.tsx` — Input de texto, submit
  llama a `testRule`, resultado renderizado correctamente.
- `frontend/src/hooks/__tests__/useRoutingRules.test.ts` — reorderRules envia array
  completo de IDs; toggleActive llama a updateRule con el flag correcto; testRule
  retorna `RoutingTestResult` tipado.
- `frontend/src/hooks/__tests__/useAnalytics.test.ts` — exportCsv inicia descarga;
  cambio de rango de fechas re-fetcha con los params correctos.
- `frontend/src/hooks/__tests__/useIntegrations.test.ts` — testConnection retorna
  `ConnectionTestResult`; error de conexion no crashea el hook.
- `frontend/src/hooks/__tests__/useLogs.test.ts` — Filtrado por level; paginacion.

## Skills aplicables

- **tighten-types** (CRITICO): La pagina de analytics es el caso mas fragil — los
  datos de charts son arrays dinamicos. `Chart.tsx` recibe `ChartDataPoint[]` donde
  `ChartDataPoint = Record<string, string | number>`. Esto es una excepcion
  documentada a "sin dict[str, Any]": los keys del chart son dinamicos (nombres de
  series de datos) y ambos key y value estan precisamente tipados. `useAnalytics`
  retorna tipos generados para `summary` y `timeseries`; la conversion a
  `ChartDataPoint[]` ocurre en la pagina (transformacion local, no en el hook).
  Aplicar en revision: `tsc --noEmit` debe dar 0 errores con strict mode.
- **pre-mortem Cat 1** (ALTO): El drag-to-reorder de routing rules asume que el
  orden en el array de respuesta de `GET /api/routing-rules` refleja el orden de
  prioridad. Si el backend ordena por un campo `priority: number` y el array no
  esta garantizado ordenado, el drag producira reordenamientos inconsistentes.
  Documentar la precondicion: el hook debe ordenar por `priority` antes de pasar
  al componente, independientemente del orden de llegada.
- **pre-mortem Cat 8** (ALTO): Defaults load-bearing de este bloque: intervalo de
  polling de health en OverviewPage (constante `HEALTH_POLL_INTERVAL_MS = 30_000`),
  limite de items en ActivityFeed (constante `ACTIVITY_FEED_LIMIT = 20`), preset
  por defecto del DateRangeSelector (`'30d'`). Ninguno hardcodeado como numero magico
  — todos nombrados como constantes exportadas desde un archivo `frontend/src/utils/constants.ts`.
- **pre-mortem Cat 6** (MEDIO): La exportacion CSV (Tier 2) usa `URL.createObjectURL`
  + `<a>` dinamico. Si el usuario navega antes de que la descarga inicie,
  `URL.revokeObjectURL` debe llamarse en el cleanup del effect. Documentar el patron
  de cleanup en el hook.
- **pre-mortem Cat 3** (MEDIO): `IntegrationType` es un enum DB-backed en el backend
  (`'email' | 'slack' | 'hubspot' | 'litellm'`). El `IntegrationPanel` no debe
  discriminar por string literal hardcodeado — debe derivar las opciones del tipo
  generado. Si el backend agrega un nuevo tipo de integracion, el panel debe manejar
  el caso desconocido con un fallback de UI generica (no un crash por switch
  exhaustivo sin default).
- **concept-analysis** (MEDIO): "Analytics" y "Overview" son conceptos distintos.
  Overview es un dashboard de estado actual (hoy, esta semana, health). Analytics es
  tendencias historicas con rango de fechas configurable. Los hooks `useAnalytics`
  y `useOverview` (si se separan) o los parametros de `useAnalytics` deben reflejar
  esta distincion. Si se usa un solo hook, el parametro `period` o `dateRange` define
  cuales datos se retornan — no mezclar summary estático con timeseries en el mismo
  tipo de retorno.

## Type Decisions

| Tipo | Naturaleza | Justificacion |
|------|-----------|---------------|
| `RoutingRule` | Generado — `types/generated/RoutingRule` | Schema canonico del backend. Incluye `id`, `name`, `priority`, `conditions`, `actions`, `is_active`. Importar directamente. |
| `RoutingRulePayload` | Generado — `types/generated/RoutingRuleCreate` o `RoutingRuleUpdate` | Input para crear/editar rules. Si el spec define schemas separados para create vs update, usar ambos. `RuleBuilder.onSubmit` acepta el union o discrimina por modo. |
| `RoutingTestResult` | Generado — `types/generated/RoutingTestResult` | Respuesta de `POST /api/routing-rules/{id}/test`. Incluye `matched_rules: RoutingRule[]` y `predicted_actions: RoutingAction[]`. |
| `IntegrationConfig` | Generado — `types/generated/IntegrationConfig` | Schema de respuesta de `GET /api/integrations`. Discriminado por campo `type: IntegrationType`. |
| `IntegrationType` | Generado — `types/generated/IntegrationType` | Enum del backend: `'email' | 'slack' | 'hubspot' | 'litellm'`. El `IntegrationPanel` importa este tipo para el prop `type`. |
| `ConnectionTestResult` | Generado — `types/generated/ConnectionTestResult` | Respuesta de `POST /api/integrations/{type}/test`. Incluye `ok: boolean`, `latency_ms?: number`, `error?: string`. |
| `AnalyticsSummary` | Generado — `types/generated/AnalyticsSummary` | Respuesta de `GET /api/analytics/summary`. Incluye totales por periodo y distribuciones. |
| `AnalyticsTimeseries` | Generado — `types/generated/AnalyticsTimeseries` | Respuesta de `GET /api/analytics/timeseries`. Array de puntos con `date: string` + campos de metricas. |
| `ChartDataPoint` | Local — `types/chart.ts` | `type ChartDataPoint = Record<string, string \| number>`. Excepcion documentada: keys son nombres de series de datos (dinamicos), ambos key y value precisamente tipados. No es `any`. Unico uso: argumento de `Chart.tsx`. Transformacion de `AnalyticsTimeseries` a `ChartDataPoint[]` ocurre en `AnalyticsPage`, no en el hook ni en el componente. |
| `LogEntry` | Generado — `types/generated/LogEntry` | Schema de cada entrada de log. Incluye `level: LogLevel`, `component: string`, `message: string`, `stack_trace?: string`, `email_id?: string`. |
| `LogLevel` | Generado — `types/generated/LogLevel` | Enum: `'error' \| 'warning' \| 'info'`. El badge de `LogEntry` deriva su color de este tipo. |
| `LogFilters` | Local — prop/parametro en `useLogs` | `interface LogFilters { level?: LogLevel; component?: string; from?: string; to?: string }`. Derivado de los query params del spec — no inventado. |
| `ActivityEvent` | Generado — `types/generated/ActivityEvent` | Schema del activity feed. Incluye `event_type`, `timestamp`, `description`, `email_id?`. |
| `DateRange` | Local — `types/date-range.ts` | `interface DateRange { from: string; to: string; preset?: DatePreset }` donde `type DatePreset = '7d' \| '30d' \| '90d' \| 'custom'`. Tipo de UI puro — el backend solo recibe `from` y `to` en ISO 8601. |
| `StatCardProps` | Local — prop interface explicita | `interface StatCardProps { label: string; value: number \| string; delta?: number; period: 'today' \| 'week' \| 'month'; isLoading?: boolean }`. Sin `any`. `delta` positivo = verde, negativo = rojo, ausente = sin indicador. |
| `RuleCardProps` | Local — prop interface explicita | `interface RuleCardProps { rule: RoutingRule; onEdit: (rule: RoutingRule) => void; onDelete: (id: string) => void; onToggleActive: (id: string, active: boolean) => void; onTest?: (id: string) => void }`. `onTest` es opcional (Tier 2). |
| `useRoutingRules` return | Local — interfaz explicita en el hook | `interface UseRoutingRulesResult { rules: RoutingRule[]; createRule: (payload: RoutingRulePayload) => Promise<RoutingRule>; updateRule: (id: string, payload: Partial<RoutingRulePayload>) => Promise<RoutingRule>; deleteRule: (id: string) => Promise<void>; reorderRules: (orderedIds: string[]) => Promise<void>; testRule: (id: string, emailText: string) => Promise<RoutingTestResult>; toggleActive: (id: string, active: boolean) => Promise<void>; isLoading: boolean; error: Error \| null }`. |
| `useAnalytics` return | Local — interfaz explicita | `interface UseAnalyticsResult { summary: AnalyticsSummary \| null; timeseries: AnalyticsTimeseries \| null; isLoading: boolean; error: Error \| null; exportCsv: () => void }`. `exportCsv` no retorna datos — dispara descarga del navegador. |

## Candidate Tools

| Tool | Tier | Status | Como aplica |
|------|------|--------|-------------|
| `recharts` | 1 | REQUIRED | Libreria de charts. `Chart.tsx` encapsula todos los imports. Instalar si B15 no lo instalo. Tipos: `@types/recharts` incluidos en el paquete. No usar d3 directamente. |
| `@dnd-kit/core` + `@dnd-kit/sortable` | 2 | PREFERRED (ya evaluado en B16) | Drag-to-reorder en `RoutingRulesPage`. Si B16 ya instalo `@dnd-kit`, reutilizar — no reinstalar. Si B16 uso HTML5 nativo, evaluar si es suficiente para el caso de routing rules (lista mas larga, posiblemente con muchas cards). |
| `date-fns` | 2 | PREFERRED | Formateo de fechas en `ActivityFeed` y `LogEntry`. Alternativa: `Intl.DateTimeFormat` nativo. Si el proyecto ya tiene `date-fns` instalado (comun con TanStack Query), reutilizar. No instalar solo para formateo si el nativo es suficiente. |

## Criterios de exito (deterministicos)

**TypeScript / Build:**
- [ ] `tsc --noEmit` en `frontend/` — 0 errores (strict mode)
- [ ] `vite build` — build exitoso
- [ ] 0 usos de `any` en archivos de este bloque (verificable via grep, excepcion documentada: `ChartDataPoint = Record<string, string | number>` no es `any`)
- [ ] 0 tipos definidos manualmente que dupliquen schemas del OpenAPI spec
- [ ] Ningun `import from 'recharts'` fuera de `frontend/src/components/Chart.tsx` y sus tests

**Overview Dashboard:**
- [ ] `GET /api/analytics/summary` se llama al montar la pagina; `StatCard` muestra totales de hoy, semana y mes
- [ ] Charts de distribucion (action breakdown, type breakdown) renderizan con datos reales
- [ ] `GET /api/health` se llama cada 30s; `StatusIndicator` muestra verde/amarillo/rojo por integracion
- [ ] `ActivityFeed` muestra los ultimos 20 eventos con timestamp formateado
- [ ] Si alguna integracion retorna `status: 'error'`, el punto correspondiente es rojo sin recargar la pagina

**Routing Rules:**
- [ ] `GET /api/routing-rules` carga la lista; las cards se renderizan en orden de `priority` ascendente
- [ ] Drag-to-reorder: soltar una card en nueva posicion llama a `PUT /api/routing-rules/reorder` con el array completo de IDs en el nuevo orden
- [ ] "New Rule" abre `RuleBuilder` en modo create; submit llama a `POST /api/routing-rules` con `RoutingRulePayload` tipado; nueva rule aparece en la lista
- [ ] "Edit" en una card abre `RuleBuilder` pre-poblado con los datos de esa rule; submit llama a `PUT /api/routing-rules/{id}`
- [ ] "Delete" muestra confirmation dialog; confirm llama a `DELETE /api/routing-rules/{id}`; card desaparece
- [ ] Toggle activo/inactivo en cada card llama a `PUT /api/routing-rules/{id}` con `{ is_active: !current }`
- [ ] `RuleTestPanel` (Tier 2): input de texto de email → `POST /api/routing-rules/{id}/test` → resultado visible con las reglas que matchearian y las acciones predichas
- [ ] Conditions builder: multi-select de action usa opciones cargadas desde `GET /api/categories?layer=action`; multi-select de type usa `GET /api/categories?layer=type`

**Integrations:**
- [ ] Cuatro paneles renderizados: Email, Channels, CRM, LLM
- [ ] Cada panel muestra estado de conexion via `StatusIndicator`
- [ ] "Test Connection" en cada panel llama a `POST /api/integrations/{type}/test` y muestra resultado en toast (ok o error con mensaje)
- [ ] Formularios de config guardan con `PUT /api/integrations/{type}`
- [ ] LLM panel: slider de temperature emite el valor numerico correcto (no string); provider select cambia el modelo visible
- [ ] API key fields: tipo `password` con toggle de visibilidad; el valor nunca se loggea en consola

**Analytics:**
- [ ] `DateRangeSelector` preset "Last 30 days" activo por defecto
- [ ] Cambio de preset (o custom range) re-fetcha `GET /api/analytics/timeseries` con los params `from` y `to` correctos en ISO 8601
- [ ] Line chart de email volume renderiza con datos del timeseries
- [ ] Bar chart de action breakdown y type breakdown renderizan con distribucion correcta
- [ ] Line chart de accuracy tracking (% overrides) renderiza
- [ ] Pie chart de emails por channel renderiza
- [ ] "Export CSV" (Tier 2): click llama a `GET /api/analytics/export`, descarga el archivo; `URL.revokeObjectURL` se llama en cleanup

**System Logs:**
- [ ] `GET /api/logs` carga la primera pagina; entradas renderizadas con timestamp, level badge, componente, mensaje truncado
- [ ] Filtro por level (error/warning/info) actualiza la query y recarga; level `error` tiene badge rojo, `warning` amarillo, `info` azul/gris
- [ ] Filtro por componente (texto libre) actualiza la query
- [ ] Date range filter en logs funciona
- [ ] Click en `LogEntry` expande la fila y muestra mensaje completo + stack trace si existe
- [ ] Paginacion: siguiente/anterior funciona; total de entradas visible

**Visual / Responsive:**
- [ ] Layout responsive a 1024px+; charts se redimensionan con el viewport (recharts `ResponsiveContainer`)
- [ ] Dark mode via CSS custom properties; ningun color hardcodeado en componentes de este bloque
- [ ] Loading states visibles (StatCard con skeleton, charts con spinner) mientras `isLoading: true`
- [ ] Error states visibles cuando los hooks retornan `error !== null`

**Tests:**
- [ ] Todos los archivos `__tests__/` del bloque pasan
- [ ] `Chart.tsx` testeado con datos mock para cada type (`'line'`, `'bar'`, `'pie'`)
- [ ] `useRoutingRules.reorderRules` verificado: envia array completo de IDs, no solo el item movido

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**

1. `tsc --noEmit` — base de tipos; 0 errores obligatorio
2. Verificacion de `any` (grep) — excepcion documentada: `ChartDataPoint`; cualquier otro `any` es un fallo
3. Verificacion de imports de recharts (grep: `import.*from 'recharts'` fuera de `Chart.tsx`) — 0 matches obligatorio
4. `vite build` — confirma build de produccion limpio
5. Vitest/jest sobre los hooks (`useRoutingRules`, `useAnalytics`, `useIntegrations`, `useLogs`)
6. Vitest/jest sobre los componentes (`Chart`, `RuleBuilder`, `RuleTestPanel`, `IntegrationPanel`, `DateRangeSelector`)
7. Vitest/jest sobre las paginas (OverviewPage, RoutingRulesPage, IntegrationsPage, AnalyticsPage, SystemLogsPage)
8. Validacion visual: abrir el browser en dev, verificar drag-to-reorder en RoutingRulesPage, verificar charts en AnalyticsPage con datos reales, verificar health polling en OverviewPage

**Verificaciones criticas (no automatizables hasta tener datos reales):**

```bash
# Confirmar encapsulacion de recharts
grep -rn "from 'recharts'" frontend/src/
# Solo debe aparecer en: frontend/src/components/Chart.tsx (y sus tests)

# Confirmar ausencia de any
grep -rn ": any\|as any\|<any>" frontend/src/pages/OverviewPage.tsx frontend/src/pages/RoutingRulesPage.tsx frontend/src/pages/IntegrationsPage.tsx frontend/src/pages/AnalyticsPage.tsx frontend/src/pages/SystemLogsPage.tsx frontend/src/components/StatCard.tsx frontend/src/components/RuleCard.tsx frontend/src/components/RuleBuilder.tsx frontend/src/components/IntegrationPanel.tsx frontend/src/hooks/useRoutingRules.ts frontend/src/hooks/useAnalytics.ts frontend/src/hooks/useIntegrations.ts frontend/src/hooks/useLogs.ts

# Confirmar que reorderRules envia array completo (no objeto con solo los items cambiados)
grep -n "reorder" frontend/src/hooks/useRoutingRules.ts
# Debe mostrar una llamada a PUT con un array de IDs, no un objeto parcial
```

**Consultas requeridas antes de implementar:**

- Consultar Inquisidor (tighten-types) para confirmar el tipo exacto de
  `AnalyticsTimeseries`: si el spec define un array de objetos con keys fijos
  (e.g., `{ date: string; email_count: number; classified_count: number }`) o
  con keys dinamicos. Si los keys son fijos, `ChartDataPoint` no es necesario
  y se puede usar el tipo generado directamente — eliminando la excepcion documentada.
- Consultar Inquisidor para confirmar si `IntegrationConfig` en el spec es un
  schema discriminado por `type` (usando `oneOf` / `discriminator` en OpenAPI 3.1)
  o un objeto con campos opcionales. La respuesta determina si el codegen genera
  un union type o un tipo aplanado con campos opcionales.
- Confirmar con backend-worker que `PUT /api/routing-rules/reorder` espera un
  array plano de IDs `string[]` o un objeto `{ rules: { id: string; priority: number }[] }`.
  El contrato exacto del endpoint determina el parametro de `reorderRules` en el hook.
- Si B16 creo `StatusIndicator.tsx`, confirmar la ubicacion exacta del archivo
  antes de importarlo en B17. No duplicar el componente.
