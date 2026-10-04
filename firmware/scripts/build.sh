#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$ROOT/vendor/build-tools/bin:$ROOT/vendor/arm-toolchain/bin:$PATH"
SDK="${STM32CUBE_G0_PATH:-$ROOT/vendor/STM32CubeG0}"
STEP="${1:-step8_final}"
STEPS=(step1_safe_boot step2_usb_cdc step3_rc_input step4_pwm_output step5_manual_auto step6_failsafe step7_full_bridge step8_final)
if [[ "$STEP" != all ]]; then
  valid=false
  for item in "${STEPS[@]}"; do [[ "$item" != "$STEP" ]] || valid=true; done
  if [[ "$valid" != true ]]; then
    echo "Usage: $0 [all|${STEPS[*]}]" >&2
    exit 2
  fi
  STEPS=("$STEP")
fi
for tool in cmake ninja arm-none-eabi-gcc; do
  command -v "$tool" >/dev/null || { echo "Missing $tool; see firmware/README.md" >&2; exit 1; }
done
for item in "${STEPS[@]}"; do
  cmake -S "$ROOT" -B "$ROOT/build/$item" -G Ninja \
    -DKART_STEP="$item" -DSTM32CUBE_G0_PATH="$SDK" -DCMAKE_BUILD_TYPE=Release
  cmake --build "$ROOT/build/$item" --parallel
done
