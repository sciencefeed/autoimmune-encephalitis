#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List

from openpyxl import load_workbook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the saved workbook on disk after a run.")
    parser.add_argument("--workbook", required=True, help="Absolute path to the workbook to verify")
    parser.add_argument("--sheet", required=True, help="Sheet name to inspect")
    parser.add_argument("--header-row", type=int, default=1, help="Header row number")
    parser.add_argument("--id-column", default="", help="Identifier column to report, e.g. PMID or ID")
    parser.add_argument(
        "--expected-id",
        action="append",
        default=[],
        help="Expected identifier value. May be supplied multiple times.",
    )
    parser.add_argument(
        "--min-nonempty-rows",
        type=int,
        default=0,
        help="Minimum required number of non-empty rows below the header",
    )
    return parser.parse_args()


def normalize_identifier(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"\b(\d{4,12})\b", text)
    return match.group(1) if match else text


def main() -> int:
    args = parse_args()
    workbook_path = Path(args.workbook)
    if not workbook_path.exists():
        print(json.dumps({"ok": False, "error": "workbook_not_found", "workbook": str(workbook_path)}))
        return 1

    wb = load_workbook(workbook_path, read_only=True)
    if args.sheet not in wb.sheetnames:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "sheet_not_found",
                    "workbook": str(workbook_path),
                    "sheet": args.sheet,
                    "available_sheets": wb.sheetnames,
                }
            )
        )
        return 1

    ws = wb[args.sheet]
    headers = [ws.cell(args.header_row, c).value for c in range(1, ws.max_column + 1)]
    header_map = {str(v).strip(): i + 1 for i, v in enumerate(headers) if v not in (None, "")}

    nonempty_rows: List[int] = []
    identifiers: List[str] = []
    id_col = header_map.get(args.id_column) if args.id_column else None

    for r in range(args.header_row + 1, ws.max_row + 1):
        values = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
        if any(v not in (None, "") for v in values):
            nonempty_rows.append(r)
            if id_col is not None:
                ident = normalize_identifier(ws.cell(r, id_col).value)
                if ident:
                    identifiers.append(ident)

    expected_ids = [normalize_identifier(v) for v in args.expected_id if normalize_identifier(v)]
    missing_expected_ids = [v for v in expected_ids if v not in identifiers]
    ok = len(nonempty_rows) >= args.min_nonempty_rows and not missing_expected_ids

    result = {
        "ok": ok,
        "workbook": str(workbook_path),
        "sheet": args.sheet,
        "nonempty_row_count": len(nonempty_rows),
        "nonempty_rows": nonempty_rows,
        "id_column": args.id_column or None,
        "identifiers": identifiers,
        "expected_identifiers": expected_ids,
        "missing_expected_identifiers": missing_expected_ids,
    }
    print(json.dumps(result))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
