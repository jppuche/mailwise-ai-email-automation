#!/bin/bash
# validate-docs.sh — Verifica que la documentacion del proyecto este al dia
# Uso: bash scripts/validate-docs.sh [--strict]
# --strict: warnings tambien causan exit 1

set -euo pipefail

STRICT=false
[[ "${1:-}" == "--strict" ]] && STRICT=true

ERRORS=0
WARNINGS=0
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

err()  { echo "  [FAIL] $1"; ERRORS=$((ERRORS + 1)); }
warn() { echo "  [WARN] $1"; WARNINGS=$((WARNINGS + 1)); }
ok()   { echo "  [ OK ] $1"; }

echo ""
echo "========================================"
echo "  Validacion de Docs"
echo "========================================"
echo ""

# --- 1. Existencia de archivos obligatorios ---
echo "1. Archivos obligatorios"
for f in CLAUDE.md docs/STATUS.md docs/DECISIONS.md docs/CHANGELOG-DEV.md docs/SCRATCHPAD.md docs/LESSONS-LEARNED.md; do
  if [ -f "$f" ]; then
    ok "$f existe"
  else
    err "$f NO ENCONTRADO"
  fi
done
echo ""

# --- 2. Limites de lineas ---
echo "2. Limites de lineas"
check_lines() {
  local file=$1 max=$2
  if [ ! -f "$file" ]; then return; fi
  local lines
  lines=$(wc -l < "$file" | tr -d ' ')
  if [ "$lines" -gt "$max" ]; then
    err "$file: $lines lineas (maximo $max)"
  else
    ok "$file: $lines/$max lineas"
  fi
}

check_lines "CLAUDE.md" 200
check_lines "docs/STATUS.md" 60
check_lines "docs/SCRATCHPAD.md" 150
echo ""

# --- 3. Formato de DECISIONS.md ---
echo "3. Formato de DECISIONS.md"
if [ -f "docs/DECISIONS.md" ]; then
  # i18n: ES/EN/PT/FR table header variants
  if grep -q "| Fecha |" docs/DECISIONS.md || grep -q "| Date |" docs/DECISIONS.md || grep -q "| Data |" docs/DECISIONS.md; then
    ok "Header de tabla presente"
  else
    err "Falta header de tabla (| Fecha/Date/Data | Decision | ...)"
  fi
  # Contar decisiones (lineas que empiezan con | 20)
  DECISION_COUNT=$(grep -c "^| 20" docs/DECISIONS.md || true)
  ok "$DECISION_COUNT decisiones registradas"
fi
echo ""

# --- 4. Formato de CHANGELOG-DEV.md ---
echo "4. Formato de CHANGELOG-DEV.md"
if [ -f "docs/CHANGELOG-DEV.md" ]; then
  ENTRY_COUNT=$(grep -c "^## 20" docs/CHANGELOG-DEV.md || true)
  if [ "$ENTRY_COUNT" -gt 0 ]; then
    ok "$ENTRY_COUNT entradas en changelog"
  else
    err "Changelog vacio (sin entradas ## YYYY-MM-DD)"
  fi
fi
echo ""

# --- 5. Actualizaciones recientes ---
echo "5. Actualizaciones recientes"
TODAY=$(date +%Y-%m-%d)

check_recent() {
  local file=$1 label=$2
  if [ ! -f "$file" ]; then return; fi
  if grep -q "$TODAY" "$file"; then
    ok "$label: actualizado hoy ($TODAY)"
  else
    # Buscar la fecha mas reciente en el archivo
    LAST=$(grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' "$file" | sort -r | head -1)
    warn "$label: ultima fecha $LAST (no hoy)"
  fi
}

check_recent "docs/STATUS.md" "STATUS.md"
check_recent "docs/CHANGELOG-DEV.md" "CHANGELOG-DEV.md"
check_recent "docs/SCRATCHPAD.md" "SCRATCHPAD.md"
echo ""

# --- 6. STATUS.md tiene fase actual ---
echo "6. Coherencia de STATUS.md"
if [ -f "docs/STATUS.md" ]; then
  # i18n: ES/EN/PT/FR variants
  if grep -qi "Fase actual\|Current phase\|Fase atual\|Phase actuelle\|## Fase\|## Phase" docs/STATUS.md; then
    ok "Tiene seccion de fase actual"
  else
    warn "No tiene indicador de fase actual"
  fi
  if grep -qi "Pendiente\|Pending\|Pendente\|En attente" docs/STATUS.md; then
    ok "Tiene seccion de pendientes"
  else
    warn "No tiene seccion de pendientes"
  fi
fi
echo ""

# --- 7. CLAUDE.md secciones obligatorias ---
echo "7. Secciones obligatorias en CLAUDE.md"
if [ -f "CLAUDE.md" ]; then
  REQUIRED_SECTIONS=("## Stack" "## Commands" "## Style" "## Rules" "## Architecture" "## Conventions" "## Learned Patterns")
  for section in "${REQUIRED_SECTIONS[@]}"; do
    if grep -q "$section" CLAUDE.md; then
      ok "CLAUDE.md tiene '$section'"
    else
      err "CLAUDE.md FALTA '$section'"
    fi
  done
fi
echo ""

# --- 8. SCRATCHPAD.md tiene sesion actual ---
echo "8. Sesion actual en SCRATCHPAD.md"
if [ -f "docs/SCRATCHPAD.md" ]; then
  if grep -q "$TODAY" docs/SCRATCHPAD.md; then
    ok "SCRATCHPAD tiene entrada de hoy ($TODAY)"
  else
    warn "SCRATCHPAD no tiene entrada de hoy"
  fi
fi
echo ""

# --- 9. Graduacion pendiente ---
echo "9. Graduacion pendiente"
if [ -f "docs/SCRATCHPAD.md" ]; then
  SCRATCHPAD_LINES=$(wc -l < "docs/SCRATCHPAD.md" | tr -d ' ')
  if [ "$SCRATCHPAD_LINES" -gt 100 ]; then
    warn "SCRATCHPAD.md tiene $SCRATCHPAD_LINES lineas (>100) — revisar candidatos de graduacion"
  else
    ok "SCRATCHPAD.md: $SCRATCHPAD_LINES lineas (< threshold de graduacion)"
  fi
fi
echo ""

# --- 10. Limite de CLAUDE.md ---
echo "10. Limite de CLAUDE.md"
if [ -f "CLAUDE.md" ]; then
  CLAUDE_LINES=$(wc -l < "CLAUDE.md" | tr -d ' ')
  if [ "$CLAUDE_LINES" -gt 180 ]; then
    warn "CLAUDE.md tiene $CLAUDE_LINES lineas (>180/200) — podar con prueba de relevancia"
  else
    ok "CLAUDE.md: $CLAUDE_LINES lineas (margen OK)"
  fi
fi
echo ""

# --- 11. Estructura de LESSONS-LEARNED.md ---
echo "11. Estructura de LESSONS-LEARNED.md"
if [ -f "docs/LESSONS-LEARNED.md" ]; then
  # i18n: ES/EN/PT/FR variants
  if grep -qi "Template de incidente\|Incident template\|Template de incidente\|Modele d'incident" docs/LESSONS-LEARNED.md; then
    ok "LESSONS-LEARNED.md tiene template de incidente"
  else
    warn "LESSONS-LEARNED.md falta template de incidente"
  fi
else
  ok "LESSONS-LEARNED.md no existe aun (se creara con /project-workflow-init)"
fi
echo ""

# --- Resumen ---
echo "========================================"
echo "  Resumen: $ERRORS errores, $WARNINGS warnings"
echo "========================================"

if [ "$ERRORS" -gt 0 ]; then
  echo "  RESULTADO: FALLO — documentacion necesita atencion"
  exit 1
elif [ "$WARNINGS" -gt 0 ]; then
  if [ "$STRICT" = true ]; then
    echo "  RESULTADO: FALLO (modo strict) — docs parcialmente al dia"
    exit 1
  else
    echo "  RESULTADO: PARCIAL — docs parcialmente al dia"
    exit 0
  fi
else
  echo "  RESULTADO: OK — documentacion al dia"
  exit 0
fi
