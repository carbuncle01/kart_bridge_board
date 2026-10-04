#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST_PYTHON="${HOST_PYTHON:-python3}"
PCBNEW_PYTHON="${PCBNEW_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9}"

if ! command -v "$HOST_PYTHON" >/dev/null 2>&1; then
  echo "Python not found: $HOST_PYTHON" >&2
  exit 2
fi
if [[ ! -x "$PCBNEW_PYTHON" ]]; then
  echo "KiCad pcbnew Python not found: $PCBNEW_PYTHON" >&2
  exit 2
fi

cd "$ROOT"

echo "== Regenerate schematic and project settings =="
"$HOST_PYTHON" scripts/generate_schematics.py
"$HOST_PYTHON" scripts/generate_project.py

echo "== Regenerate routed PCB =="
"$PCBNEW_PYTHON" scripts/generate_board.py

echo "== Independent board audit =="
"$PCBNEW_PYTHON" scripts/audit_board.py

echo "== Manufacturing and review outputs =="
./scripts/export.sh
