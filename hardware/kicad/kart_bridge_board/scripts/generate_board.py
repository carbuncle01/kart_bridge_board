#!/usr/bin/env python3
"""Generate the JPBB-01 Rev.2 PCB from the schematic XML netlist.

Run with KiCad's bundled Python (the interpreter that can import pcbnew).  The
script deliberately regenerates the PCB from scratch so that symbol UUID paths,
pad nets, placement, planes, keepouts and routing remain reproducible.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush
import argparse
import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
PROJECT = "kart_bridge_board"
SCH = ROOT / f"{PROJECT}.kicad_sch"
NETLIST = ROOT / "fabrication" / "review" / "netlist.xml"
BOARD_PATH = ROOT / f"{PROJECT}.kicad_pcb"
AUTOROUTE_DIR = ROOT / "fabrication" / "review" / "autoroute"
SEED_BOARD = AUTOROUTE_DIR / f"{PROJECT}_60x30_seed.kicad_pcb"
DSN_PATH = AUTOROUTE_DIR / f"{PROJECT}_60x30.dsn"
SESSION_PATH = AUTOROUTE_DIR / f"{PROJECT}_60x30.ses"
LEGACY_BOARD = AUTOROUTE_DIR / f"{PROJECT}_legacy_routed.kicad_pcb"
KICAD_CLI = Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")
FP_ROOT = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")

F = pcbnew.F_Cu
B = pcbnew.B_Cu
IN1 = pcbnew.In1_Cu
IN2 = pcbnew.In2_Cu
EDGE = pcbnew.Edge_Cuts
FSILK = pcbnew.F_SilkS
BSILK = pcbnew.B_SilkS

W, H = 60.0, 30.0
# Rev.2 uses adhesive mounting only.  The larger outline gives the fitted SWD
# connector and BOOT/RESET controls honest assembly/courtyard clearance while
# retaining a flat 20 x 12 mm tape window on the back.
TAPE = (22.0, 9.0, 42.0, 21.0)
GRID = 0.25
EDGE_MARGIN = 0.40
CLEARANCE = 0.20

# Generic 4-layer, 1.0 mm, 1 oz outer / 0.5 oz inner construction. Rev.2 does
# not request a vendor-specific stack-up or controlled impedance.
STANDARD_STACKUP = """\
\t\t(stackup
\t\t\t(layer \"F.SilkS\"
\t\t\t\t(type \"Top Silk Screen\")
\t\t\t)
\t\t\t(layer \"F.Paste\"
\t\t\t\t(type \"Top Solder Paste\")
\t\t\t)
\t\t\t(layer \"F.Mask\"
\t\t\t\t(type \"Top Solder Mask\")
\t\t\t\t(color \"Green\")
\t\t\t\t(thickness 0.01)
\t\t\t)
\t\t\t(layer \"F.Cu\"
\t\t\t\t(type \"copper\")
\t\t\t\t(thickness 0.035)
\t\t\t)
\t\t\t(layer \"dielectric 1\"
\t\t\t\t(type \"prepreg\")
\t\t\t\t(thickness 0.0994)
\t\t\t\t(material \"FR-4\")
\t\t\t\t(epsilon_r 4.5)
\t\t\t\t(loss_tangent 0.015)
\t\t\t)
\t\t\t(layer \"In1.Cu\"
\t\t\t\t(type \"copper\")
\t\t\t\t(thickness 0.0152)
\t\t\t)
\t\t\t(layer \"dielectric 2\"
\t\t\t\t(type \"core\")
\t\t\t\t(thickness 0.7)
\t\t\t\t(material \"FR-4\")
\t\t\t\t(epsilon_r 4.5)
\t\t\t\t(loss_tangent 0.015)
\t\t\t)
\t\t\t(layer \"In2.Cu\"
\t\t\t\t(type \"copper\")
\t\t\t\t(thickness 0.0152)
\t\t\t)
\t\t\t(layer \"dielectric 3\"
\t\t\t\t(type \"prepreg\")
\t\t\t\t(thickness 0.0994)
\t\t\t\t(material \"FR-4\")
\t\t\t\t(epsilon_r 4.5)
\t\t\t\t(loss_tangent 0.015)
\t\t\t)
\t\t\t(layer \"B.Cu\"
\t\t\t\t(type \"copper\")
\t\t\t\t(thickness 0.035)
\t\t\t)
\t\t\t(layer \"B.Mask\"
\t\t\t\t(type \"Bottom Solder Mask\")
\t\t\t\t(color \"Green\")
\t\t\t\t(thickness 0.01)
\t\t\t)
\t\t\t(layer \"B.Paste\"
\t\t\t\t(type \"Bottom Solder Paste\")
\t\t\t)
\t\t\t(layer \"B.SilkS\"
\t\t\t\t(type \"Bottom Silk Screen\")
\t\t\t)
\t\t\t(copper_finish \"HAL lead-free\")
\t\t\t(dielectric_constraints no)
\t\t)
"""


def iu(mm: float) -> int:
    return pcbnew.FromMM(mm)


def v(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(iu(x), iu(y))


def mm_pos(p: pcbnew.VECTOR2I) -> tuple[float, float]:
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


@dataclass
class Component:
    ref: str
    value: str
    footprint: str
    path: str
    fields: dict[str, str]
    dnp: bool


def export_netlist() -> None:
    NETLIST.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(KICAD_CLI), "sch", "export", "netlist", "--format", "kicadxml",
         "-o", str(NETLIST), str(SCH)], check=True
    )


def parse_netlist() -> tuple[dict[str, Component], dict[str, list[tuple[str, str]]]]:
    root = ET.parse(NETLIST).getroot()
    comps: dict[str, Component] = {}
    for c in root.findall("./components/comp"):
        ref = c.attrib["ref"]
        fields = {f.attrib["name"]: (f.text or "") for f in c.findall("./fields/field")}
        sheet = c.find("sheetpath").attrib.get("tstamps", "/").rstrip("/")
        stamp = (c.findtext("tstamps") or "").strip("/")
        path = f"{sheet}/{stamp}" if sheet else f"/{stamp}"
        dnp_attr = c.attrib.get("dnp", "0").lower() in {"1", "true", "yes"}
        dnp_field = fields.get("DNP", "").strip().lower() in {"1", "true", "yes", "y", "dnp"}
        comps[ref] = Component(
            ref, c.findtext("value", ""), c.findtext("footprint", ""),
            path, fields, dnp_attr or dnp_field,
        )
    nets: dict[str, list[tuple[str, str]]] = {}
    for n in root.findall("./nets/net"):
        nets[n.attrib["name"]] = [
            (node.attrib["ref"], node.attrib["pin"]) for node in n.findall("node")
        ]
    return comps, nets


def custom_swd_footprint(board: pcbnew.BOARD, fpid: str) -> pcbnew.FOOTPRINT:
    fp = pcbnew.FOOTPRINT(board)
    fp.SetFPIDAsString(fpid)
    fp.SetAttributes(pcbnew.FP_SMD)
    copper = pcbnew.LSET()
    # These are spring-probe/debug pads, not assembled lands.  Omitting paste
    # prevents the PCBA stencil from depositing five unnecessary solder bricks.
    for layer in (pcbnew.F_Cu, pcbnew.F_Mask):
        copper.AddLayer(layer)
    for idx in range(5):
        pad = pcbnew.PAD(fp)
        pad.SetNumber(str(idx + 1))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
        pad.SetRoundRectRadiusRatio(0.20)
        pad.SetSize(v(0.60, 1.20))
        pad.SetLayerSet(copper)
        pad.SetPosition(v(idx * 0.80, 0))
        fp.Add(pad)
    return fp


def load_footprint(board: pcbnew.BOARD, fpid: str) -> pcbnew.FOOTPRINT:
    if fpid.startswith("JPBB:"):
        name = fpid.split(":", 1)[1]
        fp = pcbnew.FootprintLoad(str(ROOT / "lib" / "footprints.pretty"), name)
        if fp is None:
            raise RuntimeError(f"local footprint not found: {fpid}")
        fp.SetFPIDAsString(fpid)
        return fp
    if ":" not in fpid:
        raise RuntimeError(f"invalid footprint id: {fpid}")
    lib, name = fpid.split(":", 1)
    fp = pcbnew.FootprintLoad(str(FP_ROOT / f"{lib}.pretty"), name)
    if fp is None:
        raise RuntimeError(f"footprint not found: {fpid}")
    fp.SetFPIDAsString(fpid)
    return fp


# Explicit placement keeps all assembly on the front and leaves the central
# 20 x 12 mm back-side adhesive area free of pads/vias/footprints.
# Coordinates are footprint anchors in millimetres.
PLACEMENTS: dict[str, tuple[float, float, float]] = {
    "J1": (6.0, 2.4, 90), "J2": (18.0, 2.4, 90), "J3": (51.0, 2.4, 90),
    "J4": (53.0, 21.0, 90), "J5": (53.0, 26.0, 90),
    "J6": (5.4, 27.75, 0),
    "J7": (32.0, 15.0, 90),
    "SW1": (3.3, 13.0, 180), "SW2": (56.0, 7.5, 180),
    "D1": (35.0, 26.0, 90), "D2": (38.0, 26.0, 90),
    "U1": (17.0, 15.0, 180), "U2": (49.0, 14.0, 0),
    "U3": (56.0, 15.0, 180), "U4": (6.6, 19.5, 0),
    "U5": (51.0, 8.5, 0),
    "Q1": (2.5, 6.0, 0), "Q2": (10.5, 6.0, 0), "Q3": (42.0, 6.0, 0),
    "Q4": (14.0, 27.0, 0),
}


def default_placement(ref: str, ordinal: int) -> tuple[float, float, float]:
    """Fallback placement for newly added passives, before connectivity tuning."""
    # Four compact front-side shelves. The final placement is then improved by
    # connectivity in assign_passive_placements().
    shelves = [(3.5, 8.0), (3.5, 16.3), (20.7, 7.7), (19.7, 18.7)]
    x0, y0 = shelves[(ordinal // 12) % len(shelves)]
    k = ordinal % 12
    return x0 + (k % 6) * 1.75, y0 + (k // 6) * 1.55, 0


def assign_passive_placements(comps: dict[str, Component], nets: dict[str, list[tuple[str, str]]]) -> None:
    """Place R/C/TP parts in functional clusters using connected active parts."""
    ref_nets: dict[str, set[str]] = defaultdict(set)
    for name, nodes in nets.items():
        for ref, _ in nodes:
            ref_nets[ref].add(name)

    # Exact locations for the intended Rev.1 reference scheme. Unknown additions
    # still receive deterministic shelf positions below.
    exact = {
        # Power / VBEC section
        "C1": (44.5, 25.5, 0),
        "C3": (53.7, 17.8, 90), "C4": (55.0, 17.8, 90),
        "C5": (56.3, 17.8, 90), "C6": (25.5, 25.0, 90),
        # Combined-supply bulk capacitor.  Keep it left of D1/D2/C1 so the
        # diode cathode bus and its 0.40 mm trunk do not neck around C1.
        "C18": (32.0, 25.5, 0),
        "R1": (23.1, 25.0, 90), "R2": (24.3, 25.0, 90),
        # USB-C, ESD, VBUS detector
        "R3": (2.0, 17.0, 90), "R4": (8.0, 15.5, 90),
        # USBLC channels are assigned so DM stays above DP through the ESD-to-MCU
        # path; this avoids a differential-pair crossover at PA11/PA12.
        "R5": (10.6, 17.76, 90), "R6": (9.2, 16.76, 90),
        "C17": (6.6, 17.0, 0),
        "R7": (12.2, 23.8, 90), "R8": (13.5, 23.8, 90), "R9": (14.8, 23.8, 90),
        # MCU local decoupling / reset / HSE
        "C7": (23.9, 12.3, 0), "C8": (23.9, 13.6, 0),
        "C9": (23.9, 16.4, 0), "C10": (23.9, 17.7, 0),
        "C11": (7.3, 12.0, 0), "R10": (9.8, 12.0, 0),
        # MUX bypass/control
        "C14": (44.8, 19.5, 90), "C15": (46.3, 19.5, 90),
        "C16": (22.4, 9.0, 0),
        "R20": (21.0, 24.0, 0), "R21": (43.5, 9.0, 0),
        "R22": (18.5, 21.5, 90), "R23": (20.0, 21.5, 90),
        "R24": (49.5, 18.5, 90),
        "R26": (9.3, 22.0, 0), "R27": (11.8, 22.0, 0),
        # RC level shifters.  Each channel is a compact vertical functional
        # cluster: series/base pull-down/pull-up.  This keeps the raw, base and
        # captured-signal routes from crossing one another.
        "R11": (5.5, 4.80, 0), "R12": (5.5, 6.05, 0), "R13": (5.5, 7.30, 0),
        "R14": (13.7, 4.80, 0), "R15": (13.7, 6.05, 0), "R16": (13.7, 7.30, 0),
        "R17": (39.0, 4.80, 0), "R18": (39.0, 6.05, 0), "R19": (39.0, 7.30, 0),
    }
    for ref, pos in exact.items():
        if ref in comps:
            PLACEMENTS[ref] = pos

    # Test points: compact, labelled pads around accessible front-side margins.
    for idx in range(1, 13):
        ref = f"TP{idx}"
        if ref not in comps:
            continue
        tp_positions = {
            1: (49.0, 28.5, 0), 2: (29.0, 28.5, 0), 3: (18.0, 28.5, 0),
            4: (3.5, 2.4, 0), 5: (15.5, 2.4, 0), 6: (48.5, 2.4, 0),
            7: (58.5, 18.0, 0), 8: (53.0, 28.5, 0),
        }
        PLACEMENTS[ref] = tp_positions[idx]

    fallback = 0
    for ref in sorted(comps):
        if comps[ref].footprint and ref not in PLACEMENTS:
            PLACEMENTS[ref] = default_placement(ref, fallback)
            fallback += 1


def make_board(comps: dict[str, Component], nets: dict[str, list[tuple[str, str]]]) -> tuple[pcbnew.BOARD, dict[str, pcbnew.FOOTPRINT], dict[str, pcbnew.NETINFO_ITEM]]:
    board = pcbnew.BOARD()
    title_block = board.GetTitleBlock()
    title_block.SetTitle("kart_bridge_board")
    title_block.SetRevision("Rev.2")
    title_block.SetDate("2026-07-23")
    title_block.SetCompany("JPBB-01")
    title_block.SetComment(0, "JPBB-HW-DEF-002")
    board.SetCopperLayerCount(4)
    # In1 is the uninterrupted ground reference. In2 is a mixed VBEC plane;
    # marking only In1 as power prevents Specctra/Freerouting from cutting the
    # USB return plane while retaining one inner escape layer for dense areas.
    board.SetLayerType(IN1, pcbnew.LT_POWER)
    board.SetLayerType(IN2, pcbnew.LT_MIXED)
    board.GetDesignSettings().SetBoardThickness(iu(1.0))
    board.GetDesignSettings().m_MinClearance = iu(0.20)
    board.GetDesignSettings().m_TrackMinWidth = iu(0.15)
    board.GetDesignSettings().m_ViasMinSize = iu(0.45)
    board.GetDesignSettings().m_MinThroughDrill = iu(0.30)
    board.GetDesignSettings().m_CopperEdgeClearance = iu(0.40)

    net_objs: dict[str, pcbnew.NETINFO_ITEM] = {}
    for name in nets:
        obj = pcbnew.NETINFO_ITEM(board, name)
        board.Add(obj)
        net_objs[name] = obj

    fps: dict[str, pcbnew.FOOTPRINT] = {}
    for ref, comp in comps.items():
        if not comp.footprint:
            continue
        fp = load_footprint(board, comp.footprint)
        fp.SetReference(ref)
        fp.SetValue(comp.value)
        footprint_fields = fp.GetFieldsText()
        footprint_fields.update(comp.fields)
        fp.SetFields(footprint_fields)
        for field_name in comp.fields:
            field = fp.GetField(field_name)
            field.SetVisible(False)
            field.SetLayer(pcbnew.F_Fab)
        fp.SetPath(pcbnew.KIID_PATH(comp.path))
        fp.SetDNP(comp.dnp)
        if ref.startswith(("TP", "H")):
            fp.SetExcludedFromBOM(True)
            fp.SetExcludedFromPosFiles(True)
        if ref in {"J1", "J2", "J3", "J4", "J5"}:
            fp.SetDNP(True)
        x, y, angle = PLACEMENTS[ref]
        fp.SetPosition(v(x, y))
        fp.SetOrientationDegrees(angle)
        fp.Reference().SetVisible(False)
        fp.Value().SetVisible(False)
        board.Add(fp)
        fps[ref] = fp

    for name, nodes in nets.items():
        net = net_objs[name]
        for ref, pin in nodes:
            if ref not in fps:
                continue
            pads = [p for p in fps[ref].Pads() if p.GetNumber() == pin]
            if not pads:
                if (
                    (ref, pin) == ("J7", "7")
                    and name.startswith("unconnected-(")
                ):
                    continue
                raise RuntimeError(f"{ref}: footprint {comps[ref].footprint} has no pad {pin}")
            for pad in pads:
                pad.SetNet(net)
    return board, fps, net_objs


def add_shape(board: pcbnew.BOARD, layer: int, start: tuple[float, float], end: tuple[float, float], width: float = 0.10) -> None:
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(v(*start))
    s.SetEnd(v(*end))
    s.SetLayer(layer)
    s.SetWidth(iu(width))
    board.Add(s)


def add_outline(board: pcbnew.BOARD) -> None:
    add_shape(board, EDGE, (0, 0), (W, 0), 0.10)
    add_shape(board, EDGE, (W, 0), (W, H), 0.10)
    add_shape(board, EDGE, (W, H), (0, H), 0.10)
    add_shape(board, EDGE, (0, H), (0, 0), 0.10)


def add_text(board: pcbnew.BOARD, text: str, x: float, y: float, size: float = 0.8,
             layer: int = FSILK, angle: float = 0.0) -> None:
    t = pcbnew.PCB_TEXT(board)
    t.SetText(text)
    t.SetPosition(v(x, y))
    t.SetLayer(layer)
    t.SetTextSize(v(size, size))
    t.SetTextThickness(iu(max(0.12, size * 0.15)))
    t.SetTextAngle(pcbnew.EDA_ANGLE(angle, pcbnew.DEGREES_T))
    board.Add(t)


def add_keepout(board: pcbnew.BOARD, rect: tuple[float, float, float, float],
                *, footprints: bool, pads: bool, tracks: bool, vias: bool, fills: bool = False,
                layers: tuple[int, ...] = (F, IN1, IN2, B), name: str = "") -> None:
    x1, y1, x2, y2 = rect
    add_polygon_keepout(
        board,
        [(x1, y1), (x2, y1), (x2, y2), (x1, y2)],
        footprints=footprints, pads=pads, tracks=tracks, vias=vias,
        fills=fills, layers=layers, name=name,
    )


def add_polygon_keepout(board: pcbnew.BOARD, points: list[tuple[float, float]],
                        *, footprints: bool, pads: bool, tracks: bool, vias: bool,
                        fills: bool = False,
                        layers: tuple[int, ...] = (F, IN1, IN2, B),
                        name: str = "") -> None:
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    if name:
        z.SetZoneName(name)
    layer_set = pcbnew.LSET()
    for layer in layers:
        layer_set.AddLayer(layer)
    z.SetLayerSet(layer_set)
    z.SetDoNotAllowFootprints(footprints)
    z.SetDoNotAllowPads(pads)
    z.SetDoNotAllowTracks(tracks)
    z.SetDoNotAllowVias(vias)
    z.SetDoNotAllowZoneFills(fills)
    poly = z.Outline()
    poly.NewOutline()
    for x, y in points:
        poly.Append(v(x, y))
    board.Add(z)


def add_circular_keepout(board: pcbnew.BOARD, center: tuple[float, float], radius: float,
                         *, footprints: bool, pads: bool, tracks: bool, vias: bool,
                         fills: bool = False,
                         layers: tuple[int, ...] = (F, IN1, IN2, B),
                         name: str = "") -> None:
    cx, cy = center
    # Circumscribe rather than inscribe the 48-gon so clearance never falls
    # below the requested radial value between vertices.
    vertex_radius = radius / math.cos(math.pi / 48.0)
    points = [
        (
            cx + vertex_radius * math.cos(2.0 * math.pi * index / 48.0),
            cy + vertex_radius * math.sin(2.0 * math.pi * index / 48.0),
        )
        for index in range(48)
    ]
    add_polygon_keepout(
        board, points, footprints=footprints, pads=pads, tracks=tracks,
        vias=vias, fills=fills, layers=layers, name=name,
    )


def add_zone(board: pcbnew.BOARD, net: pcbnew.NETINFO_ITEM, layer: int,
             rect: tuple[float, float, float, float], priority: int = 0,
             pad_connection: int = pcbnew.ZONE_CONNECTION_THERMAL) -> None:
    x1, y1, x2, y2 = rect
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net)
    z.SetAssignedPriority(priority)
    z.SetMinThickness(iu(0.20))
    z.SetLocalClearance(iu(0.20))
    z.SetPadConnection(pad_connection)
    z.SetThermalReliefGap(iu(0.25))
    z.SetThermalReliefSpokeWidth(iu(0.30))
    poly = z.Outline()
    poly.NewOutline()
    for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
        poly.Append(v(x, y))
    board.Add(z)


def decorate(board: pcbnew.BOARD, nets: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    add_outline(board)
    # Copper planes: uninterrupted ground reference on L2 and VBEC distribution on L3.
    inset = (0.45, 0.45, W - 0.45, H - 0.45)
    add_zone(board, nets["GND"], IN1, inset)
    add_zone(board, nets["VBEC"], IN2, inset)
    # Solid top-side ground avoids incomplete one-spoke thermals at the dense
    # USB-C/ESD pads while the uninterrupted In1 plane remains the reference.
    add_zone(board, nets["GND"], F, inset, pad_connection=pcbnew.ZONE_CONNECTION_FULL)
    add_zone(board, nets["+3V3"], B, inset)

    # Back-side copper may remain beneath the tape, but no via/pad/footprint may
    # disturb its flat surface. Tracks are intentionally allowed.
    # KiCad's built-in footprint keepout is not side-specific, even when the
    # area is on B.Cu.  A named-area custom rule in the .kicad_dru therefore
    # enforces bottom-side footprints only; pads and vias remain hard keepouts.
    add_keepout(
        board, TAPE, footprints=False, pads=True, tracks=False, vias=True,
        layers=(B,), name="ADHESIVE_20X12",
    )
    # H1/H2 were intentionally removed: the board is fixed by the flat 20 x 12
    # mm back-side adhesive area instead of asymmetric mounting holes.

    # Keep identification below the fitted SWD connector. Small connector and
    # button legends sit immediately beside the associated hardware.
    add_text(board, "SWD  1", 32.0, 7.9, 0.80)
    add_text(board, "kart_bridge_board", 36.85, 15.0, 0.80, angle=90)
    add_text(board, "JPBB-01 Rev.2", 37.95, 15.0, 0.80, angle=90)
    add_text(board, "ADHESIVE 20x12 (B)", 39.05, 15.0, 0.80, angle=90)
    add_text(board, "RST", 3.0, 10.55, 0.80)
    add_text(board, "BOOT", 56.0, 4.8, 0.80)
    add_text(board, "RX1  S + -", 8.55, 0.80, 0.80)
    add_text(board, "RX2  S + -", 20.55, 0.80, 0.80)
    add_text(board, "RX3  S + -", 53.55, 0.80, 0.80)
    add_text(board, "SERVO", 51.0, 21.5, 0.80, angle=90)
    add_text(board, "S + -", 56.15, 19.55, 0.80)
    add_text(board, "S + -", 56.15, 24.55, 0.80)
    add_text(board, "ESC/BEC", 57.0, 29.2, 0.80)
    # Tape boundary on Dwgs.User and back silkscreen, kept outside the actual area.
    x1, y1, x2, y2 = TAPE
    for layer in (pcbnew.Dwgs_User,):
        add_shape(board, layer, (x1, y1), (x2, y1), 0.10)
        add_shape(board, layer, (x2, y1), (x2, y2), 0.10)
        add_shape(board, layer, (x2, y2), (x1, y2), 0.10)
        add_shape(board, layer, (x1, y2), (x1, y1), 0.10)


def layer_set(pad: pcbnew.PAD) -> list[int]:
    return [layer for layer in (F, B) if pad.IsOnLayer(layer)]


def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def add_track(board: pcbnew.BOARD, net: pcbnew.NETINFO_ITEM, layer: int,
              start: tuple[float, float], end: tuple[float, float], width: float) -> pcbnew.PCB_TRACK:
    t = pcbnew.PCB_TRACK(board)
    t.SetNet(net)
    t.SetLayer(layer)
    t.SetStart(v(*start))
    t.SetEnd(v(*end))
    t.SetWidth(iu(width))
    t.SetLocked(True)
    board.Add(t)
    return t


def add_polyline(board: pcbnew.BOARD, net: pcbnew.NETINFO_ITEM, layer: int,
                 points: list[tuple[float, float]], width: float) -> None:
    for start, end in zip(points, points[1:]):
        add_track(board, net, layer, start, end, width)


def add_via(board: pcbnew.BOARD, net: pcbnew.NETINFO_ITEM, pos: tuple[float, float],
            size: float = 0.45, drill: float = 0.30) -> pcbnew.PCB_VIA:
    via = pcbnew.PCB_VIA(board)
    via.SetNet(net)
    via.SetPosition(v(*pos))
    via.SetWidth(iu(size))
    via.SetDrill(iu(drill))
    via.SetTopLayer(F)
    via.SetBottomLayer(B)
    via.SetLocked(True)
    board.Add(via)
    return via


class GridRouter:
    def __init__(self, board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                 nets: dict[str, pcbnew.NETINFO_ITEM]):
        self.board, self.fps, self.nets = board, fps, nets
        self.nx = round(W / GRID)
        self.ny = round(H / GRID)
        self.routed: dict[str, set[tuple[int, int, int]]] = defaultdict(set)

    def cell(self, point: tuple[float, float]) -> tuple[int, int]:
        return round(point[0] / GRID), round(point[1] / GRID)

    def point(self, cell: tuple[int, int]) -> tuple[float, float]:
        return cell[0] * GRID, cell[1] * GRID

    def in_tape(self, ix: int, iy: int) -> bool:
        x, y = self.point((ix, iy))
        x1, y1, x2, y2 = TAPE
        return x1 <= x <= x2 and y1 <= y <= y2

    def obstacle_cells(self, net_name: str, width: float) -> dict[int, set[tuple[int, int]]]:
        blocked = {F: set(), B: set()}
        radius = width / 2 + CLEARANCE

        def block_rect(layer: int, x1: float, y1: float, x2: float, y2: float) -> None:
            # Mark grid points whose *centres* lie inside the clearance envelope.
            # ceil/floor avoids adding a whole extra grid cell on every side.
            ax = max(0, math.ceil((x1 - radius) / GRID))
            bx = min(self.nx, math.floor((x2 + radius) / GRID))
            ay = max(0, math.ceil((y1 - radius) / GRID))
            by = min(self.ny, math.floor((y2 + radius) / GRID))
            for ix in range(ax, bx + 1):
                for iy in range(ay, by + 1):
                    blocked[layer].add((ix, iy))

        # Edge margin.
        for ix in range(self.nx + 1):
            for iy in range(self.ny + 1):
                x, y = self.point((ix, iy))
                if x < EDGE_MARGIN or x > W - EDGE_MARGIN or y < EDGE_MARGIN or y > H - EDGE_MARGIN:
                    blocked[F].add((ix, iy)); blocked[B].add((ix, iy))

        for fp in self.fps.values():
            for pad in fp.Pads():
                if pad.GetNetname() == net_name:
                    continue
                box = pad.GetBoundingBox()
                x1, y1 = pcbnew.ToMM(box.GetX()), pcbnew.ToMM(box.GetY())
                x2, y2 = x1 + pcbnew.ToMM(box.GetWidth()), y1 + pcbnew.ToMM(box.GetHeight())
                for layer in (F, B):
                    if pad.IsOnLayer(layer):
                        block_rect(layer, x1, y1, x2, y2)

        # Previously routed copper.
        for item in self.board.GetTracks():
            if item.GetNetname() == net_name:
                continue
            if isinstance(item, pcbnew.PCB_VIA):
                x, y = mm_pos(item.GetPosition())
                r = pcbnew.ToMM(item.GetWidth(F)) / 2
                for layer in (F, B):
                    block_rect(layer, x - r, y - r, x + r, y + r)
            else:
                layer = item.GetLayer()
                if layer not in (F, B):
                    continue
                a, b = mm_pos(item.GetStart()), mm_pos(item.GetEnd())
                steps = max(1, int(dist(a, b) / (GRID / 2)))
                r = pcbnew.ToMM(item.GetWidth()) / 2
                for i in range(steps + 1):
                    q = i / steps
                    x, y = a[0] + (b[0] - a[0]) * q, a[1] + (b[1] - a[1]) * q
                    block_rect(layer, x - r, y - r, x + r, y + r)
        return blocked

    def search(self, starts: list[tuple[int, int, int]], goals: set[tuple[int, int, int]],
               blocked: dict[int, set[tuple[int, int]]]) -> list[tuple[int, int, int]] | None:
        goal_xy = [(x, y) for x, y, _ in goals]
        def heuristic(n):
            x, y, layer = n
            return min(abs(x - gx) + abs(y - gy) for gx, gy in goal_xy) + (0 if any(g[2] == layer for g in goals) else 12)
        q = []
        best = {}
        parent = {}
        for s in starts:
            heappush(q, (heuristic(s), 0, s))
            best[s] = 0
        directions = ((1,0,10),(-1,0,10),(0,1,10),(0,-1,10),
                      (1,1,14),(1,-1,14),(-1,1,14),(-1,-1,14))
        goal_hit = None
        while q:
            _, cost, node = heappop(q)
            if cost != best.get(node):
                continue
            if node in goals:
                goal_hit = node
                break
            x, y, layer = node
            for dx, dy, step in directions:
                nx, ny = x + dx, y + dy
                if not (0 <= nx <= self.nx and 0 <= ny <= self.ny):
                    continue
                if (nx, ny) in blocked[layer] and (nx, ny, layer) not in goals:
                    continue
                nxt = (nx, ny, layer)
                nc = cost + step
                if nc < best.get(nxt, 10**18):
                    best[nxt] = nc; parent[nxt] = node
                    heappush(q, (nc + heuristic(nxt), nc, nxt))
            other = B if layer == F else F
            if not self.in_tape(x, y) and (x, y) not in blocked[other] and (x, y) not in blocked[layer]:
                nxt = (x, y, other)
                nc = cost + 180
                if nc < best.get(nxt, 10**18):
                    best[nxt] = nc; parent[nxt] = node
                    heappush(q, (nc + heuristic(nxt), nc, nxt))
        if goal_hit is None:
            return None
        path = [goal_hit]
        while path[-1] in parent:
            path.append(parent[path[-1]])
        path.reverse()
        return path

    @staticmethod
    def simplify(path: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
        if len(path) <= 2:
            return path
        out = [path[0]]
        last_dir = None
        for i in range(1, len(path)):
            a, b = path[i - 1], path[i]
            direction = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            if last_dir is not None and direction != last_dir:
                out.append(a)
            last_dir = direction
        out.append(path[-1])
        return out

    def route_net(self, name: str, pads: list[pcbnew.PAD], width: float = 0.20) -> None:
        if len(pads) < 2:
            return
        net = self.nets[name]
        # Start with the pad that minimizes total distance, reducing tree length.
        centers = [mm_pos(p.GetPosition()) for p in pads]
        root_index = min(range(len(pads)), key=lambda i: sum(dist(centers[i], q) for q in centers))
        root_pad = pads[root_index]
        root_xy = self.cell(mm_pos(root_pad.GetPosition()))
        root_layers = layer_set(root_pad) or [F]
        tree = {(root_xy[0], root_xy[1], layer) for layer in root_layers}
        self.routed[name].update(tree)
        remaining = [p for i, p in enumerate(pads) if i != root_index]
        remaining.sort(key=lambda p: dist(mm_pos(p.GetPosition()), mm_pos(root_pad.GetPosition())))
        for pad in remaining:
            xy = self.cell(mm_pos(pad.GetPosition()))
            starts = [(xy[0], xy[1], layer) for layer in (layer_set(pad) or [F])]
            blocked = self.obstacle_cells(name, width)
            # Fine-pitch USB/LQFP pads can sit between grid points. Clear a tiny
            # endpoint escape window; the actual segment still starts at the pad
            # centre and DRC remains the final clearance authority.
            for ex, ey, el in starts + list(tree):
                for dx in (-2, -1, 0, 1, 2):
                    for dy in (-2, -1, 0, 1, 2):
                        blocked[el].discard((ex + dx, ey + dy))
            path = self.search(starts, tree, blocked)
            if path is None:
                raise RuntimeError(f"router failed for {name}: {mm_pos(pad.GetPosition())}")
            path = self.simplify(path)
            # Exact pad-centre connection at the first point.
            first = self.point((path[0][0], path[0][1]))
            pcenter = mm_pos(pad.GetPosition())
            if dist(first, pcenter) > 0.01:
                add_track(self.board, net, path[0][2], pcenter, first, width)
            for a, b in zip(path, path[1:]):
                pa, pb = self.point((a[0], a[1])), self.point((b[0], b[1]))
                if a[2] != b[2]:
                    add_via(self.board, net, pa)
                elif pa != pb:
                    add_track(self.board, net, a[2], pa, pb, width)
            tree.update(path)
            self.routed[name].update(path)


def collect_pads(fps: dict[str, pcbnew.FOOTPRINT]) -> dict[str, list[pcbnew.PAD]]:
    by_net: dict[str, list[pcbnew.PAD]] = defaultdict(list)
    for fp in fps.values():
        for pad in fp.Pads():
            if pad.GetNetname():
                by_net[pad.GetNetname()].append(pad)
    return by_net


def fp_pad(fps: dict[str, pcbnew.FOOTPRINT], ref: str, number: str) -> tuple[float, float]:
    pads = [p for p in fps[ref].Pads() if p.GetNumber() == number]
    if not pads:
        raise RuntimeError(f"{ref} has no pad {number}")
    return mm_pos(pads[0].GetPosition())


def route_usb(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
              net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    """Route the reversible Type-C pair through ESD to PA11/PA12.

    The interleaved duplicate Type-C contacts use two short B.Cu crossovers.
    Everything from the ESD array to the MCU remains via-free on F.Cu.
    """
    width = 0.15
    dp_in, dm_in = net_objs["USB_DP_CONN"], net_objs["USB_DM_CONN"]
    u_dm, u_dp = fp_pad(fps, "U4", "1"), fp_pad(fps, "U4", "3")

    add_polyline(board, dm_in, F,
                 [fp_pad(fps, "J6", "B7"), (4.65, 21.00),
                  (4.20, 20.55), (4.20, u_dm[1]), u_dm], width)
    dm_v1, dm_v2 = (5.65, 22.60), (3.50, 19.00)
    add_polyline(board, dm_in, F,
                 [fp_pad(fps, "J6", "A7"), dm_v1], width)
    add_via(board, dm_in, dm_v1)
    add_polyline(board, dm_in, B, [dm_v1, dm_v2], width)
    add_via(board, dm_in, dm_v2)
    add_polyline(board, dm_in, F,
                 [dm_v2, (4.20, u_dm[1])], width)

    add_polyline(board, dp_in, F,
                 [fp_pad(fps, "J6", "A6"), (5.15, u_dp[1]), u_dp], width)
    dp_v1, dp_v2 = (6.15, 21.60), (6.60, 20.80)
    add_polyline(board, dp_in, F, [fp_pad(fps, "J6", "B6"), dp_v1], width)
    add_via(board, dp_in, dp_v1)
    add_polyline(board, dp_in, B, [dp_v1, dp_v2], width)
    add_via(board, dp_in, dp_v2)
    add_polyline(board, dp_in, F,
                 [dp_v2, (6.20, u_dp[1]), u_dp], width)

    add_polyline(board, net_objs["USB_DM_ESD"], F,
                 [fp_pad(fps, "U4", "6"), (8.20, 18.55),
                  (9.20, 17.55), fp_pad(fps, "R6", "1")], width)
    add_polyline(board, net_objs["USB_DM"], F,
                 [fp_pad(fps, "R6", "2"), fp_pad(fps, "U1", "33")], width)
    add_polyline(board, net_objs["USB_DP_ESD"], F,
                 [fp_pad(fps, "U4", "4"), (8.20, 20.45),
                  (8.80, 21.05), (9.40, 20.45), (8.80, 19.85),
                  (9.40, 19.25), (10.00, 19.85), (10.60, 19.25),
                  (10.00, 18.65), fp_pad(fps, "R5", "1")], width)
    add_polyline(board, net_objs["USB_DP"], F,
                 [fp_pad(fps, "R5", "2"), (11.00, 16.85),
                  (11.20, 16.75), fp_pad(fps, "U1", "34")], width)


def route_mux_outputs(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                      net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    servo = net_objs["SERVO_SIGNAL"]
    s_mux, s_tp, s_out = fp_pad(fps, "U2", "3"), fp_pad(fps, "TP7", "1"), fp_pad(fps, "J4", "1")
    s_v1, s_v2 = (23.50, 6.20), (33.10, 16.80)
    add_polyline(board, servo, F, [s_mux, (23.50, s_mux[1]), s_v1], 0.20)
    add_via(board, servo, s_v1)
    add_polyline(board, servo, B, [s_v1, (33.10, 6.20), s_v2], 0.20)
    add_via(board, servo, s_v2)
    add_polyline(board, servo, F, [s_v2, s_tp, (32.20, 17.20), s_out], 0.20)

    esc = net_objs["ESC_SIGNAL"]
    e_mux, e_tp, e_out = fp_pad(fps, "U2", "11"), fp_pad(fps, "TP8", "1"), fp_pad(fps, "J5", "1")
    via = (31.70, 12.175)
    add_polyline(board, esc, F, [e_mux, via], 0.20)
    add_via(board, esc, via)
    add_polyline(board, esc, B, [via, (31.70, 20.50), (33.10, 20.50), e_out], 0.20)
    add_polyline(board, esc, F, [e_out, (32.60, 23.10), e_tp], 0.20)


def route_mux_select(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                     net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    mcu_net = net_objs["SAFE_AUTO_SEL_MCU"]
    u1, r20_in = fp_pad(fps, "U1", "19"), fp_pad(fps, "R20", "1")
    add_polyline(board, mcu_net, F, [u1, (16.5, 8.0), r20_in], 0.20)

    safe = net_objs["SAFE_AUTO_SEL"]
    r20_out, r21_in = fp_pad(fps, "R20", "2"), fp_pad(fps, "R21", "1")
    sel1, sel2 = fp_pad(fps, "U2", "1"), fp_pad(fps, "U2", "9")
    add_polyline(board, safe, F, [r20_out, r21_in, sel1], 0.20)
    add_polyline(board, safe, F,
                 [sel1, (20.8, 9.0), (28.0, 9.0), (28.0, sel2[1]), sel2], 0.20)
    # TP11 is reached on B.Cu; both vias are outside the no-via adhesive area.
    tp = fp_pad(fps, "TP11", "1")
    v1, v2 = (21.0, 5.5), (13.0, 19.2)
    add_polyline(board, safe, F, [r20_out, (21.0, 8.0), v1], 0.20)
    add_via(board, safe, v1)
    add_polyline(board, safe, B, [v1, (21.0, 19.2), v2], 0.20)
    add_via(board, safe, v2)
    add_polyline(board, safe, F, [v2, tp], 0.20)


def route_pwm(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
              net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    # PB4/PB5 leave below the MCU and change layer outside the adhesive window.
    # Long B.Cu runs return to F.Cu above/right of U2, also outside the window.
    servo = net_objs["MCU_SERVO_PWM"]
    s_u1, s_u2 = fp_pad(fps, "U1", "43"), fp_pad(fps, "U2", "2")
    s_v1, s_v2 = (15.85, 18.80), (29.90, 5.00)
    add_polyline(board, servo, F, [s_u1, s_v1], 0.20)
    add_via(board, servo, s_v1)
    add_polyline(board, servo, B,
                 [s_v1, (15.85, 5.00), s_v2], 0.20)
    add_via(board, servo, s_v2)
    add_polyline(board, servo, F,
                 [s_v2, (29.90, 8.20), (24.60, 8.20),
                  (24.60, s_u2[1]), s_u2], 0.20)

    esc = net_objs["MCU_ESC_PWM"]
    e_u1, e_u2 = fp_pad(fps, "U1", "44"), fp_pad(fps, "U2", "10")
    e_v1, e_v2 = (16.70, 20.50), (30.20, 14.10)
    add_polyline(board, esc, F,
                 [e_u1, (16.35, 18.10), (16.70, 18.45), e_v1], 0.20)
    add_via(board, esc, e_v1)
    add_polyline(board, esc, B,
                 [e_v1, (17.40, 19.90), (30.20, 19.90), e_v2], 0.20)
    add_via(board, esc, e_v2)
    add_polyline(board, esc, F,
                 [e_v2, (30.20, e_u2[1]), e_u2], 0.20)


def route_usb_cc(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                 net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    """Route the two low-speed Type-C configuration channels on F.Cu."""
    cc1 = net_objs["USB_CC1"]
    add_polyline(board, cc1, F,
                 [fp_pad(fps, "J6", "A5"), (4.15, 22.20),
                  fp_pad(fps, "R3", "1")], 0.20)

    cc2 = net_objs["USB_CC2"]
    add_polyline(board, cc2, F,
                 [fp_pad(fps, "J6", "B5"), (7.15, 22.20),
                  fp_pad(fps, "R4", "1")], 0.20)


def route_raw_inputs(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                     net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    # Header/test/conditioning branches stay on F.Cu.
    for name, header, resistor, tp in (
        ("RX_CH1_RAW", "J1", "R11", "TP4"),
        ("RX_CH2_RAW", "J2", "R14", "TP5"),
        ("RX_CH3_RAW", "J3", "R17", "TP6"),
    ):
        net = net_objs[name]
        h, r, t = fp_pad(fps, header, "1"), fp_pad(fps, resistor, "1"), fp_pad(fps, tp, "1")
        add_polyline(board, net, F, [h, r, t], 0.20)

    # CH1/CH2 manual paths use the header's plated pad as the B.Cu endpoint.
    rx1 = net_objs["RX_CH1_RAW"]
    u1, j1, via1 = fp_pad(fps, "U2", "4"), fp_pad(fps, "J1", "1"), (20.3, 5.8)
    add_polyline(board, rx1, F, [u1, (20.3, u1[1]), via1], 0.20)
    add_via(board, rx1, via1)
    add_polyline(board, rx1, B, [via1, (20.3, 3.8), (8.0, 3.8), j1], 0.20)

    rx2 = net_objs["RX_CH2_RAW"]
    u2, j2, via2 = fp_pad(fps, "U2", "12"), fp_pad(fps, "J2", "1"), (28.2, 13.0)
    add_polyline(board, rx2, F, [u2, via2], 0.20)
    add_via(board, rx2, via2)
    add_polyline(board, rx2, B, [via2, (28.2, 5.0), (18.0, 5.0), j2], 0.20)


def route_swd(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
              net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    swdio = net_objs["SWDIO"]
    d0, d1 = fp_pad(fps, "U1", "35"), fp_pad(fps, "J7", "1")
    add_polyline(board, swdio, F,
                 [d0, (10.35, 15.25), (10.35, 16.80), (11.10, 17.80), d1], 0.20)
    swclk = net_objs["SWCLK"]
    c0, c1 = fp_pad(fps, "U1", "36"), fp_pad(fps, "J7", "2")
    add_polyline(board, swclk, F,
                 [c0, (11.00, 15.75), (11.00, 16.80), (11.90, 17.80), c1], 0.20)


def route_reset(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    net = net_objs["NRST"]
    mcu, probe = fp_pad(fps, "U1", "10"), fp_pad(fps, "J7", "3")
    top_via, probe_via = (22.10, 18.80), (12.70, 19.00)
    add_polyline(board, net, F, [mcu, (22.10, mcu[1]), top_via], 0.20)
    add_via(board, net, top_via)
    add_polyline(board, net, B,
                 [top_via, (22.10, 19.40), (12.70, 19.40), probe_via], 0.20)
    add_via(board, net, probe_via)
    add_polyline(board, net, F, [probe_via, probe], 0.20)

    # The local reset RC branch is kept on F.Cu and joins the already locked
    # MCU-to-debug path at U1.10.  This route was clearance-checked together
    # with the adjacent USB and capture circuitry.
    cap, pull = fp_pad(fps, "C11", "1"), fp_pad(fps, "R10", "2")
    add_polyline(
        board, net, F,
        [cap, (6.50, 10.25), (7.25, 11.00), (8.75, 11.00),
         (9.50, 10.25), pull, (10.00, 9.75), (12.25, 9.75),
         (13.75, 11.25), mcu], 0.20,
    )


def route_ch1_input_paths(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                          net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    """Lock CH1 raw/manual and captured-input routes before autorouting."""
    captured = net_objs["RX_CH1_MCU_N"]
    q, pull, mcu = fp_pad(fps, "Q1", "3"), fp_pad(fps, "R13", "2"), fp_pad(fps, "U1", "11")
    add_polyline(
        board, captured, F,
        [q, (3.25, 6.00), (3.25, 6.75), (4.50, 8.00), (5.25, 8.00),
         (6.00, 7.25), pull, (8.25, 5.00), (8.25, 4.50), (8.75, 4.00),
         (14.50, 4.00), (14.75, 4.25), (18.50, 4.25), (19.75, 5.50),
         (20.50, 5.50), (21.00, 6.00), (21.00, 10.50),
         (20.75, 10.75), mcu], 0.20,
    )

    raw = net_objs["RX_CH1_RAW"]
    tp, header, series, mux = (
        fp_pad(fps, "TP4", "1"), fp_pad(fps, "J1", "1"),
        fp_pad(fps, "R11", "1"), fp_pad(fps, "U2", "4"),
    )
    trunk = (6.00, 2.50)
    add_polyline(board, raw, F, [tp, (3.50, 2.50), trunk, header], 0.20)
    add_polyline(board, raw, F, [series, (5.00, 4.75), (5.00, 3.50), trunk], 0.20)
    add_polyline(
        board, raw, F,
        [trunk, (7.50, 1.00), (12.00, 1.00), (14.50, 3.50),
         (15.00, 3.50), (15.25, 3.75), (18.75, 3.75), (19.00, 4.00),
         (19.25, 4.00), (20.25, 5.00), (21.00, 5.00), (21.75, 5.75),
         (21.75, 6.50), (22.00, 6.75), (22.00, 10.50),
         (22.25, 10.75), (22.50, 10.75), (22.75, 11.00),
         (25.75, 11.00), mux], 0.20,
    )


def route_debug_power(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                      net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    for net_name, pad_number, via_pos in (
        ("+3V3", "4", (13.50, 18.80)),
        ("GND", "5", (14.30, 18.80)),
    ):
        pad = fp_pad(fps, "J7", pad_number)
        add_polyline(board, net_objs[net_name], F, [pad, via_pos], 0.35)
        add_via(board, net_objs[net_name], via_pos)


def route_hse_option(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                     net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    pf0 = net_objs["PF0_OSC_IN"]
    p0, y0, c0 = fp_pad(fps, "U1", "8"), fp_pad(fps, "Y1", "1"), fp_pad(fps, "C12", "1")
    add_polyline(board, pf0, F, [p0, (10.5, p0[1]), y0, c0], 0.20)
    pf1 = net_objs["PF1_OSC_OUT"]
    p1, y1, c1 = fp_pad(fps, "U1", "9"), fp_pad(fps, "Y1", "3"), fp_pad(fps, "C13", "1")
    add_polyline(board, pf1, F, [p1, (10.5, p1[1]), y1, c1], 0.20)


def route_capture_inputs(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                         net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    # CH2 is adjacent to its MCU pin.
    ch2 = net_objs["RX_CH2_MCU_N"]
    q2, r2, m2 = fp_pad(fps, "Q2", "3"), fp_pad(fps, "R16", "2"), fp_pad(fps, "U1", "12")
    add_polyline(board, ch2, F, [q2, r2, (19.8, 8.8), m2], 0.20)

    # CH1 and CH3 use B.Cu across the top margin to avoid crossing CH2.
    ch1 = net_objs["RX_CH1_MCU_N"]
    q1, r1, m1 = fp_pad(fps, "Q1", "3"), fp_pad(fps, "R13", "2"), fp_pad(fps, "U1", "11")
    a1, b1 = (11.2, 5.2), (20.8, 5.2)
    add_polyline(board, ch1, F, [q1, r1, a1], 0.20)
    add_via(board, ch1, a1)
    add_polyline(board, ch1, B, [a1, (11.2, 6.9), (20.8, 6.9), b1], 0.20)
    add_via(board, ch1, b1)
    add_polyline(board, ch1, F, [b1, (20.8, m1[1]), m1], 0.20)

    ch3 = net_objs["RX_CH3_MCU_N"]
    q3, r3, m3 = fp_pad(fps, "Q3", "3"), fp_pad(fps, "R19", "2"), fp_pad(fps, "U1", "13")
    a3, b3 = (29.0, 5.4), (17.0, 5.4)
    add_polyline(board, ch3, F, [q3, r3, a3], 0.20)
    add_via(board, ch3, a3)
    add_polyline(board, ch3, B, [a3, (29.0, 7.5), (17.0, 7.5), b3], 0.20)
    add_via(board, ch3, b3)
    add_polyline(board, ch3, F, [b3, (17.0, 7.8), m3], 0.20)


def route_usb_present(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                      net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    net = net_objs["USB_PRESENT_N"]
    mcu = fp_pad(fps, "U1", "20")
    top, bottom = (12.0, 6.0), (13.5, 18.8)
    add_polyline(board, net, F, [mcu, (13.0, 7.3), top], 0.20)
    add_via(board, net, top)
    add_polyline(board, net, B, [top, (12.0, 18.0), bottom], 0.20)
    add_via(board, net, bottom)
    q, pull, tp = fp_pad(fps, "Q4", "3"), fp_pad(fps, "R9", "2"), fp_pad(fps, "TP12", "1")
    add_polyline(board, net, F, [bottom, q, pull], 0.20)
    add_polyline(board, net, F, [q, tp], 0.20)


def route_3v3(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
              net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    net = net_objs["+3V3"]
    # MCU power/decoupling column and CH2 pull-up share a top-side trunk.
    trunk_x, trunk_via = 19.8, (19.8, 5.5)
    add_via(board, net, trunk_via)
    add_polyline(board, net, F, [trunk_via, (trunk_x, 15.3)], 0.35)
    for ref in ("C7", "C8", "C9", "C10"):
        p = fp_pad(fps, ref, "1")
        add_polyline(board, net, F, [p, (trunk_x, p[1])], 0.35)
    for pin in ("4", "5", "6"):
        p = fp_pad(fps, "U1", pin)
        add_polyline(board, net, F, [p, (trunk_x, p[1])], 0.35)
    for ref, pin in (("R10", "1"), ("R16", "1")):
        p = fp_pad(fps, ref, pin)
        add_polyline(board, net, F, [p, (trunk_x, p[1])], 0.35)

    # CH1/RC converter bypass group.
    left_via = (11.5, 5.5)
    add_via(board, net, left_via)
    for ref in ("R13", "C16"):
        p = fp_pad(fps, ref, "1")
        add_polyline(board, net, F, [p, (11.5, p[1]), left_via], 0.35)

    # Remaining pads sit outside the adhesive no-via area and connect directly
    # to the B.Cu +3V3 pour through short spokes.
    spokes = [
        ("U3", "2", (28.6, 15.45)),
        ("C4", "1", (26.8, 24.0)),
        ("C5", "1", (29.0, 23.8)),
        ("R9", "1", (12.7, 20.4)),
        ("R19", "1", (29.4, 7.8)),
        ("J7", "4", (2.2, fp_pad(fps, "J7", "4")[1])),
        ("TP2", "1", (32.2, 10.0)),
    ]
    for ref, pin, via_pos in spokes:
        p = fp_pad(fps, ref, pin)
        add_polyline(board, net, F, [p, via_pos], 0.35)
        add_via(board, net, via_pos)


def route_ground_escapes(
    board: pcbnew.BOARD,
    fps: dict[str, pcbnew.FOOTPRINT],
    net_objs: dict[str, pcbnew.NETINFO_ITEM],
) -> None:
    """Lock short ground escapes before autorouting.

    Dense signal fan-outs divide the F.Cu pour into small islands.  Each
    affected ground group is therefore tied explicitly to the uninterrupted
    In1.Cu reference plane.  Vias remain outside the 20 x 12 mm back-side
    adhesive window; only top copper crosses that window.
    """
    gnd = net_objs["GND"]

    def dogbone(
        ref: str,
        pad: str,
        points: list[tuple[float, float]],
        via: tuple[float, float],
    ) -> None:
        add_polyline(board, gnd, F, [fp_pad(fps, ref, pad), *points, via], 0.20)
        add_via(board, gnd, via)

    # USB/low-speed edge groups outside the adhesive window.
    dogbone("R8", "2", [], (13.50, 22.50))
    dogbone("J6", "A12", [(9.35, 23.30)], (10.20, 22.80))
    dogbone("R3", "2", [], (2.80, 16.50))
    dogbone("R27", "2", [], (13.10, 22.00))
    # Both vias sit beneath their IC bodies.  They are tented and avoid the
    # locked USB crossover and the adjacent CH3 base resistor respectively.
    dogbone("U4", "2", [], (6.60, 19.50))
    dogbone("R18", "2", [], (40.30, 6.05))

    # MUX and its two VBEC decouplers share local ground stitches.
    u2_gnd = (45.00, 14.65)
    add_polyline(board, gnd, F,
                 [fp_pad(fps, "U2", "5"), u2_gnd, fp_pad(fps, "U2", "6")], 0.20)
    add_via(board, gnd, u2_gnd)
    decoupling_gnd = (45.55, 18.25)
    add_polyline(board, gnd, F,
                 [fp_pad(fps, "C14", "2"), decoupling_gnd,
                  fp_pad(fps, "C15", "2")], 0.20)
    add_via(board, gnd, decoupling_gnd)

    # U1 ground leaves under the package body.  The tented via is outside the
    # adhesive window and has no exposed solder land beneath the component.
    dogbone("U1", "7", [(20.10, 14.75)], (17.00, 15.00))

    # C7-C10 sit above the back-side tape.  A common top-side trunk exits at
    # the upper edge before changing layer, so the tape surface stays flat.
    cap_trunk_x = 25.40
    cap_via = (cap_trunk_x, 8.40)
    add_polyline(board, gnd, F, [cap_via, (cap_trunk_x, 17.70)], 0.20)
    for ref in ("C7", "C8", "C9", "C10"):
        pad = fp_pad(fps, ref, "2")
        add_polyline(board, gnd, F, [pad, (cap_trunk_x, pad[1])], 0.20)
    add_via(board, gnd, cap_via)

    # The fitted Cortex connector is over the tape window.  Join all of its
    # GND contacts on F.Cu and escape above the window before adding the via.
    j7_via = (35.00, 8.40)
    add_polyline(
        board,
        gnd,
        F,
        [fp_pad(fps, "J7", "3"), fp_pad(fps, "J7", "5"),
         fp_pad(fps, "J7", "9"), (35.00, fp_pad(fps, "J7", "9")[1]), j7_via],
        0.20,
    )
    add_via(board, gnd, j7_via)


def route_board(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT],
                net_objs: dict[str, pcbnew.NETINFO_ITEM]) -> None:
    # Lock only the topology-critical USB routes. Debug/reset and the Rev.1
    # programming-power additions are completed after the checked legacy SES
    # route is imported, because those parts do not exist in that session.
    # outside the no-via window, Freerouting can solve the remaining low-speed
    # nets without the local fan-out traps found in the 35/40 mm trials.
    route_usb(board, fps, net_objs)
    route_ground_escapes(board, fps, net_objs)

    # Explicit low-impedance J5 BEC feed to the servo connector. The In2 plane
    # carries the remaining BEC distribution.
    if "J4" in fps and "J5" in fps:
        for pin in ("2", "3"):
            p4 = next(p for p in fps["J4"].Pads() if p.GetNumber() == pin)
            p5 = next(p for p in fps["J5"].Pads() if p.GetNumber() == pin)
            name = p4.GetNetname()
            if name and name == p5.GetNetname():
                add_track(board, net_objs[name], F, mm_pos(p4.GetPosition()), mm_pos(p5.GetPosition()), 2.0)


def apply_design_minima(board: pcbnew.BOARD) -> None:
    """Restore the manufacturing minima after a standalone seed-board reload."""
    settings = board.GetDesignSettings()
    settings.m_MinClearance = iu(0.20)
    settings.m_TrackMinWidth = iu(0.15)
    settings.m_ViasMinSize = iu(0.45)
    settings.m_MinThroughDrill = iu(0.30)
    settings.m_CopperEdgeClearance = iu(0.40)


def normalize_cost_vias(board: pcbnew.BOARD) -> None:
    """Use JLCPCB's standard 0.30/0.45 mm through-via minimum.

    The checked Rev.1 route contains a few 0.20/0.45 mm vias.  Enlarging only
    the drill keeps every route and clearance unchanged while avoiding the
    high-precision-via surcharge.
    """
    minimum_drill = iu(0.30)
    minimum_diameter = iu(0.45)
    for item in board.GetTracks():
        if item.Type() != pcbnew.PCB_VIA_T:
            continue
        if item.GetDrillValue() < minimum_drill:
            item.SetDrill(minimum_drill)
        if item.GetWidth(F) < minimum_diameter:
            item.SetWidth(minimum_diameter)


def write_standard_stackup(path: Path) -> None:
    """Insert the generic non-controlled stack-up, idempotently."""
    text = path.read_text(encoding="utf-8")
    setup_marker = "\t(setup\n"
    if setup_marker not in text:
        raise RuntimeError(f"KiCad setup block not found in {path}")

    stackup_marker = "\t\t(stackup\n"
    start = text.find(stackup_marker)
    if start >= 0:
        depth = 0
        end = None
        for index in range(start, len(text)):
            if text[index] == "(":
                depth += 1
            elif text[index] == ")":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    if end < len(text) and text[end] == "\n":
                        end += 1
                    break
        if end is None:
            raise RuntimeError(f"unterminated KiCad stack-up block in {path}")
        text = text[:start] + STANDARD_STACKUP + text[end:]
    else:
        text = text.replace(setup_marker, setup_marker + STANDARD_STACKUP, 1)

    path.write_text(text, encoding="utf-8")


def board_pad(board: pcbnew.BOARD, ref: str, number: str) -> tuple[float, float]:
    footprint = board.FindFootprintByReference(ref)
    if footprint is None:
        raise RuntimeError(f"missing footprint {ref}")
    pads = [pad for pad in footprint.Pads() if pad.GetNumber() == number]
    if not pads:
        raise RuntimeError(f"{ref} has no pad {number}")
    return mm_pos(pads[0].GetPosition())


def complete_post_route(board: pcbnew.BOARD) -> None:
    """Close the two short branches intentionally left by Freerouting.

    The C3 ground pad sits in a small F.Cu pour island bounded by the
    LOGIC_RAW escape.  A short dog-bone stitches that island to the solid
    In1.Cu ground plane.  R24's VBEC pull-up is joined directly to the nearby
    U2 decoupling branch on F.Cu, avoiding the signal tracks on In2.Cu.
    """
    gnd = board.FindNet("GND")
    c3_gnd = board_pad(board, "C3", "2")
    c3_via = (c3_gnd[0] - 0.40, c3_gnd[1])
    add_polyline(board, gnd, F, [c3_gnd, c3_via], 0.20)
    add_via(board, gnd, c3_via)

    add_polyline(
        board,
        board.FindNet("VBEC"),
        F,
        [board_pad(board, "R24", "1"), board_pad(board, "C15", "1")],
        0.20,
    )


def complete_autoroute(board: pcbnew.BOARD) -> None:
    """Apply the independently audited completion of the checked SES route."""
    # Move the large bulk capacitor far enough inside Edge.Cuts for its entire
    # assembly courtyard.  Reconnect only the short local VBEC dog-bone that
    # the checked session created for the seed position.
    c1 = board.FindFootprintByReference("C1")
    if c1 is None:
        raise RuntimeError("missing footprint C1")
    c1.SetPosition(v(35.50, 21.30))
    for item in list(board.GetTracks()):
        if isinstance(item, pcbnew.PCB_VIA):
            continue
        if item.GetNetname() != "VBEC" or item.GetLayer() != F:
            continue
        start, end = mm_pos(item.GetStart()), mm_pos(item.GetEnd())
        xs, ys = (start[0], end[0]), (start[1], end[1])
        if (
            min(xs) >= 32.90 and max(xs) <= 35.65
            and min(ys) >= 21.80 and max(ys) <= 22.00
        ):
            board.Remove(item)
    add_polyline(
        board,
        board.FindNet("VBEC"),
        F,
        [(32.9625, 21.30), (33.45, 21.60), (35.5987, 21.95)],
        0.20,
    )

    # Join the USB connector/VBUS detector tree to the ESD-array island.  The
    # compact 0.45/0.20 mm dog-bone stays clear of the differential pair.
    vbus = board.FindNet("USB_VBUS_SENSE_ONLY")
    vbus_via = (8.95, 14.95)
    existing_vbus_via = (7.3741, 17.3397)
    add_polyline(board, vbus, F, [(8.63, 15.10), vbus_via], 0.20)
    add_via(board, vbus, vbus_via)
    add_polyline(board, vbus, IN2, [vbus_via, existing_vbus_via], 0.20)

    # Escape the ADC input under U1, traverse B.Cu without adding vias inside
    # the adhesive window, and return below the window at the divider/filter.
    sense = board.FindNet("VBEC_SENSE")
    sense_upper = (17.35, 10.15)
    sense_lower = (26.50, 20.50)
    add_polyline(board, sense, F, [board_pad(board, "U1", "15"), sense_upper], 0.20)
    add_via(board, sense, sense_upper)
    add_polyline(
        board,
        sense,
        B,
        [sense_upper, (16.50, 11.00), (16.50, 17.00),
         (25.80, 17.00), (25.80, 20.00), sense_lower],
        0.20,
    )
    add_via(board, sense, sense_lower)
    add_polyline(
        board, sense, F,
        [sense_lower, (25.90, 21.10), board_pad(board, "C6", "1")], 0.20,
    )

    # Stitch every isolated F.Cu GND pour island to the uninterrupted In1.Cu
    # reference plane.  The x=40.25 mm stitch is just outside the tape window.
    gnd = board.FindNet("GND")
    for point in (
        (17.05, 14.80), (40.25, 14.00), (4.75, 15.35),
        (7.75, 12.40), (8.90, 13.30), (7.50, 9.60),
        (9.75, 8.85), (2.15, 6.65), (16.90, 6.50),
    ):
        add_via(board, gnd, point)

    for ref, via_point in (("R18", (31.90, 5.50)), ("C16", (17.70, 6.70))):
        add_polyline(board, gnd, F, [board_pad(board, ref, "2"), via_point], 0.20)
        add_via(board, gnd, via_point)

    # R15 uses a conventional dog-bone immediately beyond the land edge; its
    # centre is not in the component pad, avoiding solder-wicking via-in-pad.
    r15_via = (14.275, 6.550)
    add_polyline(board, gnd, F, [board_pad(board, "R15", "2"), r15_via], 0.20)
    add_via(board, gnd, r15_via)

    # R21 opens directly into the already-stitched U2-side F.Cu island.  A via
    # is intentionally omitted at the boundary of the no-via window.
    add_polyline(board, gnd, F, [board_pad(board, "R21", "2"), (20.45, 6.35)], 0.20)

    # Move the two high-frequency 100 nF MCU capacitors from their
    # autorouter-compatible seed shelves to the top side immediately beside the
    # VDD/VDDA and VREF+/VSS pins.  C8/C10 are bulk capacitors and stay on their
    # original shelves.  Top-side parts and F.Cu are permitted over the
    # back-side adhesive area; vias and bottom-side features remain prohibited.
    old_cap_pads = {
        ref: board_pad(board, ref, "1") for ref in ("C7", "C9")
    }
    for item in list(board.GetTracks()):
        if isinstance(item, pcbnew.PCB_VIA) or item.GetNetname() != "+3V3":
            continue
        endpoints = (mm_pos(item.GetStart()), mm_pos(item.GetEnd()))
        if any(dist(endpoint, pad) < 0.01 for endpoint in endpoints for pad in old_cap_pads.values()):
            board.Remove(item)

    local_caps = {
        "C7": (21.25, 13.25, 90.0),
        "C9": (21.25, 15.50, 270.0),
    }
    for ref, (x, y, angle) in local_caps.items():
        footprint = board.FindFootprintByReference(ref)
        if footprint is None:
            raise RuntimeError(f"missing footprint {ref}")
        footprint.SetPosition(v(x, y))
        footprint.SetOrientationDegrees(angle)

    logic = board.FindNet("+3V3")
    add_polyline(board, logic, F,
                 [board_pad(board, "U1", "6"), board_pad(board, "C7", "1")], 0.20)
    add_polyline(board, logic, F,
                 [board_pad(board, "C7", "1"), board_pad(board, "C9", "1")], 0.20)
    c9_ground_via = (21.25, 18.75)
    add_polyline(board, gnd, F,
                 [board_pad(board, "C9", "2"), c9_ground_via], 0.20)
    add_via(board, gnd, c9_ground_via)


def remove_duplicate_routing(board: pcbnew.BOARD) -> int:
    """Remove exact same-net track/via duplicates left by SES round-tripping."""
    seen: set[tuple[object, ...]] = set()
    duplicates: list[object] = []
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA):
            point = item.GetPosition()
            key = (
                "via", item.GetNetCode(), point.x, point.y,
                item.TopLayer(), item.BottomLayer(), item.GetDrillValue(),
                item.GetWidth(pcbnew.F_Cu),
            )
        else:
            start = (item.GetStart().x, item.GetStart().y)
            end = (item.GetEnd().x, item.GetEnd().y)
            key = (
                "track", item.GetNetCode(), item.GetLayer(), item.GetWidth(),
                min(start, end), max(start, end),
            )
        if key in seen:
            duplicates.append(item)
        else:
            seen.add(key)
    for item in duplicates:
        board.Delete(item)
    return len(duplicates)


REVISION_PLACEMENT_REFS = {
    "D1", "D2", "C18", "J7", "SW1", "SW2", "U5",
    "R22", "R23", "R24", "R26", "R27", "TP2",
}


def ensure_board_net(board: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    net = board.FindNet(name)
    if net is None:
        net = pcbnew.NETINFO_ITEM(board, name)
        board.Add(net)
    return net


def configure_footprint(fp: pcbnew.FOOTPRINT, comp: Component) -> None:
    fp.SetReference(comp.ref)
    fp.SetValue(comp.value)
    footprint_fields = fp.GetFieldsText()
    footprint_fields.update(comp.fields)
    fp.SetFields(footprint_fields)
    for field_name in comp.fields:
        field = fp.GetField(field_name)
        field.SetVisible(False)
        field.SetLayer(pcbnew.F_Fab)
    fp.SetPath(pcbnew.KIID_PATH(comp.path))
    fp.SetDNP(comp.dnp)
    fp.SetExcludedFromBOM(comp.ref.startswith(("TP", "H")))
    fp.SetExcludedFromPosFiles(comp.ref.startswith(("TP", "H")))
    if comp.ref in {"J1", "J2", "J3", "J4", "J5"}:
        fp.SetDNP(True)
    fp.Reference().SetVisible(False)
    fp.Value().SetVisible(False)


def remove_routing_for_nets(board: pcbnew.BOARD, names: set[str]) -> None:
    for item in list(board.GetTracks()):
        if item.GetNetname() in names:
            board.Remove(item)


def remove_old_vbec_pad_escapes(board: pcbnew.BOARD, fps: dict[str, pcbnew.FOOTPRINT]) -> None:
    """Remove legacy VBEC copper that ended on pads moved to LOGIC_RAW/EN."""
    targets = [
        fps[ref].FindPadByNumber(pin)
        for ref, pin in (
            ("U3", "3"), ("C3", "1"), ("C14", "1"), ("C15", "1"),
            ("U2", "13"), ("U2", "14"),
        )
    ]
    for item in list(board.GetTracks()):
        if item.GetNetname() != "VBEC":
            continue
        remove = False
        for pad in targets:
            for layer in (F, IN1, IN2, B):
                if not pad.IsOnLayer(layer) or not item.IsOnLayer(layer):
                    continue
                try:
                    if pad.GetEffectiveShape(layer).Collide(item.GetEffectiveShape(layer), 0):
                        remove = True
                        break
                except Exception:
                    pass
            if remove:
                break
        if remove:
            board.Remove(item)


def update_revision_graphics(board: pcbnew.BOARD) -> None:
    obsolete = {
        "kart_bridge_board", "JPBB-01  Rev.2", "JPBB-01 Rev.2",
        "ADHESIVE 20x12 (B)", "SWD  1", "RST", "BOOT",
    }
    for drawing in list(board.GetDrawings()):
        if isinstance(drawing, pcbnew.PCB_TEXT) and drawing.GetText() in obsolete:
            board.Remove(drawing)
    add_text(board, "SWD  1", 27.5, 5.95, 0.75)
    add_text(board, "kart_bridge_board", 32.35, 12.5, 0.62, angle=90)
    add_text(board, "JPBB-01 Rev.2", 33.35, 12.5, 0.62, angle=90)
    add_text(board, "ADHESIVE 20x12 (B)", 34.35, 12.5, 0.58, angle=90)
    add_text(board, "RST", 3.3, 8.55, 0.72)
    add_text(board, "BOOT", 46.7, 4.75, 0.72)


def migrate_legacy_board(
    comps: dict[str, Component],
    nets: dict[str, list[tuple[str, str]]],
) -> tuple[pcbnew.BOARD, dict[str, pcbnew.FOOTPRINT], dict[str, pcbnew.NETINFO_ITEM]]:
    """Preserve the audited Rev.1 route while applying the programming revision."""
    if not LEGACY_BOARD.exists():
        raise RuntimeError(f"checked routed template is missing: {LEGACY_BOARD}")
    board = pcbnew.LoadBoard(str(LEGACY_BOARD))
    apply_design_minima(board)

    # Delete obsolete mechanical rule areas before removing their footprints;
    # this ordering avoids dangling SWIG references in KiCad's Python wrapper.
    obsolete_zones = [
        zone for zone in board.Zones()
        if zone.GetZoneName() in {"H1_CLEARANCE", "H2_CLEARANCE"}
    ]
    for zone in obsolete_zones:
        board.Delete(zone)
    # Delete obsolete mechanical holes and replace the old bare-pad J7.
    obsolete_footprints = [
        board.FindFootprintByReference(ref) for ref in ("H1", "H2", "J7")
    ]
    for fp in obsolete_footprints:
        if fp is not None:
            board.Delete(fp)

    net_objs = {name: ensure_board_net(board, name) for name in nets}
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    for ref, comp in comps.items():
        if not comp.footprint:
            continue
        fp = fps.get(ref)
        if fp is None:
            fp = load_footprint(board, comp.footprint)
            board.Add(fp)
            fps[ref] = fp
        configure_footprint(fp, comp)
        if ref in REVISION_PLACEMENT_REFS:
            x, y, angle = PLACEMENTS[ref]
            fp.SetPosition(v(x, y))
            fp.SetOrientationDegrees(angle)

    # Reassign every pad from the generated netlist. This updates U1/U2/U3 and
    # the USB connector without disturbing unrelated, already-audited routing.
    for name, nodes in nets.items():
        net = net_objs[name]
        for ref, pin in nodes:
            if ref not in fps:
                continue
            pads = [pad for pad in fps[ref].Pads() if pad.GetNumber() == pin]
            if not pads:
                raise RuntimeError(f"{ref}: footprint {comps[ref].footprint} has no pad {pin}")
            for pad in pads:
                pad.SetNet(net)

    # Carry the proven USB-VBUS tree onto its truthful new net name.
    usb_vbus = net_objs["USB_VBUS"]
    for item in board.GetTracks():
        if item.GetNetname() == "USB_VBUS_SENSE_ONLY":
            item.SetNet(usb_vbus)

    remove_old_vbec_pad_escapes(board, fps)
    remove_routing_for_nets(
        board,
        {
            "LOGIC_RAW", "MUX_ENABLE_VBEC", "BOOT_REQ",
            "MCU_SERVO_PWM_GPIO", "MCU_ESC_PWM_GPIO",
            "MCU_SERVO_PWM", "MCU_ESC_PWM", "SWDIO", "SWCLK", "NRST",
        },
    )
    update_revision_graphics(board)
    return board, fps, net_objs


def route_revision_power(
    board: pcbnew.BOARD,
    fps: dict[str, pcbnew.FOOTPRINT],
    nets: dict[str, pcbnew.NETINFO_ITEM],
) -> None:
    # D1 anode joins the vehicle VBEC plane; D2 anode joins the existing raw
    # USB VBUS tree. Both vias are below the adhesive window.
    d1 = fp_pad(fps, "D1", "2")
    d1_via = (28.0, 18.9)
    add_polyline(board, nets["VBEC"], F, [d1, d1_via], 0.40)
    add_via(board, nets["VBEC"], d1_via)

    d2 = fp_pad(fps, "D2", "2")
    d2_via = (31.0, 18.9)
    old_vbus_via = (7.3741, 17.3397)
    add_polyline(board, nets["USB_VBUS"], F, [d2, d2_via], 0.40)
    add_via(board, nets["USB_VBUS"], d2_via)
    add_polyline(
        board, nets["USB_VBUS"], B,
        [d2_via, (19.0, 19.2), (8.0, 19.2), old_vbus_via],
        0.40,
    )

    # The BOOT switch's +3V3 end reaches the bottom power plane outside the
    # tape window. J7 VTref is routed on F.Cu to the existing TP2 +3V3 node.
    boot_supply = fp_pad(fps, "SW2", "1")
    boot_via = (48.2, 9.6)
    add_polyline(board, nets["+3V3"], F, [boot_supply, boot_via], 0.35)
    add_via(board, nets["+3V3"], boot_via)
    debug_via = (19.2, 18.9)
    add_polyline(
        board, nets["+3V3"], F,
        [fp_pad(fps, "J7", "1"), (29.55, 17.2), (21.0, 17.2), debug_via],
        0.35,
    )
    add_via(board, nets["+3V3"], debug_via)
    tp2 = fp_pad(fps, "TP2", "1")
    tp2_via = (25.8, 24.2)
    add_polyline(board, nets["+3V3"], F, [tp2, tp2_via], 0.35)
    add_via(board, nets["+3V3"], tp2_via)


def route_revision_debug(
    board: pcbnew.BOARD,
    fps: dict[str, pcbnew.FOOTPRINT],
    nets: dict[str, pcbnew.NETINFO_ITEM],
) -> None:
    swdio = nets["SWDIO"]
    swdio_mcu, swdio_j7 = fp_pad(fps, "U1", "35"), fp_pad(fps, "J7", "2")
    swdio_left, swdio_right = (10.5, 16.7), (19.0, 18.0)
    add_polyline(board, swdio, F, [swdio_mcu, swdio_left], 0.20)
    add_via(board, swdio, swdio_left)
    add_polyline(board, swdio, IN2, [swdio_left, (11.5, 17.7), swdio_right], 0.20)
    add_via(board, swdio, swdio_right)
    add_polyline(board, swdio, F,
                 [swdio_right, (21.5, 16.0), (24.0, 16.0), swdio_j7], 0.20)

    swclk = nets["SWCLK"]
    swclk_mcu, swclk_j7 = fp_pad(fps, "U1", "36"), fp_pad(fps, "J7", "4")
    swclk_left, swclk_top = (9.7, 15.75), (19.2, 8.0)
    add_polyline(board, swclk, F, [swclk_mcu, swclk_left], 0.20)
    add_via(board, swclk, swclk_left)
    add_polyline(board, swclk, IN2,
                 [swclk_left, (9.7, 8.0), swclk_top], 0.20)
    add_via(board, swclk, swclk_top)
    add_polyline(board, swclk, F,
                 [swclk_top, (23.5, 8.0), (23.5, swclk_j7[1]), swclk_j7], 0.20)
    r26, r27 = fp_pad(fps, "R26", "2"), fp_pad(fps, "R27", "1")
    add_polyline(board, swclk, F,
                 [swclk_mcu, (10.8, 16.4), (10.8, 17.8), r26, r27], 0.20)

    nrst = nets["NRST"]
    mcu, j7 = fp_pad(fps, "U1", "10"), fp_pad(fps, "J7", "10")
    add_polyline(board, nrst, F, [mcu, (21.0, 11.25), (22.5, j7[1]), j7], 0.20)
    cap, pull, button = (
        fp_pad(fps, "C11", "1"), fp_pad(fps, "R10", "2"), fp_pad(fps, "SW1", "1")
    )
    add_polyline(
        board, nrst, F,
        [button, cap, (6.50, 10.25), (7.25, 11.00), (8.75, 11.00),
         (9.50, 10.25), pull, (10.00, 9.75), (12.25, 9.75),
         (13.75, 11.25), mcu], 0.20,
    )


def route_revision_logic_raw(
    board: pcbnew.BOARD,
    fps: dict[str, pcbnew.FOOTPRINT],
    nets: dict[str, pcbnew.NETINFO_ITEM],
) -> None:
    """Route the diode-OR raw logic supply as a short, deterministic tree.

    The only B.Cu segment sits at y=19.2 mm, below the 20x12 mm adhesive
    window (y=6.5..18.5 mm).  This keeps the tape surface free of vias and
    avoids cutting a long channel through the In2 VBEC plane.
    """
    net = nets["LOGIC_RAW"]
    d1, d2, bulk = (
        fp_pad(fps, "D1", "1"), fp_pad(fps, "D2", "1"),
        fp_pad(fps, "C18", "1"),
    )
    # Schottky cathodes and local bulk capacitor.
    add_polyline(board, net, F, [d2, d1, (bulk[0], d1[1]), bulk], 0.40)

    left_via, right_via = (24.0, 19.2), (40.6, 19.2)
    add_polyline(board, net, F, [bulk, left_via], 0.40)
    add_via(board, net, left_via)
    add_polyline(board, net, B, [left_via, right_via], 0.40)
    add_via(board, net, right_via)

    c14, c15, c3 = (
        fp_pad(fps, "C14", "1"), fp_pad(fps, "C15", "1"),
        fp_pad(fps, "C3", "1"),
    )
    u3, u2 = fp_pad(fps, "U3", "3"), fp_pad(fps, "U2", "13")
    # Decouplers are entered from their lower edge; the LDO and mux supply
    # pins are approached from the right, clear of their adjacent pads.
    add_polyline(board, net, F,
                 [right_via, (40.6, 17.1), c15, c14], 0.40)
    add_polyline(board, net, F,
                 [right_via, (43.8, 18.4), c3], 0.40)
    add_polyline(board, net, F,
                 [c3, (45.2, 15.9), (45.2, 12.3), u3], 0.40)
    add_polyline(board, net, F,
                 [(45.2, 12.3), (44.8, 11.2), u2], 0.40)


def route_revision_signals(
    board: pcbnew.BOARD,
    fps: dict[str, pcbnew.FOOTPRINT],
    nets: dict[str, pcbnew.NETINFO_ITEM],
) -> None:
    router = GridRouter(board, fps, nets)
    pads = collect_pads(fps)
    for name, width in (
        # Route ESC first: its U2 pad has the tighter escape channel.  The
        # servo pair still fits after it, while the reverse order closes that
        # channel at the selected 0.20 mm/clearance grid.
        ("MCU_ESC_PWM_GPIO", 0.20), ("MCU_ESC_PWM", 0.20),
        ("MCU_SERVO_PWM_GPIO", 0.20), ("MCU_SERVO_PWM", 0.20),
        ("MUX_ENABLE_VBEC", 0.20), ("BOOT_REQ", 0.20),
    ):
        router.route_net(name, pads[name], width)

    # R24 is the only new VBEC control branch. It can enter the uninterrupted
    # In2 VBEC plane through a short dog-bone outside the tape window.
    enable_supply = fp_pad(fps, "R24", "1")
    enable_via = (41.1, 16.1)
    add_polyline(board, nets["VBEC"], F, [enable_supply, enable_via], 0.35)
    add_via(board, nets["VBEC"], enable_via)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and route kart_bridge_board")
    parser.add_argument(
        "--seed-only", action="store_true",
        help="write the 60x30 seed board and DSN, but do not import the SES route",
    )
    args = parser.parse_args()
    export_netlist()
    comps, nets = parse_netlist()
    assign_passive_placements(comps, nets)
    missing = [ref for ref, comp in comps.items() if comp.footprint and ref not in PLACEMENTS]
    if missing:
        raise SystemExit(f"no placement for: {missing}")
    board, fps, net_objs = make_board(comps, nets)
    decorate(board, net_objs)
    route_board(board, fps, net_objs)
    footprint_count, net_count = len(fps), len(net_objs)
    AUTOROUTE_DIR.mkdir(parents=True, exist_ok=True)
    apply_design_minima(board)
    # Serialize before zone filling.  KiCad's standalone Python API can retain
    # stale SWIG references after footprint loading; reloading makes the seed
    # fill deterministic and avoids a native crash.
    pcbnew.SaveBoard(str(SEED_BOARD), board)
    write_standard_stackup(SEED_BOARD)
    board = pcbnew.LoadBoard(str(SEED_BOARD))
    apply_design_minima(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(SEED_BOARD), board)
    write_standard_stackup(SEED_BOARD)
    board = pcbnew.LoadBoard(str(SEED_BOARD))
    apply_design_minima(board)
    if not pcbnew.ExportSpecctraDSN(board, str(DSN_PATH)):
        raise SystemExit(f"failed to export Specctra DSN: {DSN_PATH}")
    if args.seed_only:
        print(f"Generated autoroute seed {SEED_BOARD} and {DSN_PATH}")
        return
    if not SESSION_PATH.exists():
        raise SystemExit(f"checked autoroute session is missing: {SESSION_PATH}")
    if not pcbnew.ImportSpecctraSES(board, str(SESSION_PATH)):
        raise SystemExit(f"failed to import Specctra session: {SESSION_PATH}")
    duplicate_count = remove_duplicate_routing(board)
    if duplicate_count:
        print(f"removed {duplicate_count} duplicate routing item(s)", flush=True)
    complete_post_route(board)
    normalize_cost_vias(board)
    apply_design_minima(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.BuildConnectivity()
    unconnected = board.GetConnectivity().GetUnconnectedCount(False)
    if unconnected:
        raise SystemExit(
            f"routed board still has {unconnected} unconnected item(s); "
            "the checked session/post-route completion must be updated"
        )
    pcbnew.SaveBoard(str(BOARD_PATH), board)
    write_standard_stackup(BOARD_PATH)
    # The standalone pcbnew API can normalize the sibling project file while
    # importing the SES session.  Reapply our generated net classes last so a
    # one-command board rebuild remains deterministic.
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_project.py")], check=True)
    print(
        f"Generated {BOARD_PATH}: {footprint_count} footprints, {net_count} nets, "
        f"{len(board.GetTracks())} tracks/vias, {len(board.Zones())} zones, "
        f"unconnected={unconnected}"
    )
    if unconnected:
        raise SystemExit(f"generated board has {unconnected} unconnected item(s)")


if __name__ == "__main__":
    main()
