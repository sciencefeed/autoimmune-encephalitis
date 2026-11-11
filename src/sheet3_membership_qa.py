#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Set

from openpyxl import load_workbook


HEADER_ROW = 3
PUBMED_ID_RE = re.compile(r"\b(\d{4,9})\b")
URL_RE = re.compile(r"^https?://", flags=re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QA checks for Submitted Reference Inventory membership and links")
    parser.add_argument(
        "--workbook",
        default="/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/Autoimmune Encephalitis Research paper summary.xlsx",
        help="Path to workbook",
    )
    parser.add_argument("--sheet", default="Submitted Reference Inventory", help="Submitted inventory sheet")
    parser.add_argument("--main-sheet", default="Medium-High confidence items", help="Main retained sheet")
    parser.add_argument("--low-sheet", default="Low Confidence Items", help="Low confidence retained sheet")
    parser.add_argument(
        "--summary-out",
        default="/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/reports/sheet3_membership_qa.json",
        help="Output summary json path",
    )
    return parser.parse_args()


def header_map(ws) -> Dict[str, int]:
    return {
        str(ws.cell(HEADER_ROW, c).value).strip(): c
        for c in range(1, ws.max_column + 1)
        if ws.cell(HEADER_ROW, c).value not in (None, "")
    }


def row_has_data(ws, r: int) -> bool:
    return any(ws.cell(r, c).value not in (None, "") for c in range(1, ws.max_column + 1))


def parse_pmid(value: object) -> str:
    match = PUBMED_ID_RE.search(str(value or ""))
    return match.group(1) if match else ""


def collect_pmids(ws, id_col: int) -> Set[str]:
    out: Set[str] = set()
    for r in range(HEADER_ROW + 1, ws.max_row + 1):
        if not row_has_data(ws, r):
            continue
        pmid = parse_pmid(ws.cell(r, id_col).value)
        if pmid:
            out.add(pmid)
    return out


def main() -> int:
    args = parse_args()
    workbook = Path(args.workbook)
    out_path = Path(args.summary_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    wb = load_workbook(workbook)
    ws3 = wb[args.sheet]
    wsm = wb[args.main_sheet]
    wsl = wb[args.low_sheet]

    h3 = header_map(ws3)
    hm = header_map(wsm)
    hl = header_map(wsl)

    required = [
        "Title",
        "Direct Paper URL",
        "Resolved PMID",
        "Included in Database (Y/N)",
        "If Not Included, Why Not",
    ]
    missing = [c for c in required if c not in h3]
    if missing:
        out = {"ok": False, "error": "missing_columns", "missing": missing}
        out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(json.dumps(out))
        return 1

    main_pmids = collect_pmids(wsm, hm["ID"]) if "ID" in hm else set()
    low_pmids = collect_pmids(wsl, hl["ID"]) if "ID" in hl else set()
    retained = main_pmids | low_pmids

    errors: List[Dict[str, object]] = []
    rows_checked = 0
    blank_cells = 0
    no_nr_errors = 0
    invalid_urls = 0
    missing_hyperlinks = 0
    membership_mismatches = 0

    for r in range(HEADER_ROW + 1, ws3.max_row + 1):
        if not row_has_data(ws3, r):
            continue
        rows_checked += 1

        # Blank/placeholder cleanliness checks
        for c in range(1, ws3.max_column + 1):
            header = ws3.cell(HEADER_ROW, c).value
            if header in (None, ""):
                continue
            value = ws3.cell(r, c).value
            text = str(value or "").strip()
            if text == "":
                blank_cells += 1
                errors.append({"row": r, "column": str(header), "error": "Blank cell"})
            low = text.lower()
            if low in {"nr", "n/r", "not reported", "n/a", "na"}:
                no_nr_errors += 1
                errors.append({"row": r, "column": str(header), "error": "Placeholder value"})

        # URL format + hyperlink for direct URL
        direct_cell = ws3.cell(r, h3["Direct Paper URL"])
        direct_url = str(direct_cell.value or "").strip()
        if not URL_RE.match(direct_url):
            invalid_urls += 1
            errors.append({"row": r, "column": "Direct Paper URL", "error": "Invalid URL format"})
        if direct_url and direct_cell.hyperlink is None:
            missing_hyperlinks += 1
            errors.append({"row": r, "column": "Direct Paper URL", "error": "Missing hyperlink"})

        # Inclusion/membership consistency
        included = str(ws3.cell(r, h3["Included in Database (Y/N)"]).value or "").strip().upper()
        reason = str(ws3.cell(r, h3["If Not Included, Why Not"]).value or "").strip()
        pmid = parse_pmid(ws3.cell(r, h3["Resolved PMID"]).value)
        in_retained = bool(pmid and pmid in retained)

        if included not in {"Y", "N"}:
            membership_mismatches += 1
            errors.append({"row": r, "column": "Included in Database (Y/N)", "error": "Invalid Y/N value"})
            continue

        if included == "Y":
            if not pmid:
                membership_mismatches += 1
                errors.append({"row": r, "error": "Included=Y but PMID unresolved"})
            if not in_retained:
                membership_mismatches += 1
                errors.append({"row": r, "error": "Included=Y but PMID not found in retained sheets"})
        else:
            if not reason:
                membership_mismatches += 1
                errors.append({"row": r, "error": "Included=N but missing exclusion reason"})
            if pmid and in_retained:
                membership_mismatches += 1
                errors.append({"row": r, "error": "Included=N but PMID present in retained sheets"})

    summary = {
        "ok": len(errors) == 0,
        "rows_checked": rows_checked,
        "retained_pmids_count": len(retained),
        "blank_cells": blank_cells,
        "placeholder_values": no_nr_errors,
        "invalid_urls": invalid_urls,
        "missing_hyperlinks": missing_hyperlinks,
        "membership_mismatches": membership_mismatches,
        "error_count": len(errors),
        "errors": errors[:100],
    }
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
