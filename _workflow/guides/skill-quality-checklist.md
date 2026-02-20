# Checklist de Calidad para Skills de Claude Code

Referencia para evaluar y mejorar skills. Basado en documentacion oficial de Anthropic, el spec agentskills.io, el meta-skill skill-creator, y patrones de la comunidad.

## Fuentes (por prioridad)

1. [Anthropic Skills Best Practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
2. [Agent Skills Specification](https://agentskills.io/specification)
3. [Claude Code Skills Docs](https://code.claude.com/docs/en/skills)
4. [anthropics/skills repo](https://github.com/anthropics/skills) — skill-creator meta-skill
5. [Anthropic Engineering Blog](https://claude.com/blog/equipping-agents-for-the-real-world-with-agent-skills)
6. [Sionic AI Case Study](https://huggingface.co/blog/sionic-ai/claude-code-skills-training)

---

## A. Frontmatter YAML

| #  | Check | Severidad |
|----|-------|-----------|
| A1 | `name` presente, kebab-case, max 64 chars | REQUIRED |
| A2 | `name` coincide con nombre del directorio padre | REQUIRED |
| A3 | `name` no contiene "anthropic" ni "claude" | REQUIRED |
| A4 | `name` sin hyphens al inicio/final ni consecutivos | REQUIRED |
| A5 | `description` presente y no vacia | REQUIRED |
| A6 | `description` max 1024 chars | REQUIRED |
| A7 | `description` en tercera persona (no "I can" ni "You can") | HIGH |
| A8 | `description` incluye QUE hace Y CUANDO usarlo | HIGH |
| A9 | `description` incluye triggers especificos (frases del usuario) | HIGH |
| A10 | `disable-model-invocation` coherente con el proposito | MEDIUM |
| A11 | `allowed-tools` minimo necesario (no wildcard) | MEDIUM |
| A12 | `argument-hint` si el skill acepta argumentos | LOW |

## B. Contenido del SKILL.md (Body)

| #  | Check | Severidad |
|----|-------|-----------|
| B1 | SKILL.md body < 500 lineas | HIGH |
| B2 | Body target 1500-2000 palabras | HIGH |
| B3 | Un solo H1 como titulo | MEDIUM |
| B4 | Instrucciones en forma imperativa (no segunda persona) | MEDIUM |
| B5 | Cada parrafo justifica su costo en tokens | HIGH |
| B6 | Ejemplos concretos preferidos sobre explicaciones verbosas | MEDIUM |
| B7 | Terminologia consistente (sin sinonimos para lo mismo) | MEDIUM |
| B8 | Sin informacion time-sensitive (fechas hardcodeadas) | LOW |
| B9 | Sin explicaciones de lo que Claude ya sabe | HIGH |
| B10 | Grados de libertad apropiados (texto/pseudocode/script) | MEDIUM |

## C. Arquitectura y Estructura de Archivos

| #  | Check | Severidad |
|----|-------|-----------|
| C1 | Solo archivos necesarios para el agente (no README, CHANGELOG, etc.) | HIGH |
| C2 | Referencias a 1 nivel de profundidad desde SKILL.md | HIGH |
| C3 | Archivos de referencia >100 lineas tienen TOC | MEDIUM |
| C4 | Archivos de referencia >10k palabras: incluir grep patterns en SKILL.md | MEDIUM |
| C5 | Info en SKILL.md O en referencia, no duplicada | HIGH |
| C6 | Progressive disclosure: metadata -> body -> resources | HIGH |
| C7 | Scripts probados y funcionales (no teoricos) | HIGH |
| C8 | Paths con forward slashes (/) no backslashes | LOW |

## D. Descripcion (Discovery & Triggering)

| #  | Check | Severidad |
|----|-------|-----------|
| D1 | Description funciona como unica info de discovery (~100 tokens) | HIGH |
| D2 | Keywords del dominio incluidas en description | HIGH |
| D3 | Mensajes de error exactos en description (si aplica) | MEDIUM |
| D4 | Description diferenciada de otros skills del proyecto | MEDIUM |

## E. Invocation Control

| #  | Check | Severidad |
|----|-------|-----------|
| E1 | `disable-model-invocation: true` si tiene side effects peligrosos | HIGH |
| E2 | `user-invocable: false` si es solo background knowledge | MEDIUM |
| E3 | `context: fork` considerado para skills con mucho output | LOW |
| E4 | `allowed-tools` restrictivo (solo tools necesarias) | MEDIUM |

## F. Scripts y Hooks

| #  | Check | Severidad |
|----|-------|-----------|
| F1 | Scripts manejan errores explicitamente (no delegan a Claude) | HIGH |
| F2 | Sin magic numbers sin documentar | MEDIUM |
| F3 | Dependencias explicitamente listadas | HIGH |
| F4 | Scripts usan solo stdlib cuando es posible | MEDIUM |
| F5 | Feedback loop: script valida -> corrige -> repite | MEDIUM |

## G. Seguridad

| #  | Check | Severidad |
|----|-------|-----------|
| G1 | Sin secrets hardcodeados | CRITICAL |
| G2 | Sin conexiones a servicios externos no documentadas | HIGH |
| G3 | Dependencias de scripts auditables | HIGH |
| G4 | allowed-tools con minimo privilegio | MEDIUM |

## H. Mantenibilidad

| #  | Check | Severidad |
|----|-------|-----------|
| H1 | Documentacion de failure modes conocidos | HIGH |
| H2 | Versionado del skill (si es complejo) | LOW |
| H3 | Workflow de edicion documentado | MEDIUM |

---

## Principios clave

1. **"The context window is a public good."** Claude ya es inteligente — solo agregar contexto que no tiene.
2. **Progressive disclosure:** Metadata (~100 tokens) -> SKILL.md body (<5k tokens) -> reference files (sin limite).
3. **Evaluation-first:** Identificar gaps ejecutando el skill, no escribiendo docs de antemano.
4. **Failure modes son el contenido mas valioso** (Sionic AI: la seccion "Failed Attempts" es la mas consultada).
5. **Grados de libertad:** Alto (texto) para multiples approaches validos, bajo (scripts exactos) para operaciones fragiles.

## Limites de contexto

| Constraint | Valor |
|------------|-------|
| Descriptions budget | 2% del context window (default ~16k chars) |
| SKILL.md body max | 500 lineas recomendado |
| SKILL.md body target | 1500-2000 palabras |
| Reference files | 2000-5000+ palabras cada uno |
| Ref files grandes (>10k palabras) | Incluir grep patterns en SKILL.md |

## Campos del frontmatter

### Estandar agentskills.io (cross-platform)
`name`, `description`, `license`, `compatibility`, `metadata`

### Extensiones Claude Code
`disable-model-invocation`, `user-invocable`, `allowed-tools`, `model`, `context`, `agent`, `argument-hint`, `hooks`
