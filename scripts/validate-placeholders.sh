#!/bin/bash
# validate-placeholders.sh — Verifica consistencia entre placeholders en templates y file-map.md
# Uso: bash validate-placeholders.sh [path-to-skill-raw]
# Si no se pasa argumento, usa el directorio actual como raiz del skill raw.
#
# Checks:
#   1. All placeholders used in templates are declared in file-map.md
#   2. All placeholders declared in file-map.md are used in at least one template
#   3. Per-template placeholder inventory

set -euo pipefail

ROOT="${1:-.}"
FILEMAP="$ROOT/.claude/skills/project-workflow-init/references/file-map.md"
TEMPLATES_DIR="$ROOT/_workflow/templates"

ERRORS=0
WARNINGS=0

err()  { echo "  [FAIL] $1"; ERRORS=$((ERRORS + 1)); }
warn() { echo "  [WARN] $1"; WARNINGS=$((WARNINGS + 1)); }
ok()   { echo "  [ OK ] $1"; }

echo ""
echo "========================================"
echo "  Validacion de Placeholders"
echo "========================================"
echo ""

# --- 0. Verify required files exist ---
if [ ! -f "$FILEMAP" ]; then
  err "file-map.md not found at $FILEMAP"
  echo ""
  echo "  RESULTADO: FALLO"
  exit 1
fi

if [ ! -d "$TEMPLATES_DIR" ]; then
  err "Templates directory not found at $TEMPLATES_DIR"
  echo ""
  echo "  RESULTADO: FALLO"
  exit 1
fi

# --- 1. Extract declared placeholders from file-map.md ---
echo "1. Placeholders declarados en file-map.md"

DECLARED_FILE=$(mktemp)
grep -oE '\{\{[A-Z_]+\}\}' "$FILEMAP" | sed 's/[{}]//g' | sort -u > "$DECLARED_FILE"
DECLARED_COUNT=$(wc -l < "$DECLARED_FILE" | tr -d ' ')
ok "$DECLARED_COUNT placeholders declarados"

while IFS= read -r ph; do
  echo "       - $ph"
done < "$DECLARED_FILE"
echo ""

# --- 2. Collect all placeholders used across all templates ---
echo "2. Placeholders usados en templates"

USED_FILE=$(mktemp)
# Only scan .md files (skip .sh/.py scripts that may have placeholder patterns in comments)
grep -rhoE '\{\{[A-Z_]+\}\}' "$TEMPLATES_DIR" --include="*.md" 2>/dev/null | sed 's/[{}]//g' | sort -u > "$USED_FILE"
USED_COUNT=$(wc -l < "$USED_FILE" | tr -d ' ')
ok "$USED_COUNT placeholders unicos encontrados en templates"
echo ""

# --- 3. Check: used but NOT declared ---
echo "3. Placeholders usados pero NO declarados"

UNDECLARED=0
while IFS= read -r ph; do
  if ! grep -qx "$ph" "$DECLARED_FILE"; then
    err "{{$ph}} usado en templates pero NO declarado en file-map.md"
    # Show which files use it
    grep -rl "\{\{${ph}\}\}" "$TEMPLATES_DIR" --include="*.md" 2>/dev/null | while IFS= read -r f; do
      echo "       -> $(echo "$f" | sed "s|^$ROOT/||")"
    done || true
    UNDECLARED=$((UNDECLARED + 1))
  fi
done < "$USED_FILE"

if [ "$UNDECLARED" -eq 0 ]; then
  ok "Todos los placeholders usados estan declarados"
fi
echo ""

# --- 4. Check: declared but NOT used in any template ---
echo "4. Placeholders declarados pero sin uso"

UNUSED=0
while IFS= read -r ph; do
  if ! grep -qx "$ph" "$USED_FILE" 2>/dev/null; then
    warn "{{$ph}} declarado en file-map.md pero no usado en ningun template (.md)"
    UNUSED=$((UNUSED + 1))
  fi
done < "$DECLARED_FILE"

if [ "$UNUSED" -eq 0 ]; then
  ok "Todos los placeholders declarados estan en uso"
fi
echo ""

# --- 5. Per-template placeholder inventory ---
echo "5. Inventario por template"

for template_file in "$TEMPLATES_DIR"/*.md "$TEMPLATES_DIR"/**/*.md; do
  [ -f "$template_file" ] || continue

  rel_path=$(echo "$template_file" | sed "s|^$ROOT/||")
  ph_list=$(grep -oE '\{\{[A-Z_]+\}\}' "$template_file" 2>/dev/null | sed 's/[{}]//g' | sort -u || true)

  if [ -z "$ph_list" ]; then
    continue
  fi

  ph_count=$(echo "$ph_list" | wc -l | tr -d ' ')
  ph_inline=$(echo "$ph_list" | tr '\n' ',' | sed 's/,$//')
  ok "$rel_path: $ph_count [$ph_inline]"
done
echo ""

# --- Cleanup ---
rm -f "$DECLARED_FILE" "$USED_FILE"

# --- Resumen ---
echo "========================================"
echo "  Resumen: $ERRORS errores, $WARNINGS warnings"
echo "========================================"

if [ "$ERRORS" -gt 0 ]; then
  echo "  RESULTADO: FALLO — placeholders inconsistentes"
  exit 1
elif [ "$WARNINGS" -gt 0 ]; then
  echo "  RESULTADO: PARCIAL — hay warnings que revisar"
  exit 0
else
  echo "  RESULTADO: OK — placeholders consistentes"
  exit 0
fi
