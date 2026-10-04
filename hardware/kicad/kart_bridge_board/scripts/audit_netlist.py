#!/usr/bin/env python3
"""Fail closed when the JPBB-01 critical schematic connections drift."""

from __future__ import annotations

from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


CRITICAL_PARTS = {
    "C1": ("EEHZK1E101UP", "C454668", "JPBB:CP_Panasonic_D6.3x5.8"),
    "D1": ("1N4148W", "C84367", "Diode_SMD:D_SOD-123"),
    "D2": ("1N4148W", "C84367", "Diode_SMD:D_SOD-123"),
    "J6": ("TYPE-C-31-M-12", "C165948", "JPBB:USB_C_Receptacle_HRO_TYPE-C-31-M-12_Edge"),
    "J7": ("FTSH-105-01-L-DV-007-K", "C5296739", "JPBB:Samtec_FTSH-105-01-L-DV-007-K"),
    "SW1": ("TS-1088-AR02016", "C720477", "Button_Switch_SMD:SW_SPST_TS-1088-xR020"),
    "SW2": ("TS-1088-AR02016", "C720477", "Button_Switch_SMD:SW_SPST_TS-1088-xR020"),
    "U1": ("STM32G0B1CBT6", "C2847904", "Package_QFP:LQFP-48_7x7mm_P0.5mm"),
    "U2": ("TMUX7236PWR", "C37096021", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm"),
    "U3": ("MCP1703AT-3302E/CB", "C144183", "Package_TO_SOT_SMD:SOT-23"),
    "U4": ("USBLC6-2SC6", "C7519", "Package_TO_SOT_SMD:SOT-23-6"),
    "U5": ("HX61CN5002MR", "C47344213", "Package_TO_SOT_SMD:SOT-23"),
}

EXPECTED_PIN_NETS = {
    # RC and actuator connectors: pin 1 signal, pin 2 VBEC, pin 3 GND.
    ("J1", "1"): "RX_CH1_RAW", ("J1", "2"): "VBEC", ("J1", "3"): "GND",
    ("J2", "1"): "RX_CH2_RAW", ("J2", "2"): "VBEC", ("J2", "3"): "GND",
    ("J3", "1"): "RX_CH3_RAW", ("J3", "2"): "VBEC", ("J3", "3"): "GND",
    ("J4", "1"): "SERVO_SIGNAL", ("J4", "2"): "VBEC", ("J4", "3"): "GND",
    ("J5", "1"): "ESC_SIGNAL", ("J5", "2"): "VBEC", ("J5", "3"): "GND",
    # TMUX7236: B is manual, A is MCU, D is output, both selectors tied.
    ("U2", "1"): "SAFE_AUTO_SEL", ("U2", "2"): "MCU_SERVO_PWM",
    ("U2", "3"): "SERVO_SIGNAL", ("U2", "4"): "RX_CH1_RAW",
    ("U2", "5"): "GND", ("U2", "6"): "GND",
    ("U2", "9"): "SAFE_AUTO_SEL", ("U2", "10"): "MCU_ESC_PWM",
    ("U2", "11"): "ESC_SIGNAL", ("U2", "12"): "RX_CH2_RAW",
    ("U2", "13"): "VBEC", ("U2", "14"): "MUX_ENABLE_OK",
    # MCU capture, PWM, USB, ADC, selector and SWD assignments.
    ("U1", "4"): "+3V3", ("U1", "5"): "+3V3", ("U1", "6"): "+3V3",
    ("U1", "7"): "GND", ("U1", "10"): "NRST",
    ("U1", "11"): "RX_CH1_MCU_N", ("U1", "12"): "RX_CH2_MCU_N",
    ("U1", "13"): "RX_CH3_MCU_N", ("U1", "15"): "VBEC_SENSE",
    ("U1", "19"): "SAFE_AUTO_SEL_MCU", ("U1", "20"): "USB_PRESENT_N",
    ("U1", "33"): "USB_DM", ("U1", "34"): "USB_DP",
    ("U1", "35"): "SWDIO", ("U1", "36"): "SWCLK",
    ("U1", "43"): "MCU_SERVO_PWM_GPIO", ("U1", "44"): "MCU_ESC_PWM_GPIO",
    # Power and bulk-capacitor polarity.
    ("U3", "1"): "GND", ("U3", "2"): "+3V3", ("U3", "3"): "LOGIC_RAW",
    ("C1", "1"): "VBEC", ("C1", "2"): "GND",
    ("D1", "1"): "LOGIC_RAW", ("D1", "2"): "VBEC",
    ("D2", "1"): "LOGIC_RAW", ("D2", "2"): "USB_VBUS",
    ("U5", "1"): "MUX_ENABLE_OK", ("U5", "2"): "GND", ("U5", "3"): "VBEC",
    # PCBA-fitted Cortex SWD and local DFU controls.
    ("J7", "1"): "+3V3", ("J7", "2"): "SWDIO", ("J7", "3"): "GND",
    ("J7", "4"): "SWCLK", ("J7", "5"): "GND", ("J7", "9"): "GND",
    ("J7", "10"): "NRST",
    ("SW1", "1"): "NRST", ("SW1", "2"): "GND",
    ("SW2", "1"): "+3V3", ("SW2", "2"): "BOOT_REQ",
}

EXPECTED_USB_VBUS_NODES = {
    ("C17", "1"), ("J6", "A4"), ("J6", "A9"), ("J6", "B4"),
    ("J6", "B9"), ("R7", "1"), ("U4", "5"), ("D2", "2"),
}

EXPECTED_LOGIC_RAW_NODES = {
    ("C3", "1"), ("C18", "1"), ("D1", "1"), ("D2", "1"), ("U3", "3"),
}


def field_map(component: ET.Element) -> dict[str, str]:
    return {
        field.attrib["name"]: field.text or ""
        for field in component.findall("./fields/field")
    }


def property_names(component: ET.Element) -> set[str]:
    return {item.attrib.get("name", "") for item in component.findall("./property")}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_netlist.py NETLIST.xml")
    path = Path(sys.argv[1])
    root = ET.parse(path).getroot()
    components = {item.attrib["ref"]: item for item in root.findall("./components/comp")}
    pin_nets: dict[tuple[str, str], str] = {}
    pin_types: dict[tuple[str, str], str] = {}
    net_nodes: dict[str, set[tuple[str, str]]] = {}
    for net in root.findall("./nets/net"):
        name = net.attrib["name"]
        nodes = {(node.attrib["ref"], node.attrib["pin"]) for node in net.findall("node")}
        net_nodes[name] = nodes
        for node in nodes:
            if node in pin_nets:
                raise SystemExit(f"NETLIST AUDIT FAILED: {node[0]}.{node[1]} is on multiple nets")
            pin_nets[node] = name
        for item in net.findall("node"):
            pin_types[(item.attrib["ref"], item.attrib["pin"])] = item.attrib.get("pintype", "")

    errors: list[str] = []
    for (ref, pin), expected in EXPECTED_PIN_NETS.items():
        actual = pin_nets.get((ref, pin), "<unconnected>")
        if actual != expected:
            errors.append(f"{ref}.{pin}: expected {expected}, found {actual}")
    for ref, pin in (
        ("J6", "A8"), ("J6", "B8"),
        ("J7", "6"), ("J7", "7"), ("J7", "8"),
        ("U1", "8"), ("U1", "9"),
        ("U2", "7"), ("U2", "8"), ("U2", "15"), ("U2", "16"),
    ):
        node = (ref, pin)
        net_name = pin_nets.get(node, "")
        # KiCad 10 XML represents an explicit no-connect marker as a generated
        # single-pin `unconnected-(...)` net whose node pintype includes the
        # `no_connect` suffix; it is not omitted from the net list.
        if not (
            net_name.startswith("unconnected-(")
            and "no_connect" in pin_types.get(node, "").split("+")
            and net_nodes.get(net_name) == {node}
        ):
            errors.append(
                f"{ref}.{pin}: expected explicit no-connect, found "
                f"{net_name or '<missing>'} ({pin_types.get(node, '<no pintype>')})"
            )

    actual_vbus = net_nodes.get("USB_VBUS", set())
    if actual_vbus != EXPECTED_USB_VBUS_NODES:
        errors.append(
            "USB_VBUS nodes differ: "
            f"missing={sorted(EXPECTED_USB_VBUS_NODES - actual_vbus)}, "
            f"extra={sorted(actual_vbus - EXPECTED_USB_VBUS_NODES)}"
        )
    for forbidden in ("VBEC", "LOGIC_RAW", "+3V3"):
        overlap = actual_vbus & net_nodes.get(forbidden, set())
        if overlap:
            errors.append(f"USB VBUS overlaps {forbidden}: {sorted(overlap)}")

    actual_logic_raw = net_nodes.get("LOGIC_RAW", set())
    if actual_logic_raw != EXPECTED_LOGIC_RAW_NODES:
        errors.append(
            "LOGIC_RAW nodes differ: "
            f"missing={sorted(EXPECTED_LOGIC_RAW_NODES - actual_logic_raw)}, "
            f"extra={sorted(actual_logic_raw - EXPECTED_LOGIC_RAW_NODES)}"
        )

    expected_control_nets = {
        "MCU_SERVO_PWM_GPIO": {("U1", "43"), ("R22", "1")},
        "MCU_SERVO_PWM": {("R22", "2"), ("U2", "2")},
        "MCU_ESC_PWM_GPIO": {("U1", "44"), ("R23", "1")},
        "MCU_ESC_PWM": {("R23", "2"), ("U2", "10")},
        "MUX_ENABLE_OK": {("R24", "2"), ("U2", "14"), ("U5", "1")},
        "BOOT_REQ": {("R26", "1"), ("SW2", "2")},
        "SWCLK": {("J7", "4"), ("R26", "2"), ("R27", "1"), ("U1", "36")},
        "NRST": {("C11", "1"), ("J7", "10"), ("R10", "2"), ("SW1", "1"), ("U1", "10")},
    }
    for name, expected in expected_control_nets.items():
        actual = net_nodes.get(name, set())
        if actual != expected:
            errors.append(f"{name}: expected {sorted(expected)}, found {sorted(actual)}")

    # USB-C reversible pins, ESD array and series options must retain polarity.
    expected_usb = {
        "USB_DP_CONN": {("J6", "A6"), ("J6", "B6"), ("U4", "3")},
        "USB_DM_CONN": {("J6", "A7"), ("J6", "B7"), ("U4", "1")},
        "USB_DP_ESD": {("R5", "1"), ("U4", "4")},
        "USB_DM_ESD": {("R6", "1"), ("U4", "6")},
        "USB_DP": {("R5", "2"), ("U1", "34")},
        "USB_DM": {("R6", "2"), ("U1", "33")},
    }
    for name, expected in expected_usb.items():
        actual = net_nodes.get(name, set())
        if actual != expected:
            errors.append(f"{name}: expected {sorted(expected)}, found {sorted(actual)}")

    for ref, (mpn, lcsc, footprint) in CRITICAL_PARTS.items():
        component = components.get(ref)
        if component is None:
            errors.append(f"missing critical component {ref}")
            continue
        fields = field_map(component)
        actual = (fields.get("MPN", ""), fields.get("LCSC Part #", ""), component.findtext("footprint", ""))
        if actual != (mpn, lcsc, footprint):
            errors.append(f"{ref}: expected {(mpn, lcsc, footprint)}, found {actual}")

    for ref in ("J1", "J2", "J3", "J4", "J5"):
        component = components.get(ref)
        if component is None or "dnp" not in property_names(component):
            errors.append(f"{ref}: DNP property is missing")

    # Every fitted BOM component needs an unambiguous JLCPCB identity.
    for ref, component in components.items():
        properties = property_names(component)
        if "dnp" in properties or "exclude_from_bom" in properties:
            continue
        fields = field_map(component)
        for name in ("Manufacturer", "MPN", "LCSC Part #"):
            if not fields.get(name, "").strip():
                errors.append(f"{ref}: empty {name}")
        lcsc = fields.get("LCSC Part #", "")
        if lcsc and not re.fullmatch(r"C[0-9]+", lcsc):
            errors.append(f"{ref}: invalid LCSC Part # {lcsc!r}")

    if errors:
        print("NETLIST AUDIT FAILED:")
        print("\n".join(f"- {line}" for line in errors))
        return 1
    print(
        f"NETLIST AUDIT PASS: {len(components)} components; critical pin maps, "
        "USB VBUS isolation, DNP flags and JLCPCB identities verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
