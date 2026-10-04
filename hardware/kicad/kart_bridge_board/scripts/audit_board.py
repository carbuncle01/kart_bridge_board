#!/usr/bin/env python3
"""Independent manufacturability audit for kart_bridge_board.

Run this script with KiCad's bundled Python interpreter, for example:

    /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9 \
        scripts/audit_board.py

The checker deliberately does not call the board generator.  It reads the saved
``.kicad_pcb`` file and exits non-zero when any required invariant is violated.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import DefaultDict, Dict, List, Optional, Sequence, Tuple

try:
    import pcbnew
except ImportError as exc:  # pragma: no cover - only reached with the wrong Python
    raise SystemExit(
        "pcbnew is unavailable. Run this script with KiCad's bundled Python "
        "interpreter (see the command in the module docstring)."
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BOARD = ROOT / "kart_bridge_board.kicad_pcb"

EXPECTED_WIDTH_MM = 60.0
EXPECTED_HEIGHT_MM = 30.0
OUTLINE_TOLERANCE_MM = 0.01
GEOMETRY_TOLERANCE_MM = 0.005
TAPE_RECT_MM = (22.0, 9.0, 42.0, 21.0)  # x0, y0, x1, y1: 20 x 12 mm
WIDE_POWER_MIN_MM = 2.0
USB_TRACK_WIDTH_MM = 0.15
USB_MAX_LENGTH_MISMATCH_MM = 2.0


def mm(value: int) -> float:
    return float(pcbnew.ToMM(value))


def iu(value_mm: float) -> int:
    return int(pcbnew.FromMM(value_mm))


def point_text(point: "pcbnew.VECTOR2I") -> str:
    return f"({mm(point.x):.3f}, {mm(point.y):.3f}) mm"


class Report:
    """Bounded-detail error collector with stable, CI-friendly output."""

    def __init__(self, max_details: int) -> None:
        self.max_details = max_details
        self.order: List[str] = []
        self.counts: DefaultDict[str, int] = defaultdict(int)
        self.examples: DefaultDict[str, List[str]] = defaultdict(list)
        self.notes: List[str] = []

    def check(self, category: str) -> None:
        if category not in self.order:
            self.order.append(category)

    def add(self, category: str, message: str, count: int = 1) -> None:
        self.check(category)
        self.counts[category] += count
        if len(self.examples[category]) < self.max_details:
            self.examples[category].append(message)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def emit(self, board_path: Path) -> None:
        print(f"Board: {board_path}")
        for note in self.notes:
            print(f"INFO: {note}")
        print()
        for category in self.order:
            count = self.counts[category]
            if count == 0:
                print(f"[PASS] {category}")
                continue
            print(f"[FAIL] {category}: {count}")
            for message in self.examples[category]:
                print(f"  - {message}")
            omitted = count - len(self.examples[category])
            if omitted > 0:
                print(f"  - ... {omitted} additional violation(s) omitted")
        print()
        if self.total:
            print(f"BOARD AUDIT: FAIL ({self.total} violation(s))")
        else:
            print("BOARD AUDIT: PASS")


@dataclass
class CopperObject:
    uid: int
    item: object
    layer: int
    shape: object
    net_code: int
    net_name: str
    clearance_iu: int
    label: str

    @property
    def bbox(self):
        return self.shape.BBox()


def copper_layers(board: "pcbnew.BOARD") -> List[int]:
    count = board.GetCopperLayerCount()
    if count < 2:
        return [pcbnew.F_Cu]
    layers = [pcbnew.F_Cu]
    layers.extend(4 + 2 * index for index in range(count - 2))
    layers.append(pcbnew.B_Cu)
    return layers


def load_net_clearances(
    board_path: Path,
    board: "pcbnew.BOARD",
    project_path: Optional[Path] = None,
) -> Tuple[float, Dict[str, float]]:
    """Return default clearance and per-net clearances from the sibling project."""

    fallback = max(0.0, mm(board.GetDesignSettings().m_MinClearance))
    project_path = project_path or board_path.with_suffix(".kicad_pro")
    if not project_path.exists():
        return fallback, {}

    try:
        settings = json.loads(project_path.read_text(encoding="utf-8"))["net_settings"]
    except (OSError, ValueError, KeyError, TypeError):
        return fallback, {}

    classes = {
        entry.get("name", ""): float(entry.get("clearance", fallback))
        for entry in settings.get("classes", [])
        if entry.get("name")
    }
    default = classes.get("Default", fallback)
    assignments: Dict[str, float] = {}

    explicit = settings.get("netclass_assignments")
    if isinstance(explicit, dict):
        for net_name, class_name in explicit.items():
            if class_name in classes:
                assignments[str(net_name)] = classes[class_name]

    patterns = settings.get("netclass_patterns") or []
    net_names = {pad.GetNetname() for pad in board.GetPads() if pad.GetNetname()}
    net_names.update(track.GetNetname() for track in board.GetTracks() if track.GetNetname())
    for entry in patterns:
        pattern = str(entry.get("pattern", ""))
        class_name = str(entry.get("netclass", ""))
        if not pattern or class_name not in classes:
            continue
        for net_name in net_names:
            if fnmatch.fnmatchcase(net_name, pattern):
                assignments[net_name] = classes[class_name]

    return default, assignments


def describe_pad(pad: "pcbnew.PAD") -> str:
    parent = pad.GetParentFootprint()
    ref = parent.GetReference() if parent else "?"
    number = pad.GetNumber() or "<unnumbered>"
    return f"pad {ref}.{number} ({pad.GetNetname() or 'no-net'}) at {point_text(pad.GetPosition())}"


def describe_track(track: object) -> str:
    if isinstance(track, pcbnew.PCB_VIA):
        return f"via ({track.GetNetname() or 'no-net'}) at {point_text(track.GetPosition())}"
    return (
        f"track ({track.GetNetname() or 'no-net'}) {pcbnew.LayerName(track.GetLayer())} "
        f"{point_text(track.GetStart())} to {point_text(track.GetEnd())}, "
        f"width {mm(track.GetWidth()):.3f} mm"
    )


def collect_copper_objects(
    board: "pcbnew.BOARD",
    board_path: Path,
    project_path: Optional[Path] = None,
) -> Tuple[List[CopperObject], float]:
    default_clearance, per_net = load_net_clearances(board_path, board, project_path)
    objects: List[CopperObject] = []
    uid = 0
    layers = copper_layers(board)

    for pad in board.GetPads():
        if pad.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            continue
        uid += 1
        label = describe_pad(pad)
        clearance = per_net.get(pad.GetNetname(), default_clearance)
        for layer in layers:
            if not pad.IsOnLayer(layer):
                continue
            try:
                shape = pad.GetEffectiveShape(layer)
                if shape.BBox().GetWidth() <= 0 or shape.BBox().GetHeight() <= 0:
                    continue
            except Exception:
                continue
            objects.append(
                CopperObject(
                    uid,
                    pad,
                    layer,
                    shape,
                    pad.GetNetCode(),
                    pad.GetNetname(),
                    iu(clearance),
                    label,
                )
            )

    for track in board.GetTracks():
        uid += 1
        label = describe_track(track)
        clearance = per_net.get(track.GetNetname(), default_clearance)
        for layer in layers:
            if not track.IsOnLayer(layer):
                continue
            try:
                shape = track.GetEffectiveShape(layer)
                if shape.BBox().GetWidth() <= 0 or shape.BBox().GetHeight() <= 0:
                    continue
            except Exception:
                continue
            objects.append(
                CopperObject(
                    uid,
                    track,
                    layer,
                    shape,
                    track.GetNetCode(),
                    track.GetNetname(),
                    iu(clearance),
                    label,
                )
            )

    return objects, default_clearance


def boxes_may_collide(a, b, clearance: int) -> bool:
    return not (
        a.GetRight() + clearance < b.GetLeft()
        or b.GetRight() + clearance < a.GetLeft()
        or a.GetBottom() + clearance < b.GetTop()
        or b.GetBottom() + clearance < a.GetTop()
    )


def audit_outline(board: "pcbnew.BOARD", report: Report) -> Tuple[float, float, float, float]:
    category = f"{EXPECTED_WIDTH_MM:g} x {EXPECTED_HEIGHT_MM:g} mm closed rectangular outline"
    report.check(category)
    edges = [drawing for drawing in board.GetDrawings() if drawing.GetLayer() == pcbnew.Edge_Cuts]
    if len(edges) != 4:
        report.add(category, f"expected four Edge.Cuts segments, found {len(edges)}")

    points: List[Tuple[int, int]] = []
    degrees: DefaultDict[Tuple[int, int], int] = defaultdict(int)
    for edge in edges:
        try:
            start = edge.GetStart()
            end = edge.GetEnd()
        except Exception:
            report.add(category, f"unsupported Edge.Cuts item: {type(edge).__name__}")
            continue
        a = (start.x, start.y)
        b = (end.x, end.y)
        points.extend((a, b))
        degrees[a] += 1
        degrees[b] += 1
        if start.x != end.x and start.y != end.y:
            report.add(category, f"non-orthogonal outline segment {point_text(start)} to {point_text(end)}")

    if not points:
        report.add(category, "Edge.Cuts is empty")
        return 0.0, 0.0, EXPECTED_WIDTH_MM, EXPECTED_HEIGHT_MM

    x0 = mm(min(x for x, _ in points))
    y0 = mm(min(y for _, y in points))
    x1 = mm(max(x for x, _ in points))
    y1 = mm(max(y for _, y in points))
    width = x1 - x0
    height = y1 - y0
    if abs(width - EXPECTED_WIDTH_MM) > OUTLINE_TOLERANCE_MM or abs(height - EXPECTED_HEIGHT_MM) > OUTLINE_TOLERANCE_MM:
        report.add(
            category,
            f"outline is {width:.3f} x {height:.3f} mm "
            f"(expected {EXPECTED_WIDTH_MM:.3f} x {EXPECTED_HEIGHT_MM:.3f} mm)",
        )
    open_vertices = [point for point, degree in degrees.items() if degree != 2]
    if open_vertices:
        report.add(category, f"outline is not closed; {len(open_vertices)} vertex/vertices do not have degree 2")
    return x0, y0, x1, y1


def audit_footprints(board: "pcbnew.BOARD", report: Report) -> None:
    side_category = "all footprints on Top (F.Cu)"
    overlap_category = "footprint courtyard overlap"
    report.check(side_category)
    report.check(overlap_category)

    footprints = list(board.GetFootprints())
    for footprint in footprints:
        if footprint.GetLayer() != pcbnew.F_Cu:
            report.add(
                side_category,
                f"{footprint.GetReference()} is on {pcbnew.LayerName(footprint.GetLayer())}",
            )

    for index, first in enumerate(footprints):
        first_layer = pcbnew.F_CrtYd if first.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd
        first_courtyard = first.GetCourtyard(first_layer)
        if first_courtyard.IsEmpty():
            continue
        for second in footprints[index + 1 :]:
            if first.GetLayer() != second.GetLayer():
                continue
            second_layer = pcbnew.F_CrtYd if second.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd
            second_courtyard = second.GetCourtyard(second_layer)
            if second_courtyard.IsEmpty():
                continue
            if first_courtyard.Collide(second_courtyard, 0):
                report.add(
                    overlap_category,
                    f"{first.GetReference()} overlaps {second.GetReference()}",
                )


def audit_courtyard_edge(
    board: "pcbnew.BOARD",
    outline: Tuple[float, float, float, float],
    report: Report,
) -> None:
    """Require assembly courtyards inside the board except intentional overhangs."""
    category = "component courtyards inside board edge"
    report.check(category)
    x0, y0, x1, y1 = outline
    # J6 intentionally overhangs the board edge for cable access.
    allowed_overhang = {"J6"}
    for footprint in board.GetFootprints():
        if footprint.GetReference() in allowed_overhang:
            continue
        layer = pcbnew.F_CrtYd if footprint.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd
        courtyard = footprint.GetCourtyard(layer)
        if courtyard.IsEmpty():
            continue
        box = courtyard.BBox()
        left, top, right, bottom = map(
            mm, (box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom())
        )
        if (
            left < x0 - GEOMETRY_TOLERANCE_MM
            or top < y0 - GEOMETRY_TOLERANCE_MM
            or right > x1 + GEOMETRY_TOLERANCE_MM
            or bottom > y1 + GEOMETRY_TOLERANCE_MM
        ):
            report.add(
                category,
                f"{footprint.GetReference()} courtyard is "
                f"({left:.3f}, {top:.3f}) to ({right:.3f}, {bottom:.3f}) mm",
            )


def audit_copper_clearance(objects: Sequence[CopperObject], report: Report) -> None:
    category = "different-net pad/track/via copper clearance"
    report.check(category)
    by_layer: DefaultDict[int, List[CopperObject]] = defaultdict(list)
    for obj in objects:
        by_layer[obj.layer].append(obj)

    already_reported = set()
    for layer, layer_objects in by_layer.items():
        layer_objects.sort(key=lambda obj: obj.bbox.GetLeft())
        for index, first in enumerate(layer_objects):
            first_box = first.bbox
            for second in layer_objects[index + 1 :]:
                clearance = max(first.clearance_iu, second.clearance_iu)
                if second.bbox.GetLeft() > first_box.GetRight() + clearance:
                    break
                if first.net_code == second.net_code:
                    continue
                pair = (min(first.uid, second.uid), max(first.uid, second.uid))
                if pair in already_reported:
                    continue
                if not boxes_may_collide(first_box, second.bbox, clearance):
                    continue
                if first.shape.Collide(second.shape, clearance):
                    already_reported.add(pair)
                    report.add(
                        category,
                        f"{first.label} versus {second.label} on {pcbnew.LayerName(layer)} "
                        f"(required {mm(clearance):.3f} mm)",
                    )


def audit_edge_clearance(
    board: "pcbnew.BOARD",
    objects: Sequence[CopperObject],
    outline: Tuple[float, float, float, float],
    report: Report,
    project_path: Optional[Path] = None,
) -> None:
    category = "copper intrusion into Edge.Cuts clearance"
    report.check(category)
    x0, y0, x1, y1 = outline
    clearance_mm = max(0.0, mm(board.GetDesignSettings().m_CopperEdgeClearance))
    if project_path is not None and project_path.exists():
        try:
            settings = json.loads(project_path.read_text(encoding="utf-8"))
            clearance_mm = float(
                settings["board"]["design_settings"]["rules"]["min_copper_edge_clearance"]
            )
        except (OSError, ValueError, KeyError, TypeError):
            pass
    tolerance = GEOMETRY_TOLERANCE_MM
    seen = set()

    for obj in objects:
        if obj.uid in seen:
            continue
        box = obj.bbox
        left, top, right, bottom = map(mm, (box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom()))
        if (
            left < x0 + clearance_mm - tolerance
            or top < y0 + clearance_mm - tolerance
            or right > x1 - clearance_mm + tolerance
            or bottom > y1 - clearance_mm + tolerance
        ):
            seen.add(obj.uid)
            report.add(
                category,
                f"{obj.label} is closer than {clearance_mm:.3f} mm to the board edge",
            )

    # Filled copper zones are copper too, even though they are intentionally not
    # included in the pad/track/via pair-clearance audit.
    for zone in board.Zones():
        if zone.GetIsRuleArea() or zone.GetNetCode() == 0:
            continue
        for layer in copper_layers(board):
            if not zone.IsOnLayer(layer) or not zone.HasFilledPolysForLayer(layer):
                continue
            polys = zone.GetFilledPolysList(layer)
            if polys.IsEmpty():
                continue
            box = polys.BBox()
            left, top, right, bottom = map(mm, (box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom()))
            if (
                left < x0 + clearance_mm - tolerance
                or top < y0 + clearance_mm - tolerance
                or right > x1 - clearance_mm + tolerance
                or bottom > y1 - clearance_mm + tolerance
            ):
                report.add(
                    category,
                    f"filled zone {zone.GetNetname()} on {pcbnew.LayerName(layer)} is closer than "
                    f"{clearance_mm:.3f} mm to the board edge",
                )


def footprint_shape(footprint: "pcbnew.FOOTPRINT"):
    layer = pcbnew.F_CrtYd if footprint.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd
    courtyard = footprint.GetCourtyard(layer)
    if not courtyard.IsEmpty():
        return courtyard
    return pcbnew.SHAPE_RECT(footprint.GetBoundingBox())


def audit_no_holes_and_fitted_debug(board: "pcbnew.BOARD", report: Report) -> None:
    hole_category = "adhesive-only mounting: no H1/H2 footprints"
    debug_category = "J7/SW1/SW2 are fitted Top-SMD parts"
    report.check(hole_category)
    report.check(debug_category)

    for ref in ("H1", "H2"):
        if board.FindFootprintByReference(ref) is not None:
            report.add(hole_category, f"obsolete mounting-hole footprint {ref} is still present")

    for ref in ("J7", "SW1", "SW2"):
        footprint = board.FindFootprintByReference(ref)
        if footprint is None:
            report.add(debug_category, f"{ref} footprint is missing")
            continue
        if footprint.GetLayer() != pcbnew.F_Cu:
            report.add(debug_category, f"{ref} is not on F.Cu")
        if footprint.IsDNP() or footprint.IsExcludedFromBOM() or footprint.IsExcludedFromPosFiles():
            report.add(debug_category, f"{ref} is excluded from PCBA")
        for pad in footprint.Pads():
            if pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or pad.IsOnLayer(pcbnew.B_Cu):
                report.add(debug_category, f"{ref}.{pad.GetNumber()} is not a Top-only SMD pad")
    j7 = board.FindFootprintByReference("J7")
    if j7 is not None:
        actual = {pad.GetNumber() for pad in j7.Pads()}
        expected = {"1", "2", "3", "4", "5", "6", "8", "9", "10"}
        if actual != expected:
            report.add(
                debug_category,
                f"J7 physical pads are {sorted(actual)}; Cortex key position 7 must be absent",
            )


def effective_shape(item: object, layer: int):
    try:
        return item.GetEffectiveShape(layer)
    except Exception:
        try:
            return pcbnew.SHAPE_RECT(item.GetBoundingBox())
        except Exception:
            return None


def audit_tape_region(board: "pcbnew.BOARD", report: Report) -> None:
    keepout_category = "20 x 12 mm tape area: named B.Cu keepout"
    footprint_category = "20 x 12 mm tape area: Bottom footprints"
    pad_category = "20 x 12 mm tape area: Bottom pads/PTH protrusions"
    via_category = "20 x 12 mm tape area: vias"
    silk_category = "20 x 12 mm tape area: Bottom silkscreen"
    for category in (keepout_category, footprint_category, pad_category, via_category, silk_category):
        report.check(category)

    x0, y0, x1, y1 = TAPE_RECT_MM
    tape = pcbnew.SHAPE_RECT(
        pcbnew.BOX2I(
            pcbnew.VECTOR2I(iu(x0), iu(y0)),
            pcbnew.VECTOR2I(iu(x1 - x0), iu(y1 - y0)),
        )
    )

    keepouts = [
        zone for zone in board.Zones()
        if zone.GetIsRuleArea() and zone.GetZoneName() == "ADHESIVE_20X12"
    ]
    if len(keepouts) != 1:
        report.add(keepout_category, f"expected one ADHESIVE_20X12 rule area, found {len(keepouts)}")
    else:
        keepout = keepouts[0]
        box = keepout.Outline().BBox()
        actual = tuple(map(mm, (box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom())))
        expected = TAPE_RECT_MM
        if any(abs(a - e) > GEOMETRY_TOLERANCE_MM for a, e in zip(actual, expected)):
            report.add(keepout_category, f"keepout bounds are {actual}; expected {expected}")
        layers = keepout.GetLayerSet()
        if not layers.Contains(pcbnew.B_Cu) or any(
            layers.Contains(layer) for layer in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu)
        ):
            report.add(keepout_category, "keepout must exist on B.Cu only")
        if not keepout.GetDoNotAllowPads() or not keepout.GetDoNotAllowVias():
            report.add(keepout_category, "keepout must prohibit pads and vias")
        if keepout.GetDoNotAllowTracks() or keepout.GetDoNotAllowZoneFills():
            report.add(keepout_category, "keepout must allow covered B.Cu tracks and zone fills")

    for footprint in board.GetFootprints():
        if footprint.GetLayer() == pcbnew.B_Cu and footprint_shape(footprint).Collide(tape, 0):
            report.add(footprint_category, f"{footprint.GetReference()} intersects the tape area")

        for pad in footprint.Pads():
            if not pad.IsOnLayer(pcbnew.B_Cu):
                continue
            shape = effective_shape(pad, pcbnew.B_Cu)
            if shape is not None and shape.Collide(tape, 0):
                report.add(pad_category, describe_pad(pad))

        for field in footprint.GetFields():
            if not field.IsVisible() or field.GetLayer() != pcbnew.B_SilkS:
                continue
            shape = effective_shape(field, pcbnew.B_SilkS)
            if shape is not None and shape.Collide(tape, 0):
                report.add(silk_category, f"{footprint.GetReference()} field '{field.GetText()}'")

        for graphic in footprint.GraphicalItems():
            if graphic.GetLayer() != pcbnew.B_SilkS:
                continue
            shape = effective_shape(graphic, pcbnew.B_SilkS)
            if shape is not None and shape.Collide(tape, 0):
                report.add(silk_category, f"{footprint.GetReference()} footprint graphic")

    for track in board.GetTracks():
        if not isinstance(track, pcbnew.PCB_VIA) or not track.IsOnLayer(pcbnew.B_Cu):
            continue
        shape = effective_shape(track, pcbnew.B_Cu)
        if shape is not None and shape.Collide(tape, 0):
            report.add(via_category, describe_track(track))

    for drawing in board.GetDrawings():
        if drawing.GetLayer() != pcbnew.B_SilkS:
            continue
        if hasattr(drawing, "IsVisible") and not drawing.IsVisible():
            continue
        shape = effective_shape(drawing, pcbnew.B_SilkS)
        if shape is not None and shape.Collide(tape, 0):
            report.add(silk_category, f"board-level {type(drawing).__name__}")


def audit_connectivity(board: "pcbnew.BOARD", report: Report) -> None:
    category = "unconnected copper items"
    report.check(category)
    board.BuildConnectivity()
    count = board.GetConnectivity().GetUnconnectedCount(False)
    if count:
        report.add(category, f"KiCad connectivity reports {count} unconnected item(s)", count=count)


def audit_duplicate_routing(board: "pcbnew.BOARD", report: Report) -> None:
    category = "duplicate same-net routing items"
    report.check(category)
    seen: Dict[Tuple[object, ...], object] = {}
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
            report.add(category, describe_track(item))
        else:
            seen[key] = item


def audit_usb_vias(board: "pcbnew.BOARD", report: Report) -> None:
    category = "USB D+/D- via topology"
    report.check(category)
    counts: DefaultDict[str, int] = defaultdict(int)
    details: DefaultDict[str, List[str]] = defaultdict(list)
    for track in board.GetTracks():
        if not isinstance(track, pcbnew.PCB_VIA):
            continue
        name = track.GetNetname()
        if name.startswith("USB_DP") or name.startswith("USB_DM"):
            counts[name] += 1
            details[name].append(describe_track(track))
    expected = {
        "USB_DP_CONN": 2,
        "USB_DM_CONN": 2,
        "USB_DP_ESD": 0,
        "USB_DM_ESD": 0,
        "USB_DP": 0,
        "USB_DM": 0,
    }
    report.notes.append(
        "USB vias: " + ", ".join(f"{name}={counts[name]}" for name in expected)
    )
    for name, wanted in expected.items():
        if counts[name] != wanted:
            report.add(category, f"{name}: expected {wanted} via(s), found {counts[name]}")
            for detail in details[name]:
                report.add(category, detail)


def audit_usb_routing(board: "pcbnew.BOARD", report: Report) -> None:
    category = "USB D+/D- width, layer and length matching"
    report.check(category)
    dp_nets = {"USB_DP_CONN", "USB_DP_ESD", "USB_DP"}
    dm_nets = {"USB_DM_CONN", "USB_DM_ESD", "USB_DM"}
    all_nets = dp_nets | dm_nets
    fcu_only = {"USB_DP_ESD", "USB_DM_ESD", "USB_DP", "USB_DM"}
    lengths: DefaultDict[str, float] = defaultdict(float)
    for item in board.GetTracks():
        if isinstance(item, pcbnew.PCB_VIA) or item.GetNetname() not in all_nets:
            continue
        width = mm(item.GetWidth())
        if abs(width - USB_TRACK_WIDTH_MM) > GEOMETRY_TOLERANCE_MM:
            report.add(category, f"{describe_track(item)}; expected {USB_TRACK_WIDTH_MM:.2f} mm")
        if item.GetNetname() in fcu_only and item.GetLayer() != pcbnew.F_Cu:
            report.add(category, f"{describe_track(item)}; post-ESD route must remain on F.Cu")
        start, end = item.GetStart(), item.GetEnd()
        lengths[item.GetNetname()] += math.hypot(mm(start.x - end.x), mm(start.y - end.y))
    dp_length = sum(lengths[name] for name in dp_nets)
    dm_length = sum(lengths[name] for name in dm_nets)
    mismatch = abs(dp_length - dm_length)
    report.notes.append(
        f"USB routed length: D+={dp_length:.3f} mm, D-={dm_length:.3f} mm, "
        f"mismatch={mismatch:.3f} mm"
    )
    if mismatch > USB_MAX_LENGTH_MISMATCH_MM + GEOMETRY_TOLERANCE_MM:
        report.add(
            category,
            f"D+/D- mismatch {mismatch:.3f} mm exceeds {USB_MAX_LENGTH_MISMATCH_MM:.3f} mm",
        )


def pad_track_touch(pad: "pcbnew.PAD", track: object, tolerance_iu: int) -> bool:
    layer = track.GetLayer()
    if not pad.IsOnLayer(layer):
        return False
    return pad.GetEffectiveShape(layer).Collide(track.GetEffectiveShape(layer), tolerance_iu)


def has_wide_track_path(
    board: "pcbnew.BOARD",
    start_pad: "pcbnew.PAD",
    end_pad: "pcbnew.PAD",
    net_name: str,
    minimum_width_mm: float,
) -> Tuple[bool, int]:
    tracks = [
        track
        for track in board.GetTracks()
        if not isinstance(track, pcbnew.PCB_VIA)
        and track.GetNetname() == net_name
        and mm(track.GetWidth()) + GEOMETRY_TOLERANCE_MM >= minimum_width_mm
    ]
    if not tracks:
        return False, 0

    tolerance = iu(GEOMETRY_TOLERANCE_MM)
    adjacency: DefaultDict[int, List[int]] = defaultdict(list)
    starts: List[int] = []
    ends = set()

    for index, track in enumerate(tracks):
        if pad_track_touch(start_pad, track, tolerance):
            starts.append(index)
        if pad_track_touch(end_pad, track, tolerance):
            ends.add(index)

    for index, first in enumerate(tracks):
        first_shape = first.GetEffectiveShape(first.GetLayer())
        for second_index in range(index + 1, len(tracks)):
            second = tracks[second_index]
            if first.GetLayer() != second.GetLayer():
                continue
            second_shape = second.GetEffectiveShape(second.GetLayer())
            if first_shape.Collide(second_shape, tolerance):
                adjacency[index].append(second_index)
                adjacency[second_index].append(index)

    queue = deque((index, 1) for index in starts)
    visited = set(starts)
    while queue:
        node, length = queue.popleft()
        if node in ends:
            return True, length
        for neighbor in adjacency[node]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, length + 1))
    return False, 0


def audit_j5_j4_power_paths(board: "pcbnew.BOARD", report: Report) -> None:
    category = "J5 to J4 VBEC/GND >= 2.0 mm track paths"
    report.check(category)
    j4 = board.FindFootprintByReference("J4")
    j5 = board.FindFootprintByReference("J5")
    if j4 is None or j5 is None:
        report.add(category, "J4 or J5 footprint is missing")
        return

    for pad_number, net_name in (("2", "VBEC"), ("3", "GND")):
        start = j5.FindPadByNumber(pad_number)
        end = j4.FindPadByNumber(pad_number)
        if start is None or end is None:
            report.add(category, f"J5/J4 pad {pad_number} is missing for {net_name}")
            continue
        if start.GetNetname() != net_name or end.GetNetname() != net_name:
            report.add(
                category,
                f"J5/J4 pad {pad_number} net mismatch; expected {net_name}, got "
                f"{start.GetNetname()}/{end.GetNetname()}",
            )
            continue
        connected, segment_count = has_wide_track_path(
            board, start, end, net_name, WIDE_POWER_MIN_MM
        )
        if not connected:
            report.add(category, f"no continuous >= 2.0 mm track path for {net_name}")
        else:
            report.notes.append(
                f"J5 to J4 {net_name} wide path: PASS ({segment_count} segment(s))"
            )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "board",
        nargs="?",
        type=Path,
        default=DEFAULT_BOARD,
        help=f"board to audit (default: {DEFAULT_BOARD})",
    )
    parser.add_argument(
        "--max-details",
        type=int,
        default=20,
        help="maximum printed examples per failed check (default: 20)",
    )
    parser.add_argument(
        "--project",
        type=Path,
        help="KiCad project used for net-class clearances (defaults to the board's sibling .kicad_pro)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    board_path = args.board.resolve()
    if not board_path.exists():
        print(f"Board not found: {board_path}", file=sys.stderr)
        return 2
    if args.max_details < 1:
        print("--max-details must be at least 1", file=sys.stderr)
        return 2

    board = pcbnew.LoadBoard(str(board_path))
    report = Report(args.max_details)
    outline = audit_outline(board, report)
    audit_footprints(board, report)
    audit_courtyard_edge(board, outline, report)
    project_path = args.project.resolve() if args.project else None
    objects, default_clearance = collect_copper_objects(board, board_path, project_path)
    report.notes.append(f"Default copper clearance used by audit: {default_clearance:.3f} mm")
    audit_copper_clearance(objects, report)
    audit_edge_clearance(board, objects, outline, report, project_path)
    audit_no_holes_and_fitted_debug(board, report)
    audit_tape_region(board, report)
    audit_connectivity(board, report)
    audit_duplicate_routing(board, report)
    audit_usb_vias(board, report)
    audit_usb_routing(board, report)
    audit_j5_j4_power_paths(board, report)
    report.emit(board_path)
    return 1 if report.total else 0


if __name__ == "__main__":
    raise SystemExit(main())
