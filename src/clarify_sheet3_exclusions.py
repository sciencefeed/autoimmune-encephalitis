#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlparse

import requests
from openpyxl import load_workbook
from openpyxl.styles import Alignment


WORKBOOK = Path("/work/Autoimmune Encephalitis Research paper summary.xlsx")
TARGET_SHEET = "Submitted Reference Inventory"
MAIN_SHEET = "Medium-High confidence items"
LOW_SHEET = "Low Confidence Items"
HEADER_ROW = 3
MIN_DURATION_DAYS = 90
CONFIDENCE_THRESHOLD = "LOW"
NON_RESEARCH_DOMAINS = (
    "washingtonpost.com",
    "science.org",
    "lupus.org",
    "snfnostos.org",
)


def load_pipeline_module():
    spec = importlib.util.spec_from_file_location("ae_pipeline", "/work/src/ae_review_pipeline.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def header_map(ws) -> Dict[str, int]:
    return {
        str(ws.cell(HEADER_ROW, c).value).strip(): c
        for c in range(1, ws.max_column + 1)
        if ws.cell(HEADER_ROW, c).value not in (None, "")
    }


def row_has_values(ws, row_idx: int) -> bool:
    return any(ws.cell(row_idx, c).value not in (None, "") for c in range(1, ws.max_column + 1))


def parse_pmid(value: object) -> str:
    raw = str(value or "").strip()
    m = re.search(r"\b(\d{4,9})\b", raw)
    return m.group(1) if m else ""


def fetch_abstracts(pmids: List[str]) -> Dict[str, str]:
    if not pmids:
        return {}
    out: Dict[str, str] = {}
    unique = sorted(set(pmids), key=lambda v: int(v))
    for i in range(0, len(unique), 100):
        batch = unique[i : i + 100]
        resp = requests.get(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
            params={"db": "pubmed", "id": ",".join(batch), "retmode": "xml"},
            timeout=40,
        )
        resp.raise_for_status()
        text = resp.text
        # lightweight parse to avoid extra deps; enough for abstract extraction here
        for pmid in batch:
            pmid_block = re.search(
                rf"<PMID[^>]*>\s*{pmid}\s*</PMID>.*?(?=<PubmedArticle>|$)",
                text,
                flags=re.DOTALL,
            )
            if not pmid_block:
                continue
            block = pmid_block.group(0)
            parts = re.findall(r"<AbstractText[^>]*>(.*?)</AbstractText>", block, flags=re.DOTALL)
            clean_parts = [re.sub(r"<[^>]+>", "", p).strip() for p in parts if p.strip()]
            out[pmid] = " ".join(clean_parts).strip()
    return out


def collect_db_pmids(wb, main_h: Dict[str, int], low_h: Dict[str, int]) -> Dict[str, set]:
    pmids_main, pmids_low = set(), set()

    if MAIN_SHEET in wb.sheetnames:
        ws = wb[MAIN_SHEET]
        id_col = main_h.get("ID")
        for r in range(4, ws.max_row + 1):
            if not row_has_values(ws, r) or id_col is None:
                continue
            p = parse_pmid(ws.cell(r, id_col).value)
            if p:
                pmids_main.add(p)

    if LOW_SHEET in wb.sheetnames:
        ws = wb[LOW_SHEET]
        id_col = low_h.get("ID")
        for r in range(4, ws.max_row + 1):
            if not row_has_values(ws, r) or id_col is None:
                continue
            p = parse_pmid(ws.cell(r, id_col).value)
            if p:
                pmids_low.add(p)

    return {"main": pmids_main, "low": pmids_low}


def main() -> int:
    ae = load_pipeline_module()
    wb = load_workbook(WORKBOOK)
    ws = wb[TARGET_SHEET]
    h = header_map(ws)
    main_h = header_map(wb[MAIN_SHEET]) if MAIN_SHEET in wb.sheetnames else {}
    low_h = header_map(wb[LOW_SHEET]) if LOW_SHEET in wb.sheetnames else {}
    db_pmids = collect_db_pmids(wb, main_h, low_h)

    required = [
        "Title",
        "Direct Paper URL",
        "Resolved PMID",
        "Included in Database (Y/N)",
        "If Not Included, Why Not",
    ]
    missing = [c for c in required if c not in h]
    if missing:
        raise RuntimeError(f"Missing required sheet columns: {missing}")

    target_rows = []
    pmids_to_fetch = []
    for r in range(4, ws.max_row + 1):
        if not row_has_values(ws, r):
            continue
        included = str(ws.cell(r, h["Included in Database (Y/N)"]).value or "").strip().upper()
        if included != "N":
            continue
        pmid = parse_pmid(ws.cell(r, h["Resolved PMID"]).value)
        url = str(ws.cell(r, h["Direct Paper URL"]).value or "").strip()
        title = str(ws.cell(r, h["Title"]).value or "").strip()
        target_rows.append({"row": r, "pmid": pmid, "url": url, "title": title})
        if pmid:
            pmids_to_fetch.append(pmid)

    abstracts = fetch_abstracts(pmids_to_fetch)
    threshold_rank = ae.CONFIDENCE_RANK.get(CONFIDENCE_THRESHOLD, 1)

    counts = {
        "non_research_source": 0,
        "identifier_unresolved": 0,
        "duration_below_threshold": 0,
        "duration_not_extractable": 0,
        "confidence_below_threshold": 0,
        "scope_mismatch": 0,
    }

    for item in target_rows:
        r = item["row"]
        pmid = item["pmid"]
        url = item["url"]
        title = item["title"]
        domain = urlparse(url).netloc.lower()

        reason = ""
        if not pmid:
            if any(d in domain for d in NON_RESEARCH_DOMAINS):
                reason = (
                    "EXCLUSION_TRACE: Gate1(source-type)=FAIL: non-research/news/conference source. "
                    "Gate2(identifier)=SKIP. Gate3(duration)=SKIP. Final=Excluded before paper-screening."
                )
                counts["non_research_source"] += 1
            else:
                reason = (
                    "EXCLUSION_TRACE: Gate1(source-type)=POSSIBLE_RESEARCH. "
                    "Gate2(identifier)=FAIL: PMID could not be resolved from URL/PMCID/DOI/PII. "
                    "Gate3(duration)=SKIP. Final=Excluded due to unresolved identifier."
                )
                counts["identifier_unresolved"] += 1
        else:
            # included should already be N; confirm it is not in retained db tabs
            in_retained = pmid in db_pmids["main"] or pmid in db_pmids["low"]
            if in_retained:
                reason = (
                    "EXCLUSION_TRACE: Data inconsistency detected; PMID appears in retained database "
                    "while Included=No. Please re-run membership sync."
                )
            else:
                abstract = abstracts.get(pmid, "")
                if not abstract:
                    reason = (
                        f"EXCLUSION_TRACE: Gate1(source-type)=PASS (PMID {pmid}). "
                        "Gate2(identifier)=PASS. Gate3(duration)=FAIL: abstract unavailable, "
                        "duration rule could not be applied. Final=Excluded from retained set."
                    )
                    counts["duration_not_extractable"] += 1
                else:
                    d_days, d_months, _evidence, d_conf = ae.extract_duration_info(title, abstract)
                    if d_days is None:
                        reason = (
                            f"EXCLUSION_TRACE: Gate1(source-type)=PASS (PMID {pmid}). "
                            "Gate2(identifier)=PASS. Gate3(duration)=FAIL: no explicit pre-diagnosis "
                            "duration could be extracted from abstract. Final=Excluded."
                        )
                        counts["duration_not_extractable"] += 1
                    elif d_days < MIN_DURATION_DAYS:
                        reason = (
                            f"EXCLUSION_TRACE: Gate1(source-type)=PASS (PMID {pmid}). Gate2(identifier)=PASS. "
                            f"Gate3(duration-threshold)=FAIL: extracted {d_days} days (~{d_months} months) "
                            f"< required {MIN_DURATION_DAYS} days. Final=Excluded."
                        )
                        counts["duration_below_threshold"] += 1
                    elif ae.CONFIDENCE_RANK.get(str(d_conf).upper(), 0) < threshold_rank:
                        reason = (
                            f"EXCLUSION_TRACE: Gate1(source-type)=PASS (PMID {pmid}). Gate2(identifier)=PASS. "
                            f"Gate3(confidence)=FAIL: extracted confidence={d_conf}, threshold={CONFIDENCE_THRESHOLD}. "
                            "Final=Excluded."
                        )
                        counts["confidence_below_threshold"] += 1
                    else:
                        reason = (
                            f"EXCLUSION_TRACE: Gate1(source-type)=PASS (PMID {pmid}). Gate2(identifier)=PASS. "
                            f"Gate3(duration)=PASS ({d_days} days, confidence={d_conf}). "
                            "Gate4(retrieval-scope)=FAIL: paper not present in current retained database candidate set. "
                            "Final=Excluded by scope/retrieval mismatch."
                        )
                        counts["scope_mismatch"] += 1

        cell = ws.cell(r, h["If Not Included, Why Not"])
        cell.value = reason
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(WORKBOOK)
    report = {"rows_updated": len(target_rows), "counts": counts}
    reports_dir = Path("/work/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "sheet3_exclusion_trace_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
