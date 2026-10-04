#!/usr/bin/env python3
"""Compare the schematic XML netlist with the generated PCB.

This is deliberately headless. It checks the exact reference/value/footprint/path
mapping and every (reference, pin/pad) net membership.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import pcbnew


# J7 is the keyed Samtec -007 variant.  The schematic preserves Cortex pin
# numbering and marks position 7 NC, while the physical PCB land is omitted.
ALLOWED_KEYED_MISSING_PADS = {("J7", "7")}



def xml_data(path: Path):
    root = ET.parse(path).getroot()
    comps = {}
    for c in root.findall("./components/comp"):
        ref = c.attrib["ref"]
        sheet = c.find("sheetpath").attrib.get("tstamps", "/").rstrip("/")
        stamp = (c.findtext("tstamps") or "").strip("/")
        sch_path = f"{sheet}/{stamp}" if sheet else f"/{stamp}"
        comps[ref] = {
            "value": c.findtext("value", ""),
            "footprint": c.findtext("footprint", ""),
            "path": sch_path,
            "dnp": c.find("./property[@name='dnp']") is not None,
        }
    nodes = defaultdict(dict)
    for net in root.findall("./nets/net"):
        name = net.attrib["name"]
        for node in net.findall("node"):
            nodes[node.attrib["ref"]][node.attrib["pin"]] = name
    return comps, nodes


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_parity.py NETLIST.xml BOARD.kicad_pcb")
    comps, nodes = xml_data(Path(sys.argv[1]))
    board = pcbnew.LoadBoard(sys.argv[2])
    errors = []
    pcb_refs = set()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        pcb_refs.add(ref)
        if ref not in comps:
            errors.append(f"extra PCB footprint: {ref}")
            continue
        expected = comps[ref]
        if fp.GetValue() != expected["value"]:
            errors.append(f"{ref}: value PCB={fp.GetValue()!r} SCH={expected['value']!r}")
        fpid = fp.GetFPIDAsString()
        if expected["footprint"] and fpid != expected["footprint"]:
            errors.append(f"{ref}: footprint PCB={fpid!r} SCH={expected['footprint']!r}")
        actual_path = fp.GetPath().AsString()
        if actual_path != expected["path"]:
            errors.append(f"{ref}: path PCB={actual_path!r} SCH={expected['path']!r}")
        if fp.IsDNP() != expected["dnp"]:
            errors.append(f"{ref}: DNP PCB={fp.IsDNP()} SCH={expected['dnp']}")
        actual = {}
        for pad in fp.Pads():
            if pad.GetNetname():
                actual[pad.GetNumber()] = pad.GetNetname()
        for pin, net in nodes.get(ref, {}).items():
            if actual.get(pin) != net:
                if (
                    (ref, pin) in ALLOWED_KEYED_MISSING_PADS
                    and pin not in actual
                    and net.startswith("unconnected-(")
                ):
                    continue
                errors.append(f"{ref}.{pin}: PCB={actual.get(pin)!r} SCH={net!r}")
        for pin, net in actual.items():
            if nodes.get(ref, {}).get(pin) != net:
                errors.append(f"{ref}.{pin}: PCB has unexpected net {net!r}")
    expected_refs = {ref for ref, c in comps.items() if c["footprint"]}
    for ref in sorted(expected_refs - pcb_refs):
        errors.append(f"missing PCB footprint: {ref}")
    if errors:
        print("Schematic/PCB parity FAILED:")
        print("\n".join(f"- {line}" for line in errors))
        raise SystemExit(1)
    print(f"Schematic/PCB parity OK: {len(pcb_refs)} footprints, all pad nets match")


if __name__ == "__main__":
    main()
