#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from openpyxl import load_workbook
from rapidfuzz import fuzz

PUBMED_URL_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate PMID/title/url consistency against PubMed metadata")
    parser.add_argument(
        "--workbook",
        default="/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/Autoimmune Encephalitis Research paper summary.xlsx",
        help="Path to workbook",
    )
    parser.add_argument(
        "--sheet",
        default="Medium-High confidence items",
        help="Sheet name to validate",
    )
    parser.add_argument(
        "--reports-dir",
        default="/Users/zeryabmeyer/Documents/Autoimmune Encephalitis/reports",
        help="Reports output directory",
    )
    parser.add_argument(
        "--csv-out",
        default="id_match_qa.csv",
        help="CSV filename (or absolute path)",
    )
    parser.add_argument(
        "--summary-out",
        default="id_match_qa_summary.json",
        help="Summary JSON filename (or absolute path)",
    )
    return parser.parse_args()


def extract_pmid(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = PUBMED_URL_RE.search(text)
    if match:
        return match.group(1)
    if re.fullmatch(r"\d{4,9}", text):
        return text
    return None


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", title.lower())).strip()


def fetch_titles(pmids: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not pmids:
        return out

    unique = sorted(set(pmids), key=lambda x: int(x))
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

    # Try bulk first.
    ids = ",".join(unique)
    try:
        resp = requests.get(url, params={"db": "pubmed", "id": ids, "retmode": "json"}, timeout=40)
        resp.raise_for_status()
        payload = resp.json().get("result", {})
        for pmid in unique:
            title = payload.get(pmid, {}).get("title", "")
            if title:
                out[pmid] = title
    except Exception:
        pass

    # Per-ID retry fallback for anything missing.
    missing = [p for p in unique if p not in out]
    for pmid in missing:
        last_exc: Optional[Exception] = None
        for attempt in range(4):
            try:
                resp = requests.get(url, params={"db": "pubmed", "id": pmid, "retmode": "json"}, timeout=40)
                resp.raise_for_status()
                payload = resp.json().get("result", {})
                title = payload.get(pmid, {}).get("title", "")
                if title:
                    out[pmid] = title
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(0.8 * (attempt + 1))
        if pmid not in out and last_exc:
            raise last_exc
    return out


def main() -> int:
    args = parse_args()
    workbook = Path(args.workbook)
    reports = Path(args.reports_dir)
    reports.mkdir(parents=True, exist_ok=True)
    csv_path = Path(args.csv_out)
    if not csv_path.is_absolute():
        csv_path = reports / csv_path
    summary_path = Path(args.summary_out)
    if not summary_path.is_absolute():
        summary_path = reports / summary_path

    wb = load_workbook(workbook)
    if args.sheet in wb.sheetnames:
        ws = wb[args.sheet]
    else:
        ws = wb[wb.sheetnames[0]]
    headers = [ws.cell(row=3, column=c).value for c in range(1, ws.max_column + 1)]
    col = {v: i + 1 for i, v in enumerate(headers) if v}

    required = ["ID", "Title", "PubMed URL"]
    missing = [k for k in required if k not in col]
    if missing:
        raise RuntimeError(f"Missing required columns: {missing}")

    rows = []
    pmids = []
    for r in range(4, ws.max_row + 1):
        vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
        if all(v in (None, "") for v in vals):
            continue
        pmid_id = extract_pmid(ws.cell(r, col["ID"]).value)
        pmid_url = extract_pmid(ws.cell(r, col["PubMed URL"]).value)
        pmid = pmid_id or pmid_url
        if pmid:
            pmids.append(pmid)
        rows.append(
            {
                "row": r,
                "title_sheet": str(ws.cell(r, col["Title"]).value or "").strip(),
                "pmid_id": pmid_id or "",
                "pmid_url": pmid_url or "",
                "pmid": pmid or "",
                "pubmed_url": str(ws.cell(r, col["PubMed URL"]).value or "").strip(),
                "pubmed_hyperlink": bool(ws.cell(r, col["PubMed URL"]).hyperlink),
            }
        )

    title_map = fetch_titles(pmids)

    checks = []
    for row in rows:
        pmid = row["pmid"]
        title_pubmed = title_map.get(pmid, "")
        id_url_match = bool(row["pmid_id"] and row["pmid_url"] and row["pmid_id"] == row["pmid_url"])
        if row["pmid_id"] and not row["pmid_url"]:
            id_url_match = True
        expected_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        url_match = bool(expected_url and row["pubmed_url"] == expected_url)
        hyperlink_match = row["pubmed_hyperlink"]
        title_similarity = (
            fuzz.ratio(normalize_title(row["title_sheet"]), normalize_title(title_pubmed)) if title_pubmed else 0.0
        )
        title_match = title_similarity >= 85.0
        overall = bool(pmid and id_url_match and url_match and hyperlink_match and title_match)
        checks.append(
            {
                "row": row["row"],
                "pmid": pmid,
                "id_url_match": "PASS" if id_url_match else "FAIL",
                "url_match": "PASS" if url_match else "FAIL",
                "hyperlink_match": "PASS" if hyperlink_match else "FAIL",
                "title_similarity": f"{title_similarity:.1f}",
                "title_match": "PASS" if title_match else "FAIL",
                "overall": "PASS" if overall else "FAIL",
                "title_pubmed": title_pubmed,
            }
        )

    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(checks[0].keys()) if checks else [])
        if checks:
            writer.writeheader()
            writer.writerows(checks)

    summary = {
        "rows_checked": len(checks),
        "overall_pass": sum(1 for c in checks if c["overall"] == "PASS"),
        "overall_fail": sum(1 for c in checks if c["overall"] == "FAIL"),
        "sheet": ws.title,
        "csv": str(csv_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
