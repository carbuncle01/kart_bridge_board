#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/build/host-tests"
mkdir -p "$OUT"
python3 "$ROOT/scripts/validate_firmware_layout.py"
for module in control protocol; do
  "${CC:-cc}" -std=c11 -Wall -Wextra -Werror \
    -I"$ROOT/tests/stubs" -I"$ROOT/common/Inc" \
    "$ROOT/tests/test_jpbb_${module}.c" "$ROOT/common/Src/jpbb_${module}.c" \
    -o "$OUT/test_jpbb_${module}"
  "$OUT/test_jpbb_${module}"
done
