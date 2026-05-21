#!/bin/bash
# =============================================================================
# Dewa AI / FloodAI — SAFE cleanup script
# =============================================================================
# IMPORTANT: This repo is already a well-organised, working FastAPI package
# rooted at `app/` (app/api, app/agents, app/services, app/core, ...), with
# top-level db/, models/, data/, demnas/, scripts/, tests/, frontend/.
#
# The generic "flatten into top-level api/ agents/ models/ ..." mapping was
# NOT applied: it would break every `from app.* import ...` (~60 source + ~50
# test files), the entrypoint `uvicorn app.api.main:app`, pyproject packaging,
# and vercel.json. Wrong move = a broken, already-committed system.
#
# This script therefore does ONLY non-destructive cleanup that cannot break
# imports. It is idempotent and safe to re-run. Review before executing:
#     bash reorganize.sh
# =============================================================================
set -euo pipefail
echo "=== Dewa AI — safe cleanup ==="

# Never touch dependency / VCS trees.
PRUNE=( -path './.venv/*' -o -path './node_modules/*' -o -path '*/node_modules/*' -o -path './.git/*' )

# ---------------------------------------------------------------------------
# 1. Delete bytecode caches (regenerated automatically; scoped to our code)
# ---------------------------------------------------------------------------
for d in app tests db scripts poskobanjir; do
  [ -d "$d" ] && find "$d" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
done
find . \( "${PRUNE[@]}" \) -prune -o -type f \( -name '*.pyc' -o -name '*.pyo' \) -print -delete 2>/dev/null || true
rm -rf .pytest_cache 2>/dev/null || true

# ---------------------------------------------------------------------------
# 2. Delete temp / scratch / log files (NOT source, NOT data, NOT config)
# ---------------------------------------------------------------------------
rm -f temp_index_html.txt        # scratch dump of an old index.html
rm -f server_log.txt             # stray runtime log
rm -f poskobanjir/logs/log.txt   # stray runtime log

# ---------------------------------------------------------------------------
# 3. Delete a byte-identical duplicate (verified same md5 as the non-(1) file)
# ---------------------------------------------------------------------------
rm -f "data/raw/data-wilayah-potensi-banjir-akibat-luapan-sungai-komponen-data (1).xls"

# ---------------------------------------------------------------------------
# 4. Archive a stray vendored bootstrap script (a .py, so archived not deleted)
# ---------------------------------------------------------------------------
mkdir -p _archive
[ -f get-pip.py ] && mv -f get-pip.py _archive/ || true

# ---------------------------------------------------------------------------
# 5. Remove now-empty dirs created by the moves above (never .venv/node_modules)
# ---------------------------------------------------------------------------
for d in poskobanjir/logs; do
  [ -d "$d" ] && rmdir "$d" 2>/dev/null || true
done

echo "=== Done. The app/ package layout is unchanged — no imports broken. ==="
echo "Review with: git status --short"
