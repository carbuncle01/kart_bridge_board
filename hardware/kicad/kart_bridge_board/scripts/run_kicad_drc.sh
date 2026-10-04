#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: run_kicad_drc.sh KICAD_CLI [kicad-cli arguments...]" >&2
  exit 2
fi

KICAD_CLI="$1"
shift

KICAD_VERSION="$("$KICAD_CLI" --version)"
USE_SHIM=0
if [[ "$(uname -s)" == "Darwin" && "${JPBB_DISABLE_KICAD_DRC_SHIM:-0}" != "1" ]]; then
  if [[ "$KICAD_VERSION" == "10.0.4" || "${JPBB_FORCE_KICAD_DRC_SHIM:-0}" == "1" ]]; then
    USE_SHIM=1
  fi
fi

if [[ "$USE_SHIM" != "1" ]]; then
  exec "$KICAD_CLI" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KICAD_CONTENTS="$(cd "$(dirname "$KICAD_CLI")/.." && pwd)"
WX_LIBRARY="$KICAD_CONTENTS/Frameworks/libwx_osx_cocoau-3.2.0.dylib"
SHIM_DIR="${JPBB_DRC_SHIM_DIR:-${TMPDIR:-/tmp}/jpbb-kicad-drc-shim}"
SHIM_LIBRARY="$SHIM_DIR/libjpbb_kicad_drc_mouse.dylib"

if [[ ! -f "$WX_LIBRARY" ]]; then
  echo "KiCad wxWidgets library not found: $WX_LIBRARY" >&2
  exit 2
fi
if ! command -v clang >/dev/null 2>&1; then
  echo "clang is required for the KiCad macOS CLI DRC compatibility shim" >&2
  exit 2
fi

mkdir -p "$SHIM_DIR"
clang -Os -dynamiclib \
  -o "$SHIM_LIBRARY" \
  "$SCRIPT_DIR/kicad_cli_mouse_shim.c" \
  "$WX_LIBRARY"

export DYLD_INSERT_LIBRARIES="$SHIM_LIBRARY${DYLD_INSERT_LIBRARIES:+:$DYLD_INSERT_LIBRARIES}"
exec "$KICAD_CLI" "$@"
