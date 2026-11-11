#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from openpyxl import load_workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter

URL_RE = re.compile(r"https?://[^\s<>\]\"']+")
PUBMED_URL_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?")
PMCID_RE = re.compile(r"\bPMC\d+\b", flags=re.IGNORECASE)
PMID_RE = re.compile(r"\b\d{4,9}\b")

LOW_SHEET = "Low Confidence Items"
MAIN_SHEET = "Medium-High confidence items"
TARGET_SHEET = "Submitted Reference Inventory"

OUTPUT_HEADERS = [
    "Date",
    "Authors",
    "Title",
    "Type of study",
    "Suspected AE Duration (months)",
    "Description",
    "Findings",
    "PubMed URL",
    "Direct Paper URL",
    "ID",
    "Submitted List Entry",
    "Submitted URL",
    "Submitted PMCID",
    "Resolved PMID",
    "Research Item (Y/N)",
    "If Not Research, Why",
    "Included in Database (Y/N)",
    "If Not Included, Why Not",
    "Included In Medium-High (Y/N)",
    "Included In Low (Y/N)",
]

NON_RESEARCH_DOMAINS = {
    "washingtonpost.com",
    "science.org",
    "lupus.org",
    "snfnostos.org",
}

RESEARCH_DOMAINS = {
    "pubmed.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "frontiersin.org",
    "cambridge.org",
    "jocn-journal.com",
    "jaapl.org",
    "doi.org",
}


def normalize_url(value: str) -> str:
    text = str(value or "").strip().rstrip(".,;:)")
    if text.startswith("http://"):
        text = "https://" + text[len("http://") :]
    if "pubmed.ncbi.nlm.nih.gov/" in text and not text.endswith("/"):
        text += "/"
    return text


def extract_urls(text: str) -> List[str]:
    return [normalize_url(m.group(0)) for m in URL_RE.finditer(text or "")]


def extract_pmid(text: str) -> str:
    if not text:
        return ""
    m = PUBMED_URL_RE.search(text)
    if m:
        return m.group(1)
    m2 = re.search(r"\bPMID[:\s]+(\d{4,9})\b", text, flags=re.IGNORECASE)
    if m2:
        return m2.group(1)
    stripped = text.strip()
    if stripped.isdigit() and 4 <= len(stripped) <= 9:
        return stripped
    return ""


def extract_pmcid(text: str) -> str:
    m = PMCID_RE.search(text or "")
    return m.group(0).upper() if m else ""


def header_map(ws, header_row: int = 3) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for c in range(1, ws.max_column + 1):
        h = str(ws.cell(header_row, c).value or "").strip()
        if h:
            out[h] = c
    return out


def row_has_data(ws, row_idx: int) -> bool:
    return any(ws.cell(row_idx, c).value not in (None, "") for c in range(1, ws.max_column + 1))


def infer_title_from_url(url: str) -> str:
    if not url:
        return "Not available"
    parsed = urlparse(url)
    segments = [seg for seg in parsed.path.strip("/").split("/") if seg]
    if not segments:
        return parsed.netloc or "Not available"

    part = segments[-1]
    if part.lower() in {"full", "abstract", "pdf"} and len(segments) >= 2:
        part = segments[-2]
    if part.lower() in {"content", "article", "articles"} and len(segments) >= 2:
        part = segments[-2]

    part = unquote(part)
    if part.startswith("10.") and "/" in part:
        return f"Article DOI {part}"

    part = part.replace("-", " ").replace("_", " ").strip()
    if not part:
        return parsed.netloc or "Not available"
    return part[:1].upper() + part[1:]


def classify_research(url: str, pmid: str, matched: bool) -> Tuple[str, str]:
    if matched:
        return "Y", ""
    if pmid:
        return "Y", ""
    if not url:
        return "N", "No URL/PMID provided."
    netloc = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    if any(d in netloc for d in NON_RESEARCH_DOMAINS):
        return "N", "News/organization/conference source, not a peer-reviewed research article."
    if any(d in netloc for d in RESEARCH_DOMAINS):
        return "Y", ""
    if any(token in path for token in ("/article", "/articles", "/abstract", "/full", "/journals", "/content")):
        return "Y", ""
    return "N", "Could not classify as peer-reviewed research from the submitted link."


def build_submitted_items(list_path: Path) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    idx = 0
    for line_no, raw in enumerate(list_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        urls = extract_urls(line)
        pmid = extract_pmid(line)
        pmcid = extract_pmcid(line)
        if urls:
            for u in urls:
                idx += 1
                items.append(
                    {
                        "item_id": str(idx),
                        "line_no": str(line_no),
                        "raw_entry": line,
                        "submitted_url": u,
                        "pmid": extract_pmid(u) or pmid,
                        "pmcid": extract_pmcid(u) or pmcid,
                    }
                )
            continue
        idx += 1
        items.append(
            {
                "item_id": str(idx),
                "line_no": str(line_no),
                "raw_entry": line,
                "submitted_url": "",
                "pmid": pmid,
                "pmcid": pmcid,
            }
        )
    return items


def collect_db_records(wb) -> Tuple[Dict[str, Dict[str, object]], Dict[str, Dict[str, object]], Dict[str, Dict[str, object]]]:
    records_by_pmid: Dict[str, Dict[str, object]] = {}
    records_by_url: Dict[str, Dict[str, object]] = {}
    records_by_sheet_row: Dict[str, Dict[str, object]] = {}
    for sheet_name in [MAIN_SHEET, LOW_SHEET]:
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        h = header_map(ws)
        id_col = h.get("ID")
        pub_col = h.get("PubMed URL")
        dir_col = h.get("Direct Paper URL")
        for r in range(4, ws.max_row + 1):
            if not row_has_data(ws, r):
                continue
            row = {k: ws.cell(r, c).value for k, c in h.items()}
            pmid = extract_pmid(str(row.get("ID") or "")) or extract_pmid(str(row.get("PubMed URL") or ""))
            key = f"{sheet_name}:{r}"
            row["__sheet_name"] = sheet_name
            row["__row"] = r
            records_by_sheet_row[key] = row
            if pmid and pmid not in records_by_pmid:
                records_by_pmid[pmid] = row
            for col in [pub_col, dir_col]:
                if col is None:
                    continue
                cell = ws.cell(r, col)
                url = normalize_url(str(cell.value or ""))
                if url.startswith("http://") or url.startswith("https://"):
                    records_by_url[url] = row
                if cell.hyperlink is not None and cell.hyperlink.target:
                    records_by_url[normalize_url(str(cell.hyperlink.target))] = row
    return records_by_pmid, records_by_url, records_by_sheet_row


def copy_presentation(main_ws, target_ws, max_col: int) -> None:
    target_ws.freeze_panes = main_ws.freeze_panes
    for c in range(1, max_col + 1):
        letter = get_column_letter(c)
        target_ws.column_dimensions[letter].width = main_ws.column_dimensions[letter].width
    for r in (1, 2, 3):
        target_ws.row_dimensions[r].height = main_ws.row_dimensions[r].height


def run(workbook_path: Path, submitted_list_path: Path, reports_dir: Path) -> Dict[str, object]:
    wb = load_workbook(workbook_path)
    if MAIN_SHEET not in wb.sheetnames:
        raise RuntimeError(f"Missing sheet: {MAIN_SHEET}")
    main_ws = wb[MAIN_SHEET]
    items = build_submitted_items(submitted_list_path)
    records_by_pmid, records_by_url, _records_by_sheet_row = collect_db_records(wb)

    if TARGET_SHEET in wb.sheetnames:
        del wb[TARGET_SHEET]
    ws = wb.create_sheet(TARGET_SHEET)

    headers = list(OUTPUT_HEADERS)

    max_col = len(headers)
    copy_presentation(main_ws, ws, max_col)

    for r in (1, 2):
        for c in range(1, min(main_ws.max_column, max_col) + 1):
            ws.cell(r, c).value = main_ws.cell(r, c).value
    if ws.cell(1, 1).value in (None, ""):
        ws.cell(1, 1).value = "Submitted reference list inventory and inclusion audit"

    for c, h in enumerate(headers, start=1):
        ws.cell(3, c).value = h

    included_count = 0
    rows: List[Dict[str, str]] = []
    for i, item in enumerate(items, start=1):
        pmid = str(item.get("pmid") or "").strip()
        url = normalize_url(str(item.get("submitted_url") or ""))
        pmcid = str(item.get("pmcid") or "").strip().upper()

        matched_row: Optional[Dict[str, object]] = None
        if pmid and pmid in records_by_pmid:
            matched_row = records_by_pmid[pmid]
        elif url and url in records_by_url:
            matched_row = records_by_url[url]
        elif pmid:
            pubmed_url = normalize_url(f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
            if pubmed_url in records_by_url:
                matched_row = records_by_url[pubmed_url]

        if matched_row and not pmid:
            pmid = extract_pmid(str(matched_row.get("ID") or "")) or extract_pmid(str(matched_row.get("PubMed URL") or ""))

        included = matched_row is not None
        in_main = "Y" if included and matched_row and matched_row.get("__sheet_name") == MAIN_SHEET else "N"
        in_low = "Y" if included and matched_row and matched_row.get("__sheet_name") == LOW_SHEET else "N"

        research_flag, not_research_why = classify_research(url, pmid, included)

        if included:
            included_count += 1
            not_included_why = ""
        else:
            if research_flag == "N":
                not_included_why = not_research_why
            elif pmcid and not pmid:
                not_included_why = "PMCID present but no matched PMID/URL in current database."
            elif pmid:
                not_included_why = "PMID not present in current database (likely excluded by filtering/scope)."
            else:
                not_included_why = "No PMID/URL match to current database."

        row_data: Dict[str, object] = {h: "Not available" for h in headers}
        if matched_row:
            for h in headers:
                if h in matched_row:
                    value = matched_row.get(h, "")
                    row_data[h] = value if value not in (None, "") else "Not available"
        else:
            if "Title" in row_data:
                row_data["Title"] = infer_title_from_url(url) or item.get("raw_entry", "")
            if "Type of study" in row_data:
                row_data["Type of study"] = "Not available (not matched to database)"
            if "Description" in row_data:
                row_data["Description"] = "Not available (not matched to database)"
            if "Findings" in row_data:
                row_data["Findings"] = "Not available (not matched to database)"
            if "Date" in row_data:
                row_data["Date"] = "Not available"
            if "Authors" in row_data:
                row_data["Authors"] = "Not available"
            if "Suspected AE Duration (months)" in row_data:
                row_data["Suspected AE Duration (months)"] = "Not available"
            if "ID" in row_data:
                row_data["ID"] = pmid or "Not available"
            if "PubMed URL" in row_data and pmid:
                row_data["PubMed URL"] = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            elif "PubMed URL" in row_data:
                row_data["PubMed URL"] = "Not available"
            if "Direct Paper URL" in row_data and url:
                row_data["Direct Paper URL"] = url
            elif "Direct Paper URL" in row_data:
                row_data["Direct Paper URL"] = "Not available"

        row_data["Submitted List Entry"] = item.get("raw_entry", "") or "Not available"
        row_data["Submitted URL"] = url or "Not provided"
        row_data["Submitted PMCID"] = pmcid or "Not provided"
        row_data["Resolved PMID"] = pmid or "Not resolved"
        row_data["Research Item (Y/N)"] = research_flag
        row_data["If Not Research, Why"] = (
            not_research_why if research_flag == "N" else "Not applicable (research item)"
        )
        row_data["Included in Database (Y/N)"] = "Y" if included else "N"
        row_data["If Not Included, Why Not"] = (
            not_included_why if not_included_why else "Included in database"
        )
        row_data["Included In Medium-High (Y/N)"] = in_main
        row_data["Included In Low (Y/N)"] = in_low

        row_idx = 3 + i
        for c, h in enumerate(headers, start=1):
            ws.cell(row_idx, c).value = row_data.get(h, "")

        rows.append(
            {
                "row": row_idx,
                "raw_entry": str(item.get("raw_entry", "")),
                "pmid": pmid,
                "submitted_url": url,
                "research": research_flag,
                "included": "Y" if included else "N",
                "not_included_why": not_included_why,
            }
        )

    # hyperlinks + wrap alignment
    hmap = {h: i + 1 for i, h in enumerate(headers)}
    for r in range(4, ws.max_row + 1):
        if not row_has_data(ws, r):
            continue
        for h in ["PubMed URL", "Direct Paper URL", "Submitted URL"]:
            c = hmap.get(h)
            if c is None:
                continue
            v = normalize_url(str(ws.cell(r, c).value or ""))
            if v.startswith("http://") or v.startswith("https://"):
                ws.cell(r, c).value = v
                ws.cell(r, c).hyperlink = v
                ws.cell(r, c).style = "Hyperlink"

        for h in ["Title", "Description", "Findings", "Duration Evidence", "Submitted List Entry", "If Not Research, Why", "If Not Included, Why Not"]:
            c = hmap.get(h)
            if c is None:
                continue
            ws.cell(r, c).alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = None

    for h in ["Submitted List Entry", "If Not Research, Why", "If Not Included, Why Not"]:
        c = hmap.get(h)
        if c is not None:
            letter = get_column_letter(c)
            if ws.column_dimensions[letter].width is None or ws.column_dimensions[letter].width < 42:
                ws.column_dimensions[letter].width = 42

    width_overrides = {
        "Title": 52,
        "Description": 60,
        "Findings": 55,
        "PubMed URL": 40,
        "Direct Paper URL": 45,
        "Submitted URL": 45,
        "Type of study": 34,
        "Authors": 30,
        "If Not Included, Why Not": 48,
        "If Not Research, Why": 48,
    }
    for header, width in width_overrides.items():
        c = hmap.get(header)
        if c is None:
            continue
        ws.column_dimensions[get_column_letter(c)].width = width

    ws.auto_filter.ref = f"A3:{get_column_letter(max_col)}{ws.max_row}"
    wb.save(workbook_path)

    # QA step 1: completeness
    qa1 = {"name": "qa1_completeness", "ok": len(items) == (ws.max_row - 3), "items": len(items), "rows_written": ws.max_row - 3}
    # QA step 2: inclusion logic
    qa2_errors = []
    for r in range(4, ws.max_row + 1):
        inc = str(ws.cell(r, hmap["Included in Database (Y/N)"]).value or "").strip().upper()
        why = str(ws.cell(r, hmap["If Not Included, Why Not"]).value or "").strip()
        if inc == "N" and (not why or why == "Included in database"):
            qa2_errors.append({"row": r, "error": "Missing reason for non-included item"})
        if inc == "Y" and why != "Included in database":
            qa2_errors.append({"row": r, "error": "Included item reason should be 'Included in database'"})
    qa2 = {"name": "qa2_inclusion_consistency", "ok": len(qa2_errors) == 0, "errors": qa2_errors[:20], "error_count": len(qa2_errors)}
    # QA step 3: cleanliness + link format/hyperlink
    qa3_errors = []
    for r in range(4, ws.max_row + 1):
        for c in range(1, ws.max_column + 1):
            value = ws.cell(r, c).value
            if value in (None, ""):
                qa3_errors.append({"row": r, "column": headers[c - 1], "error": "Blank cell"})
                continue
            if isinstance(value, str) and value.strip().upper() == "NR":
                qa3_errors.append({"row": r, "column": headers[c - 1], "error": "NR placeholder"})
        for h in ["Submitted URL", "PubMed URL", "Direct Paper URL"]:
            c = hmap.get(h)
            if c is None:
                continue
            v = str(ws.cell(r, c).value or "").strip()
            if not v or v.lower().startswith("not "):
                continue
            if not (v.startswith("http://") or v.startswith("https://")):
                qa3_errors.append({"row": r, "column": h, "error": "Invalid URL format"})
            if ws.cell(r, c).hyperlink is None:
                qa3_errors.append({"row": r, "column": h, "error": "Missing hyperlink"})
    qa3 = {"name": "qa3_link_hyperlink_check", "ok": len(qa3_errors) == 0, "errors": qa3_errors[:20], "error_count": len(qa3_errors)}

    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "submitted_inventory_rows.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (reports_dir / "submitted_inventory_qa1.json").write_text(json.dumps(qa1, indent=2), encoding="utf-8")
    (reports_dir / "submitted_inventory_qa2.json").write_text(json.dumps(qa2, indent=2), encoding="utf-8")
    (reports_dir / "submitted_inventory_qa3.json").write_text(json.dumps(qa3, indent=2), encoding="utf-8")

    return {
        "items_total": len(items),
        "included_total": included_count,
        "sheet_rows": ws.max_row - 3,
        "qa1_ok": qa1["ok"],
        "qa2_ok": qa2["ok"],
        "qa3_ok": qa3["ok"],
    }


def main() -> int:
    base = Path("/Users/zeryabmeyer/Documents/Autoimmune Encephalitis")
    workbook = base / "Autoimmune Encephalitis Research paper summary.xlsx"
    submitted = base / "submitted_reference_list.txt"
    reports = base / "reports"
    out = run(workbook, submitted, reports)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
