#!/usr/bin/env python3
"""Generate the JPBB-01 Rev.2 KiCad hierarchical schematics and symbol library.

The files are intentionally generated from a compact, reviewable connectivity model.
Every electrical connection is made with an explicit global net label so hierarchy
changes cannot silently disconnect a sheet.  KiCad 10 can open the emitted 2025
schematic schema directly and will resave it in the installed point-release schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import uuid


ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = ROOT / "lib" / "symbols" / "kart_bridge_board.kicad_sym"
PROJECT = "kart_bridge_board"
FORMAT_VERSION = 20250114
LIB_VERSION = 20251024
UUID_NAMESPACE = uuid.UUID("a486fd9c-03e3-5a4e-a55d-4793c44c5ca4")


def stable_uuid(*parts: object) -> str:
    return str(uuid.uuid5(UUID_NAMESPACE, "/".join(str(p) for p in parts)))


def quote(value: object) -> str:
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def number(value: float) -> str:
    if abs(value) < 0.0000001:
        return "0"
    rendered = f"{value:.4f}".rstrip("0").rstrip(".")
    return rendered


def indent(block: str, levels: int = 1) -> str:
    prefix = "  " * levels
    return "\n".join(prefix + line if line else line for line in block.splitlines())


@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    electrical_type: str = "passive"
    side: str = "left"


@dataclass
class SymbolDef:
    name: str
    reference_prefix: str
    pins: list[Pin] = field(default_factory=list)
    body_width: float = 10.16
    in_bom: bool = True
    on_board: bool = True
    shape: str = "rectangle"
    pin_pitch: float = 2.54

    def pin_layout(self) -> dict[str, tuple[float, float, float, str]]:
        """Return endpoint x/y, rotation, and side for each pin."""
        groups: dict[str, list[Pin]] = {"left": [], "right": []}
        for pin in self.pins:
            groups[pin.side].append(pin)
        result: dict[str, tuple[float, float, float, str]] = {}
        endpoint_x = self.body_width / 2 + 2.54
        for side, pins in groups.items():
            start_y = -((len(pins) - 1) * self.pin_pitch) / 2
            for index, pin in enumerate(pins):
                y = start_y + index * self.pin_pitch
                if side == "left":
                    result[pin.number] = (-endpoint_x, y, 0, side)
                else:
                    result[pin.number] = (endpoint_x, y, 180, side)
        return result

    @property
    def body_height(self) -> float:
        largest = max(
            (sum(pin.side == side for pin in self.pins) for side in ("left", "right")),
            default=1,
        )
        return max(5.08, (largest - 1) * self.pin_pitch + 2.54)


@dataclass
class Component:
    symbol: str
    reference: str
    value: str
    at: tuple[float, float]
    nets: dict[str, str | None]
    footprint: str = ""
    datasheet: str = ""
    manufacturer: str = ""
    mpn: str = ""
    lcsc: str = ""
    dnp: bool = False
    notes: str = ""
    in_bom: bool | None = None
    on_board: bool | None = None


def lr_pins(specs: list[tuple[str, str, str]], split: int | None = None) -> list[Pin]:
    if split is None:
        split = (len(specs) + 1) // 2
    return [
        Pin(num, name, kind, "left" if index < split else "right")
        for index, (num, name, kind) in enumerate(specs)
    ]


MCU_PIN_NAMES = [
    "PC13", "PC14-OSC32_IN", "PC15-OSC32_OUT", "VBAT", "VREF+", "VDD/VDDA",
    "VSS/VSSA", "PF0-OSC_IN", "PF1-OSC_OUT", "PF2-NRST", "PA0", "PA1",
    "PA2", "PA3", "PA4", "PA5", "PA6", "PA7", "PB0", "PB1", "PB2",
    "PB10", "PB11", "PB12", "PB13", "PB14", "PB15", "PA8", "PA9",
    "PC6", "PC7", "PA10", "PA11/USB_DM", "PA12/USB_DP", "PA13/SWDIO",
    "PA14-BOOT0/SWCLK", "PA15", "PD0", "PD1", "PD2", "PD3", "PB3",
    "PB4", "PB5", "PB6", "PB7", "PB8", "PB9",
]


def mcu_pin_type(pin_number: int) -> str:
    if pin_number in (4, 5, 6, 7):
        return "power_in"
    if pin_number in (10, 11, 12, 13, 15, 20):
        return "input"
    if pin_number in (19, 43, 44):
        return "output"
    return "bidirectional"


SYMBOLS: dict[str, SymbolDef] = {
    "R": SymbolDef(
        "R", "R", [Pin("1", "1", side="left"), Pin("2", "2", side="right")],
        body_width=5.08,
    ),
    "C": SymbolDef(
        "C", "C", [Pin("1", "+", side="left"), Pin("2", "-", side="right")],
        body_width=5.08,
    ),
    "D_Schottky": SymbolDef(
        "D_Schottky", "D",
        [Pin("2", "A", side="left"), Pin("1", "K", side="right")],
        body_width=5.08,
    ),
    "SW_Push": SymbolDef(
        "SW_Push", "SW",
        [Pin("1", "1", side="left"), Pin("2", "2", side="right")],
        body_width=5.08,
    ),
    "Conn_01x03": SymbolDef(
        "Conn_01x03", "J",
        [Pin("1", "SIGNAL"), Pin("2", "VBEC"), Pin("3", "GND")],
        body_width=7.62,
    ),
    "Conn_01x05": SymbolDef(
        "Conn_01x05", "J",
        [Pin(str(i), name) for i, name in enumerate(("SWDIO", "SWCLK", "NRST", "3V3", "GND"), 1)],
        body_width=7.62,
    ),
    "Conn_02x05_ARM_SWD": SymbolDef(
        "Conn_02x05_ARM_SWD", "J",
        [
            Pin("1", "VTREF", side="left"), Pin("3", "GND", side="left"),
            Pin("5", "GND", side="left"), Pin("7", "KEY/NC", side="left"),
            Pin("9", "GNDDetect", side="left"), Pin("2", "SWDIO", side="right"),
            Pin("4", "SWCLK", side="right"), Pin("6", "SWO/NC", side="right"),
            Pin("8", "TDI/NC", side="right"), Pin("10", "NRST", side="right"),
        ],
        body_width=10.16,
    ),
    "USB_C": SymbolDef(
        "USB_C", "J",
        lr_pins([
            ("A1", "GND", "power_in"), ("A4", "VBUS", "passive"),
            ("A5", "CC1", "passive"), ("A6", "D+", "bidirectional"),
            ("A7", "D-", "bidirectional"), ("A8", "SBU1", "passive"),
            ("A9", "VBUS", "passive"), ("A12", "GND", "power_in"),
            ("SH", "SHIELD", "power_in"),
            ("B1", "GND", "power_in"), ("B4", "VBUS", "passive"),
            ("B5", "CC2", "passive"), ("B6", "D+", "bidirectional"),
            ("B7", "D-", "bidirectional"), ("B8", "SBU2", "passive"),
            ("B9", "VBUS", "passive"), ("B12", "GND", "power_in"),
        ], split=9),
        body_width=17.78,
    ),
    "STM32G0B1CBT6": SymbolDef(
        "STM32G0B1CBT6", "U",
        [
            Pin(str(index), name, mcu_pin_type(index), "left" if index <= 24 else "right")
            for index, name in enumerate(MCU_PIN_NAMES, 1)
        ],
        body_width=25.4,
    ),
    "TMUX7236PWR": SymbolDef(
        "TMUX7236PWR", "U",
        lr_pins([
            ("1", "SEL1", "input"), ("2", "S1A", "bidirectional"),
            ("3", "D1", "bidirectional"), ("4", "S1B", "bidirectional"),
            ("5", "VSS", "power_in"), ("6", "GND", "power_in"),
            ("7", "NC", "no_connect"), ("8", "NC", "no_connect"),
            ("9", "SEL2", "input"), ("10", "S2A", "bidirectional"),
            ("11", "D2", "bidirectional"), ("12", "S2B", "bidirectional"),
            ("13", "VDD", "power_in"), ("14", "EN", "input"),
            ("15", "NC", "no_connect"), ("16", "NC", "no_connect"),
        ], split=8),
        body_width=17.78,
    ),
    "MCP1703AT_3302E_CB": SymbolDef(
        "MCP1703AT_3302E_CB", "U",
        [Pin("1", "GND", "power_in", "left"), Pin("3", "VIN", "power_in", "left"),
         Pin("2", "VOUT", "power_out", "right")],
        body_width=10.16,
    ),
    "HX61CN5002MR": SymbolDef(
        "HX61CN5002MR", "U",
        [Pin("1", "VOUT", "open_collector", "right"),
         Pin("2", "VSS", "power_in", "left"),
         Pin("3", "VIN", "power_in", "left")],
        body_width=10.16,
    ),
    "USBLC6_2SC6": SymbolDef(
        "USBLC6_2SC6", "U",
        lr_pins([
            ("1", "I/O1", "bidirectional"), ("2", "GND", "power_in"),
            ("3", "I/O2", "bidirectional"), ("6", "I/O1", "bidirectional"),
            ("5", "VBUS", "passive"), ("4", "I/O2", "bidirectional"),
        ], split=3),
        body_width=12.7,
    ),
    "MMBT3904LT1G": SymbolDef(
        "MMBT3904LT1G", "Q",
        [Pin("1", "B", "input", "left"), Pin("3", "C", "open_collector", "right"),
         Pin("2", "E", "passive", "right")],
        body_width=7.62,
    ),
    "Crystal4": SymbolDef(
        "Crystal4", "Y",
        [Pin("1", "X1", side="left"), Pin("2", "CASE", side="left"),
         Pin("3", "X2", side="right"), Pin("4", "CASE", side="right")],
        body_width=7.62,
    ),
    "TestPoint": SymbolDef(
        "TestPoint", "TP", [Pin("1", "TP")], body_width=5.08, in_bom=False,
    ),
    "PWR_FLAG": SymbolDef(
        "PWR_FLAG", "#FLG", [Pin("1", "pwr", "power_out")], body_width=5.08,
        in_bom=False, on_board=False,
    ),
}


def property_block(name: str, value: str, x: float, y: float, *, hidden: bool = False) -> str:
    hide = "\n      (hide yes)" if hidden else ""
    return (
        f"(property {quote(name)} {quote(value)}\n"
        f"  (at {number(x)} {number(y)} 0)\n"
        f"  (effects (font (size 1.27 1.27)){hide})\n"
        f")"
    )


def symbol_definition(symbol: SymbolDef, *, embedded: bool) -> str:
    name = f"JPBB:{symbol.name}" if embedded else symbol.name
    height = symbol.body_height
    lines = [
        f"(symbol {quote(name)}",
        "  (exclude_from_sim no)",
        f"  (in_bom {'yes' if symbol.in_bom else 'no'})",
        f"  (on_board {'yes' if symbol.on_board else 'no'})",
        indent(property_block("Reference", symbol.reference_prefix, 0, -(height / 2 + 2.54)), 1),
        indent(property_block("Value", symbol.name, 0, height / 2 + 2.54), 1),
        indent(property_block("Footprint", "", 0, 0, hidden=True), 1),
        indent(property_block("Datasheet", "", 0, 0, hidden=True), 1),
        indent(property_block("Description", "JPBB generated symbol", 0, 0, hidden=True), 1),
        indent(property_block("Manufacturer", "", 0, 0, hidden=True), 1),
        indent(property_block("MPN", "", 0, 0, hidden=True), 1),
        indent(property_block("LCSC Part #", "", 0, 0, hidden=True), 1),
        indent(property_block("DNP", "", 0, 0, hidden=True), 1),
        indent(property_block("Notes", "", 0, 0, hidden=True), 1),
        f"  (symbol {quote(symbol.name + '_1_1')}",
    ]
    if symbol.shape == "circle":
        lines.extend([
            "    (circle",
            "      (center 0 0)",
            "      (radius 2.54)",
            "      (stroke (width 0) (type default))",
            "      (fill (type none))",
            "    )",
        ])
    else:
        lines.extend([
            "    (rectangle",
            f"      (start {number(-symbol.body_width / 2)} {number(-height / 2)})",
            f"      (end {number(symbol.body_width / 2)} {number(height / 2)})",
            "      (stroke (width 0) (type default))",
            "      (fill (type background))",
            "    )",
        ])
    layout = symbol.pin_layout()
    for pin in symbol.pins:
        x, y, rotation, _ = layout[pin.number]
        lines.extend([
            f"    (pin {pin.electrical_type} line",
            f"      (at {number(x)} {number(y)} {number(rotation)})",
            "      (length 2.54)",
            f"      (name {quote(pin.name)} (effects (font (size 1.27 1.27))))",
            f"      (number {quote(pin.number)} (effects (font (size 1.27 1.27))))",
            "    )",
        ])
    lines.extend(["  )", "  (embedded_fonts no)", ")"])
    return "\n".join(lines)


def write_symbol_library() -> None:
    LIB_PATH.parent.mkdir(parents=True, exist_ok=True)
    definitions = "\n".join(indent(symbol_definition(symbol, embedded=False), 1)
                              for symbol in SYMBOLS.values())
    LIB_PATH.write_text(
        f"(kicad_symbol_lib\n  (version {LIB_VERSION})\n  (generator {quote('jpbb_generator')})\n"
        f"{definitions}\n)\n",
        encoding="utf-8",
    )
    (ROOT / "sym-lib-table").write_text(
        "(sym_lib_table\n"
        "  (version 7)\n"
        "  (lib (name \"JPBB\") (type \"KiCad\")\n"
        "    (uri \"${KIPRJMOD}/lib/symbols/kart_bridge_board.kicad_sym\")\n"
        "    (options \"\") (descr \"JPBB-01 generated local symbols\"))\n"
        ")\n",
        encoding="utf-8",
    )


def component_properties(component: Component, symbol: SymbolDef) -> list[tuple[str, str, bool]]:
    return [
        ("Reference", component.reference, False),
        ("Value", component.value, False),
        ("Footprint", component.footprint, True),
        ("Datasheet", component.datasheet, True),
        ("Description", component.notes or component.value, True),
        ("Manufacturer", component.manufacturer, True),
        ("MPN", component.mpn, True),
        ("LCSC Part #", component.lcsc, True),
        ("DNP", "Yes" if component.dnp else "No", True),
        ("Notes", component.notes, True),
    ]


def component_block(component: Component, sheet_key: str, instance_path: str) -> tuple[str, list[str]]:
    symbol = SYMBOLS[component.symbol]
    x, y = component.at
    component_id = stable_uuid(sheet_key, component.reference, "symbol")
    in_bom = symbol.in_bom if component.in_bom is None else component.in_bom
    on_board = symbol.on_board if component.on_board is None else component.on_board
    lines = [
        "(symbol",
        f"  (lib_id {quote('JPBB:' + component.symbol)})",
        f"  (at {number(x)} {number(y)} 0)",
        "  (unit 1)",
        "  (exclude_from_sim no)",
        f"  (in_bom {'yes' if in_bom else 'no'})",
        f"  (on_board {'yes' if on_board else 'no'})",
        f"  (dnp {'yes' if component.dnp else 'no'})",
        "  (fields_autoplaced yes)",
        f"  (uuid {quote(component_id)})",
    ]
    height = symbol.body_height
    for index, (name, value, hidden) in enumerate(component_properties(component, symbol)):
        if name == "Reference":
            px, py = x, y - height / 2 - 2.54
        elif name == "Value":
            px, py = x, y + height / 2 + 2.54
        else:
            px, py = x, y
        lines.append(indent(property_block(name, value, px, py, hidden=hidden), 1))
    for pin in symbol.pins:
        lines.extend([
            f"  (pin {quote(pin.number)}",
            f"    (uuid {quote(stable_uuid(sheet_key, component.reference, 'pin', pin.number))})",
            "  )",
        ])
    lines.extend([
        "  (instances",
        f"    (project {quote(PROJECT)}",
        f"      (path {quote(instance_path)}",
        f"        (reference {quote(component.reference)})",
        "        (unit 1)",
        "      )",
        "    )",
        "  )",
        ")",
    ])

    attachments: list[str] = []
    layout = symbol.pin_layout()
    for pin in symbol.pins:
        endpoint_x, endpoint_y, _rotation, side = layout[pin.number]
        # KiCad symbol-library Y coordinates are Cartesian (positive up), while
        # schematic sheet coordinates are screen-like (positive down).
        world_x, world_y = x + endpoint_x, y - endpoint_y
        net = component.nets.get(pin.number)
        if net is None:
            attachments.append(
                "(no_connect\n"
                f"  (at {number(world_x)} {number(world_y)})\n"
                f"  (uuid {quote(stable_uuid(sheet_key, component.reference, 'nc', pin.number))})\n"
                ")"
            )
        else:
            justification = "right" if side == "left" else "left"
            attachments.append(
                f"(global_label {quote(net)}\n"
                "  (shape bidirectional)\n"
                f"  (at {number(world_x)} {number(world_y)} 0)\n"
                "  (fields_autoplaced yes)\n"
                f"  (effects (font (size 1.27 1.27)) (justify {justification}))\n"
                f"  (uuid {quote(stable_uuid(sheet_key, component.reference, 'label', pin.number))})\n"
                ")"
            )
    return "\n".join(lines), attachments


RESISTOR_PARTS = {
    "0R": ("0402WGF0000TCE", "C17168"),
    "1k": ("0402WGF1001TCE", "C11702"),
    "5.1k": ("0402WGF5101TCE", "C25905"),
    "10k": ("0402WGF1002TCE", "C25744"),
    "22k": ("0402WGF2202TCE", "C25768"),
    "47k": ("0402WGF4702TCE", "C25792"),
    "100k": ("0402WGF1003TCE", "C25741"),
    "1M": ("0402WGF1004TCE", "C26083"),
}

CAPACITOR_0402_PARTS = {
    "10nF": ("Samsung Electro-Mechanics", "CL05B103KB5NNNC", "C15195"),
    "100nF": ("Samsung Electro-Mechanics", "CL05B104KO5NNNC", "C1525"),
    "1uF": ("Samsung Electro-Mechanics", "CL05A105KA5NQNC", "C52923"),
}


def r(ref: str, value: str, at: tuple[float, float], net1: str, net2: str, *,
      dnp: bool = False, notes: str = "") -> Component:
    if value not in RESISTOR_PARTS:
        raise ValueError(f"{ref}: no approved 0402 resistor part for {value}")
    mpn, lcsc = RESISTOR_PARTS[value]
    return Component(
        "R", ref, value, at, {"1": net1, "2": net2},
        footprint="Resistor_SMD:R_0402_1005Metric",
        manufacturer="UNI-ROYAL", mpn=mpn,
        lcsc=lcsc, dnp=dnp, notes=notes,
    )


def c(ref: str, value: str, at: tuple[float, float], net1: str, net2: str, *,
      lcsc: str = "", dnp: bool = False, footprint: str = "Capacitor_SMD:C_0402_1005Metric",
      manufacturer: str = "", mpn: str = "", datasheet: str = "",
      notes: str = "") -> Component:
    if footprint == "Capacitor_SMD:C_0402_1005Metric":
        if value not in CAPACITOR_0402_PARTS:
            raise ValueError(f"{ref}: no approved 0402 capacitor part for {value}")
        manufacturer, mpn, lcsc = CAPACITOR_0402_PARTS[value]
    return Component(
        "C", ref, value, at, {"1": net1, "2": net2}, footprint=footprint,
        datasheet=datasheet, manufacturer=manufacturer, mpn=mpn, lcsc=lcsc,
        dnp=dnp, notes=notes,
    )


def power_components() -> list[Component]:
    components = [
        Component("MCP1703AT_3302E_CB", "U3", "MCP1703AT-3302E/CB", (111.76, 55.88),
                  {"1": "GND", "2": "+3V3", "3": "LOGIC_RAW"},
                  "Package_TO_SOT_SMD:SOT-23", manufacturer="Microchip Technology",
                  mpn="MCP1703AT-3302E/CB", lcsc="C144183",
                  datasheet="https://ww1.microchip.com/downloads/aemDocuments/documents/APID/ProductDocuments/DataSheets/MCP1703-Data-Sheet-DS20005122.pdf",
                  notes="SOT-23A: Pin 1 GND, Pin 2 VOUT, Pin 3 VIN; LOGIC_RAW is diode-OR powered"),
        Component("D_Schottky", "D1", "1N4148W", (68.58, 40.64),
                  {"1": "LOGIC_RAW", "2": "VBEC"}, "Diode_SMD:D_SOD-123",
                  manufacturer="MDD(Microdiode Semiconductor)", mpn="1N4148W", lcsc="C84367",
                  datasheet="https://jlcpcb.com/partdetail/MDD_Microdiode_Semiconductor-1N4148W/C84367",
                  notes="Low-leakage VBEC-to-logic OR diode; Pin 1 cathode at LOGIC_RAW"),
        Component("D_Schottky", "D2", "1N4148W", (68.58, 53.34),
                  {"1": "LOGIC_RAW", "2": "USB_VBUS"}, "Diode_SMD:D_SOD-123",
                  manufacturer="MDD(Microdiode Semiconductor)", mpn="1N4148W", lcsc="C84367",
                  datasheet="https://jlcpcb.com/partdetail/MDD_Microdiode_Semiconductor-1N4148W/C84367",
                  notes="Low-leakage USB-to-logic OR diode; Pin 1 cathode at LOGIC_RAW"),
        c("C1", "100uF 25V", (73.66, 101.6), "VBEC", "GND", lcsc="C454668",
          footprint="JPBB:CP_Panasonic_D6.3x5.8", manufacturer="Panasonic",
          mpn="EEHZK1E101UP",
          datasheet="https://industrial.panasonic.com/content/data/CP/PDF/Hybrid/Hybrid_data_e.pdf",
          notes="Polarized hybrid C_BULK; place beside J4/J5; Pin 1 positive"),
        c("C3", "1uF", (91.44, 40.64), "LOGIC_RAW", "GND", notes="LDO input"),
        c("C18", "4.7uF 16V", (91.44, 53.34), "LOGIC_RAW", "GND", lcsc="C19666",
          footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Samsung Electro-Mechanics",
          mpn="CL10A475KO8NNNC", notes="USB/VBEC logic-rail hold-up and OR-node bypass"),
        c("C4", "1uF", (142.24, 35.56), "+3V3", "GND", notes="LDO output"),
        c("C5", "100nF", (142.24, 48.26), "+3V3", "GND", notes="LDO output bypass"),
        r("R1", "100k", (101.6, 101.6), "VBEC", "VBEC_SENSE"),
        r("R2", "22k", (165.1, 101.6), "VBEC_SENSE", "GND"),
        c("C6", "10nF", (165.1, 116.84), "VBEC_SENSE", "GND",
          notes="ADC anti-noise filter"),
        Component("PWR_FLAG", "#FLG01", "PWR_FLAG", (86.36, 139.7), {"1": "VBEC"},
                  in_bom=False, on_board=False, notes="J5 Pin 2 is the VBEC source"),
        Component("PWR_FLAG", "#FLG02", "PWR_FLAG", (116.84, 139.7), {"1": "GND"},
                  in_bom=False, on_board=False, notes="Ground reference source for ERC"),
        Component("PWR_FLAG", "#FLG03", "PWR_FLAG", (147.32, 139.7), {"1": "LOGIC_RAW"},
                  in_bom=False, on_board=False,
                  notes="D1/D2 diode-OR is the valid LOGIC_RAW source for ERC"),
    ]
    return components


def mcu_usb_components() -> list[Component]:
    mcu_nets: dict[str, str | None] = {str(pin): None for pin in range(1, 49)}
    mcu_nets.update({
        "4": "+3V3", "5": "+3V3", "6": "+3V3", "7": "GND",
        "10": "NRST",
        "11": "RX_CH1_MCU_N", "12": "RX_CH2_MCU_N", "13": "RX_CH3_MCU_N",
        "15": "VBEC_SENSE",
        "19": "SAFE_AUTO_SEL_MCU", "20": "USB_PRESENT_N", "33": "USB_DM",
        "34": "USB_DP", "35": "SWDIO", "36": "SWCLK",
        "43": "MCU_SERVO_PWM_GPIO", "44": "MCU_ESC_PWM_GPIO",
    })
    usb_nets = {
        "A1": "GND", "A4": "USB_VBUS", "A5": "USB_CC1",
        "A6": "USB_DP_CONN", "A7": "USB_DM_CONN", "A8": None,
        "A9": "USB_VBUS", "A12": "GND", "SH": "GND",
        "B1": "GND", "B4": "USB_VBUS", "B5": "USB_CC2",
        "B6": "USB_DP_CONN", "B7": "USB_DM_CONN", "B8": None,
        "B9": "USB_VBUS", "B12": "GND",
    }
    return [
        Component("STM32G0B1CBT6", "U1", "STM32G0B1CBT6", (177.8, 101.6), mcu_nets,
                  "Package_QFP:LQFP-48_7x7mm_P0.5mm", manufacturer="STMicroelectronics",
                  mpn="STM32G0B1CBT6", lcsc="C2847904",
                  datasheet="https://www.st.com/resource/en/datasheet/stm32g0b1cb.pdf",
                  notes="USB FS MCU; 128 KiB cost-optimized variant; TIM2 CH1/2/3 inputs; PB4/PB5 TIM3 CH1/2 PWM outputs; firmware must fit 128 KiB"),
        Component("USB_C", "J6", "USB_C_USB2.0_DEVICE", (53.34, 50.8), usb_nets,
                  "JPBB:USB_C_Receptacle_HRO_TYPE-C-31-M-12_Edge",
                  manufacturer="Korean Hroparts Elec", mpn="TYPE-C-31-M-12", lcsc="C165948",
                  datasheet="https://datasheet.lcsc.com/lcsc/1811131822_Korean-Hroparts-Elec-TYPE-C-31-M-12_C165948.pdf",
                  notes="USB 2.0 device only; VBUS powers LOGIC_RAW through D2 only; shield tied to GND"),
        Component("USBLC6_2SC6", "U4", "USBLC6-2SC6", (91.44, 83.82),
                  {"1": "USB_DM_CONN", "2": "GND", "3": "USB_DP_CONN",
                   "4": "USB_DP_ESD", "5": "USB_VBUS", "6": "USB_DM_ESD"},
                  "Package_TO_SOT_SMD:SOT-23-6", manufacturer="STMicroelectronics",
                  mpn="USBLC6-2SC6", lcsc="C7519",
                  datasheet="https://www.st.com/resource/en/datasheet/usblc6-2.pdf",
                  notes="Place immediately behind J6"),
        c("C17", "100nF", (119.38, 127.0), "USB_VBUS", "GND",
          notes="USBLC6-2 VBUS rail bypass; place immediately beside U4 pin 5"),
        Component("MMBT3904LT1G", "Q4", "MMBT3904LT1G", (119.38, 149.86),
                  {"1": "USB_VBUS_BASE", "2": "GND", "3": "USB_PRESENT_N"},
                  "Package_TO_SOT_SMD:SOT-23", manufacturer="onsemi", mpn="MMBT3904LT1G",
                  lcsc="C81464", datasheet="https://www.onsemi.com/pdf/datasheet/mmbt3904lt1-d.pdf",
                  notes="USB VBUS detector; logic is active low"),
        c("C7", "100nF", (243.84, 35.56), "+3V3", "GND", notes="VDD/VDDA decoupling"),
        c("C8", "4.7uF 16V", (243.84, 50.8), "+3V3", "GND", lcsc="C19666",
          footprint="Capacitor_SMD:C_0603_1608Metric", manufacturer="Samsung Electro-Mechanics",
          mpn="CL10A475KO8NNNC", notes="VDD/VDDA bulk"),
        c("C9", "100nF", (243.84, 66.04), "+3V3", "GND", notes="VREF+ decoupling"),
        c("C10", "1uF", (243.84, 81.28), "+3V3", "GND", notes="VREF+ decoupling"),
        c("C11", "100nF", (243.84, 96.52), "NRST", "GND", notes="NRST filter"),
        r("R3", "5.1k", (35.56, 101.6), "USB_CC1", "GND",
          notes="USB Type-C Rd"),
        r("R4", "5.1k", (35.56, 116.84), "USB_CC2", "GND",
          notes="USB Type-C Rd"),
        r("R5", "0R", (129.54, 40.64), "USB_DP_ESD", "USB_DP",
          notes="USB series option; fit 0 ohm initially"),
        r("R6", "0R", (129.54, 55.88), "USB_DM_ESD", "USB_DM",
          notes="USB series option; fit 0 ohm initially"),
        r("R7", "47k", (50.8, 149.86), "USB_VBUS", "USB_VBUS_BASE",
          notes="USB-presence base resistor"),
        r("R8", "10k", (50.8, 170.18), "USB_VBUS_BASE", "GND",
          notes="Strong pull-down prevents false USB-present indication from OR-diode leakage"),
        r("R9", "10k", (170.18, 149.86), "+3V3", "USB_PRESENT_N"),
        r("R10", "10k", (243.84, 111.76), "+3V3", "NRST",
          notes="External NRST pull-up"),
    ]


def rc_mux_components() -> list[Component]:
    connector_fp = "JPBB:RC_Header_1x03_P2.54mm"
    connector_notes = "Hand solder after PCBA; Pin 1 SIG, Pin 2 VBEC, Pin 3 GND"
    components: list[Component] = [
        Component("Conn_01x03", "J1", "RX_CH1", (25.4, 30.48),
                  {"1": "RX_CH1_RAW", "2": "VBEC", "3": "GND"}, connector_fp,
                  manufacturer="BOOMELE", mpn="2.54-1*3P Pin", dnp=True,
                  notes=connector_notes),
        Component("Conn_01x03", "J2", "RX_CH2", (25.4, 71.12),
                  {"1": "RX_CH2_RAW", "2": "VBEC", "3": "GND"}, connector_fp,
                  manufacturer="BOOMELE", mpn="2.54-1*3P Pin", dnp=True,
                  notes=connector_notes),
        Component("Conn_01x03", "J3", "RX_CH3", (25.4, 111.76),
                  {"1": "RX_CH3_RAW", "2": "VBEC", "3": "GND"}, connector_fp,
                  manufacturer="BOOMELE", mpn="2.54-1*3P Pin", dnp=True,
                  notes=connector_notes),
        Component("Conn_01x03", "J4", "SERVO_OUT", (256.54, 60.96),
                  {"1": "SERVO_SIGNAL", "2": "VBEC", "3": "GND"}, connector_fp,
                  manufacturer="BOOMELE", mpn="2.54-1*3P Pin", dnp=True,
                  notes=connector_notes),
        Component("Conn_01x03", "J5", "ESC_OUT_BEC_IN", (256.54, 101.6),
                  {"1": "ESC_SIGNAL", "2": "VBEC", "3": "GND"}, connector_fp,
                  manufacturer="BOOMELE", mpn="2.54-1*3P Pin", dnp=True,
                  notes="BEC input source; " + connector_notes),
        Component("TMUX7236PWR", "U2", "TMUX7236PWR", (187.96, 88.9),
                  {"1": "SAFE_AUTO_SEL", "2": "MCU_SERVO_PWM", "3": "SERVO_SIGNAL",
                   "4": "RX_CH1_RAW", "5": "GND", "6": "GND", "7": None, "8": None,
                   "9": "SAFE_AUTO_SEL", "10": "MCU_ESC_PWM", "11": "ESC_SIGNAL",
                   "12": "RX_CH2_RAW", "13": "VBEC", "14": "MUX_ENABLE_OK", "15": None, "16": None},
                  "Package_SO:TSSOP-16_4.4x5mm_P0.65mm", manufacturer="Texas Instruments",
                  mpn="TMUX7236PWR", lcsc="C37096021",
                  datasheet="https://www.ti.com/lit/ds/symlink/tmux7236.pdf",
                  notes="VBEC-powered dual 2:1 mux; SEL low selects B/manual; EN releases only above 5V"),
        Component("MMBT3904LT1G", "Q1", "MMBT3904LT1G", (78.74, 45.72),
                  {"1": "RX_CH1_BASE", "2": "GND", "3": "RX_CH1_MCU_N"},
                  "Package_TO_SOT_SMD:SOT-23", manufacturer="onsemi", mpn="MMBT3904LT1G",
                  lcsc="C81464", datasheet="https://www.onsemi.com/pdf/datasheet/mmbt3904lt1-d.pdf",
                  notes="Inverting RC input level converter"),
        Component("MMBT3904LT1G", "Q2", "MMBT3904LT1G", (78.74, 88.9),
                  {"1": "RX_CH2_BASE", "2": "GND", "3": "RX_CH2_MCU_N"},
                  "Package_TO_SOT_SMD:SOT-23", manufacturer="onsemi", mpn="MMBT3904LT1G",
                  lcsc="C81464", datasheet="https://www.onsemi.com/pdf/datasheet/mmbt3904lt1-d.pdf",
                  notes="Inverting RC input level converter"),
        Component("MMBT3904LT1G", "Q3", "MMBT3904LT1G", (78.74, 132.08),
                  {"1": "RX_CH3_BASE", "2": "GND", "3": "RX_CH3_MCU_N"},
                  "Package_TO_SOT_SMD:SOT-23", manufacturer="onsemi", mpn="MMBT3904LT1G",
                  lcsc="C81464", datasheet="https://www.onsemi.com/pdf/datasheet/mmbt3904lt1-d.pdf",
                  notes="Inverting RC input level converter"),
        c("C14", "100nF", (226.06, 35.56), "VBEC", "GND", notes="TMUX VDD bypass"),
        c("C15", "1uF", (226.06, 53.34), "VBEC", "GND", notes="TMUX VDD bypass"),
        Component("HX61CN5002MR", "U5", "HX61CN5002MR", (248.92, 152.4),
                  {"1": "MUX_ENABLE_OK", "2": "GND", "3": "VBEC"},
                  "Package_TO_SOT_SMD:SOT-23", manufacturer="HANSCHIP semiconductor",
                  mpn="HX61CN5002MR", lcsc="C47344213",
                  datasheet="https://datasheet.lcsc.com/datasheet/pdf/30431468595607e63851b9a518c8a627.pdf?productCode=C296259",
                  notes="5.0V open-drain VBEC detector; holds TMUX EN low while VDD is below its valid range"),
        c("C16", "100nF", (116.84, 154.94), "+3V3", "GND", notes="RC input converter bypass"),
    ]
    channel_rows = [("1", 43.18, "R11", "R12", "R13"),
                    ("2", 86.36, "R14", "R15", "R16"),
                    ("3", 129.54, "R17", "R18", "R19")]
    for channel, y, series_ref, base_ref, pull_ref in channel_rows:
        components.extend([
            r(series_ref, "47k", (35.56, y), f"RX_CH{channel}_RAW", f"RX_CH{channel}_BASE"),
            r(base_ref, "100k", (35.56, y + 12.7), f"RX_CH{channel}_BASE", "GND"),
            r(pull_ref, "10k", (116.84, y), "+3V3", f"RX_CH{channel}_MCU_N"),
        ])
    components.extend([
        r("R20", "1k", (149.86, 139.7), "SAFE_AUTO_SEL_MCU", "SAFE_AUTO_SEL",
          notes="Series isolation from MCU GPIO to tied TMUX SEL1/SEL2"),
        r("R21", "10k", (220.98, 139.7), "SAFE_AUTO_SEL", "GND",
          notes="Hardware default to MANUAL during reset/unpowered MCU"),
        r("R22", "1k", (149.86, 152.4), "MCU_SERVO_PWM_GPIO", "MCU_SERVO_PWM",
          notes="Limits fault current between MCU and powered signal mux"),
        r("R23", "1k", (149.86, 165.1), "MCU_ESC_PWM_GPIO", "MCU_ESC_PWM",
          notes="Limits fault current between MCU and powered signal mux"),
        r("R24", "100k", (220.98, 152.4), "VBEC", "MUX_ENABLE_OK",
          notes="Pull-up for U5 open-drain power-good output and TMUX EN"),
    ])
    return components


def debug_components() -> list[Component]:
    components: list[Component] = [
        Component("Conn_02x05_ARM_SWD", "J7", "ARM_CORTEX_SWD_10", (55.88, 127.0),
                  {"1": "+3V3", "2": "SWDIO", "3": "GND", "4": "SWCLK",
                   "5": "GND", "6": None, "7": None, "8": None,
                   "9": "GND", "10": "NRST"},
                  "JPBB:Samtec_FTSH-105-01-L-DV-007-K",
                  manufacturer="Samtec", mpn="FTSH-105-01-L-DV-007-K", lcsc="C5296739",
                  datasheet="https://suddendocs.samtec.com/prints/ftsh-1xx-xx-xxx-dv-xxx-footprint.pdf",
                  notes="PCBA-fitted Cortex SWD header with physical position 7 omitted; VTref is target reference, not a power input"),
        Component("SW_Push", "SW1", "RESET", (55.88, 149.86),
                  {"1": "NRST", "2": "GND"},
                  "Button_Switch_SMD:SW_SPST_TS-1088-xR020",
                  manufacturer="XUNPU", mpn="TS-1088-AR02016", lcsc="C720477",
                  datasheet="https://lcsc.com/datasheet/lcsc_datasheet_2504101957_XUNPU-TS-1088-AR02016_C720477.pdf",
                  notes="Hold low to reset the MCU"),
        Component("SW_Push", "SW2", "BOOT", (111.76, 149.86),
                  {"1": "+3V3", "2": "BOOT_REQ"},
                  "Button_Switch_SMD:SW_SPST_TS-1088-xR020",
                  manufacturer="XUNPU", mpn="TS-1088-AR02016", lcsc="C720477",
                  datasheet="https://lcsc.com/datasheet/lcsc_datasheet_2504101957_XUNPU-TS-1088-AR02016_C720477.pdf",
                  notes="Hold while pulsing RESET to request ROM USB DFU after option-byte setup"),
        r("R26", "1k", (83.82, 149.86), "BOOT_REQ", "SWCLK",
          notes="Isolates the BOOT pushbutton branch from the SWD clock line"),
        r("R27", "100k", (83.82, 165.1), "SWCLK", "GND",
          notes="Hardware BOOT0 default low; PA14 is shared with SWCLK"),
    ]
    tp_nets = [
        "VBEC", "+3V3", "GND", "RX_CH1_RAW", "RX_CH2_RAW", "RX_CH3_RAW",
        "SERVO_SIGNAL", "ESC_SIGNAL",
    ]
    for index, net in enumerate(tp_nets, 1):
        column = (index - 1) % 4
        row = (index - 1) // 4
        components.append(Component(
            "TestPoint", f"TP{index}", net, (111.76 + column * 38.1, 45.72 + row * 30.48),
            {"1": net}, "JPBB:TP_SMD_D1.0mm", notes=f"Top-side test point for {net}",
            in_bom=False,
        ))
    return components


SHEETS: list[tuple[str, str, list[Component]]] = [
    ("10_power", "Power, connectors, LDO and VBEC monitor", power_components()),
    ("20_mcu_usb", "STM32G0B1, USB-C and VBUS presence detection", mcu_usb_components()),
    ("30_rc_mux", "RC input conditioning and fail-safe signal multiplexer", rc_mux_components()),
    ("40_debug", "PCBA-fitted SWD, BOOT/RESET controls and test points", debug_components()),
]


ROOT_UUID = stable_uuid(PROJECT, "root")
SHEET_UUIDS = {sheet_name: stable_uuid(PROJECT, "sheet", sheet_name) for sheet_name, _, _ in SHEETS}


def title_block(sheet_name: str, description: str) -> str:
    return (
        "(title_block\n"
        f"  (title {quote('kart_bridge_board — ' + sheet_name)})\n"
        f"  (date {quote('2026-07-22')})\n"
        f"  (rev {quote('Rev.2')})\n"
        f"  (company {quote('JPBB-01')})\n"
        f"  (comment 1 {quote('JPBB-HW-DEF-002')})\n"
        f"  (comment 2 {quote(description)})\n"
        ")"
    )


def write_child_sheet(sheet_name: str, description: str, components: list[Component]) -> None:
    sheet_uuid = SHEET_UUIDS[sheet_name]
    instance_path = f"/{ROOT_UUID}/{sheet_uuid}"
    page = str(2 + [sheet[0] for sheet in SHEETS].index(sheet_name))
    used_symbols = sorted({component.symbol for component in components})
    embedded = "\n".join(indent(symbol_definition(SYMBOLS[name], embedded=True), 2)
                           for name in used_symbols)
    symbol_blocks: list[str] = []
    attachments: list[str] = []
    for component in components:
        block, component_attachments = component_block(component, sheet_name, instance_path)
        symbol_blocks.append(indent(block, 1))
        attachments.extend(indent(item, 1) for item in component_attachments)
    content = [
        "(kicad_sch",
        f"  (version {FORMAT_VERSION})",
        f"  (generator {quote('jpbb_generator')})",
        f"  (uuid {quote(stable_uuid(PROJECT, sheet_name, 'document'))})",
        '  (paper "A4")',
        indent(title_block(sheet_name, description), 1),
        "  (lib_symbols",
        embedded,
        "  )",
    ]
    content.extend(attachments)
    content.extend(symbol_blocks)
    content.extend([
        "  (sheet_instances",
        f"    (path {quote(instance_path)} (page {quote(page)}))",
        "  )",
        "  (embedded_fonts no)",
        ")",
    ])
    (ROOT / f"{sheet_name}.kicad_sch").write_text("\n".join(content) + "\n", encoding="utf-8")


def write_root_sheet() -> None:
    lines = [
        "(kicad_sch",
        f"  (version {FORMAT_VERSION})",
        f"  (generator {quote('jpbb_generator')})",
        f"  (uuid {quote(ROOT_UUID)})",
        '  (paper "A4")',
        indent(title_block("top", "Hierarchical block overview; nets are explicit global labels"), 1),
        "  (lib_symbols)",
    ]
    for index, (sheet_name, _description, _components) in enumerate(SHEETS):
        x = 38.1
        y = 38.1 + index * 35.56
        sheet_uuid = SHEET_UUIDS[sheet_name]
        page = str(index + 2)
        lines.extend([
            "  (sheet",
            f"    (at {number(x)} {number(y)})",
            "    (size 88.9 25.4)",
            "    (stroke (width 0) (type default))",
            "    (fill (color 0 0 0 0.0000))",
            f"    (uuid {quote(sheet_uuid)})",
            f"    (property {quote('Sheetname')} {quote(sheet_name)}",
            f"      (at {number(x)} {number(y - 0.8125)} 0)",
            "      (effects (font (size 1.27 1.27)) (justify left bottom))",
            "    )",
            f"    (property {quote('Sheetfile')} {quote(sheet_name + '.kicad_sch')}",
            f"      (at {number(x)} {number(y + 26.1116)} 0)",
            "      (effects (font (size 1.27 1.27)) (justify left top))",
            "    )",
            "    (instances",
            f"      (project {quote(PROJECT)}",
            f"        (path {quote('/' + ROOT_UUID + '/' + sheet_uuid)} (page {quote(page)}))",
            "      )",
            "    )",
            "  )",
        ])
    lines.extend([
        "  (sheet_instances (path \"/\" (page \"1\")))",
        "  (embedded_fonts no)",
        ")",
    ])
    (ROOT / f"{PROJECT}.kicad_sch").write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate_model() -> None:
    references: set[str] = set()
    critical_datasheets = {"C1", "J6", "Q1", "Q2", "Q3", "Q4", "U1", "U2", "U3", "U4"}
    for sheet_name, _description, components in SHEETS:
        for component in components:
            if component.reference in references:
                raise ValueError(f"duplicate reference: {component.reference}")
            references.add(component.reference)
            symbol_pins = {pin.number for pin in SYMBOLS[component.symbol].pins}
            net_pins = set(component.nets)
            if symbol_pins != net_pins:
                missing = sorted(symbol_pins - net_pins)
                extra = sorted(net_pins - symbol_pins)
                raise ValueError(
                    f"{sheet_name}/{component.reference}: nets do not cover symbol pins; "
                    f"missing={missing}, extra={extra}"
                )
            if component.on_board is not False and SYMBOLS[component.symbol].on_board and not component.footprint:
                raise ValueError(f"{sheet_name}/{component.reference}: board item has no footprint")
            in_bom = SYMBOLS[component.symbol].in_bom if component.in_bom is None else component.in_bom
            on_board = SYMBOLS[component.symbol].on_board if component.on_board is None else component.on_board
            if in_bom and on_board and not component.dnp:
                for field_name, value in (
                    ("Manufacturer", component.manufacturer),
                    ("MPN", component.mpn),
                    ("LCSC Part #", component.lcsc),
                ):
                    if not value:
                        raise ValueError(f"{sheet_name}/{component.reference}: empty {field_name}")
                if not re.fullmatch(r"C[0-9]+", component.lcsc):
                    raise ValueError(
                        f"{sheet_name}/{component.reference}: invalid LCSC Part # {component.lcsc!r}"
                    )
            if component.reference in critical_datasheets and not component.datasheet:
                raise ValueError(f"{sheet_name}/{component.reference}: critical part has no datasheet")


def main() -> None:
    validate_model()
    write_symbol_library()
    for sheet_name, description, components in SHEETS:
        write_child_sheet(sheet_name, description, components)
    write_root_sheet()
    print(f"Generated {PROJECT}.kicad_sch and {len(SHEETS)} hierarchy sheets")
    print(f"Generated {LIB_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
