#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from openpyxl import load_workbook

WORKBOOK = Path("/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/Autoimmune Encephalitis Research paper summary.xlsx")
SHEET3 = "Submitted Reference Inventory"
MAIN = "Medium-High confidence items"
LOW = "Low Confidence Items"
HEADER_ROW = 3


def hmap(ws) -> Dict[str, int]:
    return {
        str(ws.cell(HEADER_ROW, c).value).strip(): c
        for c in range(1, ws.max_column + 1)
        if ws.cell(HEADER_ROW, c).value not in (None, "")
    }


def row_has_data(ws, r: int) -> bool:
    return any(ws.cell(r, c).value not in (None, "") for c in range(1, ws.max_column + 1))


def parse_gate3(reason: str) -> Optional[Tuple[int, str]]:
    # Example: Gate3(duration)=PASS (5114 days, confidence=MEDIUM).
    m = re.search(r"Gate3\(duration\)=PASS \((\d+)\s+days,\s*confidence=([A-Z]+)\)", reason or "")
    if not m:
        return None
    return int(m.group(1)), m.group(2).upper()


def parse_pmid(text: object) -> str:
    m = re.search(r"\b(\d{4,9})\b", str(text or ""))
    return m.group(1) if m else ""


def existing_pmids(*worksheets) -> set:
    seen = set()
    for ws in worksheets:
        hm = hmap(ws)
        id_col = hm.get("ID")
        if id_col is None:
            continue
        for r in range(HEADER_ROW + 1, ws.max_row + 1):
            if not row_has_data(ws, r):
                continue
            p = parse_pmid(ws.cell(r, id_col).value)
            if p:
                seen.add(p)
    return seen


def append_main(ws, item: Dict[str, object]) -> None:
    hm = hmap(ws)
    row = ws.max_row + 1
    def setv(col: str, val):
        c = hm.get(col)
        if c is not None:
            ws.cell(row, c).value = val
    pmid = str(item["pmid"])
    days = int(item["days"])
    months = round(days / 30.4375, 1)
    conf = str(item["conf"])
    setv("Date", item["date"])
    setv("Authors", item["authors"])
    setv("Title", item["title"])
    setv("Type of study", item["study_type"])
    setv("Suspected AE Duration (months)", months)
    setv("Description", item["description"])
    setv("Findings", item["findings"])
    setv("PubMed URL", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
    setv("Direct Paper URL", item["direct_url"])
    setv("In Submitted List (Y/N)", "Y")
    setv("Duration Evidence", f"Promoted from submitted inventory: Gate3 PASS ({days} days, confidence={conf}).")
    setv("Duration Confidence", conf)
    setv("ID", pmid)
    setv("Suspected AE Duration (days)", days)
    setv(">=3 months (Y/N)", "Y")
    setv(">=6 months (Y/N)", "Y" if days >= 180 else "N")
    setv(">=3 months @HIGH (Y/N)", "Y" if conf == "HIGH" else "N")
    setv(">=3 months @MEDIUM (Y/N)", "Y" if conf in ("HIGH", "MEDIUM") else "N")
    setv(">=3 months @LOW (Y/N)", "Y")
    setv("Newly Included at LOW Threshold (Y/N)", "N" if conf in ("HIGH", "MEDIUM") else "Y")
    if conf == "HIGH":
        setv("Inclusion Confidence Label", "HIGH_CONFIDENCE")
    elif conf == "MEDIUM":
        setv("Inclusion Confidence Label", "MEDIUM_CONFIDENCE")
    else:
        setv("Inclusion Confidence Label", "LOW_CONFIDENCE_ADDED")

    for col in ("PubMed URL", "Direct Paper URL"):
        c = hm.get(col)
        if c is None:
            continue
        cell = ws.cell(row, c)
        v = str(cell.value or "")
        if v.startswith("http://") or v.startswith("https://"):
            cell.hyperlink = v
            cell.style = "Hyperlink"


def append_low(ws, item: Dict[str, object]) -> None:
    hm = hmap(ws)
    row = ws.max_row + 1
    def setv(col: str, val):
        c = hm.get(col)
        if c is not None:
            ws.cell(row, c).value = val
    pmid = str(item["pmid"])
    days = int(item["days"])
    months = round(days / 30.4375, 1)
    conf = str(item["conf"])
    setv("Date", item["date"])
    setv("Authors", item["authors"])
    setv("Title", item["title"])
    setv("Type of study", item["study_type"])
    setv("Suspected AE Duration (months)", months)
    setv("Description", item["description"])
    setv("Findings", item["findings"])
    setv("PubMed URL", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
    setv("Direct Paper URL", item["direct_url"])
    setv("In Submitted List (Y/N)", "Y")
    setv("Duration Evidence", f"Promoted from submitted inventory: Gate3 PASS ({days} days, confidence={conf}).")
    setv("Duration Confidence", conf)
    setv("ID", pmid)

    for col in ("PubMed URL", "Direct Paper URL"):
        c = hm.get(col)
        if c is None:
            continue
        cell = ws.cell(row, c)
        v = str(cell.value or "")
        if v.startswith("http://") or v.startswith("https://"):
            cell.hyperlink = v
            cell.style = "Hyperlink"


def sort_by_months_desc(ws) -> None:
    hm = hmap(ws)
    months_col = hm.get("Suspected AE Duration (months)")
    if months_col is None:
        return
    rows = []
    for r in range(HEADER_ROW + 1, ws.max_row + 1):
        if not row_has_data(ws, r):
            continue
        vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
        try:
            key = float(ws.cell(r, months_col).value)
        except Exception:
            key = -1.0
        rows.append((key, vals))
    rows.sort(key=lambda x: x[0], reverse=True)
    for r in range(HEADER_ROW + 1, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None
            ws.cell(r, c).hyperlink = None
    w = HEADER_ROW + 1
    for _, vals in rows:
        for c, v in enumerate(vals, start=1):
            ws.cell(w, c).value = v
        w += 1
    # restore links
    hm2 = hmap(ws)
    for r in range(HEADER_ROW + 1, ws.max_row + 1):
        if not row_has_data(ws, r):
            continue
        for col in ("PubMed URL", "Direct Paper URL"):
            c = hm2.get(col)
            if c is None:
                continue
            v = str(ws.cell(r, c).value or "")
            if v.startswith("http://") or v.startswith("https://"):
                ws.cell(r, c).hyperlink = v
                ws.cell(r, c).style = "Hyperlink"


def main() -> int:
    wb = load_workbook(WORKBOOK)
    ws3 = wb[SHEET3]
    wsm = wb[MAIN]
    wsl = wb[LOW]
    h3 = hmap(ws3)
    required = ["Title", "Direct Paper URL", "Resolved PMID", "Included in Database (Y/N)", "If Not Included, Why Not"]
    missing = [c for c in required if c not in h3]
    if missing:
        raise RuntimeError(f"Sheet3 missing columns: {missing}")

    seen = existing_pmids(wsm, wsl)
    candidates: List[Dict[str, object]] = []
    for r in range(HEADER_ROW + 1, ws3.max_row + 1):
        if not row_has_data(ws3, r):
            continue
        included = str(ws3.cell(r, h3["Included in Database (Y/N)"]).value or "").strip().upper()
        reason = str(ws3.cell(r, h3["If Not Included, Why Not"]).value or "")
        pmid = parse_pmid(ws3.cell(r, h3["Resolved PMID"]).value)
        if included != "N":
            continue
        if not pmid:
            continue
        if "Gate4(retrieval-scope)=FAIL" not in reason:
            continue
        gate = parse_gate3(reason)
        if gate is None:
            continue
        days, conf = gate
        if pmid in seen:
            continue
        candidates.append(
            {
                "row": r,
                "pmid": pmid,
                "days": days,
                "conf": conf,
                "date": ws3.cell(r, h3.get("Date", 1)).value,
                "authors": ws3.cell(r, h3.get("Authors", 1)).value,
                "title": ws3.cell(r, h3.get("Title", 1)).value,
                "study_type": ws3.cell(r, h3.get("Type of study", 1)).value,
                "description": ws3.cell(r, h3.get("Description", 1)).value,
                "findings": ws3.cell(r, h3.get("Findings", 1)).value,
                "direct_url": ws3.cell(r, h3.get("Direct Paper URL", 1)).value,
            }
        )
        seen.add(pmid)

    added_main, added_low = [], []
    for item in candidates:
        if item["conf"] in ("HIGH", "MEDIUM"):
            append_main(wsm, item)
            added_main.append(item["pmid"])
        else:
            append_low(wsl, item)
            added_low.append(item["pmid"])

    sort_by_months_desc(wsm)
    sort_by_months_desc(wsl)

    # update sheet3 inclusion Y for promoted rows
    for r in range(HEADER_ROW + 1, ws3.max_row + 1):
        if not row_has_data(ws3, r):
            continue
        pmid = parse_pmid(ws3.cell(r, h3["Resolved PMID"]).value)
        if pmid in set(added_main + added_low):
            ws3.cell(r, h3["Included in Database (Y/N)"]).value = "Y"
            ws3.cell(r, h3["If Not Included, Why Not"]).value = (
                "Included after manual promotion from submitted-reference audit (previously retrieval-scope miss)."
            )

    wb.save(WORKBOOK)
    print(
        {
            "candidates_found": len(candidates),
            "added_main_medium_high": len(added_main),
            "added_low": len(added_low),
            "pmids_added_main": added_main,
            "pmids_added_low": added_low,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

