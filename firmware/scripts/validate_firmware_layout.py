#!/usr/bin/env python3
"""Static, dependency-free checks for the JPBB staged firmware."""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
GENERATOR = (
    REPO
    / "hardware"
    / "kicad"
    / "kart_bridge_board"
    / "scripts"
    / "generate_schematics.py"
)

STEPS = [
    "step1_safe_boot",
    "step2_usb_cdc",
    "step3_rc_input",
    "step4_pwm_output",
    "step5_manual_auto",
    "step6_failsafe",
    "step7_full_bridge",
    "step8_final",
]

EXPECTED_SCHEMATIC_NETS = {
    "11": "RX_CH1_MCU_N",
    "12": "RX_CH2_MCU_N",
    "13": "RX_CH3_MCU_N",
    "15": "VBEC_SENSE",
    "19": "SAFE_AUTO_SEL_MCU",
    "20": "USB_PRESENT_N",
    "33": "USB_DM",
    "34": "USB_DP",
    "35": "SWDIO",
    "36": "SWCLK",
    "43": "MCU_SERVO_PWM_GPIO",
    "44": "MCU_ESC_PWM_GPIO",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    for step in STEPS:
        source = ROOT / step / "main.c"
        if not source.is_file():
            fail(f"missing {source.relative_to(REPO)}")

    generator = GENERATOR.read_text(encoding="utf-8")
    for pin, net in EXPECTED_SCHEMATIC_NETS.items():
        if re.search(rf'"{pin}"\s*:\s*"{re.escape(net)}"', generator) is None:
            fail(f"schematic no longer maps U1 pin {pin} to {net}")

    board = (ROOT / "common" / "Src" / "jpbb_board.c").read_text(
        encoding="utf-8"
    )
    required_board_tokens = [
        "#define SAFE_AUTO_PIN GPIO_PIN_0",
        "#define USB_PRESENT_PIN GPIO_PIN_1",
        "#define RC_CH1_PIN GPIO_PIN_0",
        "#define RC_CH2_PIN GPIO_PIN_1",
        "#define RC_CH3_PIN GPIO_PIN_2",
        "ADC_CHANNEL_4",
        "GPIO_AF2_TIM2",
        "GPIO_AF1_TIM3",
    ]
    combined = board + (
        ROOT / "common" / "Src" / "stm32g0xx_hal_msp.c"
    ).read_text(encoding="utf-8")
    for token in required_board_tokens:
        if token not in combined:
            fail(f"firmware pin definition is missing: {token}")

    for step in STEPS[:4]:
        source = (ROOT / step / "main.c").read_text(encoding="utf-8")
        if "jpbb_manual_force()" not in source:
            fail(f"{step} must force MANUAL")
        if "jpbb_auto_select(true)" in source:
            fail(f"{step} must not select AUTO")

    linker = (ROOT / "linker" / "STM32G0B1CBTX_FLASH.ld").read_text(
        encoding="utf-8"
    )
    if "FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 128K" not in linker:
        fail("linker flash size must remain 128 KiB for STM32G0B1CBT6")

    print(
        "Firmware layout OK: 8 steps, schematic pin parity, "
        "MANUAL locks, and 128 KiB flash limit"
    )


if __name__ == "__main__":
    main()
