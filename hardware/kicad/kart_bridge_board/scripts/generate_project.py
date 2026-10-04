#!/usr/bin/env python3
"""Create the KiCad project settings file with JPBB net classes."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/template/kicad.kicad_pro")
TARGET = ROOT / "kart_bridge_board.kicad_pro"

# Nominal USB Full-Speed routing preset for a standard JLCPCB 4-layer, 1.0 mm
# board. These values preserve the short Rev.1 topology; Rev.2 does not order
# controlled impedance.
USB_DIFF_WIDTH = 0.15
USB_DIFF_GAP = 0.15


def netclass(name: str, width: float, clearance: float, diff_width: float = 0.2,
             diff_gap: float = 0.2, priority: int = 0) -> dict:
    return {
        "bus_width": 12,
        "clearance": clearance,
        "diff_pair_gap": diff_gap,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": diff_width,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "name": name,
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "priority": priority,
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": width,
        "via_diameter": 0.45,
        "via_drill": 0.30,
        "wire_width": 6,
    }


def main() -> None:
    if not TEMPLATE.exists():
        raise SystemExit(f"KiCad template not found: {TEMPLATE}")
    data = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    data["meta"]["filename"] = TARGET.name
    data["meta"]["version"] = 1
    data["net_settings"] = {
        "classes": [
            netclass("Default", 0.20, 0.20, priority=2_147_483_647),
            netclass("SIGNAL", 0.20, 0.20, priority=10),
            netclass("LOGIC_PWR", 0.40, 0.20, priority=20),
            netclass("VBEC_PWR", 2.00, 0.20, priority=30),
            netclass(
                "USB_DIFF", USB_DIFF_WIDTH, 0.20,
                diff_width=USB_DIFF_WIDTH, diff_gap=USB_DIFF_GAP, priority=40,
            ),
        ],
        "meta": {"version": 5},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": [
            {"netclass": "VBEC_PWR", "pattern": "VBEC"},
            {"netclass": "SIGNAL", "pattern": "VBEC_SENSE"},
            {"netclass": "LOGIC_PWR", "pattern": "+3V3"},
            {"netclass": "LOGIC_PWR", "pattern": "LOGIC_RAW"},
            {"netclass": "LOGIC_PWR", "pattern": "USB_VBUS"},
            {"netclass": "USB_DIFF", "pattern": "USB_DP"},
            {"netclass": "USB_DIFF", "pattern": "USB_DM"},
            {"netclass": "USB_DIFF", "pattern": "USB_DP_CONN"},
            {"netclass": "USB_DIFF", "pattern": "USB_DM_CONN"},
            {"netclass": "USB_DIFF", "pattern": "USB_DP_ESD"},
            {"netclass": "USB_DIFF", "pattern": "USB_DM_ESD"},
        ],
    }
    board_settings = data["board"]["design_settings"]
    board_settings["track_widths"] = [USB_DIFF_WIDTH, 0.20, 0.40, 2.00]
    board_settings["via_dimensions"] = [{"diameter": 0.45, "drill": 0.30}]
    board_settings["diff_pair_dimensions"] = [
        {"gap": USB_DIFF_GAP, "via_gap": 0.25, "width": USB_DIFF_WIDTH}
    ]
    # The stock empty-project template leaves these values absent.  KiCad then
    # falls back to 0.25/0.50/0.30 mm for tracks/vias/drills, which disagrees
    # with the JLCPCB-compatible geometry used by the deterministic router.
    # Record every manufacturing minimum needed by CLI DRC explicitly.
    board_settings["rules"] = {
        "max_error": 0.005,
        "min_clearance": 0.20,
        "min_connection": 0.0,
        "min_copper_edge_clearance": 0.40,
        "min_groove_width": 0.0,
        "min_hole_clearance": 0.25,
        "min_hole_to_hole": 0.25,
        "min_microvia_diameter": 0.20,
        "min_microvia_drill": 0.10,
        "min_resolved_spokes": 2,
        "min_silk_clearance": 0.0,
        "min_text_height": 0.80,
        "min_text_thickness": 0.08,
        "min_through_hole_diameter": 0.30,
        "min_track_width": 0.15,
        "min_via_annular_width": 0.075,
        "min_via_diameter": 0.45,
        "solder_mask_to_copper_clearance": 0.0,
        "use_height_for_length_calcs": True,
    }
    board_settings["meta"] = {"version": 2}
    TARGET.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(TARGET)


if __name__ == "__main__":
    main()
