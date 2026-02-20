# Workflow Guide -- Claude Code Agent Teams

> Guia central de workflow para proyectos con Claude Code y Agent Teams.
> Generico y agnositco de stack. Extraido de experiencia real en produccion.

---

## 0. Project Values

Three commitments that shape every decision in this workflow.

**Transparency** — Every decision is documented with context and alternatives. Every rejected option has a reason on record. The user never has to guess why something was chosen.

**Timely, Adequate Information** — The right information at the right moment. Not everything at once (overload), not too late (surprise). Each phase surfaces what the user needs to decide NOW, and defers what they don't.

**Improved Experience** — Every automation, template, and gate exists to make design and implementation better — not just faster. Quality of the development experience is a first-class metric alongside code quality.

Complementary principles: Rigor (measurable exit conditions, not vibes). Compound learning (every session builds on the last). Security-first (evaluate before install, always). Context economy (every token earns its place).

---

## 1. Principios

Cinco principios universales que gobiernan todo el workflow.

### P1: Contexto es recurso escaso

El contexto del modelo es finito. Cada token cuenta.

- Ejecutar `/clear` entre bloques para resetear contexto.
- Mantener CLAUDE.md por debajo de 200 lineas. Si crece, podar.
- Delegar investigacion pesada a subagentes (contexto separado, resultado compacto).
- `/compact` proactivamente al 60-70% de capacidad, no al limite. Al limite el modelo degrada calidad (paddo.dev).
- `/effort` para controlar profundidad de razonamiento: `low` (trivial), `high`/`max` (arquitectura, debug complejo).

### P2: Verificacion automatica = quality gate

Nunca confiar en que "parece que funciona". Definir gates concretos.

- Typecheck: cero errores de tipos antes de avanzar.
- Lint: cero warnings sin justificar.
- Tests: todos verdes. NUNCA avanzar con tests rotos.
- Build: compilacion exitosa antes de cerrar un bloque.
- Validacion visual: screenshots o inspeccion manual para cambios de UI.

Estos gates son obligatorios al cierre de cada bloque. No hay excepciones.

### Hooks como quality gates automatizados

Los hooks de Claude Code automatizan gates sin intervencion manual.
Configurar en `.claude/settings.json` o `.claude/settings.local.json`:

- **PostToolUse (Edit/Write):** Auto-format tras cada edicion (`prettier --write $FILE || true`).
  Previene fallos de CI por formato (Boris Cherny, creador de Claude Code).
- **PreToolUse (git commit):** Ejecutar typecheck + lint antes de permitir commit.
  Bloquea commits rotos automaticamente.
- **Stop:** Validacion al final de cada turno del agente (opcional, avanzado).

Ejemplo minimo (`.claude/settings.local.json`):

```json
{
  "hooks": {
    "PostToolUse": [
      { "matcher": "Edit|Write", "command": "npx prettier --write $FILE_PATH || true" }
    ]
  }
}
```

Los hooks son locales (no se commitean) a menos que el equipo acuerde compartirlos.

> **Note:** PostToolUse auto-format is a recommended practice, not installed by `/project-workflow-init`.
> Configure manually if your project uses a formatter (Prettier, Black, rustfmt, gofmt).
> The formatter must be available in the project's dependencies.

### P3: Ralph Loop -- iterar hasta completar

El desarrollo se estructura como un loop determinista:

1. Leer la spec con exit conditions claras.
2. Implementar.
3. Ejecutar quality gates (P2).
4. Si falla: corregir y volver a 3.
5. Si pasa: cerrar bloque.

Las specs deben tener criterios de salida que un script pueda verificar.
"La pagina se ve bien" no es un criterio. "461/461 tests pasan, typecheck limpio,
build exitoso" si lo es.

### P4: Compound Engineering

Cada sesion construye sobre las anteriores. El conocimiento se acumula.

- SCRATCHPAD.md: log de errores, correcciones y patrones por sesion.
- Cuando un patron se repite 3+ veces, se gradua a CLAUDE.md "Learned Patterns".
- CLAUDE.md es la memoria permanente. SCRATCHPAD es la memoria de trabajo.
- Al inicio de cada sesion: leer ambos.

### P5: Preguntar antes de asumir

Regla universal de proyecto. Aplica siempre.

- Ante ambiguedad tecnica: preguntar al usuario, no inventar.
- Ante decision de arquitectura no cubierta por la spec: preguntar.
- Ante duda sobre alcance de una tarea: preguntar.
- Documentar las respuestas en DECISIONS.md para no volver a preguntar.

---

## REGLA TRANSVERSAL: Uso de Skills

A partir de Phase 2 (Tooling & Security), las skills instaladas son conocimiento especializado disponible.
Tratarlas como manuales de referencia, no como decoracion.

- ANTES de cada tarea (planificar, implementar, revisar): identificar que skills aplican.
- Usar solo cuando el trigger de la skill matchea la tarea actual (ahorrar contexto).
- Documentar en las specs de cada bloque que skills aplican.
- Mapear skills por agente: cada worker consulta solo las skills relevantes a su dominio.
- Si ninguna skill aplica a una tarea, documentar por que no aplica.

---

## 2. Project Phases

### Estimated Execution Times (LLM agents)

| Phase | Estimated Time | Bottleneck |
|-------|---------------|------------|
| Phase 0: Foundation | ~3-5 min | File generation, git init |
| Phase 1: Technical Landscape | ~5-10 min | 1.4 Ecosystem Scan: parallel web search |
| Phase 2: Tooling & Security | ~3-5 min per candidate | Cerbero 4-layer evaluation |
| Phase 3: Strategic Review | ~5-8 min | Analysis + writing assessment |
| Phase 4: Architecture Blueprint | ~15-30 min | Design complexity dependent |
| Phase 5: Team Assembly | ~5-10 min | Agent config + review pass |
| Phase N: Development Blocks | Variable | Per-spec |
| Phase Final: Hardening | ~15-30 min | Audit depth dependent |

Phases 0-5 total: ~45-90 min for a typical project.

### Phase 0: Foundation (~3-5 min)

Establecer la estructura base del proyecto.

- Crear `.claude/` con agentes, reglas y `settings.json`.
- Crear `docs/` con STATUS.md, SCRATCHPAD.md, DECISIONS.md.
- Inicializar git con primer commit.
- Escribir CLAUDE.md con stack, comandos, convenciones, reglas.
- Pre-seleccionar agentes (preferencia registrada en STATUS.md).
- Solo Lorekeeper se instala. Demas agentes se instalan en Phase 5.

**Exit condition:** Estructura creada, git inicializado, CLAUDE.md escrito, Lorekeeper activo.

### Phase 1: Technical Landscape (~5-10 min)

Definir decisiones de arquitectura detalladas, herramientas de validacion y documentar decisiones.

- Evaluar opciones tecnicas dentro del stack elegido (auth pattern, ORM, state management, etc.).
- Definir herramientas de validacion para cada dimension:

| Dimension | Herramientas tipicas |
|-----------|---------------------|
| Codigo | Linters (ESLint, Clippy), type checkers (tsc, mypy) |
| Visual | Playwright screenshots, Chrome DevTools, webapp-testing skill |
| Seguridad | SAST/DAST (audit-context-building skill, npm audit, Snyk) |
| Performance | Budgets (JS < 300KB, LCP < 2500ms), Lighthouse, bundle analysis |

- La validacion visual es obligatoria para proyectos con frontend.
  No basta con que los tests pasen; hay que verificar que la UI se ve correcta.
- Documentar todas las decisiones en DECISIONS.md con formato:
  `YYYY-MM-DD | decision | alternativas consideradas | razon`.

#### 1.4 Ecosystem Scan (~2-3 min)

Discover skills, MCPs, and plugins relevant to this project's stack and domain.

**Execution:** Delegate to subagent(s) for context economy. Run 3-5 targeted searches.

##### Search Query Templates

Adapt queries to detected stack and project. Use quoted phrases for precision,
OR for alternatives, date ranges for freshness.

**Q1 — Stack tooling (always):**
`"Claude Code" (skill OR MCP) "{framework}" site:github.com OR site:npmjs.com OR site:pypi.org`
- Next.js: `"Claude Code" (skill OR MCP) "Next.js" site:github.com`
- FastAPI: `"Claude Code" (skill OR MCP) "FastAPI" OR "Python" site:github.com OR site:pypi.org`
- Rails: `"Claude Code" (skill OR MCP) "Rails" OR "Ruby" site:github.com`
- Generic: `"Claude Code" skill "{language}" 2025..2026`

**Q2 — Domain services (if external services detected):**
`MCP server "{service}" (official OR verified) 2025..2026`
- DB: `MCP server "PostgreSQL" OR "Supabase" official 2025..2026`
- Auth: `MCP server "Auth0" OR "Clerk" OR "Firebase Auth" 2025..2026`
- Cloud: `MCP server "AWS" OR "GCP" OR "Vercel" official 2025..2026`
Run once per major service integration.

**Q3 — Quality & testing (always):**
`Claude Code (skill OR plugin) ({test_runner} OR "code quality" OR linter) {language}`
- Node: `Claude Code (skill OR plugin) (vitest OR jest OR "code quality") TypeScript`
- Python: `Claude Code (skill OR plugin) (pytest OR "code quality" OR ruff) Python`
- Rust: `Claude Code (skill OR plugin) (clippy OR "cargo test" OR "code quality") Rust`

**Q4 — Security (if Cerbero enabled):**
`Claude Code MCP security (SAST OR "vulnerability scanner" OR "dependency audit") {language}`

**Q5 — Specialist (if full-stack or complex project):**
`Claude Code skill "{domain_keyword}" site:github.com 2025..2026`
- Domain keywords by project type:
  - E-commerce: "payment", "Stripe", "inventory"
  - SaaS: "multi-tenant", "billing", "subscription"
  - Data: "ETL", "pipeline", "analytics"
  - Mobile: "React Native", "Flutter", "push notification"

##### Query Engineering Notes
- Quoted multi-word phrases: `"Claude Code"` not `Claude Code`
- Date range `2025..2026` filters pre-skills-era results
- `site:github.com` limits to repos with evaluable source (Cerbero needs source)
- Cap at 5 queries — context economy
- If a query returns <3 relevant results, broaden by removing site: filter

**Output: Candidate Ecosystem Catalog** — organized in two tiers:

##### Tier 1 — Core Tools (direct project impact)
Skills/MCPs that directly affect the primary development workflow:
- Stack tools (linters, formatters, framework-specific)
- Domain tools (database MCPs, API integrators, deployment)
- Quality tools (testing frameworks, code analysis)

##### Tier 2 — Agent & Specialist Tools (supporting impact)
Tools for specialized agents and roles:
- Security tools (vulnerability scanners, SAST/DAST for Sentinel)
- Testing tools (coverage analysis, E2E frameworks for Inquisidor)
- Potential specialist tools (UI/UX skills for design-heavy projects, DevOps for infra-heavy, data skills for data-heavy)
- Future-agent tools: skills that would justify adding a specialist agent not yet pre-selected

Each candidate records: Name | Source | Tier | Target (who benefits) | Impact (1-line) | Risk estimate (Low/Medium/High)

**Cap:** Maximum 15 candidates total (both tiers).
**No installation.** No security evaluation. No source code reading. Discovery only.
**Destination:** Append to DECISIONS.md as "Candidate Ecosystem Catalog" table.

**Critical principle:** Architectural decisions can leverage INSTALLED tools directly. For capabilities where no tool was found or approved, design fallback paths. Rejected candidates are documented in DECISIONS.md for future reference.

**Exit condition:** Stack decided, validation tools defined, DECISIONS.md updated,
Candidate Ecosystem Catalog documented (may be empty if no relevant candidates found).

### Phase 2: Tooling & Security (~3-5 min per candidate)

> *Security-first: no tool enters the project without completing the full evaluation protocol.*

Evaluate and install skills/MCPs from the Candidate Ecosystem Catalog (Phase 1.4).

#### 2.1 Evaluate Tier 1 candidates (core tools)
- Full Cerbero evaluation (4 layers, Section 5) per candidate, in priority order
- Install immediately if APPROVED
- If a HIGH-impact candidate is REJECTED, document reason and impact
- Maximum: 10 Tier 1 installations

#### 2.2 Evaluate Tier 2 candidates (agent & specialist tools)
- Same full Cerbero evaluation (security is never optional)
- If APPROVED: record as "approved, pending assignment" in STATUS.md
- Installation deferred to Phase 5 (assigned to specific agent)
- Maximum: 5 Tier 2 installations

#### 2.3 Cerbero installation (if enabled)
Install Cerbero security framework: skill files, hooks, trusted-publishers list,
and hook configuration.

**Full logic:** See ref-cerbero-installation.md — sections 4.0 through 4.5.

> **Note:** `cerbero-scanner.py` is copied to `.claude/hooks/` for co-location but is NOT registered as an automatic hook. It is a Tier 0 external scanner invoked manually by Sentinel or `/cerbero audit`.

**Present to user:**
```
--- Tooling Summary ---
TIER 1 (Core): Installed: {list} | Rejected: {list with reasons}
TIER 2 (Specialist): Approved: {list with target agent} | Rejected: {list}
Total: {evaluated} | Installed: {N} | Pending: {K} | Rejected: {J}
```

**Exit condition:** Candidates evaluated per priority list. Installed and rejected documented in STATUS.md with tier designation.

### Phase 3: Strategic Review (~5-8 min)

> *Transparency: document every decision adjustment with the evidence that prompted it.*

Full plan re-evaluation enriched by installed tools from Phase 2. This review now operates on actual capabilities (installed tools) rather than candidates, making it a concrete assessment instead of speculative.

**Input:** All Phase 1 outputs (stack decisions, validation tools, DECISIONS.md, Candidate Ecosystem Catalog) + Phase 2 outputs (installed tools, rejected candidates, Tooling Summary).

**Fast-path:** Skip analysis if ALL true:
- Candidate Ecosystem Catalog is empty (no candidates found in 1.4)
- Single stack (no full-stack, no monorepo)
- Agent pre-selection is "Generalistas" or "Lorekeeper only"

If skipping: copy Phase 1 decisions as-is. Note "Fast-path: no candidates." in DECISIONS.md Strategic Assessment. Advance to Phase 4.

**Analysis dimensions:**

| Dimension | Question | Source |
|-----------|----------|--------|
| Stack fit | Do installed tools confirm or challenge the stack choice? | Phase 2 installed tools |
| Agent composition | Does the pre-selected agent set match installed tooling? Add specialist agent? | Tier 2 results |
| Skill coverage | Are there critical gaps no installed tool covers? | Phase 2 results |
| MCP opportunities | Do installed MCPs enable architectural shortcuts? | Tier 1 installed |
| Validation strategy | Do installed testing/quality tools improve the validation approach? | Phase 2 results |
| Security posture | Do installed security tools cover the project's risk surface? | Tier 2 results |
| Architecture implications | Do any installed tools fundamentally change how the system should be designed? | Phase 2 results |

**Output: Strategic Assessment** — appended to DECISIONS.md with:
1. Confirmation or revision of each Phase 1 decision, citing installed tools as evidence
2. Agent composition recommendation (confirm pre-selection or suggest changes)
3. Architecture directives for Phase 4 (what installed tools enable or constrain)

#### 3.1 Decision Gate

| Condition | Action |
|-----------|--------|
| All Phase 1 decisions confirmed | Advance to Phase 4 |
| Minor adjustments (tool swap, validation change) | Apply to DECISIONS.md, advance to Phase 4 |
| Stack choice challenged by evidence | **Loop back to Phase 1** with specific scope |
| Agent pre-selection inadequate | Update STATUS.md, advance to Phase 4 |

**Loop-back protocol:**
- Maximum 1 loop-back (prevents infinite cycles)
- Scope is NARROW: only re-evaluate the specific flagged dimension
- Document loop-back reason in DECISIONS.md before re-entering Phase 1
- Second pass through Phase 3 MUST advance

**Present to user before proceeding:**
```
--- Strategic Review Summary ---
Phase 1 decisions: {N confirmed, M adjusted, K flagged}
Installed tools: {X Tier 1, Y Tier 2} | Rejected: {Z}
Agent composition: {confirmed / updated}
Recommendation: {Advance to Phase 4 / Loop back (scope: ...)}
```

**Exit condition:** User approves strategic assessment. DECISIONS.md updated. Architecture directives documented.

### Phase 4: Architecture Blueprint (~15-30 min)

**Input:** Strategic Assessment from Phase 3 + installed tools from Phase 2.
Design the system leveraging actual installed capabilities. For capabilities where no tool was approved, design fallback paths.

Disenar el sistema completo antes de implementar.

- Modelo de datos: tablas/colecciones, relaciones, indices, constraints.
- API: endpoints, auth, formatos de request/response, cache strategy.
- Componentes: estructura de directorios, server vs client, responsive strategy.
- Descomponer en bloques de trabajo con specs individuales.
- Cada spec debe tener: scope, archivos afectados, exit conditions, skills que aplican.
- Reference installed tools directly in specs (no need for fallback paths on installed tools).

**Exit condition:** architecture.md completo, N specs en docs/specs/, cada una con exit conditions.

### Phase 5: Team Assembly (~5-10 min)

Instalar agentes y sincronizar documentacion del proyecto.

#### 5.1 Instalar agentes pre-seleccionados
- Revisar pre-seleccion registrada en STATUS.md (Phase 0, pregunta 5).
- Instalar agentes desde templates (excepto Lorekeeper, ya instalado).
- Confirmar file ownership en AGENT-COORDINATION.md (seccion 5).
- Check Tier 2 approved tools — install any assigned to this agent.

#### 5.2 Review pass de CLAUDE.md y AGENT-COORDINATION.md
- Lorekeeper revisa CLAUDE.md: verificar que refleja decisiones de Phase 1, 3, and 4.
- Actualizar AGENT-COORDINATION.md con informacion real del proyecto.

#### 5.3 Asignar skills a agentes (including Tier 2 tools)
- Completar seccion 13 de AGENT-COORDINATION.md (Skills Instaladas + Asignacion por Agente).
- Cada skill debe tener un agente responsable de consultarla.

> *Context economy: assign each agent only the tools it needs. Unused tools are wasted tokens.*

#### 5.4 Final Consistency Check

> *Note: Full architecture reconciliation is unnecessary because the architecture (Phase 4) was designed after tooling was installed (Phase 2). Verify only that specs correctly reference installed tools.*

- Confirm each spec in docs/specs/ references only installed (not rejected) tools.
- If any discrepancy is found, update the spec. Log corrections in DECISIONS.md.

**Exit condition:** Agentes activos, AGENT-COORDINATION.md seccion 13 completa. Specs verified against installed tooling.

### Phase N: Development Blocks

Cada bloque sigue el Ralph Loop (seccion 3).

- Un bloque por sesion (o sub-sesion con `/clear` entre ellos).
- Branch por bloque: `feature/bloque-N-nombre`.
- Leer SCRATCHPAD.md al inicio para contexto de sesiones previas.
- Al cerrar: actualizar SCRATCHPAD.md, CLAUDE.md si hay patrones nuevos, STATUS.md.

**Exit condition:** Definida en la spec del bloque. Siempre incluye quality gates (P2).

### Phase Final: Hardening (~15-30 min)

Iteracion final de calidad sobre el proyecto completo.

- Seguridad: headers, rate limiting, sanitizacion, audit con skill de seguridad.
- Performance: budgets, Lighthouse, bundle analysis, caching, lazy loading.
- Accesibilidad: contraste, focus indicators, skip links, screen reader testing.
- Validacion visual completa: todas las paginas, todos los breakpoints.

**Exit condition:** Audit de seguridad limpio, performance dentro de budgets,
accesibilidad WCAG AA, build de produccion exitoso.

---

## 3. Ralph Loop

### Nivel Simple: Un agente

Un solo agente (o el usuario directamente) itera hasta cumplir exit conditions.

```
+------------------+
|   Leer spec      |
|  (exit conditions)|
+--------+---------+
         |
         v
+------------------+
|   Implementar    |
+--------+---------+
         |
         v
+------------------+     FALLA     +------------------+
| Quality gates    +-------------->+   Corregir       |
| (typecheck, lint,|               |   errores        |
|  test, build)    |               +--------+---------+
+--------+---------+                        |
         |                                  |
         | PASA                             |
         v                                  |
+------------------+                        |
| Cerrar bloque    |<-----------------------+
| (scratchpad,     |        (volver a gates)
|  status, commit) |
+------------------+
```

### Distribucion de esfuerzo

Distribucion recomendada basada en compound engineering (Every Inc):

- **Plan: ~40%** — Investigar codebase, leer specs, diseñar approach. Plan Mode antes de escribir codigo.
- **Work: ~20%** — Implementar segun el plan. El codigo es la parte rapida si el plan es solido.
- **Review: ~40%** — Verificar quality gates, revisar diffs, documentar learnings.

### Declarativo > Imperativo

No dar instrucciones paso a paso. Dar criterios de exito y dejar que el agente itere.
"Don't tell it what to do, give it success criteria and watch it go" — Karpathy.

Specs con exit conditions claros (P3) son superiores a instrucciones procedurales.
El agente decide el "como", el humano define el "que" y valida el resultado.

### Stop conditions

Evitar loops infinitos con limites explicitos:

- **Max iteraciones:** Si un gate falla 3+ veces consecutivas en el mismo error, parar y escalar al usuario.
- **"No asumir no implementado":** SIEMPRE buscar en el codebase antes de crear algo nuevo.
  El failure mode mas comun de agentes es reimplementar funcionalidad existente (ghuntley).
- **Timeout de sesion:** Si el contexto supera ~70% sin progreso, `/compact` o `/clear` y reiniciar con spec fresco.
- **Sycophancy check:** Los modelos no pushean back cuando deberian. Si el agente acepta todo
  sin cuestionar, o genera 1000 lineas donde bastan 100, intervenir y recalibrar (Karpathy).

### Nivel Agent Teams: Lead + Workers

Para bloques con trabajo paralelizable. El Lead coordina, NUNCA implementa.

```
+------------------+
|      LEAD        |
|  (Delegate Mode) |
+--+-----+-----+--+
   |     |     |
   v     v     v
+----+ +----+ +----+
| W1 | | W2 | | W3 |    Workers paralelos
+--+-+ +--+-+ +--+-+    (file ownership estricto)
   |     |     |
   v     v     v
+------------------+
| Quality gates    |     Lead ejecuta validacion
+--------+---------+
         |
    PASA | FALLA
         v
+------------------+
| Lead reasigna    |     Si falla: Lead identifica worker
| correcciones     |     responsable y reasigna
+------------------+
```

Reglas de Agent Teams:

- **File ownership estricto:** Dos workers NUNCA editan el mismo archivo.
- **Orden de spawn:** El worker que genera tipos/contratos va primero.
  Los consumidores se spawnean cuando los tipos estan listos.
- **Foreground vs background:** Foreground si el Lead espera el resultado para
  continuar. Background solo si el Lead tiene trabajo propio en paralelo.
- **Congelado de tipos:** Una vez que los tipos se publican, son read-only
  para el resto del bloque. Cambios requieren archivo nuevo.
- **Task sizing:** 5-6 tareas por teammate es el sweet spot. Muy pocas = overhead
  sin beneficio. Muchas = esfuerzo desperdiciado antes del check-in (Osmani).
- **Start read-only:** La primera ejecucion con Agent Teams deberia ser code review,
  no refactor. Aprender coordinacion antes de dejar que multiples agentes escriban (Osmani).
- **Competing hypotheses (debug):** Para bugs complejos, spawnear 3-5 agentes con
  teorias diferentes. Investigacion secuencial sufre de anchoring bias (Osmani).

---

## 4. Compound Engineering

### SCRATCHPAD.md

Log de aprendizaje por sesion. Todos los agentes escriben con su tag.

**Template por sesion:**

```markdown
## YYYY-MM-DD -- [descripcion breve]

### Errores cometidos
- [agente] Descripcion del error y como se manifesto

### Correcciones del usuario
- "Cita textual del usuario" -- interpretacion y accion tomada

### Que funciono bien
- [agente] Patron o tecnica que produjo buen resultado

### Que NO funciono
- [agente] Enfoque que se descarto y por que

### Preferencias descubiertas
- Preferencia del usuario observada en esta sesion
```

**Reglas:**

- Todos los agentes escriben con tag `[nombre-agente]`.
- El Lorekeeper es custodio: organiza, poda, gradua.
- Limite: 150 lineas maximo. Si crece, podar entradas antiguas ya graduadas.

### Graduation a CLAUDE.md

Cuando un patron se repite 3 o mas veces en el SCRATCHPAD:

1. El Lorekeeper lo identifica y lo mueve a CLAUDE.md seccion "Learned Patterns".
2. La entrada en SCRATCHPAD se marca como "graduada" y se poda en la siguiente sesion.
3. CLAUDE.md se agrupa por bloque o por tema.

Formato en CLAUDE.md:

```markdown
### Learned Patterns
#### Bloque N: Nombre
- patron corto en una linea -- contexto minimo necesario
```

---

## 5. Evaluacion de Skills/MCPs (4 capas + sandbox)

Toda skill o MCP debe pasar 4 capas de evaluacion antes de instalarse.

### Capa 1 -- Source code review (SANDBOXED)

La capa mas critica. Ejecutar en aislamiento.

- Spawnear un agente aislado (Sentinel o subagente read-only).
- El agente revisa el source de la skill buscando:
  - `eval()`, `exec()`, `spawn()`, `Function()` (ejecucion dinamica)
  - `fetch()`, `http`, `net` (acceso a red no declarado)
  - `fs`, `writeFile`, `readFile` (acceso a filesystem no declarado)
  - Patron de prompt injection (instrucciones ocultas en comentarios o strings)
- El agente reporta hallazgos al Lead SIN que el Lead lea el source directamente.
  Esto previene contaminacion del contexto del Lead con instrucciones maliciosas.
- Solo tras aprobacion explicita del Lead se procede a instalar.

### Capa 2 -- Reputacion y procedencia

- Publisher verificado: organizacion conocida (ej: Vercel, Anthropic, Supabase,
  Google, Trail of Bits, Currents.dev).
- Repositorio publico con stars, issues, actividad reciente.
- Sin CVEs conocidas asociadas al paquete.
- Descartar publishers desconocidos o sin historial verificable.

### Capa 3 -- Dependencias

- Ejecutar audit de dependencias (`npm audit`, `pip audit`, equivalente del ecosistema).
- Revisar dependencias transitivas: una skill limpia con una dependencia comprometida
  es una skill comprometida.
- Verificar que la version publicada en el registry coincide con el source en el repositorio.

### Capa 4 -- Risk matrix

Clasificar el nivel de riesgo segun las capacidades que requiere:

| Nivel | Capacidades | Ejemplo | Accion |
|-------|------------|---------|--------|
| Bajo | Solo prompt (markdown, texto) | Guias de best practices | Instalar tras Capas 1-3 |
| Medio | Lectura de archivos | Audit tools read-only | Instalar tras Capas 1-3 + revision manual |
| Alto | Shell, red, DB, escritura | MCP con acceso a bash | Requiere aprobacion explicita del usuario |

### Protocolo de aprobacion

Las 4 capas deben pasar. Si cualquier capa falla, la skill se rechaza.
Documentar skills rechazadas con la razon para no reevaluar en el futuro.

---

## 6. Gestion de Contexto

### Que persiste despues de /clear

| Persiste | Se pierde |
|----------|-----------|
| CLAUDE.md y su contenido | Conversacion actual |
| docs/ completo | Variables de sesion |
| Todo el filesystem (git, src/) | Contexto de agentes/subagentes |
| Git history | Resultados de tools no guardados |

### Estrategias

- **`/clear` entre bloques:** Resetea contexto. El agente vuelve a leer CLAUDE.md
  automaticamente. Ideal entre bloques de desarrollo.
- **`/compact` proactivo:** Comprimir al 60-70% de capacidad, NO esperar al limite.
  Al limite, el modelo se apura y degrada calidad (paddo.dev).
- **Document & Clear:** Alternativa a `/compact` — exportar progreso a markdown,
  `/clear`, resumir con archivo de contexto. Preserva precision vs compresion lossy (Shankar).
- **Subagentes para investigacion:** Resultado compacto (1-2K tokens) vuelve al caller
  sin contaminar su contexto con material intermedio.
- **`/effort max`:** Para decisiones arquitectonicas complejas o debug dificil.
  `/effort low` para tareas triviales (ahorra tokens).
- **Foreground vs background:** Foreground cuando espero el resultado.
  Background solo con trabajo propio en paralelo.
- **Git worktrees (avanzado):** Para sesiones paralelas reales — cada sesion en su
  propio worktree con archivos aislados, mismo Git history. Mejor que branches
  para evitar conflictos (Boris Cherny, incident.io).

### Document Reference Strategy

How docs reference each other — evaluated for token efficiency, maintenance, and cross-platform compatibility.

| Method | Token Impact | Maintenance | Platform | Used In | Verdict |
|--------|-------------|-------------|----------|---------|---------|
| **Symlinks** | Zero (OS-level) | Low | Windows needs admin, OneDrive ignores, git tracks poorly | — | **Rejected** |
| **Relative markdown links** | Zero (display only) | Low | Universal | README, CONTRIBUTING | **Active** |
| **`@docs/FILE.md` refs** | Zero (Claude auto-loads) | Low | Claude Code only | CLAUDE.md | **Active** |
| **`ref-*.md` delegation** | Deferred (loaded on demand) | Medium | Universal | SKILL.md | **Active — primary pattern** |
| **Doc consolidation** | Higher (full file per read) | Low | Universal | — | **Rejected** |

**Decision:** The current hybrid system is optimal:
1. **`ref-*.md` files** for skill logic — keeps SKILL.md focused, Claude loads refs only when needed (saves tokens)
2. **`@docs/FILE.md`** in CLAUDE.md — Claude Code auto-includes referenced files in context
3. **Relative markdown links** for human-readable cross-references in docs

Symlinks are explicitly rejected: Windows requires admin permissions for symlinks, OneDrive sync ignores them, and Git doesn't track them reliably. The current system achieves the same goal (modular info access) without OS-level dependencies.

---

## 7. Antipatrones

| # | Antipatron | Consecuencia | Correccion |
|---|-----------|--------------|------------|
| 1 | Olvidar usar skills | Reinventar soluciones que la skill ya cubre | Regla en CLAUDE.md: revisar skills antes de cada tarea |
| 2 | Instalar skill sin sandbox | Prompt injection o codigo malicioso en contexto | Siempre Capa 1 con agente aislado (seccion 5) |
| 3 | Validar solo con tests de archivo | UI rota que pasa tests unitarios | Validacion visual obligatoria (screenshots, inspeccion) |
| 4 | Bloque demasiado grande | Sesion agota contexto, errores cascadean | Dividir en sub-bloques con exit conditions propios |
| 5 | Lead que implementa | Pierde vision global, conflictos de archivos | Delegate Mode: Lead coordina, workers implementan |
| 6 | Workers pisandose archivos | Merge conflicts, overwrites silenciosos | File ownership estricto: un archivo = un owner |
| 7 | Avanzar con tests rojos | Deuda tecnica acumulada, errores enmascarados | NUNCA avanzar. Corregir antes de continuar |
| 8 | CLAUDE.md inflado | Modelo pierde foco, respuestas genericas | Podar a menos de 200 lineas. Mover detalle a docs/ |
| 9 | Sesion kitchen sink | Multiples bloques en una sesion, contexto saturado | Un bloque por sesion. /clear entre bloques |
| 10 | Documentar de mas | Ruido en docs, mantenimiento costoso | Solo documentar lo que no se infiere del codigo |
| 11 | Specs vagos | "Se ve bien" no es verificable, iteraciones infinitas | Criterios deterministicos: N tests pasan, build OK |
| 12 | No actualizar CLAUDE.md post-bloque | Sesion siguiente repite errores ya resueltos | Siempre actualizar Learned Patterns al cerrar bloque |
| 13 | Reimplementar sin buscar | Crear codigo que ya existe en el codebase | SIEMPRE buscar antes de crear. Regla en CLAUDE.md (ghuntley) |
| 14 | El Trap de 19 agentes | Recrear org charts humanos en agentes (Analyst→PM→Dev→QA) | Minimal effective structure: 1-2 agentes, agregar ante limites concretos (paddo.dev) |
| 15 | No usar hooks | Gates manuales que se olvidan, CI falla por formato | PostToolUse auto-format + PreToolUse pre-commit (Boris Cherny) |

---

## 8. Fuentes y Referencias

### Ralph Loop
- ghuntley.com/loop -- Articulo original sobre el patron de iteracion con LLMs.
- vincirufus.com -- Variaciones y adaptaciones del loop para proyectos reales.
- paddo.dev -- Implementacion practica y casos de uso.

### Claude Code
- code.claude.com/docs -- Documentacion oficial:
  - Best Practices: estructura de CLAUDE.md, comandos, workflows.
  - Agent Teams: Lead/Teammate, Task tool, comunicacion entre agentes.
  - Skills: instalacion, triggers, evaluacion de seguridad.
  - MCP: configuracion, servidores, permisos.

### Anthropic
- anthropic.com/engineering/multi-agent-research-system -- Arquitectura multi-agente.
- anthropic.com/engineering/effective-context-engineering -- Smallest set of high-signal tokens.
- claude.com/blog/eight-trends-defining-how-software-gets-built-in-2026 -- 60% AI-assisted, 57% multi-agent.

### Compound Engineering
- every.to/chain-of-thought/compound-engineering -- Plan 40% / Work 20% / Review 40%.
- github.com/EveryInc/compound-engineering-plugin -- Plugin oficial con 4 workflows.

### Practicas de la industria
- Andrej Karpathy -- Vibe coding → agentic engineering, declarativo > imperativo, sycophancy awareness.
- Boris Cherny (creador Claude Code) -- CLAUDE.md como mistake log, PostToolUse hooks, verification loops.
- Addy Osmani -- Spec-first, task sizing, competing hypotheses, self-improving agents.
- Simon Willison -- Two-phase approach (research → production), LLMs como pair programmers.
- Harper Reed -- TDD como counter a hallucination, spec → plan → execute.
- paddo.dev -- Minimal effective structure, 19-Agent Trap, /compact timing.
- swyx (Latent Space) -- IMPACT framework, conductor model.
