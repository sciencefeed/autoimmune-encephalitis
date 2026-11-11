#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from openpyxl import load_workbook


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="QA validator for AE review workbook")
    parser.add_argument(
        "--workbook",
        default="/work/Autoimmune Encephalitis Research paper summary.xlsx",
        help="Path to workbook",
    )
    parser.add_argument(
        "--sheet",
        default="",
        help="Optional sheet name override. Defaults to Medium-High confidence items or first sheet.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workbook = Path(args.workbook)
    out_dir = workbook.parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    wb = load_workbook(workbook)
    if args.sheet:
        ws = wb[args.sheet]
    elif "Medium-High confidence items" in wb.sheetnames:
        ws = wb["Medium-High confidence items"]
    else:
        ws = wb[wb.sheetnames[0]]

    headers = [ws.cell(row=3, column=c).value for c in range(1, ws.max_column + 1)]
    idx = {v: i + 1 for i, v in enumerate(headers) if v}
    required = [
        "Title",
        "PubMed URL",
        "Direct Paper URL",
    ]
    duration_days_col = idx.get("Suspected AE Duration (days)")
    duration_months_col = idx.get("Suspected AE Duration (months)")
    missing = [c for c in required if c not in idx]
    if duration_days_col is None and duration_months_col is None:
        missing.append("Suspected AE Duration (days) or Suspected AE Duration (months)")
    if missing:
        print(json.dumps({"ok": False, "error": "missing_columns", "missing": missing}))
        return 1

    rows = []
    for r in range(4, ws.max_row + 1):
        vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
        if all(v in (None, "") for v in vals):
            continue
        rows.append(r)

    url_re = re.compile(r"^https?://")
    bad = []
    durations = []
    for r in rows:
        pub = ws.cell(r, idx["PubMed URL"])
        direct = ws.cell(r, idx["Direct Paper URL"])
        dur_days = ws.cell(r, duration_days_col).value if duration_days_col else None
        dur_months = ws.cell(r, duration_months_col).value if duration_months_col else None
        part = ws.cell(r, idx["Number of participants"]).value if "Number of participants" in idx else "NR"
        find = ws.cell(r, idx["Findings"]).value if "Findings" in idx else "NR"
        if not pub.value or not url_re.match(str(pub.value)) or pub.hyperlink is None:
            bad.append({"row": r, "field": "PubMed URL"})
        if not direct.value or not url_re.match(str(direct.value)) or direct.hyperlink is None:
            bad.append({"row": r, "field": "Direct Paper URL"})
        parsed_duration = None
        if dur_days not in (None, ""):
            try:
                parsed_duration = float(dur_days)
            except Exception:
                parsed_duration = None
        if parsed_duration is None and dur_months not in (None, ""):
            try:
                parsed_duration = float(dur_months) * 30.4375
            except Exception:
                parsed_duration = None
        if parsed_duration is None:
            bad.append({"row": r, "field": "DurationMissing"})
        else:
            durations.append(parsed_duration)
            if parsed_duration < 90:
                bad.append({"row": r, "field": "Duration<90"})
            gte3_col = idx.get(">=3 months (Y/N)")
            if gte3_col is not None:
                gte3_val = str(ws.cell(r, gte3_col).value or "").strip().upper()
                expected = "Y" if parsed_duration >= 90 else "N"
                if gte3_val and gte3_val != expected:
                    bad.append({"row": r, "field": ">=3 months mismatch"})
            gte6_col = idx.get(">=6 months (Y/N)")
            if gte6_col is not None:
                gte6_val = str(ws.cell(r, gte6_col).value or "").strip().upper()
                expected = "Y" if parsed_duration >= 180 else "N"
                if gte6_val and gte6_val != expected:
                    bad.append({"row": r, "field": ">=6 months mismatch"})
        if part in (None, ""):
            bad.append({"row": r, "field": "ParticipantsBlank"})
        if find in (None, ""):
            bad.append({"row": r, "field": "FindingsBlank"})

    sorted_ok = all(durations[i] >= durations[i + 1] for i in range(len(durations) - 1))
    result = {
        "ok": len(bad) == 0 and sorted_ok,
        "rows": len(rows),
        "sorted_descending": sorted_ok,
        "bad_count": len(bad),
        "bad_examples": bad[:20],
        "top_durations_days": durations[:20],
    }
    print(json.dumps(result))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
