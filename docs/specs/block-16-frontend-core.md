# Bloque 16: FE — Email Browser, Review Queue, Classification Config

## Objetivo

Implementar las paginas centrales del dashboard: browser paginado de emails con
busqueda/filtrado, cola de revision con vista lado a lado de drafts, y gestion de
categorias de clasificacion con drag-to-reorder — consumiendo exclusivamente tipos
auto-generados desde el OpenAPI spec (D4).

## Dependencias

- Bloque 15 (FE Shell): SPA shell, React Router, layout con sidebar, auth context,
  cliente API tipado, script de codegen OpenAPI-to-TypeScript, CSS custom properties
  y tema base. Sin B15 no existe la estructura de rutas ni los tipos generados.
- Bloque 13 (Email CRUD API): endpoints de emails (`GET /api/emails`,
  `GET /api/emails/{id}`, `POST /api/emails/{id}/reclassify`,
  `POST /api/emails/{id}/reroute`), endpoints de drafts (`GET /api/drafts`,
  `POST /api/drafts/{id}/approve`, `POST /api/drafts/{id}/reject`,
  `PUT /api/drafts/{id}`), endpoint de review queue
  (`GET /api/review-queue`).
- Bloque 14 (Config API): endpoints de categorias
  (`GET /api/categories`, `POST /api/categories`,
  `PUT /api/categories/{id}`, `DELETE /api/categories/{id}`,
  `PUT /api/categories/reorder`), endpoints de few-shot examples
  (`GET /api/few-shot-examples`, `POST`, `PUT`, `DELETE`),
  endpoint de config de clasificacion (`GET /api/classification-config`,
  `PUT /api/classification-config`).

## Archivos a crear/modificar

### Backend (backend-worker)

- N/A — este bloque es exclusivamente frontend. Las APIs las implementa backend-worker
  en B13 y B14. Si frontend descubre un contrato faltante durante la implementacion,
  abre un issue al backend-worker y usa un mock tipado mientras tanto.

### Frontend (frontend-worker)

**Pages (contenedores de ruta, sin logica de negocio inline):**

- `frontend/src/pages/EmailBrowserPage.tsx` — Contenedor de ruta para `/emails`.
  Orquesta `FilterBar`, `EmailTable`, paginacion. Delega fetch a `useEmails`.
- `frontend/src/pages/EmailDetailPage.tsx` — Contenedor de ruta para
  `/emails/:id`. Vista completa: cuerpo del email, clasificacion, routing actions,
  estado CRM, estado draft. Puede abrirse como modal sobre el browser o como pagina
  independiente (decision de implementacion — usar React Router modal pattern si B15
  lo soporta).
- `frontend/src/pages/ReviewQueuePage.tsx` — Contenedor de ruta para
  `/review-queue`. Dos tabs: "Low Confidence" y "Pending Drafts". Badge count
  sincronizado con sidebar nav via contexto o prop drilling desde el layout de B15.
- `frontend/src/pages/ClassificationConfigPage.tsx` — Contenedor de ruta para
  `/config/classification`. Tres secciones: Action categories, Type categories,
  Few-shot examples. Cuarta seccion colapsable: System prompt + confidence threshold.

**Components (reutilizables, sin fetch propio — solo props):**

- `frontend/src/components/EmailTable.tsx` — Tabla paginada de emails. Columnas:
  fecha, remitente, asunto, clasificacion (action + type), prioridad, estado routing,
  estado draft. Sortable. Row click emite callback. Checkbox por fila para bulk actions.
- `frontend/src/components/FilterBar.tsx` — Controles de filtrado: date range,
  action, type, priority, routing status, sender domain. Search input para
  subject/sender. Emite objeto `EmailFilters` tipado al padre via `onChange`.
- `frontend/src/components/ClassificationBadge.tsx` — Badge visual para action y
  type. Colores derivados de CSS custom properties. Props: `action: string`,
  `type: string`, `size?: 'sm' | 'md'`.
- `frontend/src/components/ConfidenceBadge.tsx` — Indicador de confianza. Alto:
  verde. Bajo: amarillo/ambar. Props: `confidence: 'high' | 'low'`.
- `frontend/src/components/DraftReview.tsx` — Vista lado a lado. Panel izquierdo:
  email original con formato (remitente, asunto, cuerpo). Panel derecho: draft
  generado con editor inline opcional. Barra de acciones: Approve, Edit, Reject,
  Reassign. Props completamente tipadas — sin raw strings para IDs.
- `frontend/src/components/CategoryList.tsx` — Lista draggable de categorias (action
  o type). Usa la API nativa de drag-and-drop HTML5 o una libreria ligera (ver
  Candidate Tools). Cada item: nombre, descripcion, toggle activo/inactivo,
  boton edit, boton delete con confirmation dialog. Emite `onReorder` con el nuevo
  orden completo (no solo el item movido).
- `frontend/src/components/FewShotEditor.tsx` — Formulario para agregar/editar un
  few-shot example. Campos: email summary (textarea), expected action (select),
  expected type (select). Modo add y modo edit controlados por prop `example?`.

**Hooks (logica de fetch y mutacion, sin JSX):**

- `frontend/src/hooks/useEmails.ts` — Fetch paginado de emails. Parametros:
  `EmailFilters & PaginationParams`. Retorna `{ emails, total, page, isLoading,
  error, refetch }` con tipos derivados de generated types. Usa SWR o React Query
  (decision de B15 — este hook adapta a lo que B15 haya instalado).
- `frontend/src/hooks/useReviewQueue.ts` — Fetch de items de la cola de revision.
  Dos queries: `useReviewQueue('low_confidence')` y `useReviewQueue('pending_drafts')`.
  Expone `{ items, count, approveDraft, rejectDraft, editDraft, reassignDraft,
  overrideClassification }`. Mutaciones optimistas para approve/reject.
- `frontend/src/hooks/useCategories.ts` — CRUD de categorias. Parametro: `layer:
  'action' | 'type'`. Expone `{ categories, createCategory, updateCategory,
  deleteCategory, reorderCategories, isLoading, error }`. `reorderCategories` llama a
  `PUT /api/categories/reorder` con el array completo de IDs en el nuevo orden.

### Tests (Inquisidor)

- `frontend/src/pages/__tests__/EmailBrowserPage.test.tsx` — Render con emails mock,
  verificar tabla renderizada, filtros actualizan query, paginacion avanza. Mock de
  `useEmails` hook.
- `frontend/src/pages/__tests__/ReviewQueuePage.test.tsx` — Tab switch, render de
  ambas listas, acciones de approve/reject llaman a mutacion correcta.
- `frontend/src/pages/__tests__/ClassificationConfigPage.test.tsx` — CRUD de
  categoria: add, edit, delete con confirmacion, drag-to-reorder.
- `frontend/src/components/__tests__/DraftReview.test.tsx` — Render lado a lado,
  boton Approve llama callback, Edit habilita inline editor, Reject muestra campo
  opcional de reclasificacion.
- `frontend/src/components/__tests__/CategoryList.test.tsx` — Drag reorder emite
  nuevo orden via `onReorder`.
- `frontend/src/components/__tests__/FilterBar.test.tsx` — Cambio de filtro emite
  `EmailFilters` tipado completo.
- `frontend/src/hooks/__tests__/useEmails.test.ts` — Fetch con filtros, paginacion,
  error state, refetch.
- `frontend/src/hooks/__tests__/useReviewQueue.test.ts` — Approve/reject optimista,
  rollback en error de red.
- `frontend/src/hooks/__tests__/useCategories.test.ts` — Reorder envia array completo
  de IDs al endpoint correcto.

## Skills aplicables

- **tighten-types** (CRITICO): Todos los tipos del componente vienen de
  `frontend/src/types/generated/` (generados por el script de B15 desde el OpenAPI
  spec). Ninguna interfaz duplicada manualmente. Props de componentes son interfaces
  explicitas derivadas de los tipos generados. El cliente API es el unico punto de
  contacto con el servidor — nunca `fetch()` directo con cast a `any`. Aplicar en
  planificacion (definir la tabla de Type Decisions antes de crear archivos) y en
  revision (tsc --noEmit debe dar 0 errores).
- **pre-mortem Cat 4** (ALTO): La cola de revision asume que el campo
  `confidence` del item llega como `'high' | 'low'`. Si el backend retorna un numero
  (0.0–1.0) en lugar de un string enum, el badge visual quedara en blanco. Documentar
  la precondicion en el hook y validar contra el OpenAPI spec durante codegen.
- **pre-mortem Cat 8** (MEDIO): El badge count de la sidebar es un default de
  polling cada 30s. Si el intervalo no es configurable y la API tiene latencia alta,
  el count puede ser stale. Documentar el intervalo como constante nombrada en el hook,
  no un numero magico.
- **pre-mortem Cat 3** (MEDIO): Los slugs de action/type de las categorias (e.g.,
  `"respond"`, `"complaint"`) no son free-form strings — son valores de un enum
  DB-backed. El select del `FewShotEditor` debe cargar las opciones desde la API
  (`useCategories`), no desde un array hardcodeado.
- **concept-analysis** (MEDIO): Claridad de nombres en componentes. "Review Queue"
  tiene dos conceptos distintos: "Low Confidence" (clasificacion dudosa, accion:
  override) vs "Pending Drafts" (draft listo, accion: approve/reject). Los componentes
  y hooks deben reflejar esta distincion semantica en sus nombres y props — no
  colapsarlos en un concepto generico "review item".

## Type Decisions

| Tipo | Naturaleza | Justificacion |
|------|-----------|---------------|
| `Email` | Generado — `types/generated/Email` | Tipo canonico del backend; incluye todos los campos del modelo ORM serializados. Importar directamente, sin wrapper. |
| `EmailFilters` | Local — `hooks/useEmails.ts` | Objeto de estado de UI que mapea 1:1 a los query params de `GET /api/emails`. Derivado del OpenAPI `parameters` del endpoint — no inventado manualmente. |
| `PaginationParams` | Generado — `types/generated/PaginationParams` o local si el spec no lo exporta | Reutilizable entre todos los hooks paginados. Si el spec no lo define como schema reutilizable, se define una vez en `types/pagination.ts` (excepcion documentada, no duplicacion). |
| `ReviewQueueItem` | Generado — `types/generated/ReviewQueueItem` | Schema de respuesta de `GET /api/review-queue`. El backend define la forma; frontend la consume. |
| `DraftDetail` | Generado — `types/generated/Draft` | Schema del modelo Draft tal como lo expone la API. Incluye `content`, `status`, `gmail_draft_id`. |
| `Category` (action/type) | Generado — `types/generated/Category` | Schema de respuesta de `GET /api/categories`. El campo `layer: 'action' | 'type'` discrimina el subtipo. |
| `FewShotExample` | Generado — `types/generated/FewShotExample` | Schema de `GET /api/few-shot-examples`. |
| `ClassificationConfig` | Generado — `types/generated/ClassificationConfig` | Schema de `GET /api/classification-config`. Incluye `confidence_threshold: number`, `system_prompt: string`. |
| `EmailFilters` props en `FilterBar` | Local — prop interface explicita | `interface FilterBarProps { value: EmailFilters; onChange: (f: EmailFilters) => void }`. Deriva `EmailFilters` del hook, no redefine los campos. |
| `DraftReviewProps` | Local — prop interface explicita | `interface DraftReviewProps { email: Email; draft: DraftDetail; onApprove: (id: string) => void; onReject: (id: string, reason?: string) => void; onEdit: (id: string, content: string) => void; onReassign: (id: string, reviewerId: string) => void }`. IDs son `string` (UUID), nunca `any`. |
| `CategoryListProps` | Local — prop interface explicita | `interface CategoryListProps { categories: Category[]; onReorder: (orderedIds: string[]) => void; onEdit: (category: Category) => void; onDelete: (id: string) => void; onToggleActive: (id: string, active: boolean) => void }`. |
| `useEmails` return | Local — interfaz explicita en el hook | `interface UseEmailsResult { emails: Email[]; total: number; page: number; pageSize: number; isLoading: boolean; error: Error | null; refetch: () => void }`. Nunca retornar `any`. |
| `useReviewQueue` return | Local — interfaz explicita en el hook | `interface UseReviewQueueResult { items: ReviewQueueItem[]; count: number; isLoading: boolean; approveDraft: (id: string) => Promise<void>; rejectDraft: (id: string, reason?: string) => Promise<void>; ... }`. |
| Confidence literal | Derivado del spec — `'high' | 'low'` | El spec define este enum; el tipo generado lo expresa como union literal. `ConfidenceBadge` tipa su prop contra ese literal, no contra `string`. |

## Candidate Tools

| Tool | Tier | Status | Como aplica |
|------|------|--------|-------------|
| `@dnd-kit/core` + `@dnd-kit/sortable` | 2 | PREFERRED | Drag-to-reorder para `CategoryList`. Alternativa: HTML5 drag API nativa (mas fragil en touch). dnd-kit es ligero, accesible, TypeScript-first. Instalar si el proyecto no tiene libreria drag-and-drop desde B15. |
| `recharts` | 2 | PREFERRED | No aplica directamente en B16 (los charts van en B17), pero si B15 ya lo instalo, importar desde ahi. No re-instalar. |
| SWR o TanStack Query | 1 | REQUIRED (decision de B15) | Los hooks de fetch de este bloque dependen de lo que B15 eligio. Si SWR: `useSWR` y `useSWRMutation`. Si TanStack Query: `useQuery` y `useMutation`. El hook encapsula la eleccion — las paginas no importan SWR ni TanStack directamente. |

## Criterios de exito (deterministicos)

**TypeScript / Build:**
- [ ] `tsc --noEmit` en `frontend/` — 0 errores (strict mode)
- [ ] `vite build` — build exitoso, 0 warnings de tipo
- [ ] 0 usos de `any` en archivos de este bloque (verificable: `grep -rn ": any\|as any\|<any>" frontend/src/pages/EmailBrowserPage.tsx frontend/src/pages/EmailDetailPage.tsx frontend/src/pages/ReviewQueuePage.tsx frontend/src/pages/ClassificationConfigPage.tsx frontend/src/components/EmailTable.tsx frontend/src/components/FilterBar.tsx frontend/src/components/ClassificationBadge.tsx frontend/src/components/ConfidenceBadge.tsx frontend/src/components/DraftReview.tsx frontend/src/components/CategoryList.tsx frontend/src/components/FewShotEditor.tsx frontend/src/hooks/useEmails.ts frontend/src/hooks/useReviewQueue.ts frontend/src/hooks/useCategories.ts` — resultado debe estar vacio)
- [ ] 0 tipos definidos manualmente que dupliquen schemas del OpenAPI spec (verificable: no existe ningun `interface Email {` ni `type Email =` en el codigo del bloque — solo imports desde `types/generated/`)

**Email Browser:**
- [ ] `GET /api/emails` se llama con los parametros de filtro correctos al cambiar `FilterBar`
- [ ] Tabla muestra columnas: fecha, remitente, asunto, clasificacion (action + type), prioridad, estado routing
- [ ] Paginacion: boton siguiente/anterior cambia la pagina y recarga los datos
- [ ] Ordenamiento por columna: click en header alterna asc/desc y actualiza la query
- [ ] Search: input de busqueda debounced (300ms) llama a la API con el parametro `q`
- [ ] Row click navega a EmailDetailPage o abre modal con el detalle correcto
- [ ] Bulk actions: checkbox selecciona multiples emails; "Reclassify selected" y "Re-route selected" habilitan cuando hay seleccion
- [ ] Empty state visible cuando la API retorna `total: 0`

**Email Detail:**
- [ ] Vista muestra: cuerpo del email, `ClassificationBadge` con action + type, `ConfidenceBadge`, lista de routing actions tomadas, estado CRM sync (con `contact_id` si aplica), estado draft (con link al draft si existe)
- [ ] Boton "Reclassify" disponible; al confirmar llama a `POST /api/emails/{id}/reclassify`

**Review Queue:**
- [ ] Tab "Low Confidence": lista de emails con clasificacion dudosa; dropdown inline de override llama a la API correcta
- [ ] Tab "Pending Drafts": lista de drafts pendientes; click abre `DraftReview` con el email original y el draft
- [ ] Badge count en sidebar refleja el total de items pendientes (ambos tabs combinados)
- [ ] Approve draft: llama a `POST /api/drafts/{id}/approve`, item desaparece de la lista (mutacion optimista)
- [ ] Reject draft: llama a `POST /api/drafts/{id}/reject` con campo de razon opcional
- [ ] Edit draft: inline editor en panel derecho de `DraftReview`; guardar llama a `PUT /api/drafts/{id}`
- [ ] Reassign: dropdown de reviewers disponibles; llama al endpoint de asignacion

**Classification Config:**
- [ ] Action categories: lista con drag-to-reorder; soltar en nueva posicion llama a `PUT /api/categories/reorder` con array completo de IDs
- [ ] Type categories: misma UI y comportamiento
- [ ] Add category: formulario abre; submit llama a `POST /api/categories`; nueva categoria aparece en la lista
- [ ] Edit category: formulario pre-poblado; submit llama a `PUT /api/categories/{id}`
- [ ] Delete category: confirmation dialog; confirm llama a `DELETE /api/categories/{id}`
- [ ] Toggle active: switch inline llama a `PUT /api/categories/{id}` con `{ is_active: !current }`
- [ ] Few-shot examples: add/edit/delete funcionan con sus respectivos endpoints
- [ ] Seccion "Advanced" (system prompt + confidence threshold) colapsada por defecto; slider de threshold emite el valor correcto al guardar

**Visual / Responsive:**
- [ ] Layout responsive a 1024px+ (desktop target) — sin overflow horizontal en pantallas de 1280px
- [ ] Dark mode funcional via CSS custom properties (definidas en B15); ningun color hardcodeado en los componentes de este bloque
- [ ] `ConfidenceBadge` alta confianza: color `var(--success)` o equivalente; baja confianza: color `var(--warning)`
- [ ] Loading state visible (spinner o skeleton) mientras los hooks tienen `isLoading: true`
- [ ] Error state visible cuando el hook retorna `error !== null`

**Tests:**
- [ ] Todos los archivos `__tests__/` del bloque pasan sin errores
- [ ] Cobertura de los hooks: mutaciones optimistas con rollback en error

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.

**Gates ordenados (ejecutar en este orden):**

1. `tsc --noEmit` — base de tipos; si falla, nada mas tiene sentido
2. Verificacion de `any` (grep) — 0 matches obligatorio antes de continuar
3. Verificacion de duplicacion de tipos (grep para `interface Email`, `interface Draft`, etc.) — 0 matches en codigo del bloque
4. `vite build` — confirma que el build de produccion es limpio
5. `pytest` / vitest sobre los hooks (`useEmails`, `useReviewQueue`, `useCategories`) — logica de fetch y mutacion
6. `pytest` / vitest sobre los componentes (`DraftReview`, `CategoryList`, `FilterBar`) — comportamiento de UI aislado
7. `pytest` / vitest sobre las paginas (`EmailBrowserPage`, `ReviewQueuePage`, `ClassificationConfigPage`) — integracion de hooks + componentes
8. Validacion visual: abrir el browser en dev, verificar Email Browser con datos reales de la API, verificar DraftReview lado a lado, verificar drag-to-reorder de categorias

**Consultas requeridas antes de implementar:**

- Consultar Inquisidor (tighten-types) para confirmar si `PaginationParams` aparece
  como schema reutilizable en el OpenAPI spec de B13/B14, o si debe definirse localmente
  una vez en `frontend/src/types/pagination.ts` como excepcion documentada a D4.
- Consultar Inquisidor para confirmar el tipo exacto de `confidence` en `ReviewQueueItem`:
  union literal `'high' | 'low'` vs numero flotante 0.0–1.0. El backend (B08) usa
  `"high" | "low"` internamente — verificar que el serializer de B13 no lo convierte
  a numero en la respuesta JSON.
- Si B15 eligio SWR: los hooks usan `useSWR` y `useSWRMutation`. Si eligio TanStack
  Query: `useQuery` y `useMutation`. Confirmar antes de implementar los hooks.

**Verificacion critica de tipos (no automatizable en CI hasta que exista codegen):**

```bash
# Confirmar que todos los imports de tipos vienen de generated/
grep -rn "from.*types/generated" frontend/src/pages/EmailBrowserPage.tsx frontend/src/pages/ReviewQueuePage.tsx frontend/src/pages/ClassificationConfigPage.tsx frontend/src/hooks/useEmails.ts frontend/src/hooks/useReviewQueue.ts frontend/src/hooks/useCategories.ts

# Confirmar ausencia de any
grep -rn ": any\|as any\|<any>" frontend/src/pages/ frontend/src/components/EmailTable.tsx frontend/src/components/DraftReview.tsx frontend/src/components/CategoryList.tsx frontend/src/hooks/
```

Ambos comandos deben producir resultados esperados (primero: imports presentes;
segundo: sin matches) antes de marcar el bloque como COMPLETO.

## Amendments (post-implementation review)

> Added 2026-03-02. Backend API (B13) and config endpoints (B14 spec) are the source of truth.
> Frontend consumes generated types from OpenAPI — field names come from backend schemas.

### Cross-cutting deltas

| ID | Spec assumption | Codebase reality |
|----|-----------------|-------------------|
| X1 | `Email.received_at` | Field is `Email.date` (`src/models/email.py:105`) |
| X2 | `Email.from_address` | Field is `Email.sender_email` (`src/models/email.py:98`) |
| X3 | `Draft.body` | Field is `Draft.content` (`src/models/draft.py:47`) |
| X5 | Endpoint paths `/api/...` | Prefix is `/api/v1/...` (`src/api/main.py:68-72`) |
| X8 | `IntegrationConfig` DB model | Does NOT exist — config is env vars via `Settings` |

### Deltas

| # | Category | Spec says | Codebase reality | Resolution |
|---|----------|-----------|-------------------|------------|
| 1 | Endpoint | `POST /api/emails/{id}/reroute` | Does NOT exist — only `retry` and `reclassify` (`src/api/routers/emails.py`) | Use `retry` or `reclassify` |
| 2 | Endpoint | `PUT /api/drafts/{id}` (edit body) | Does NOT exist (B13 has approve/reject/reassign only) | Decision needed: add in B14, or client-side edit before approve |
| 3 | Endpoint | `GET /api/review-queue` | Does NOT exist | Compose from: `GET /api/v1/emails` (filtered) + `GET /api/v1/drafts?status=pending` |
| 4 | Endpoint | `GET /api/categories?layer=action` (query param) | B14: separate paths `/api/v1/categories/actions` and `/api/v1/categories/types` | Two API calls, one per layer |
| 5 | Endpoint | `GET /api/few-shot-examples` | B14: `GET /api/v1/classification/examples` | Use actual path |
| 6 | Endpoint | `GET /api/classification-config` + `PUT` | Don't exist — LLM config via integrations endpoints | Use `GET /api/v1/integrations/llm` |
| 7 | Field | `Email.from_address` (X2) | `Email.sender_email` | Use generated type field name |
| 8 | Field | `Email.received_at` (X1) | `Email.date` | Use generated type field name |
| 9 | Field | `Draft.body` (X3) | `Draft.content` | Use `content` in generated types |
| 10 | Model | `Email.draft_id` FK | No FK from Email to Draft; `Draft.email_id` FKs to Email | Query drafts by `email_id`, not from Email |
| 11 | Model | Category `layer` discriminator field | Separate tables: `ActionCategory`, `TypeCategory` | No `layer` field — separate API calls per table |
| 12 | Model | `Email.classification` / `Email.routing_actions` inline | Separate tables, composed in `EmailDetailResponse` | Use detail response shape from OpenAPI codegen |
| 13 | Path | All paths `/api/...` (X5) | Prefix: `/api/v1/...` | All frontend API calls use `/api/v1/` |
| 14 | Type | `ReviewQueueItem.confidence: 'high' \| 'low'` | Matches `ClassificationConfidence` enum — confirmed | No change needed |
