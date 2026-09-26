"""Inspect layout of committed government spreadsheets without guessing schemas.

Prints worksheet names, dimensions and first nonempty rows. This is also
useful locally when a government portal changes its report layout.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "datasets/dilrmp/Uttar Pradesh"


def inspect_workbook(path: Path, sample: int = 14):
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        print(f"FILE: {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
        for sheet in book:
            print(f"SHEET: {sheet.title!r} dimensions={sheet.max_row}x{sheet.max_column}")
            nonempty = 0
            for line_no, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                cells = [(i + 1, str(v).strip()[:100]) for i, v in enumerate(row) if v is not None and str(v).strip()]
                if not cells:
                    continue
                print(f"  ROW {line_no}: {cells[:24]}")
                nonempty += 1
                if nonempty >= sample:
                    break
    finally:
        book.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=14)
    p.add_argument("--dir", type=Path, default=DEFAULT)
    args = p.parse_args()
    for file in sorted(args.dir.rglob("*.xlsx")):
        inspect_workbook(file, args.sample)
