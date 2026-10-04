#!/usr/bin/env bash
set -euo pipefail

PROJECT="kart_bridge_board"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${ROOT}/fabrication/build"
KICAD_CLI="${KICAD_CLI:-/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli}"
PCBNEW_PYTHON="${PCBNEW_PYTHON:-/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9}"

if [[ ! -x "$KICAD_CLI" ]]; then
  echo "KiCad CLI not found: $KICAD_CLI" >&2
  exit 2
fi
if [[ ! -x "$PCBNEW_PYTHON" ]]; then
  echo "KiCad pcbnew Python not found: $PCBNEW_PYTHON" >&2
  exit 2
fi

cd "$ROOT"
rm -rf "$OUT"
mkdir -p "$OUT/gerber" "$OUT/assembly" "$OUT/reports" "$OUT/review" "$OUT/.tools"

echo "== Fill zones =="
"$PCBNEW_PYTHON" scripts/fill_zones.py "$PROJECT.kicad_pcb"

echo "== ERC =="
"$KICAD_CLI" sch erc \
  --format json \
  --severity-error \
  --severity-warning \
  --exit-code-violations \
  -o "$OUT/reports/erc.json" \
  "$PROJECT.kicad_sch"

echo "== Netlist and schematic/PCB parity =="
"$KICAD_CLI" sch export netlist \
  --format kicadxml \
  -o "$OUT/review/netlist.xml" \
  "$PROJECT.kicad_sch"
"$PCBNEW_PYTHON" scripts/audit_netlist.py \
  "$OUT/review/netlist.xml" \
  | tee "$OUT/reports/netlist_audit.txt"
"$PCBNEW_PYTHON" scripts/check_parity.py \
  "$OUT/review/netlist.xml" "$PROJECT.kicad_pcb" \
  | tee "$OUT/reports/parity.txt"

echo "== DRC =="
JPBB_DRC_SHIM_DIR="$OUT/.tools" scripts/run_kicad_drc.sh "$KICAD_CLI" pcb drc \
  --format json \
  --all-track-errors \
  --refill-zones \
  --severity-error \
  --severity-warning \
  --exit-code-violations \
  -o "$OUT/reports/drc.json" \
  "$PROJECT.kicad_pcb"

echo "== Independent PCB audit =="
"$PCBNEW_PYTHON" scripts/audit_board.py \
  "$PROJECT.kicad_pcb" --project "$PROJECT.kicad_pro" \
  | tee "$OUT/reports/board_audit.txt"

echo "== Gerber =="
JPBB_DRC_SHIM_DIR="$OUT/.tools" scripts/run_kicad_drc.sh "$KICAD_CLI" pcb export gerbers \
  --layers 'F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts' \
  --subtract-soldermask \
  --check-zones \
  --hide-DNP-footprints-on-fab-layers \
  -o "$OUT/gerber" \
  "$PROJECT.kicad_pcb"

echo "== Drill =="
JPBB_DRC_SHIM_DIR="$OUT/.tools" scripts/run_kicad_drc.sh "$KICAD_CLI" pcb export drill \
  --format excellon \
  --drill-origin absolute \
  --excellon-zeros-format decimal \
  --excellon-oval-format alternate \
  --excellon-units mm \
  --excellon-separate-th \
  --generate-report \
  --report-path "$OUT/reports/drill_report.txt" \
  -o "$OUT/gerber" \
  "$PROJECT.kicad_pcb"

echo "== BOM =="
"$KICAD_CLI" sch export bom \
  --fields 'Reference,Value,Footprint,Manufacturer,MPN,LCSC Part #,DNP,Notes,QUANTITY' \
  --labels 'Reference,Value,Footprint,Manufacturer,MPN,LCSC Part #,DNP,Notes,Quantity' \
  --sort-field Reference \
  -o "$OUT/review/${PROJECT}_BOM_full.csv" \
  "$PROJECT.kicad_sch"
"$KICAD_CLI" sch export bom \
  --exclude-dnp \
  --fields 'Value,Reference,Footprint,LCSC Part #,QUANTITY' \
  --labels 'Comment,Designator,Footprint,JLCPCB Part #,Quantity' \
  --group-by 'Value,Footprint,LCSC Part #' \
  --sort-field Reference \
  --ref-delimiter ',' \
  --ref-range-delimiter '' \
  -o "$OUT/assembly/${PROJECT}_BOM_JLCPCB.csv" \
  "$PROJECT.kicad_sch"

echo "== CPL =="
JPBB_DRC_SHIM_DIR="$OUT/.tools" scripts/run_kicad_drc.sh "$KICAD_CLI" pcb export pos \
  --format csv \
  --units mm \
  --side both \
  --smd-only \
  --exclude-dnp \
  -o "$OUT/review/${PROJECT}_positions_raw.csv" \
  "$PROJECT.kicad_pcb"
"$PCBNEW_PYTHON" scripts/convert_jlc_cpl.py \
  "$OUT/review/${PROJECT}_positions_raw.csv" \
  "$OUT/assembly/${PROJECT}_CPL_JLCPCB.csv"

echo "== Validate JLCPCB BOM/CPL =="
"$PCBNEW_PYTHON" scripts/validate_jlc_outputs.py \
  "$OUT/review/netlist.xml" \
  "$PROJECT.kicad_pcb" \
  "$OUT/assembly/${PROJECT}_BOM_JLCPCB.csv" \
  "$OUT/assembly/${PROJECT}_CPL_JLCPCB.csv" \
  | tee "$OUT/reports/jlcpcb_validation.txt"

echo "== Validate fabrication file set =="
required_fabrication_files=(
  "${PROJECT}-F_Cu.gtl"
  "${PROJECT}-In1_Cu.g1"
  "${PROJECT}-In2_Cu.g2"
  "${PROJECT}-B_Cu.gbl"
  "${PROJECT}-F_Paste.gtp"
  "${PROJECT}-B_Paste.gbp"
  "${PROJECT}-F_Silkscreen.gto"
  "${PROJECT}-B_Silkscreen.gbo"
  "${PROJECT}-F_Mask.gts"
  "${PROJECT}-B_Mask.gbs"
  "${PROJECT}-Edge_Cuts.gm1"
  "${PROJECT}-PTH.drl"
  "${PROJECT}-NPTH.drl"
  "${PROJECT}-job.gbrjob"
)
for fabrication_file in "${required_fabrication_files[@]}"; do
  if [[ ! -s "$OUT/gerber/$fabrication_file" ]]; then
    echo "Missing or empty fabrication output: $fabrication_file" >&2
    exit 1
  fi
done
echo "Fabrication file set OK: ${#required_fabrication_files[@]} required files"

echo "== Build manifest =="
"$PCBNEW_PYTHON" scripts/write_build_manifest.py \
  "$OUT/reports/build_manifest.txt" "$KICAD_CLI"

echo "== Review drawings =="
"$KICAD_CLI" sch export pdf \
  -o "$OUT/review/${PROJECT}_schematic.pdf" \
  "$PROJECT.kicad_sch"
JPBB_DRC_SHIM_DIR="$OUT/.tools" scripts/run_kicad_drc.sh "$KICAD_CLI" pcb render \
  --width 1800 --height 1200 --side top --quality high --background opaque \
  -o "$OUT/review/${PROJECT}_top.png" \
  "$PROJECT.kicad_pcb"
JPBB_DRC_SHIM_DIR="$OUT/.tools" scripts/run_kicad_drc.sh "$KICAD_CLI" pcb render \
  --width 1800 --height 1200 --side bottom --quality high --background opaque \
  -o "$OUT/review/${PROJECT}_bottom.png" \
  "$PROJECT.kicad_pcb"

echo "== Package =="
(
  cd "$OUT/gerber"
  zip -q -r "../${PROJECT}_Gerber.zip" .
)
(
  cd "$OUT"
  zip -q -r "${PROJECT}_JLCPCB_package.zip" \
    "${PROJECT}_Gerber.zip" assembly reports review
)

echo "Generated:"
find "$OUT" -maxdepth 3 -type f -print | sort
