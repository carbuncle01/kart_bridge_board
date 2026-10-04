#!/usr/bin/env python3
"""Fill all copper zones using KiCad's bundled pcbnew runtime."""

from pathlib import Path
import sys

import pcbnew


def main() -> None:
    board_path = Path(sys.argv[1] if len(sys.argv) > 1 else "kart_bridge_board.kicad_pcb").resolve()
    board = pcbnew.LoadBoard(str(board_path))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(board_path), board)
    print(f"Filled {len(board.Zones())} zones: {board_path}")


if __name__ == "__main__":
    main()
