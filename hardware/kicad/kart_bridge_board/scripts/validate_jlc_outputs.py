#!/usr/bin/env python3
"""Fail closed when JLCPCB BOM/CPL files do not describe one assembly set."""

from __future__ import annotations

import csv
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import pcbnew


BOM_COLUMNS = ["Comment", "Designator", "Footprint", "JLCPCB Part #", "Quantity"]
CPL_COLUMNS = ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"]
LCSC_RE = re.compile(r"C[0-9]+", re.IGNORECASE)


def read_csv(path: Path, expected_columns: list[str]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != expected_columns:
            raise ValueError(
                f"{path.name}: columns are {reader.fieldnames!r}; expected {expected_columns!r}"
            )
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path.name}: no data rows")
    return rows


def split_designators(value: str) -> list[str]:
    refs = [item.strip() for item in value.split(",")]
    if not refs or any(not ref for ref in refs):
        raise ValueError(f"invalid Designator cell: {value!r}")
    # export.sh disables reference ranges so every reference can be checked exactly.
    if any("-" in ref for ref in refs):
        raise ValueError(f"reference ranges are not permitted in Designator: {value!r}")
    return refs


def schematic_flags(path: Path) -> tuple[set[str], set[str]]:
    root = ET.parse(path).getroot()
    dnp: set[str] = set()
    excluded: set[str] = set()
    for comp in root.findall("./components/comp"):
        ref = comp.attrib["ref"]
        if comp.find("./property[@name='dnp']") is not None:
            dnp.add(ref)
        if comp.find("./property[@name='exclude_from_bom']") is not None:
            excluded.add(ref)
    return dnp, excluded


def board_sets(path: Path) -> tuple[set[str], set[str], set[str]]:
    board = pcbnew.LoadBoard(str(path))
    assembly: set[str] = set()
    dnp: set[str] = set()
    excluded: set[str] = set()
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if fp.IsDNP():
            dnp.add(ref)
        if fp.IsExcludedFromBOM() or fp.IsExcludedFromPosFiles():
            excluded.add(ref)
        is_smd = bool(fp.GetAttributes() & pcbnew.FP_SMD)
        if (
            is_smd
            and not fp.IsDNP()
            and not fp.IsExcludedFromBOM()
            and not fp.IsExcludedFromPosFiles()
        ):
            assembly.add(ref)
    return assembly, dnp, excluded


def collect_bom(rows: list[dict[str, str]], errors: list[str]) -> set[str]:
    refs: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        try:
            row_refs = split_designators(row["Designator"])
        except ValueError as exc:
            errors.append(f"BOM line {line_number}: {exc}")
            continue
        duplicates = refs.intersection(row_refs)
        if duplicates:
            errors.append(f"BOM line {line_number}: duplicate refs {sorted(duplicates)}")
        refs.update(row_refs)
        lcsc = row["JLCPCB Part #"].strip()
        if not LCSC_RE.fullmatch(lcsc):
            errors.append(
                f"BOM line {line_number} ({','.join(row_refs)}): invalid/empty LCSC number {lcsc!r}"
            )
        if not row["Comment"].strip():
            errors.append(f"BOM line {line_number}: empty Comment")
        if not row["Footprint"].strip():
            errors.append(f"BOM line {line_number}: empty Footprint")
        quantity = row["Quantity"].strip()
        try:
            parsed_quantity = int(quantity)
        except ValueError:
            errors.append(f"BOM line {line_number}: invalid Quantity {quantity!r}")
        else:
            if parsed_quantity != len(row_refs):
                errors.append(
                    f"BOM line {line_number}: Quantity={parsed_quantity} but Designator has {len(row_refs)} refs"
                )
    return refs


def collect_cpl(rows: list[dict[str, str]], errors: list[str]) -> set[str]:
    refs: set[str] = set()
    for line_number, row in enumerate(rows, start=2):
        ref = row["Designator"].strip()
        if not ref:
            errors.append(f"CPL line {line_number}: empty Designator")
            continue
        if ref in refs:
            errors.append(f"CPL line {line_number}: duplicate ref {ref}")
        refs.add(ref)
        if row["Layer"].strip() not in {"Top", "Bottom"}:
            errors.append(f"CPL line {line_number} ({ref}): invalid Layer {row['Layer']!r}")
        for column in ("Mid X", "Mid Y", "Rotation"):
            value = row[column].strip()
            try:
                number = float(value)
            except ValueError:
                errors.append(f"CPL line {line_number} ({ref}): {column} is not numeric: {value!r}")
            else:
                if not math.isfinite(number):
                    errors.append(f"CPL line {line_number} ({ref}): {column} is not finite: {value!r}")
    return refs


def set_difference_message(label: str, actual: set[str], expected: set[str]) -> list[str]:
    messages = []
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        messages.append(f"{label}: missing refs {missing}")
    if extra:
        messages.append(f"{label}: unexpected refs {extra}")
    return messages


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit(
            "usage: validate_jlc_outputs.py NETLIST.xml BOARD.kicad_pcb BOM.csv CPL.csv"
        )
    netlist_path, board_path, bom_path, cpl_path = map(Path, sys.argv[1:])
    errors: list[str] = []
    try:
        bom_rows = read_csv(bom_path, BOM_COLUMNS)
        cpl_rows = read_csv(cpl_path, CPL_COLUMNS)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"JLCPCB output validation FAILED:\n- {exc}") from exc

    bom_refs = collect_bom(bom_rows, errors)
    cpl_refs = collect_cpl(cpl_rows, errors)
    expected_refs, pcb_dnp, pcb_excluded = board_sets(board_path)
    sch_dnp, sch_excluded = schematic_flags(netlist_path)
    forbidden_refs = pcb_dnp | sch_dnp | pcb_excluded | sch_excluded

    leaked = sorted((bom_refs | cpl_refs) & forbidden_refs)
    if leaked:
        errors.append(f"DNP/excluded references leaked into assembly files: {leaked}")
    errors.extend(set_difference_message("BOM vs PCB assembly set", bom_refs, expected_refs))
    errors.extend(set_difference_message("CPL vs PCB assembly set", cpl_refs, expected_refs))
    errors.extend(set_difference_message("BOM vs CPL", bom_refs, cpl_refs))

    if errors:
        print("JLCPCB output validation FAILED:")
        print("\n".join(f"- {line}" for line in errors))
        raise SystemExit(1)
    print(
        f"JLCPCB output validation OK: {len(expected_refs)} populated refs; "
        f"BOM/CPL sets match; all LCSC numbers present"
    )


if __name__ == "__main__":
    main()
