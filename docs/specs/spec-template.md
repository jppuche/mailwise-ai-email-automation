# Bloque N: {{NOMBRE_BLOQUE}}

## Objetivo

<!-- Que se logra al completar este bloque. Ser especifico y medible. -->
<!-- Test de una oracion: si necesitas "y" (conjuncion) para describirlo, dividir en 2 specs (ghuntley). -->

## Dependencias

<!-- Bloques anteriores que deben estar completos antes de iniciar este -->

## Archivos a crear/modificar

### Backend (backend-worker)

<!-- Lista de archivos con descripcion breve de cada uno -->
- ...

### Frontend (frontend-worker)

<!-- Lista de archivos con descripcion breve -->
- ...

### Tests (Inquisidor)

<!-- Lista de archivos de test -->
- ...

## Skills aplicables

<!-- Listar skills que aplican a este bloque y por que -->
<!-- Consultar ANTES de implementar (planificacion, implementacion, revision) -->
- skill-name: razon por la que aplica a este bloque

## Candidate Tools

<!-- Tools from the Ecosystem Catalog (DECISIONS.md) relevant to this block -->
<!-- PREFERRED: block benefits from this tool but works without it -->
<!-- If none: "No candidate tool dependencies — exit conditions achievable without candidates" -->
| Tool | Tier | Status | How it applies |
|------|------|--------|----------------|

## Criterios de exito (deterministicos)

- [ ] Typecheck: 0 errores
- [ ] Lint: 0 violaciones
- [ ] Tests: todos pasan
- [ ] Build: exitoso
- [ ] Validacion visual: screenshots/dev tools confirman UI correcta (si aplica)
- [ ] {{CRITERIOS_ESPECIFICOS}}

## Exit conditions para Ralph Loop

El bloque esta COMPLETO cuando TODOS los criterios de exito se cumplen.
Si CUALQUIER criterio falla, el loop itera hasta que pase.

**Stop condition:** Si un gate falla 3+ veces en el mismo error, escalar al usuario.
