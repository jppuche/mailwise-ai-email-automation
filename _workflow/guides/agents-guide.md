# Guia de Seleccion e Inicializacion de Agentes

## Modelo de pre-seleccion

Durante `/project-workflow-init` (Phase 0), el usuario elige una preferencia de agentes. Esta preferencia se registra en `docs/STATUS.md` pero **no se instala** (excepto Lorekeeper). La instalacion real ocurre en Phase 5: Team Assembly, cuando la arquitectura este definida y las skills asignadas. Note: Tier 2 tools from Phase 4 may influence agent composition.

### Opciones de pre-seleccion (pregunta 5 de /project-workflow-init)

| Opcion | Agentes incluidos | Nota |
|--------|------------------|------|
| **Generalistas** (default) | Lorekeeper + Inquisidor + Sentinel | Cubren documentacion, testing y seguridad |
| **Generalistas + especificos** | Los 3 generalistas + backend-worker + frontend-worker | Los especificos se confirman en Phase 5 |
| **Lorekeeper only** | Lorekeeper | Solo compound engineering y documentacion. Sin testing (Inquisidor) ni auditorias (Sentinel). Quality gates dependen enteramente de hooks |
| **Ninguno** | (ninguno) | ADVERTENCIA: sin compound engineering, quality gates ni auditorias |
| **Otro** | Texto libre | Se registra para Phase 5 |

Lorekeeper se instala siempre en Phase 0 (compound engineering desde el inicio).

---

## Agentes disponibles

| Agente | Rol | Siempre necesario | Cuando incluir |
|--------|-----|-------------------|----------------|
| **Lorekeeper** | Documentacion, CLAUDE.md, compound engineering | Si | Siempre (instalado en Phase 0) |
| **Inquisidor** | Tests unitarios, integracion, E2E, quality gates | Si | Todo proyecto debe tener tests |
| **Sentinel** | Auditorias de seguridad, evaluacion sandboxed, custodia de hooks | Si | Seguridad no es opcional |
| **backend-worker** | API, base de datos, logica server-side | No | Si hay API, DB o logica server |
| **frontend-worker** | UI, componentes, estilos, assets | No | Si hay interfaz de usuario |

### Sentinel — custodia de hooks y Cerbero

Sentinel es el agente ejecutor del skill Cerbero. Custodia:
- `.claude/hooks/validate-prompt.py` — deteccion de prompt injection
- `.claude/hooks/pre-tool-security.py` — bloqueo de comandos peligrosos + warnings
- `.claude/hooks/mcp-audit.py` — logging de invocaciones MCP
- `.claude/hooks/cerbero-scanner.py` — scanner externo Tier 0

Si un hook falla o necesita actualizacion, Sentinel diagnostica y reporta al lead.

---

## Protocolo de inicializacion de agente (Gap 17)

Al spawnear cualquier agente, ejecutar estos 7 pasos:

1. **Leer CLAUDE.md** — memoria del proyecto, reglas, patrones
2. **Leer SCRATCHPAD.md** — contexto de sesiones previas, errores conocidos
3. **Leer AGENT-COORDINATION.md** — protocolo de comunicacion, file ownership
4. **Verificar file ownership** — confirmar dominio exclusivo y archivos prohibidos (seccion 5)
5. **Verificar skills asignadas** — consultar seccion 13 de AGENT-COORDINATION
6. **Check Tier 2 approved tools** — install any assigned to this agent (from STATUS.md)
7. **Confirmar permisos** — prueba inocua por herramienta requerida

Solo despues de los 6 pasos el agente comienza su tarea.

---

## Agentes custom

Si el proyecto tiene dominios especificos no cubiertos por los 5 agentes base:

1. Copiar el template mas cercano
2. Adaptar: dominio, reglas criticas, archivos prohibidos
3. Asignar skills relevantes
4. Documentar en AGENT-COORDINATION.md (seccion 5 + seccion 13)

---

## File ownership

**REGLA:** Dos workers NUNCA editan el mismo archivo. Si hay conflicto, el lead reasigna.

| Worker | Exclusivo | Prohibido |
|--------|-----------|-----------|
| frontend-worker | componentes, paginas, estilos, assets | backend, API, DB, tests, docs |
| backend-worker | logica, API, DB, tipos compartidos | frontend, tests, docs |
| Inquisidor | tests, config de testing | codigo produccion, docs |
| Lorekeeper | docs/, CLAUDE.md | codigo fuente |
| Sentinel | .claude/hooks/, .claude/security/ | todo excepto hooks y security |

---

## Protocolo universal (todos los agentes)

1. **Al inicio de sesion:** leer `docs/SCRATCHPAD.md`
2. **Durante sesion:** trabajar en dominio exclusivo
3. **Al cierre:** append en `docs/SCRATCHPAD.md` con tag `[nombre-agente]`
