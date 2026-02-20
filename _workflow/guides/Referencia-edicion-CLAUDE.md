# Referencia para Edicion de CLAUDE.md

> Guia para crear y mantener archivos CLAUDE.md.
> Basada en documentacion oficial de Anthropic + workflow de este proyecto.
> Ultima actualizacion: 2026-02-10

**Lo esencial en 4 reglas:**

1. Mantener < 200 lineas — mas alla, las reglas se ignoran
2. Solo incluir lo que Claude no puede inferir del codigo
3. Reglas criticas → implementar como hook, no solo texto
4. SCRATCHPAD → 3+ ocurrencias → graduar a CLAUDE.md

---

## 1. Que es CLAUDE.md

Archivo Markdown leido al inicio de cada sesion de Claude Code. Memoria persistente del proyecto: convenciones, comandos, arquitectura y reglas que Claude no infiere del codigo. Nombre obligatorio: `CLAUDE.md` (case-sensitive). Se recarga automaticamente tras compactacion del contexto.

---

## 2. Jerarquia de archivos

Mayor prioridad = mas abajo:

| Tipo | Ubicacion | Alcance | Git |
|------|-----------|---------|-----|
| Enterprise policy | `C:\Program Files\ClaudeCode\CLAUDE.md` | Organizacion | IT/DevOps |
| User memory | `~/.claude/CLAUDE.md` | Todos tus proyectos | No |
| User rules | `~/.claude/rules/*.md` | Todos tus proyectos | No |
| Project memory | `./CLAUDE.md` o `./.claude/CLAUDE.md` | Equipo | Si |
| Project rules | `./.claude/rules/*.md` | Equipo | Si |
| Project local | `./CLAUDE.local.md` | Solo tu, este proyecto | No (auto-gitignore) |
| Child dirs | `./subdir/CLAUDE.md` | On-demand al leer archivos del subdir | Segun ubicacion |
| Auto memory | `~/.claude/projects/<id>/memory/` | Solo tu, por proyecto | No |

Instrucciones mas especificas prevalecen sobre las generales.

---

## 3. Estructura recomendada

### Secciones esenciales

```markdown
# Proyecto
Descripcion breve del proyecto y su stack principal.

# Comandos
- Build: `npm run build`
- Test: `npm run test -- --watch`
- Lint: `npm run lint`

# Estilo de codigo
- ES Modules, no CommonJS
- Componentes PascalCase, hooks con prefijo `use`

# Workflow
- Typecheck despues de cada serie de cambios
- Preferir tests individuales, no toda la suite
```

### Secciones opcionales

| Seccion | Proposito | Ejemplo |
|---------|-----------|---------|
| Arquitectura | Decisiones no evidentes en el codigo | Monorepo: apps/web, apps/api |
| Advertencias | Gotchas y errores comunes | NUNCA modificar /migrations |
| Skills | Skills instalados con triggers | `/cerbero` → evaluacion seguridad |
| Hooks | Enforcement automatico activo | validate-prompt.py bloquea injection |
| Terminologia | Definiciones del dominio | Sprint = iteracion de 2 semanas |
| Agent Teams | File ownership y skills por agente | Ver subseccion Agent Teams |
| Scratchpad | Referencia al log de sesion | Ver `docs/SCRATCHPAD.md` |
| Learned Patterns | Patrones graduados desde SCRATCHPAD | Ver Compound Engineering |
| Compactacion | Que preservar al compactar contexto | Ver Limites y compactacion |

### Skills en CLAUDE.md

Documentar skills instalados para que Claude y agentes sepan que consultar:

```markdown
# Skills
| Skill | Trigger | Descripcion |
|-------|---------|-------------|
| Cerbero | /cerbero | Evaluacion de seguridad de MCPs/Skills |
```

Skills son conocimiento consultivo — invocar ANTES de cada tarea relevante.

### Agent Teams

Cuando el proyecto usa Agent Teams, CLAUDE.md debe incluir:

- **File ownership** — Carpetas exclusivas por worker. Dos workers NUNCA editan el mismo archivo.
- **Architecture** — Decisiones que los agentes consultan para coherencia.
- **Skills mapping** — Que skill consulta cada agente antes de su tarea.

Coordinacion detallada va en `docs/AGENT-COORDINATION.md`, no en CLAUDE.md.

### Imports con @

```markdown
Ver @docs/api-patterns.md para convenciones de API.
```

- Rutas relativas al archivo contenedor. Max 5 niveles
- No se evaluan dentro de bloques de codigo
- Primera vez requiere aprobacion del usuario; si se rechaza, quedan deshabilitados permanentemente

---

## 4. Enforcement: reglas y hooks

### Reglas modulares (.claude/rules/)

Todos los `.md` en `.claude/rules/` se cargan con misma prioridad que CLAUDE.md. Reglas condicionales por ruta:

```markdown
---
paths: ["src/api/**/*.ts"]
---
Todos los endpoints deben incluir validacion de input.
```

### Hooks

Enforcement determinista para reglas que CLAUDE.md no puede garantizar por si solo.

| Evento | Cuando | Uso tipico |
|--------|--------|------------|
| `UserPromptSubmit` | Al enviar prompt | Detectar prompt injection |
| `PreToolUse` | Antes de ejecutar herramienta | Bloquear comandos peligrosos, auditar MCP |
| `PostToolUse` | Despues de ejecutar herramienta | Logging, validacion |
| `Stop` | Antes de que Claude termine | Quality gates, evitar paradas prematuras |
| `PreCompact` | Antes de compactar contexto | Preservar informacion critica |
| `SessionStart` | Al iniciar sesion | Inyectar contexto dinamico |

Configuracion en `.claude/settings.local.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "command": "python .claude/hooks/validate-prompt.py" }],
    "PreToolUse": [{ "command": "python .claude/hooks/pre-tool-security.py", "tools": ["Bash"] }]
  }
}
```

**Regla:** Si una regla es critica → implementar como hook, no depender solo de texto en CLAUDE.md.

> Existen 14 eventos de hook en total. Ver [documentacion de hooks](https://code.claude.com/docs/en/hooks) para referencia completa.

---

## 5. Compound Engineering — evolucion de CLAUDE.md

Ciclo para que CLAUDE.md crezca con aprendizajes reales, no suposiciones:

```
SCRATCHPAD.md (sesion) → patron repetido 3+ veces → CLAUDE.md "Learned Patterns"
```

1. **Registrar** — Al final de cada sesion, anotar en SCRATCHPAD: errores, correcciones, que funciono, que no.
2. **Detectar** — Patron 3+ veces en SCRATCHPAD = candidato a graduacion.
3. **Graduar** — Mover a seccion `# Learned Patterns` de CLAUDE.md como regla permanente.
4. **Podar** — Eliminar graduados de SCRATCHPAD. Eliminar de CLAUDE.md patrones obsoletos.

> **Prueba de relevancia:** "Si elimino esta linea, Claude cometeria errores?" Si NO → eliminar.

### Cuando actualizar

| Senal | Accion |
|-------|--------|
| Claude repite un error evitable | Agregar regla |
| Claude pregunta algo que CLAUDE.md deberia responder | Mejorar redaccion |
| Claude acierta sin necesitar la regla | Eliminar (podar) |
| Nuevas herramientas o workflows | Actualizar comandos |

---

## 6. Limites y compactacion

| Restriccion | Valor | Impacto |
|-------------|-------|---------|
| Lineas CLAUDE.md root | 50-100, max 300 | Mas lineas = reglas ignoradas |
| Instrucciones efectivas | ~150-200 (system prompt usa ~50) | Solo ~100-150 tuyas se siguen |
| Auto memory | Primeras 200 lineas | Mover detalles a archivos topicos |
| Budget de skills | 2% del context window (~16k chars) | Skills excedentes se excluyen silenciosamente |
| Context window | Finito, se degrada | Usar /clear entre tareas |

### Compactacion

Cuando el contexto se llena (~95%), Claude Code compacta (resume) la conversacion. CLAUDE.md se recarga tras compactacion, pero instrucciones de sesion pueden perderse.

- Agregar directivas en CLAUDE.md: `Al compactar, preservar lista de archivos modificados y comandos de test`
- `/compact <instrucciones>` para compactacion manual dirigida
- `/context` muestra uso actual del contexto y warnings de skills excluidos

---

## 7. Criterios de contenido

### Que incluir

- Comandos que Claude no puede adivinar
- Reglas de estilo que difieren de convenciones estandar
- Runners de test y configuracion especifica
- Convenciones de repo (branches, commits, PRs)
- Decisiones arquitecturales del proyecto
- Gotchas y comportamientos no obvios
- Terminologia de dominio
- Skills instalados con triggers
- Hooks activos y su proposito

### Que NO incluir

- Convenciones que Claude ya conoce por defecto
- Documentacion extensa (enlazar con @imports)
- Info que cambia frecuentemente
- Credenciales o API keys
- Instrucciones task-specific (→ Skills)
- Coordinacion detallada de agentes (→ docs/)

### Anti-patrones

| Anti-patron | Solucion |
|-------------|----------|
| > 300 lineas | Podar. Si Claude acierta sin la regla, eliminarla |
| Instrucciones vagas | Especifico: "2 espacios, semicolons siempre" |
| Contenido desactualizado | Tratar como codigo vivo, revisar periodicamente |
| Duplicacion | Una vez, clara y directa |
| Todo en un archivo | Modularizar con `.claude/rules/` |
| Reglas sin enforcement | Implementar como hook |
| Info task-specific | Mover a Skills |
| Coordinacion de agentes inline | Mover a `docs/AGENT-COORDINATION.md` |

### Redaccion

- Imperativo directo: "Usar X", "No hacer Y"
- Una instruccion por bullet
- `IMPORTANTE` o `NUNCA` para reglas criticas
- Ejemplos concretos > explicaciones abstractas

---

## 8. Verificacion y diagnostico

### Checklist pre-commit

- [ ] < 200 lineas (idealmente 50-100 en root)
- [ ] Cada linea pasa prueba de relevancia
- [ ] Sin credenciales ni info sensible
- [ ] Comandos probados y actualizados
- [ ] Sin duplicacion
- [ ] Skills con triggers documentados
- [ ] Hooks criticos implementados (no solo texto)
- [ ] Task-specific en Skills, no en CLAUDE.md
- [ ] Coordinacion de agentes en docs/, no inline
- [ ] Imports (@) apuntan a archivos existentes

### Diagnostico

| Comando | Que muestra |
|---------|-------------|
| `/memory` | Archivos de memoria cargados y sus fuentes |
| `/context` | Uso del contexto y warnings de skills excluidos |
| `claude --debug` | Detalle de hooks ejecutados y matching |
| `Ctrl+O` | Modo verbose: thinking, hooks, razonamiento interno |

### Problemas comunes

| Sintoma | Causa probable | Solucion |
|---------|---------------|----------|
| Claude ignora instrucciones | CLAUDE.md muy largo | Podar por debajo de 200 lineas |
| Instrucciones perdidas tras sesion larga | Compactacion elimino contexto | Agregar directivas de compactacion |
| Claude pregunta cosas en CLAUDE.md | Redaccion ambigua | Reformular en imperativo directo |
| Hook no se ejecuta | Configuracion incorrecta | Verificar con `claude --debug` |
| Skill no aparece | Budget de chars excedido | Verificar con `/context` |

---

## 9. Ecosistema

| Herramienta | Relacion con CLAUDE.md |
|-------------|------------------------|
| `.claude/rules/` | Misma prioridad, carga automatica. Modulariza reglas |
| `CLAUDE.local.md` | Override local (sandbox URLs, datos test). Auto-gitignore |
| `.claude/skills/` | Conocimiento consultivo. Documentar en seccion Skills |
| `.claude/agents/` | Subagentes con system prompt y tools propios. Consumen CLAUDE.md |
| Hooks | Enforcement determinista. 14 eventos disponibles |
| Auto memory | Notas de Claude para si mismo. Candidatos a graduacion |
| `SCRATCHPAD.md` | Log de sesion. Fuente para Learned Patterns |
| `.claude/commands/` | Slash commands personalizados. Independientes de CLAUDE.md |
| Plugins | Paquetes distribuibles (skills + hooks + agents). Namespace propio |

---

## Apendice: generacion con templates

Para equipos que inicializan proyectos frecuentemente, CLAUDE.md puede generarse desde templates:

```
_workflow/templates/CLAUDE.template.md  →  ./CLAUDE.md (proyecto destino)
```

- Formato de placeholders: `{{NOMBRE_PLACEHOLDER}}`
- Declarar TODOS los placeholders en archivo de mapeo (ej: `file-map.md`)
- Regla bidireccional: placeholder en mapeo ↔ placeholder en template
- Skill de generacion con `disable-model-invocation: true` — procesamiento determinista

---

## Fuentes

**Oficiales:** [Memory](https://code.claude.com/docs/en/memory) · [Best Practices](https://code.claude.com/docs/en/best-practices) · [CLAUDE.md Files](https://claude.com/blog/using-claude-md-files) · [Engineering](https://www.anthropic.com/engineering/claude-code-best-practices) · [Hooks](https://code.claude.com/docs/en/hooks) · [Skills](https://code.claude.com/docs/en/skills)

**Comunidad:** [Builder.io](https://www.builder.io/blog/claude-md-guide) · [HumanLayer](https://www.humanlayer.dev/blog/writing-a-good-claude-md) · [Dometrain](https://dometrain.com/blog/creating-the-perfect-claudemd-for-claude-code/) · [Gend.co](https://www.gend.co/blog/claude-skills-claude-md-guide)
