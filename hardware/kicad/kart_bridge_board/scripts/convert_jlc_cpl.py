#!/usr/bin/env python3
"""Convert and validate KiCad CSV position output for JLCPCB CPL upload."""

from __future__ import annotations

import csv
import math
from pathlib import Path
import sys


def pick(row: dict[str, str], *names: str) -> str:
    for name in names:
        if name in row:
            return row[name]
    raise KeyError(f"None of {names!r} found in {list(row)}")


def normalized_layer(value: str) -> str:
    layer = value.strip().lower()
    if layer in {"top", "front", "f", "f.cu"}:
        return "Top"
    if layer in {"bottom", "back", "b", "b.cu"}:
        return "Bottom"
    raise ValueError(f"unsupported placement layer {value!r}; expected top/front or bottom/back")


def checked_number(value: str, *, ref: str, column: str) -> str:
    text = value.strip()
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError(f"{ref}: {column} is not numeric: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{ref}: {column} is not finite: {value!r}")
    return text


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: convert_jlc_cpl.py INPUT.csv OUTPUT.csv")
    source, target = map(Path, sys.argv[1:])
    with source.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit(f"empty or headerless placement file: {source}")
        rows = list(reader)
    if not rows:
        raise SystemExit(f"no placements in {source}")
    out = []
    seen: set[str] = set()
    for row in rows:
        ref = pick(row, "Ref", "Designator").strip()
        if not ref:
            raise ValueError("placement has an empty reference designator")
        if ref in seen:
            raise ValueError(f"duplicate placement reference: {ref}")
        seen.add(ref)
        out.append({
            "Designator": ref,
            "Mid X": checked_number(pick(row, "PosX", "Mid X"), ref=ref, column="Mid X"),
            "Mid Y": checked_number(pick(row, "PosY", "Mid Y"), ref=ref, column="Mid Y"),
            "Layer": normalized_layer(pick(row, "Side", "Layer")),
            "Rotation": checked_number(
                pick(row, "Rot", "Rotation"), ref=ref, column="Rotation"
            ),
        })
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        writer.writeheader()
        writer.writerows(out)
    print(f"Wrote {len(out)} placements: {target}")


if __name__ == "__main__":
    main()
