#!/usr/bin/env python3
"""
Autoimmune encephalitis + psychosis review pipeline.

Stages:
1) Retrieval/Search
2) Metadata QA
3) Abstract/verbatim QA

Design requirements:
- Do not overwrite source workbook by default.
- Use openpyxl only for workbook writes.
- Keep retrieval and QA stages explicit and separated.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from copy import copy
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

import requests
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from rapidfuzz import fuzz


REQUIRED_HEADERS = [
    "Title",
    "ID",
    "PubMed URL",
]

LOW_CONF_SHEET_TITLE = "Low Confidence Items"
SUBMITTED_INVENTORY_SHEET_TITLE = "Submitted Reference Inventory"
WRAP_TEXT_HEADERS = {"Title", "Description", "Findings", "Duration Evidence"}

NON_RESEARCH_DOMAIN_HINTS = (
    "washingtonpost.com",
    "science.org",
    "lupus.org",
    "snfnostos.org",
)

RESEARCH_DOMAIN_HINTS = (
    "pubmed.ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "frontiersin.org",
    "cambridge.org",
    "jocn-journal.com",
    "jaapl.org",
    "doi.org",
)

SUBMITTED_INVENTORY_HEADERS = [
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

DEFAULT_QUERY = (
    "("
    "\"autoimmune encephalitis\"[Title/Abstract] "
    "OR \"anti-NMDA receptor encephalitis\"[Title/Abstract] "
    "OR \"limbic encephalitis\"[Title/Abstract]"
    ") AND ("
    "psychosis[Title/Abstract] "
    "OR psychotic[Title/Abstract] "
    "OR schizophrenia[Title/Abstract] "
    "OR schizoaffective[Title/Abstract]"
    ")"
)

PUBMED_URL_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/?")
PMCID_RE = re.compile(r"\bPMC\d+\b", flags=re.IGNORECASE)
PMID_RE = re.compile(r"^\d{4,9}$")
DOI_RE = re.compile(r"\b10\.\d{4,9}/\S+\b", re.IGNORECASE)
WS_RE = re.compile(r"\s+")
URL_RE = re.compile(r"https?://[^\s<>\]\"']+")
DURATION_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:[-–]\s*|to\s+)?(\d+(?:\.\d+)?)?\s*[-–]?\s*"
    r"(days?|weeks?|months?|mos?|years?|yrs?)\b",
    flags=re.IGNORECASE,
)
WORD_DURATION_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\s*[- ]\s*"
    r"(days?|weeks?|months?|years?)\b",
    flags=re.IGNORECASE,
)
MONTH_YEAR_RE = re.compile(
    r"\b("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\s+((?:19|20)\d{2})\b",
    flags=re.IGNORECASE,
)
DAY_MONTH_YEAR_RE = re.compile(
    r"\b(\d{1,2})\s+("
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    r")\s+((?:19|20)\d{2})\b",
    flags=re.IGNORECASE,
)

CONFIDENCE_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
DURATION_INCLUDE_KEYWORDS = (
    "before diagnosis",
    "prior to diagnosis",
    "before being diagnosed",
    "until diagnosis",
    "pre-diagnosis",
    "prediagnosis",
    "prodrom",
    "psychiatric",
    "psychosis",
    "psychotic",
    "hallucination",
    "delusion",
    "behavioral",
    "symptom",
    "misdiagn",
    "preced",
)
DURATION_EXCLUDE_KEYWORDS = (
    "follow-up",
    "follow up",
    "post-treatment",
    "post treatment",
    "after treatment",
    "after discharge",
    "outcome at",
    "followed for",
    "over the past",
    "within",
    "participants were included",
    "patients were included",
    "mean age",
    "ages ",
    "cohort",
    "prospective",
    "retrospective",
)

WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}

MONTH_NAME_TO_NUM = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

ONSET_HINTS = (
    "onset",
    "history of",
    "had",
    "for ",
    "since",
    "developed",
    "preceded",
    "prodrom",
    "symptom",
    "psycho",
)

DX_HINTS = (
    "diagnos",
    "diagnosed",
    "admitted",
    "hospital",
    "confirmed",
    "identified",
    "workup",
    "evaluation",
    "found to have",
)

CHRONIC_QUERY_CANDIDATES = [
    ("chronic", "\"chronic\"[Title/Abstract]"),
    ("persistent", "\"persistent\"[Title/Abstract]"),
    ("prolonged", "\"prolonged\"[Title/Abstract]"),
    ("long-term", "\"long-term\"[Title/Abstract]"),
    ("long term", "\"long term\"[Title/Abstract]"),
    ("diagnostic delay", "\"diagnostic delay\"[Title/Abstract]"),
    ("history of", "\"history of\"[Title/Abstract]"),
    ("months", "months[Title/Abstract]"),
    ("years", "years[Title/Abstract]"),
    ("refractory", "\"refractory\"[Title/Abstract]"),
    ("treatment resistant", "\"treatment-resistant\"[Title/Abstract] OR \"treatment resistant\"[Title/Abstract]"),
    ("prodrom", "prodrom*[Title/Abstract]"),
    ("duration", "duration[Title/Abstract]"),
    ("misdiagn", "misdiagn*[Title/Abstract]"),
]

CHRONIC_QUERY_DEFAULT_BLOCK = (
    "\"chronic\"[Title/Abstract] OR \"persistent\"[Title/Abstract] OR "
    "\"prolonged\"[Title/Abstract] OR \"long-term\"[Title/Abstract] OR "
    "months[Title/Abstract] OR years[Title/Abstract] OR "
    "\"diagnostic delay\"[Title/Abstract] OR \"history of\"[Title/Abstract]"
)

SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

MONTH_MAP = {
    "jan": "January",
    "feb": "February",
    "mar": "March",
    "apr": "April",
    "may": "May",
    "jun": "June",
    "jul": "July",
    "aug": "August",
    "sep": "September",
    "oct": "October",
    "nov": "November",
    "dec": "December",
}


@dataclass
class CandidateRecord:
    topic: str
    date: str
    month: str
    authors: str
    title: str
    pmid: str
    study_type: str
    participants: str
    description: str
    findings: str
    pubmed_url: str
    direct_paper_url: str


def normalize_space(text: str) -> str:
    return WS_RE.sub(" ", text).strip()


def normalize_title(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return normalize_space(cleaned)


def normalize_pubmed_url(pmid: str) -> str:
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"


def normalize_doi(doi_raw: str) -> str:
    cleaned = str(doi_raw or "").strip()
    if not cleaned:
        return ""
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    cleaned = cleaned.split("?", 1)[0].split("#", 1)[0].strip().rstrip(".,;:)")
    for suffix in ("/full", "/abstract", "/pdf"):
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
            break
    return cleaned.strip()


def normalize_url(url: str) -> str:
    cleaned = str(url).strip()
    cleaned = cleaned.rstrip(".,;:)")
    if cleaned.startswith("http://"):
        cleaned = "https://" + cleaned[len("http://") :]
    if "pubmed.ncbi.nlm.nih.gov/" in cleaned and not cleaned.endswith("/"):
        cleaned += "/"
    return cleaned


def chunked(items: Sequence[str], size: int) -> Iterable[List[str]]:
    for idx in range(0, len(items), size):
        yield list(items[idx : idx + size])


def extract_pmid(text: object) -> Optional[str]:
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    if DOI_RE.search(raw):
        return None
    match = PUBMED_URL_RE.search(raw)
    if match:
        return match.group(1)
    if PMID_RE.fullmatch(raw):
        return raw
    pmid_label = re.search(r"\bPMID[:\s]+(\d{4,9})\b", raw, flags=re.IGNORECASE)
    if pmid_label:
        return pmid_label.group(1)
    return None


def extract_urls(text: str) -> List[str]:
    urls = [normalize_url(match.group(0)) for match in URL_RE.finditer(text or "")]
    return [u for u in urls if u]


def extract_pmcid(text: object) -> Optional[str]:
    if text is None:
        return None
    match = PMCID_RE.search(str(text))
    if not match:
        return None
    return match.group(0).upper()


def infer_title_from_url(url: str) -> str:
    if not url:
        return "Not available"
    parsed = urlparse(url)
    segments = [segment for segment in parsed.path.strip("/").split("/") if segment]
    if not segments:
        return parsed.netloc or "Not available"

    slug = segments[-1]
    if slug.lower() in {"full", "abstract", "pdf"} and len(segments) >= 2:
        slug = segments[-2]
    if slug.lower() in {"article", "articles", "content"} and len(segments) >= 2:
        slug = segments[-2]

    text = normalize_space(slug.replace("-", " ").replace("_", " "))
    return text[:1].upper() + text[1:] if text else (parsed.netloc or "Not available")


def first_sentence(text: str) -> str:
    text = normalize_space(text)
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)
    sentence = parts[0].strip()
    if len(sentence) > 500:
        return sentence[:497].rstrip() + "..."
    return sentence


def split_sentences(text: str) -> List[str]:
    cleaned = normalize_space(text)
    if not cleaned:
        return []
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]


def duration_to_days(value: float, unit: str) -> int:
    key = unit.lower()
    if key.startswith("day"):
        factor = 1.0
    elif key.startswith("week"):
        factor = 7.0
    elif key.startswith("mo") or key.startswith("month"):
        factor = 30.4375
    elif key.startswith("yr") or key.startswith("year"):
        factor = 365.25
    else:
        factor = 1.0
    return int(round(value * factor))


def duration_confidence(sentence: str, match_start: int, match_end: int) -> str:
    lower = sentence.lower()
    window = lower[max(0, match_start - 35) : min(len(lower), match_end + 35)]
    include_hit = any(k in lower for k in DURATION_INCLUDE_KEYWORDS)
    exclude_hit = any(k in lower for k in DURATION_EXCLUDE_KEYWORDS)
    symptom_hit = any(
        token in lower
        for token in ("symptom", "psychiatr", "psychos", "hallucin", "delusion", "behavior", "encephalitis")
    )

    explicit_pre_dx = any(
        phrase in lower
        for phrase in (
            "before diagnosis",
            "prior to diagnosis",
            "before being diagnosed",
            "until diagnosis",
            "diagnostic delay",
            "prodrom",
            "history of",
            "preceded by",
        )
    ) or ("before" in window and "diagnos" in lower)

    if exclude_hit:
        return "LOW"
    if symptom_hit and explicit_pre_dx:
        return "HIGH"
    if symptom_hit and include_hit and ("for " in window or "history" in window or "duration" in lower):
        return "MEDIUM"
    return "LOW"


def is_age_expression(sentence: str, start: int, end: int, unit: str) -> bool:
    lower = sentence.lower()
    window = lower[max(0, start - 16) : min(len(lower), end + 16)]
    before = lower[max(0, start - 24) : start]
    unit_lower = unit.lower()

    if unit_lower.startswith("year") or unit_lower.startswith("yr"):
        if "year-old" in window or "years-old" in window or "year old" in window or "years old" in window:
            return True
        if re.search(r"\baged?\s+\d{1,3}\b", window):
            return True
        if re.search(r"\bage[s]?\b", before):
            return True
        if "older than" in before:
            return True
    return False


def extract_duration_info(title: str, abstract: str) -> Tuple[Optional[int], Optional[float], str, str]:
    sentences = split_sentences(abstract)
    if title:
        sentences = [normalize_space(title)] + sentences

    best: Optional[Tuple[int, str, str]] = None  # days, confidence, evidence
    for sentence in sentences:
        for match in DURATION_RE.finditer(sentence):
            start = float(match.group(1))
            end = float(match.group(2)) if match.group(2) else start
            value = max(start, end)
            unit = match.group(3)
            if is_age_expression(sentence, match.start(), match.end(), unit):
                continue
            conf = duration_confidence(sentence, match.start(), match.end())
            days = duration_to_days(value, unit)
            candidate = (days, conf, sentence)
            if best is None:
                best = candidate
            else:
                if CONFIDENCE_RANK[candidate[1]] > CONFIDENCE_RANK[best[1]]:
                    best = candidate
                elif CONFIDENCE_RANK[candidate[1]] == CONFIDENCE_RANK[best[1]] and candidate[0] > best[0]:
                    best = candidate

        for match in WORD_DURATION_RE.finditer(sentence):
            word = match.group(1).lower()
            value = float(WORD_NUMBERS.get(word, 0))
            if value <= 0:
                continue
            unit = match.group(2)
            if is_age_expression(sentence, match.start(), match.end(), unit):
                continue
            conf = duration_confidence(sentence, match.start(), match.end())
            days = duration_to_days(value, unit)
            candidate = (days, conf, sentence)
            if best is None:
                best = candidate
            else:
                if CONFIDENCE_RANK[candidate[1]] > CONFIDENCE_RANK[best[1]]:
                    best = candidate
                elif CONFIDENCE_RANK[candidate[1]] == CONFIDENCE_RANK[best[1]] and candidate[0] > best[0]:
                    best = candidate

    if best is None:
        return None, None, "", "NONE"

    days, confidence, evidence = best
    months = round(days / 30.4375, 1)
    return days, months, first_sentence(evidence), confidence


def parse_month_name(value: str) -> Optional[int]:
    return MONTH_NAME_TO_NUM.get(value.strip().lower())


def find_date_mentions(sentence: str) -> List[Tuple[date, str]]:
    mentions: List[Tuple[date, str]] = []
    for match in DAY_MONTH_YEAR_RE.finditer(sentence):
        day = int(match.group(1))
        month = parse_month_name(match.group(2))
        year = int(match.group(3))
        if not month:
            continue
        try:
            dt = date(year, month, day)
        except ValueError:
            continue
        mentions.append((dt, match.group(0)))

    for match in MONTH_YEAR_RE.finditer(sentence):
        month = parse_month_name(match.group(1))
        year = int(match.group(2))
        if not month:
            continue
        dt = date(year, month, 1)
        mentions.append((dt, match.group(0)))
    return mentions


def extract_duration_from_dates(title: str, abstract: str) -> Tuple[Optional[int], Optional[float], str, str]:
    sentences = split_sentences(abstract)
    if title:
        sentences = [normalize_space(title)] + sentences

    onset_candidates: List[Tuple[date, str]] = []
    dx_candidates: List[Tuple[date, str]] = []

    for sentence in sentences:
        lower = sentence.lower()
        mentions = find_date_mentions(sentence)
        if not mentions:
            continue

        has_onset = any(hint in lower for hint in ONSET_HINTS)
        has_dx = any(hint in lower for hint in DX_HINTS)

        if has_onset:
            onset_candidates.extend([(dt, sentence) for dt, _ in mentions])
        if has_dx:
            dx_candidates.extend([(dt, sentence) for dt, _ in mentions])

    if not onset_candidates or not dx_candidates:
        return None, None, "", "NONE"

    onset_date = min(dt for dt, _ in onset_candidates)
    dx_date = max(dt for dt, _ in dx_candidates if dt >= onset_date) if any(
        dt >= onset_date for dt, _ in dx_candidates
    ) else None
    if not dx_date:
        return None, None, "", "NONE"

    delta_days = (dx_date - onset_date).days
    if delta_days < 1:
        return None, None, "", "NONE"

    onset_sentence = next((s for dt, s in onset_candidates if dt == onset_date), "")
    dx_sentence = next((s for dt, s in dx_candidates if dt == dx_date), "")
    evidence = f"Onset context: {first_sentence(onset_sentence)} Diagnosis context: {first_sentence(dx_sentence)}"
    months = round(delta_days / 30.4375, 1)
    confidence = "MEDIUM"
    if "before diagnosis" in evidence.lower() or "prior to diagnosis" in evidence.lower():
        confidence = "HIGH"
    return delta_days, months, evidence[:800], confidence


def downgraded_confidence(confidence: str) -> str:
    if confidence == "HIGH":
        return "MEDIUM"
    if confidence == "MEDIUM":
        return "LOW"
    return "LOW"


def adjudicate_duration(
    agent_a: Tuple[Optional[int], Optional[float], str, str],
    agent_b: Tuple[Optional[int], Optional[float], str, str],
) -> Tuple[Optional[int], Optional[float], str, str, str, Optional[int], Optional[int]]:
    a_days, a_months, a_ev, a_conf = agent_a
    b_days, b_months, b_ev, b_conf = agent_b

    if a_days is None and b_days is None:
        return None, None, "", "NONE", "NONE", None, None
    if a_days is not None and b_days is None:
        return a_days, a_months, a_ev, a_conf, "AGENT_A", a_days, None
    if a_days is None and b_days is not None:
        return b_days, b_months, b_ev, b_conf, "AGENT_B", None, b_days

    assert a_days is not None and b_days is not None
    diff = abs(a_days - b_days)
    if diff <= 45:
        if CONFIDENCE_RANK.get(a_conf, 0) > CONFIDENCE_RANK.get(b_conf, 0):
            chosen = ("AGENT_A+CONSENSUS", a_days, a_months, a_ev, a_conf)
        elif CONFIDENCE_RANK.get(b_conf, 0) > CONFIDENCE_RANK.get(a_conf, 0):
            chosen = ("AGENT_B+CONSENSUS", b_days, b_months, b_ev, b_conf)
        else:
            if a_days >= b_days:
                chosen = ("AGENT_A+CONSENSUS", a_days, a_months, a_ev, a_conf)
            else:
                chosen = ("AGENT_B+CONSENSUS", b_days, b_months, b_ev, b_conf)
        method, days, months, ev, conf = chosen
        return days, months, ev, conf, method, a_days, b_days

    # conflict: choose more conservative duration with downgraded confidence
    if a_days <= b_days:
        days = a_days
        months = a_months
        evidence = f"Conflict A vs B; conservative pick A. A: {first_sentence(a_ev)} | B: {first_sentence(b_ev)}"
        conf = downgraded_confidence(a_conf)
        method = "CONFLICT_PICK_A"
    else:
        days = b_days
        months = b_months
        evidence = f"Conflict A vs B; conservative pick B. A: {first_sentence(a_ev)} | B: {first_sentence(b_ev)}"
        conf = downgraded_confidence(b_conf)
        method = "CONFLICT_PICK_B"
    return days, months, evidence[:800], conf, method, a_days, b_days


def infer_participant_count(study_type: str, title: str, abstract: str) -> str:
    text = normalize_space(f"{title}. {abstract}")
    lower = text.lower()
    study_lower = str(study_type or "").lower()

    if "case report" in lower or "case report" in study_lower:
        return "1"

    n_match = re.search(r"\bn\s*[:=]\s*(\d{1,4})\b", lower)
    if n_match:
        return n_match.group(1)

    matches = [int(m.group(1)) for m in re.finditer(r"\b(\d{1,4})\s+(patients|participants|subjects|cases)\b", lower)]
    if matches:
        return str(max(matches))

    for word, number in WORD_NUMBERS.items():
        if re.search(rf"\b{word}\s+(patients|participants|subjects|cases)\b", lower):
            return str(number)

    return "NR"


def extract_findings_text(abstract: str) -> str:
    text = normalize_space(abstract)
    if not text:
        return "NR (no abstract available)"

    lower = text.lower()
    for label in ("[conclusions]", "[conclusion]", "[interpretation]", "[results]"):
        idx = lower.find(label)
        if idx >= 0:
            segment = text[idx + len(label) :].strip()
            next_label = segment.find("[")
            if next_label > 0:
                segment = segment[:next_label].strip()
            candidate = first_sentence(segment)
            if candidate:
                return candidate

    parts = split_sentences(text)
    if parts:
        return first_sentence(parts[-1])
    return first_sentence(text) or "NR"


def parse_pubdate(pubdate: str) -> Tuple[str, str]:
    value = (pubdate or "").strip()
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", value)
    year = year_match.group(1) if year_match else ""

    month = ""
    lower = value.lower()
    for short, full in MONTH_MAP.items():
        if re.search(rf"\b{short}\b", lower):
            month = full
            break
    return year, month


def derive_direct_paper_url(summary: Dict[str, object], pmid: str) -> str:
    articleids = summary.get("articleids", [])
    pmc_id = ""
    doi = ""
    if isinstance(articleids, list):
        for item in articleids:
            if not isinstance(item, dict):
                continue
            id_type = str(item.get("idtype", "")).strip().lower()
            value = str(item.get("value", "")).strip()
            if not value:
                continue
            if id_type == "pmc":
                pmc_id = value if value.upper().startswith("PMC") else f"PMC{value}"
            elif id_type == "doi":
                doi = normalize_doi(value)

    if pmc_id:
        return f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc_id}/"
    if doi:
        return f"https://doi.org/{doi}"
    return normalize_pubmed_url(pmid)


class PubMedClient:
    def __init__(self, email: Optional[str], api_key: Optional[str], tool_name: str = "ae-review-pipeline"):
        self.session = requests.Session()
        self.base_params: Dict[str, str] = {"tool": tool_name}
        if email:
            self.base_params["email"] = email
        if api_key:
            self.base_params["api_key"] = api_key
        self.headers = {"User-Agent": f"{tool_name}/1.0 (+systematic-review-workflow)"}

    def _request(self, url: str, params: Dict[str, str], expect: str) -> requests.Response:
        merged = dict(self.base_params)
        merged.update(params)
        last_exc: Optional[Exception] = None
        for attempt in range(4):
            try:
                response = self.session.get(url, params=merged, headers=self.headers, timeout=40)
                response.raise_for_status()
                if expect == "json":
                    _ = response.json()
                return response
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt == 3:
                    raise
                time.sleep(0.75 * (attempt + 1))
        if last_exc:
            raise last_exc
        raise RuntimeError("Request failed unexpectedly")

    def search_pmids(self, query: str, max_results: int, mindate: str, maxdate: str) -> List[str]:
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": str(max_results),
            "datetype": "pdat",
            "mindate": mindate,
            "maxdate": maxdate,
        }
        response = self._request(SEARCH_URL, params, expect="json")
        payload = response.json()
        return payload.get("esearchresult", {}).get("idlist", [])

    def fetch_summaries(self, pmids: Sequence[str]) -> Dict[str, Dict[str, object]]:
        if not pmids:
            return {}
        summaries: Dict[str, Dict[str, object]] = {}
        unique = sorted(set(pmids), key=lambda v: int(v))
        for group in chunked(unique, 200):
            params = {
                "db": "pubmed",
                "id": ",".join(group),
                "retmode": "json",
            }
            response = self._request(SUMMARY_URL, params, expect="json")
            payload = response.json().get("result", {})
            for pmid in group:
                doc = payload.get(pmid)
                if doc:
                    summaries[pmid] = doc
        return summaries

    def fetch_abstracts(self, pmids: Sequence[str]) -> Dict[str, str]:
        if not pmids:
            return {}
        abstracts: Dict[str, str] = {}
        unique = sorted(set(pmids), key=lambda v: int(v))
        for group in chunked(unique, 100):
            params = {
                "db": "pubmed",
                "id": ",".join(group),
                "retmode": "xml",
            }
            response = self._request(EFETCH_URL, params, expect="xml")
            root = ET.fromstring(response.text)
            for article in root.findall(".//PubmedArticle"):
                pmid_node = article.find(".//MedlineCitation/PMID")
                if pmid_node is None or not pmid_node.text:
                    continue
                pmid = pmid_node.text.strip()
                segments: List[str] = []
                for node in article.findall(".//Article/Abstract/AbstractText"):
                    text = normalize_space("".join(node.itertext()))
                    if not text:
                        continue
                    label = node.attrib.get("Label")
                    if label:
                        text = f"[{label}] {text}"
                    segments.append(text)
                abstracts[pmid] = " ".join(segments).strip()
        return abstracts


def find_header_row_and_map(sheet: Worksheet) -> Tuple[int, Dict[str, int]]:
    for row_idx in range(1, min(sheet.max_row, 50) + 1):
        row_values = [sheet.cell(row=row_idx, column=col).value for col in range(1, sheet.max_column + 1)]
        text_values = [str(v).strip() if v is not None else "" for v in row_values]
        if all(required in text_values for required in REQUIRED_HEADERS):
            mapping: Dict[str, int] = {}
            for col_idx, value in enumerate(text_values, start=1):
                if value:
                    mapping[value] = col_idx
            missing = [h for h in REQUIRED_HEADERS if h not in mapping]
            if missing:
                raise ValueError(f"Header row found at row {row_idx}, but missing columns: {missing}")
            return row_idx, mapping
    raise ValueError("Could not locate workbook header row containing required columns")


def row_is_empty(sheet: Worksheet, row_idx: int, header_map: Dict[str, int]) -> bool:
    check_headers = [
        "Title",
        "ID",
        "PubMed URL",
        "Direct Paper URL",
        "Authors",
        "Date",
        "Description",
        "Findings",
    ]
    check_cols = [header_map[h] for h in check_headers if h in header_map]
    if not check_cols:
        check_cols = list(header_map.values())
    for col_idx in check_cols:
        value = sheet.cell(row=row_idx, column=col_idx).value
        if value not in (None, ""):
            return False
    return True


def first_empty_data_row(sheet: Worksheet, header_row: int, header_map: Dict[str, int]) -> int:
    row_idx = header_row + 1
    while row_idx <= max(sheet.max_row, header_row + 1):
        if row_is_empty(sheet, row_idx, header_map):
            return row_idx
        row_idx += 1
    return row_idx


def existing_pmids(sheet: Worksheet, header_row: int, header_map: Dict[str, int]) -> Dict[str, int]:
    seen: Dict[str, int] = {}
    for row_idx in range(header_row + 1, sheet.max_row + 1):
        id_value = sheet.cell(row=row_idx, column=header_map["ID"]).value
        url_value = sheet.cell(row=row_idx, column=header_map["PubMed URL"]).value
        pmid = extract_pmid(id_value) or extract_pmid(url_value)
        if pmid:
            seen[pmid] = row_idx
    return seen


def build_candidate_records(
    pmids: Sequence[str],
    summaries: Dict[str, Dict[str, object]],
    abstracts: Dict[str, str],
) -> List[CandidateRecord]:
    records: List[CandidateRecord] = []
    for pmid in pmids:
        summary = summaries.get(pmid)
        if not summary:
            continue
        title = normalize_space(str(summary.get("title", "")))
        if not title:
            continue
        pubdate = str(summary.get("pubdate", ""))
        year, month = parse_pubdate(pubdate)

        authors = format_authors_from_summary(summary)

        pubtypes_raw = summary.get("pubtype", [])
        study_type = "; ".join([str(p).strip() for p in pubtypes_raw if str(p).strip()]) or "NR"

        abstract = abstracts.get(pmid, "")
        description = first_sentence(abstract)
        direct_paper_url = derive_direct_paper_url(summary, pmid)

        records.append(
            CandidateRecord(
                topic="Autoimmune encephalitis with psychosis",
                date=year,
                month=month,
                authors=authors,
                title=title,
                pmid=pmid,
                study_type=study_type,
                participants="NR",
                description=description or "NR (no abstract available)",
                findings="NR",
                pubmed_url=normalize_pubmed_url(pmid),
                direct_paper_url=direct_paper_url,
            )
        )
    return records


def format_authors_from_summary(summary: Dict[str, object]) -> str:
    authors_raw = summary.get("authors", [])
    author_names: List[str] = []
    if isinstance(authors_raw, list):
        for author in authors_raw[:4]:
            name = str(author.get("name", "")).strip() if isinstance(author, dict) else str(author).strip()
            if name:
                author_names.append(name)
    authors = ", ".join(author_names)
    if isinstance(authors_raw, list) and len(authors_raw) > 4:
        authors = f"{authors}, et al."
    return authors


def append_records_to_sheet(
    sheet: Worksheet,
    header_row: int,
    header_map: Dict[str, int],
    records: Sequence[CandidateRecord],
    direct_col: int,
) -> List[int]:
    def set_link_cell(row_idx: int, col_idx: int, url: str) -> None:
        cell = sheet.cell(row=row_idx, column=col_idx)
        value = normalize_url(url)
        cell.value = value
        if value:
            cell.hyperlink = value
            cell.style = "Hyperlink"

    def set_value_if_present(row_idx: int, header: str, value: object) -> None:
        col_idx = header_map.get(header)
        if col_idx is None:
            return
        sheet.cell(row=row_idx, column=col_idx).value = value

    row_idx = first_empty_data_row(sheet, header_row, header_map)
    written_rows: List[int] = []
    for record in records:
        set_value_if_present(row_idx, "Topic", record.topic)
        set_value_if_present(row_idx, "Date", record.date)
        set_value_if_present(row_idx, "Month", record.month)
        set_value_if_present(row_idx, "Authors", record.authors)
        set_value_if_present(row_idx, "Title", record.title)
        set_value_if_present(row_idx, "ID", record.pmid)
        set_value_if_present(row_idx, "Type of study", record.study_type)
        set_value_if_present(row_idx, "Number of participants", record.participants)
        set_value_if_present(row_idx, "Description", record.description)
        set_value_if_present(row_idx, "Findings", record.findings)
        set_link_cell(row_idx, header_map["PubMed URL"], record.pubmed_url)
        set_link_cell(row_idx, direct_col, record.direct_paper_url)
        written_rows.append(row_idx)
        row_idx += 1
    return written_rows


def sheet_rows_as_records(sheet: Worksheet, header_row: int, header_map: Dict[str, int]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for row_idx in range(header_row + 1, sheet.max_row + 1):
        if row_is_empty(sheet, row_idx, header_map):
            continue
        row_data: Dict[str, object] = {"row_index": row_idx}
        for header, col_idx in header_map.items():
            row_data[header] = sheet.cell(row=row_idx, column=col_idx).value
        rows.append(row_data)
    return rows


def ensure_clean_sheet(workbook, title: str):
    if title in workbook.sheetnames:
        del workbook[title]
    return workbook.create_sheet(title=title)


def ensure_column(sheet: Worksheet, header_row: int, header_name: str) -> int:
    for col_idx in range(1, sheet.max_column + 1):
        value = sheet.cell(row=header_row, column=col_idx).value
        if normalize_space(str(value or "")) == header_name:
            return col_idx
    new_col = sheet.max_column + 1
    sheet.cell(row=header_row, column=new_col).value = header_name
    return new_col


def compute_direct_link_map(records: Sequence[Dict[str, object]], client: PubMedClient) -> Dict[str, str]:
    pmids = sorted(
        {
            p
            for p in (
                extract_pmid(r.get("ID")) or extract_pmid(r.get("PubMed URL"))
                for r in records
            )
            if p
        },
        key=lambda v: int(v),
    )
    summaries = client.fetch_summaries(pmids)
    direct_links: Dict[str, str] = {}
    for pmid in pmids:
        summary = summaries.get(pmid, {})
        direct_links[pmid] = derive_direct_paper_url(summary, pmid)
    return direct_links


def apply_main_sheet_enrichment(
    sheet: Worksheet,
    header_row: int,
    header_map: Dict[str, int],
    direct_col: int,
    direct_link_map: Dict[str, str],
) -> None:
    def set_link(row_idx: int, col_idx: int, url: str) -> None:
        value = normalize_url(url)
        cell = sheet.cell(row=row_idx, column=col_idx)
        cell.value = value
        if value:
            cell.hyperlink = value
            cell.style = "Hyperlink"

    for row_idx in range(header_row + 1, sheet.max_row + 1):
        if row_is_empty(sheet, row_idx, header_map):
            continue

        id_value = sheet.cell(row=row_idx, column=header_map["ID"]).value
        url_value = sheet.cell(row=row_idx, column=header_map["PubMed URL"]).value
        pmid = extract_pmid(id_value) or extract_pmid(url_value)

        if pmid:
            pubmed_url = normalize_pubmed_url(pmid)
            set_link(row_idx, header_map["PubMed URL"], pubmed_url)
            direct_url = direct_link_map.get(pmid) or pubmed_url
            set_link(row_idx, direct_col, direct_url)
        elif url_value:
            set_link(row_idx, header_map["PubMed URL"], str(url_value))
            set_link(row_idx, direct_col, str(url_value))

        desc_col = header_map.get("Description")
        if desc_col is not None:
            if not normalize_space(str(sheet.cell(row=row_idx, column=desc_col).value or "")):
                sheet.cell(row=row_idx, column=desc_col).value = "NR (no abstract available)"

        findings_col = header_map.get("Findings")
        if findings_col is not None:
            if not normalize_space(str(sheet.cell(row=row_idx, column=findings_col).value or "")):
                sheet.cell(row=row_idx, column=findings_col).value = "NR"


def enrich_content_and_duration(
    sheet: Worksheet,
    header_row: int,
    header_map: Dict[str, int],
    client: PubMedClient,
    min_duration_days: int,
    preferred_duration_days: int,
    confidence_threshold: str,
) -> Dict[str, int]:
    duration_days_col = ensure_column(sheet, header_row, "Suspected AE Duration (days)")
    duration_months_col = ensure_column(sheet, header_row, "Suspected AE Duration (months)")
    duration_evidence_col = ensure_column(sheet, header_row, "Duration Evidence")
    duration_conf_col = ensure_column(sheet, header_row, "Duration Confidence")
    duration_method_col = ensure_column(sheet, header_row, "Duration Method")
    duration_agent_a_col = ensure_column(sheet, header_row, "Duration Agent A (days)")
    duration_agent_b_col = ensure_column(sheet, header_row, "Duration Agent B (days)")
    include_3m_col = ensure_column(sheet, header_row, ">=3 months (Y/N)")
    include_6m_col = ensure_column(sheet, header_row, ">=6 months (Y/N)")
    include_3m_high_col = ensure_column(sheet, header_row, ">=3 months @HIGH (Y/N)")
    include_3m_med_col = ensure_column(sheet, header_row, ">=3 months @MEDIUM (Y/N)")
    include_3m_low_col = ensure_column(sheet, header_row, ">=3 months @LOW (Y/N)")
    low_added_col = ensure_column(sheet, header_row, "Newly Included at LOW Threshold (Y/N)")
    inclusion_label_col = ensure_column(sheet, header_row, "Inclusion Confidence Label")

    data_rows = sheet_rows_as_records(sheet, header_row, header_map)
    pmids = sorted(
        {
            p
            for p in (
                extract_pmid(r.get("ID")) or extract_pmid(r.get("PubMed URL"))
                for r in data_rows
            )
            if p
        },
        key=lambda v: int(v),
    )
    abstracts = client.fetch_abstracts(pmids)

    explicit_duration_rows = 0
    include_rows = 0
    include_6m_rows = 0
    low_added_rows = 0
    threshold_rank = CONFIDENCE_RANK.get(confidence_threshold, CONFIDENCE_RANK["HIGH"])

    for record in data_rows:
        row_idx = int(record["row_index"])
        pmid = extract_pmid(record.get("ID")) or extract_pmid(record.get("PubMed URL"))
        title = normalize_space(str(record.get("Title") or ""))
        abstract = abstracts.get(pmid or "", "")
        study_type = normalize_space(str(record.get("Type of study") or ""))

        participants = infer_participant_count(study_type, title, abstract)
        findings = extract_findings_text(abstract)
        desc_col = header_map.get("Description")
        if desc_col is not None:
            desc_value = normalize_space(str(sheet.cell(row=row_idx, column=desc_col).value or ""))
            if not desc_value or desc_value.upper() == "NR":
                sheet.cell(row=row_idx, column=desc_col).value = (
                    first_sentence(abstract) if abstract else "NR (no abstract available)"
                )

        participants_col = header_map.get("Number of participants")
        if participants_col is not None:
            sheet.cell(row=row_idx, column=participants_col).value = participants

        findings_col = header_map.get("Findings")
        if findings_col is not None:
            sheet.cell(row=row_idx, column=findings_col).value = findings

        agent_a = extract_duration_info(title, abstract)
        agent_b = extract_duration_from_dates(title, abstract)
        (
            duration_days,
            duration_months,
            duration_evidence,
            duration_confidence_value,
            duration_method,
            duration_agent_a_days,
            duration_agent_b_days,
        ) = adjudicate_duration(agent_a, agent_b)

        sheet.cell(row=row_idx, column=duration_agent_a_col).value = (
            "" if duration_agent_a_days is None else duration_agent_a_days
        )
        sheet.cell(row=row_idx, column=duration_agent_b_col).value = (
            "" if duration_agent_b_days is None else duration_agent_b_days
        )
        sheet.cell(row=row_idx, column=duration_method_col).value = duration_method

        if duration_days is None:
            sheet.cell(row=row_idx, column=duration_days_col).value = ""
            sheet.cell(row=row_idx, column=duration_months_col).value = ""
            sheet.cell(row=row_idx, column=duration_evidence_col).value = "NR"
            sheet.cell(row=row_idx, column=duration_conf_col).value = "NONE"
            sheet.cell(row=row_idx, column=include_3m_col).value = "N"
            sheet.cell(row=row_idx, column=include_6m_col).value = "N"
            sheet.cell(row=row_idx, column=include_3m_high_col).value = "N"
            sheet.cell(row=row_idx, column=include_3m_med_col).value = "N"
            sheet.cell(row=row_idx, column=include_3m_low_col).value = "N"
            sheet.cell(row=row_idx, column=low_added_col).value = "N"
            sheet.cell(row=row_idx, column=inclusion_label_col).value = "EXCLUDED_NO_DURATION"
            continue

        explicit_duration_rows += 1
        sheet.cell(row=row_idx, column=duration_days_col).value = duration_days
        sheet.cell(row=row_idx, column=duration_months_col).value = duration_months
        sheet.cell(row=row_idx, column=duration_evidence_col).value = duration_evidence or "NR"
        sheet.cell(row=row_idx, column=duration_conf_col).value = duration_confidence_value

        include_high = (
            CONFIDENCE_RANK.get(duration_confidence_value, 0) >= CONFIDENCE_RANK["HIGH"]
            and duration_days >= min_duration_days
        )
        include_med = (
            CONFIDENCE_RANK.get(duration_confidence_value, 0) >= CONFIDENCE_RANK["MEDIUM"]
            and duration_days >= min_duration_days
        )
        include_low = duration_days >= min_duration_days
        sheet.cell(row=row_idx, column=include_3m_high_col).value = "Y" if include_high else "N"
        sheet.cell(row=row_idx, column=include_3m_med_col).value = "Y" if include_med else "N"
        sheet.cell(row=row_idx, column=include_3m_low_col).value = "Y" if include_low else "N"

        low_added = include_low and not include_med
        sheet.cell(row=row_idx, column=low_added_col).value = "Y" if low_added else "N"
        if low_added:
            sheet.cell(row=row_idx, column=inclusion_label_col).value = "LOW_CONFIDENCE_ADDED"
            low_added_rows += 1
        elif include_med and not include_high:
            sheet.cell(row=row_idx, column=inclusion_label_col).value = "MEDIUM_CONFIDENCE"
        elif include_high:
            sheet.cell(row=row_idx, column=inclusion_label_col).value = "HIGH_CONFIDENCE"
        else:
            sheet.cell(row=row_idx, column=inclusion_label_col).value = "EXCLUDED_BY_DURATION"

        confidence_ok = CONFIDENCE_RANK.get(duration_confidence_value, 0) >= threshold_rank
        include_3m = confidence_ok and duration_days >= min_duration_days
        include_6m = confidence_ok and duration_days >= preferred_duration_days
        sheet.cell(row=row_idx, column=include_3m_col).value = "Y" if include_3m else "N"
        sheet.cell(row=row_idx, column=include_6m_col).value = "Y" if include_6m else "N"
        if include_3m:
            include_rows += 1
        if include_6m:
            include_6m_rows += 1

    return {
        "duration_days_col": duration_days_col,
        "duration_months_col": duration_months_col,
        "duration_evidence_col": duration_evidence_col,
        "duration_conf_col": duration_conf_col,
        "duration_method_col": duration_method_col,
        "duration_agent_a_col": duration_agent_a_col,
        "duration_agent_b_col": duration_agent_b_col,
        "include_3m_col": include_3m_col,
        "include_6m_col": include_6m_col,
        "explicit_duration_rows": explicit_duration_rows,
        "include_rows": include_rows,
        "include_6m_rows": include_6m_rows,
        "low_added_rows": low_added_rows,
    }


def row_has_any_value(sheet: Worksheet, row_idx: int, max_col: int) -> bool:
    for col_idx in range(1, max_col + 1):
        if sheet.cell(row=row_idx, column=col_idx).value not in (None, ""):
            return True
    return False


def sort_and_filter_by_duration(
    sheet: Worksheet,
    header_row: int,
    duration_days_col: int,
    min_duration_days: int,
    confidence_col: int,
    confidence_threshold: str,
    pubmed_col: int,
    direct_col: int,
) -> Dict[str, int]:
    max_col = sheet.max_column
    max_row = sheet.max_row
    threshold_rank = CONFIDENCE_RANK.get(confidence_threshold, CONFIDENCE_RANK["HIGH"])

    kept: List[Tuple[float, List[object]]] = []
    total_rows = 0
    dropped_missing_duration = 0
    dropped_short_duration = 0
    dropped_low_confidence = 0

    for row_idx in range(header_row + 1, max_row + 1):
        if not row_has_any_value(sheet, row_idx, max_col):
            continue
        total_rows += 1

        raw_days = sheet.cell(row=row_idx, column=duration_days_col).value
        try:
            days = float(raw_days)
        except (TypeError, ValueError):
            dropped_missing_duration += 1
            continue

        confidence = str(sheet.cell(row=row_idx, column=confidence_col).value or "NONE").strip().upper()
        if CONFIDENCE_RANK.get(confidence, 0) < threshold_rank:
            dropped_low_confidence += 1
            continue
        if days < float(min_duration_days):
            dropped_short_duration += 1
            continue

        values = [sheet.cell(row=row_idx, column=c).value for c in range(1, max_col + 1)]
        kept.append((days, values))

    kept.sort(key=lambda item: item[0], reverse=True)

    for row_idx in range(header_row + 1, max_row + 1):
        for col_idx in range(1, max_col + 1):
            cell = sheet.cell(row=row_idx, column=col_idx)
            cell.value = None
            cell.hyperlink = None

    write_row = header_row + 1
    for _, values in kept:
        for col_idx, value in enumerate(values, start=1):
            sheet.cell(row=write_row, column=col_idx).value = value
        write_row += 1

    for row_idx in range(header_row + 1, header_row + 1 + len(kept)):
        for col_idx in (pubmed_col, direct_col):
            raw = sheet.cell(row=row_idx, column=col_idx).value
            url = normalize_url(str(raw or ""))
            if not url:
                continue
            cell = sheet.cell(row=row_idx, column=col_idx)
            cell.value = url
            cell.hyperlink = url
            cell.style = "Hyperlink"

    # Remove physically empty trailing rows so downstream QA and reviewers do not
    # see a long blank tail after filtering.
    first_trailing_row = header_row + 1 + len(kept)
    if first_trailing_row <= max_row:
        sheet.delete_rows(first_trailing_row, max_row - first_trailing_row + 1)

    return {
        "rows_total_before_filter": total_rows,
        "rows_kept_after_filter": len(kept),
        "rows_dropped_missing_duration": dropped_missing_duration,
        "rows_dropped_short_duration": dropped_short_duration,
        "rows_dropped_low_confidence": dropped_low_confidence,
    }


def header_map_from_row(sheet: Worksheet, header_row: int) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for col_idx in range(1, sheet.max_column + 1):
        value = normalize_space(str(sheet.cell(row=header_row, column=col_idx).value or ""))
        if value:
            mapping[value] = col_idx
    return mapping


def extract_row_values_and_links(sheet: Worksheet, row_idx: int, max_col: int) -> Tuple[List[object], Dict[int, str]]:
    values: List[object] = []
    links: Dict[int, str] = {}
    for col_idx in range(1, max_col + 1):
        cell = sheet.cell(row=row_idx, column=col_idx)
        values.append(cell.value)
        target = ""
        if cell.hyperlink is not None and cell.hyperlink.target:
            target = normalize_url(str(cell.hyperlink.target))
        if not target:
            raw = normalize_url(str(cell.value or ""))
            if raw.startswith("http://") or raw.startswith("https://"):
                target = raw
        if target:
            links[col_idx] = target
    return values, links


def write_compacted_rows(
    sheet: Worksheet,
    header_row: int,
    max_col: int,
    rows: Sequence[Tuple[List[object], Dict[int, str]]],
) -> int:
    max_row = sheet.max_row
    for row_idx in range(header_row + 1, max_row + 1):
        for col_idx in range(1, max_col + 1):
            cell = sheet.cell(row=row_idx, column=col_idx)
            cell.value = None
            cell.hyperlink = None

    write_row = header_row + 1
    for values, links in rows:
        for col_idx in range(1, max_col + 1):
            if col_idx <= len(values):
                sheet.cell(row=write_row, column=col_idx).value = values[col_idx - 1]
        for col_idx, link in links.items():
            if col_idx > max_col:
                continue
            cell = sheet.cell(row=write_row, column=col_idx)
            cell.hyperlink = link
            cell.style = "Hyperlink"
        sheet.row_dimensions[write_row].height = None
        write_row += 1

    if write_row <= max_row:
        sheet.delete_rows(write_row, max_row - write_row + 1)
    return len(rows)


def copy_sheet_presentation(
    source_sheet: Worksheet,
    target_sheet: Worksheet,
    header_row: int,
    max_col: int,
) -> None:
    target_sheet.freeze_panes = source_sheet.freeze_panes
    if source_sheet.auto_filter and source_sheet.auto_filter.ref:
        target_sheet.auto_filter.ref = source_sheet.auto_filter.ref

    for col_idx in range(1, max_col + 1):
        col_letter = get_column_letter(col_idx)
        src_dim = source_sheet.column_dimensions[col_letter]
        dst_dim = target_sheet.column_dimensions[col_letter]
        dst_dim.width = src_dim.width
        dst_dim.hidden = src_dim.hidden
        dst_dim.outlineLevel = src_dim.outlineLevel
        dst_dim.collapsed = src_dim.collapsed

    for row_idx in range(1, header_row + 1):
        target_sheet.row_dimensions[row_idx].height = source_sheet.row_dimensions[row_idx].height

    for merged in list(target_sheet.merged_cells.ranges):
        target_sheet.unmerge_cells(str(merged))
    for merged in source_sheet.merged_cells.ranges:
        min_col, min_row, max_merged_col, max_merged_row = merged.bounds
        if max_merged_row <= header_row and max_merged_col <= max_col:
            target_sheet.merge_cells(str(merged))

    for row_idx in range(1, header_row + 1):
        for col_idx in range(1, max_col + 1):
            src_cell = source_sheet.cell(row=row_idx, column=col_idx)
            dst_cell = target_sheet.cell(row=row_idx, column=col_idx)
            dst_cell._style = copy(src_cell._style)
            dst_cell.number_format = src_cell.number_format
            dst_cell.protection = copy(src_cell.protection)
            dst_cell.alignment = copy(src_cell.alignment)


def apply_template_data_style(
    source_sheet: Worksheet,
    target_sheet: Worksheet,
    header_row: int,
    max_col: int,
) -> None:
    template_row = header_row + 1
    for row_idx in range(header_row + 1, source_sheet.max_row + 1):
        if row_has_any_value(source_sheet, row_idx, max_col):
            template_row = row_idx
            break

    for row_idx in range(header_row + 1, target_sheet.max_row + 1):
        if not row_has_any_value(target_sheet, row_idx, max_col):
            continue
        for col_idx in range(1, max_col + 1):
            src_cell = source_sheet.cell(row=template_row, column=col_idx)
            dst_cell = target_sheet.cell(row=row_idx, column=col_idx)
            dst_cell._style = copy(src_cell._style)
            dst_cell.number_format = src_cell.number_format
            dst_cell.protection = copy(src_cell.protection)
            dst_cell.alignment = copy(src_cell.alignment)
        target_sheet.row_dimensions[row_idx].height = None


def enforce_wrapped_text_columns(sheet: Worksheet, header_row: int, max_col: int) -> None:
    header_map = header_map_from_row(sheet, header_row)
    wrap_cols = [header_map[h] for h in WRAP_TEXT_HEADERS if h in header_map]
    for row_idx in range(header_row + 1, sheet.max_row + 1):
        if not row_has_any_value(sheet, row_idx, max_col):
            continue
        for col_idx in wrap_cols:
            cell = sheet.cell(row=row_idx, column=col_idx)
            alignment = copy(cell.alignment)
            alignment.wrap_text = True
            if not alignment.vertical:
                alignment.vertical = "top"
            cell.alignment = alignment
        sheet.row_dimensions[row_idx].height = None


def split_low_confidence_sheet(
    workbook,
    main_sheet: Worksheet,
    header_row: int,
) -> Dict[str, int]:
    header_map = header_map_from_row(main_sheet, header_row)
    duration_conf_col = header_map.get("Duration Confidence")
    low_added_col = header_map.get("Newly Included at LOW Threshold (Y/N)")
    inclusion_label_col = header_map.get("Inclusion Confidence Label")

    if duration_conf_col is None and low_added_col is None and inclusion_label_col is None:
        return {"main_rows": 0, "low_rows": 0}

    max_col = main_sheet.max_column
    low_rows: List[Tuple[List[object], Dict[int, str]]] = []
    main_rows: List[Tuple[List[object], Dict[int, str]]] = []

    for row_idx in range(header_row + 1, main_sheet.max_row + 1):
        if not row_has_any_value(main_sheet, row_idx, max_col):
            continue
        values, links = extract_row_values_and_links(main_sheet, row_idx, max_col)

        label_value = (
            normalize_space(str(main_sheet.cell(row=row_idx, column=inclusion_label_col).value or "")).upper()
            if inclusion_label_col is not None
            else ""
        )
        conf_value = (
            normalize_space(str(main_sheet.cell(row=row_idx, column=duration_conf_col).value or "")).upper()
            if duration_conf_col is not None
            else ""
        )
        low_added_value = (
            normalize_space(str(main_sheet.cell(row=row_idx, column=low_added_col).value or "")).upper()
            if low_added_col is not None
            else ""
        )
        is_low = (
            label_value == "LOW_CONFIDENCE_ADDED"
            or conf_value == "LOW"
            or low_added_value == "Y"
        )
        if is_low:
            low_rows.append((values, links))
        else:
            main_rows.append((values, links))

    if not low_rows and LOW_CONF_SHEET_TITLE in workbook.sheetnames:
        existing_low = workbook[LOW_CONF_SHEET_TITLE]
        existing_low_rows = 0
        for row_idx in range(header_row + 1, existing_low.max_row + 1):
            if row_has_any_value(existing_low, row_idx, existing_low.max_column):
                existing_low_rows += 1
        if existing_low_rows > 0:
            copy_sheet_presentation(main_sheet, existing_low, header_row, main_sheet.max_column)
            apply_template_data_style(main_sheet, existing_low, header_row, main_sheet.max_column)
            enforce_wrapped_text_columns(existing_low, header_row, main_sheet.max_column)
            return {"main_rows": len(main_rows), "low_rows": existing_low_rows}

    write_compacted_rows(main_sheet, header_row, max_col, main_rows)

    low_sheet = ensure_clean_sheet(workbook, LOW_CONF_SHEET_TITLE)
    for row_idx in range(1, header_row + 1):
        for col_idx in range(1, max_col + 1):
            low_sheet.cell(row=row_idx, column=col_idx).value = main_sheet.cell(row=row_idx, column=col_idx).value
    write_compacted_rows(low_sheet, header_row, max_col, low_rows)

    copy_sheet_presentation(main_sheet, low_sheet, header_row, max_col)
    apply_template_data_style(main_sheet, low_sheet, header_row, max_col)
    enforce_wrapped_text_columns(low_sheet, header_row, max_col)

    return {"main_rows": len(main_rows), "low_rows": len(low_rows)}


def parse_submitted_reference_items(list_path: Path) -> List[Dict[str, object]]:
    items: List[Dict[str, object]] = []
    item_id = 0
    raw_text = list_path.read_text(encoding="utf-8")

    for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        urls = extract_urls(line)
        explicit_pmids = re.findall(r"\bPMID[:\s]+(\d{4,9})\b", line, flags=re.IGNORECASE)
        line_is_pmid = line if PMID_RE.fullmatch(line) else ""
        line_pmid = explicit_pmids[0] if explicit_pmids else (line_is_pmid or (extract_pmid(line) or ""))
        pmcid_in_line = extract_pmcid(line)

        if urls:
            for url in urls:
                item_id += 1
                item_pmid = extract_pmid(url) or line_pmid
                item_pmcid = extract_pmcid(url) or pmcid_in_line
                items.append(
                    {
                        "item_id": item_id,
                        "line_no": line_no,
                        "raw_entry": line,
                        "submitted_url": normalize_url(url),
                        "submitted_pmid": item_pmid or "",
                        "submitted_pmcid": item_pmcid or "",
                    }
                )
            continue

        if explicit_pmids:
            for pmid in list(dict.fromkeys(explicit_pmids)):
                item_id += 1
                items.append(
                    {
                        "item_id": item_id,
                        "line_no": line_no,
                        "raw_entry": line,
                        "submitted_url": "",
                        "submitted_pmid": pmid,
                        "submitted_pmcid": pmcid_in_line or "",
                    }
                )
            continue

        if line_pmid:
            item_id += 1
            items.append(
                {
                    "item_id": item_id,
                    "line_no": line_no,
                    "raw_entry": line,
                    "submitted_url": "",
                    "submitted_pmid": line_pmid,
                    "submitted_pmcid": pmcid_in_line or "",
                }
            )
            continue

        item_id += 1
        items.append(
            {
                "item_id": item_id,
                "line_no": line_no,
                "raw_entry": line,
                "submitted_url": "",
                "submitted_pmid": "",
                "submitted_pmcid": pmcid_in_line or "",
            }
        )
    return items


def classify_research_item(
    submitted_url: str,
    resolved_pmid: str,
    summary: Dict[str, object],
) -> Tuple[str, str]:
    pubtypes = [str(p).strip().lower() for p in summary.get("pubtype", []) if str(p).strip()]
    non_research_pubtypes = {
        "newspaper article",
        "news",
        "comment",
        "editorial",
        "interview",
        "biography",
    }
    if pubtypes and any(p in non_research_pubtypes for p in pubtypes):
        return "N", f"PubMed publication type is non-research ({'; '.join(summary.get('pubtype', []))})."

    if resolved_pmid:
        return "Y", ""

    url = normalize_url(submitted_url)
    if not url:
        return "N", "No paper URL or PMID was provided."

    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower()

    if any(hint in domain for hint in NON_RESEARCH_DOMAIN_HINTS):
        return "N", "News/organization/conference webpage, not a peer-reviewed research article."

    if any(hint in domain for hint in RESEARCH_DOMAIN_HINTS):
        return "Y", ""

    likely_research_path = any(
        token in path
        for token in (
            "/article/",
            "/articles/",
            "/abstract",
            "/full",
            "/content/",
            "/journals/",
        )
    )
    likely_research_domain = any(
        token in domain
        for token in (
            "journal",
            "journals",
            "springer",
            "wiley",
            "sciencedirect",
            "oup",
            "bmj",
            "nature",
            "thelancet",
            "elsevier",
        )
    )
    if likely_research_path or likely_research_domain:
        return "Y", ""

    return "N", "Could not confirm this URL as a peer-reviewed research source."


def extract_doi_from_text(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    match = DOI_RE.search(raw)
    if match:
        return normalize_doi(match.group(0))
    doi_url_match = re.search(r"doi\.org/([^?\s#]+)", raw, flags=re.IGNORECASE)
    if doi_url_match:
        return normalize_doi(doi_url_match.group(1))
    return ""


def resolve_doi_to_pmid(client: PubMedClient, doi: str) -> str:
    normalized = normalize_doi(doi)
    if not normalized:
        return ""
    queries = [
        f'"{normalized}"[AID]',
        f'"{normalized}"[Title/Abstract]',
    ]
    for query in queries:
        try:
            pmids = client.search_pmids(query=query, max_results=3, mindate="1900/01/01", maxdate="2100/12/31")
        except Exception:
            pmids = []
        if pmids:
            return pmids[0]
    return ""


def extract_pii_from_text(text: str) -> str:
    raw = str(text or "")
    if not raw:
        return ""
    patterns = [
        r"\bS\d{4}-\d{4}\(\d{2}\)\d{5}-\d\b",
        r"\bS\d{15,17}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return ""


def resolve_pii_to_pmid(client: PubMedClient, pii: str) -> str:
    value = normalize_space(str(pii or ""))
    if not value:
        return ""
    query = f'"{value}"[AID]'
    try:
        pmids = client.search_pmids(query=query, max_results=3, mindate="1900/01/01", maxdate="2100/12/31")
    except Exception:
        pmids = []
    return pmids[0] if pmids else ""


def fetch_web_title(url: str) -> str:
    cleaned = normalize_url(url)
    if not cleaned:
        return ""
    try:
        response = requests.get(cleaned, timeout=25, headers={"User-Agent": "ae-review-pipeline/1.0"})
        response.raise_for_status()
    except Exception:
        return ""
    text = response.text or ""
    og_title = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        text,
        flags=re.IGNORECASE,
    )
    if og_title:
        return normalize_space(og_title.group(1))
    title_match = re.search(r"<title>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        return normalize_space(title_match.group(1))
    return ""


def fetch_web_metadata(url: str) -> Tuple[str, str]:
    cleaned = normalize_url(url)
    if not cleaned:
        return "", ""
    try:
        response = requests.get(cleaned, timeout=25, headers={"User-Agent": "ae-review-pipeline/1.0"})
        response.raise_for_status()
    except Exception:
        return "", ""

    html = response.text or ""
    title = ""
    doi = ""

    title_patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']citation_title["\'][^>]+content=["\']([^"\']+)["\']',
        r"<title>(.*?)</title>",
    ]
    for pattern in title_patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE | re.DOTALL)
        if match:
            title = normalize_space(match.group(1))
            if title:
                break

    doi_patterns = [
        r'<meta[^>]+name=["\']citation_doi["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']dc\.identifier["\'][^>]+content=["\']doi:([^"\']+)["\']',
        r"https?://doi\.org/([^\"'<>\\s]+)",
        r"\b10\.\d{4,9}/[^\s\"'<>]+",
    ]
    for pattern in doi_patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            doi = normalize_doi(match.group(1) if match.lastindex else match.group(0))
            if doi:
                break

    return title, doi


def build_database_membership(
    workbook,
    main_sheet: Worksheet,
    header_row: int,
) -> Dict[str, object]:
    sheet_names = [main_sheet.title]
    if LOW_CONF_SHEET_TITLE in workbook.sheetnames:
        sheet_names.append(LOW_CONF_SHEET_TITLE)

    pmids_all: Set[str] = set()
    urls_all: Set[str] = set()
    pmids_main: Set[str] = set()
    pmids_low: Set[str] = set()
    urls_main: Set[str] = set()
    urls_low: Set[str] = set()
    records_by_pmid: Dict[str, Dict[str, object]] = {}
    records_by_url: Dict[str, Dict[str, object]] = {}

    for sheet_name in sheet_names:
        ws = workbook[sheet_name]
        hmap = header_map_from_row(ws, header_row)
        id_col = hmap.get("ID")
        pub_col = hmap.get("PubMed URL")
        direct_col = hmap.get("Direct Paper URL")
        max_col = ws.max_column

        for row_idx in range(header_row + 1, ws.max_row + 1):
            if not row_has_any_value(ws, row_idx, max_col):
                continue

            row_record = {header: ws.cell(row=row_idx, column=col_idx).value for header, col_idx in hmap.items()}
            row_record["__sheet_name"] = sheet_name

            id_value = ws.cell(row=row_idx, column=id_col).value if id_col is not None else ""
            pub_value = ws.cell(row=row_idx, column=pub_col).value if pub_col is not None else ""
            pmid = extract_pmid(id_value) or extract_pmid(pub_value)
            if pmid:
                pmids_all.add(pmid)
                if pmid not in records_by_pmid:
                    records_by_pmid[pmid] = row_record
                if sheet_name == main_sheet.title:
                    pmids_main.add(pmid)
                else:
                    pmids_low.add(pmid)

            for col_idx in (pub_col, direct_col):
                if col_idx is None:
                    continue
                cell = ws.cell(row=row_idx, column=col_idx)
                raw = normalize_url(str(cell.value or ""))
                if raw.startswith("http://") or raw.startswith("https://"):
                    urls_all.add(raw)
                    if raw not in records_by_url:
                        records_by_url[raw] = row_record
                    if sheet_name == main_sheet.title:
                        urls_main.add(raw)
                    else:
                        urls_low.add(raw)
                if cell.hyperlink is not None and cell.hyperlink.target:
                    target = normalize_url(str(cell.hyperlink.target))
                    if target:
                        urls_all.add(target)
                        if target not in records_by_url:
                            records_by_url[target] = row_record
                        if sheet_name == main_sheet.title:
                            urls_main.add(target)
                        else:
                            urls_low.add(target)

    return {
        "pmids_all": pmids_all,
        "urls_all": urls_all,
        "pmids_main": pmids_main,
        "pmids_low": pmids_low,
        "urls_main": urls_main,
        "urls_low": urls_low,
        "records_by_pmid": records_by_pmid,
        "records_by_url": records_by_url,
    }


def build_submitted_reference_inventory_sheet(
    workbook,
    main_sheet: Worksheet,
    header_row: int,
    submitted_list_path: Path,
    client: PubMedClient,
    min_duration_days: int,
    confidence_threshold: str,
) -> Dict[str, object]:
    items = parse_submitted_reference_items(submitted_list_path)
    sheet = ensure_clean_sheet(workbook, SUBMITTED_INVENTORY_SHEET_TITLE)

    max_col = len(SUBMITTED_INVENTORY_HEADERS)
    copy_sheet_presentation(main_sheet, sheet, header_row, max_col)
    for row_idx in (1, 2):
        for col_idx in range(1, min(main_sheet.max_column, max_col) + 1):
            sheet.cell(row=row_idx, column=col_idx).value = main_sheet.cell(row=row_idx, column=col_idx).value
    if sheet.cell(row=1, column=1).value in (None, ""):
        sheet.cell(row=1, column=1).value = "Submitted reference list inventory and inclusion audit"
    for col_idx, header in enumerate(SUBMITTED_INVENTORY_HEADERS, start=1):
        sheet.cell(row=header_row, column=col_idx).value = header

    if not items:
        return {
            "submitted_items_total": 0,
            "submitted_items_included": 0,
            "qa1_ok": True,
            "qa2_ok": True,
            "qa3_ok": True,
            "qa2_error_count": 0,
            "qa3_error_count": 0,
        }

    pmcid_set = {str(item.get("submitted_pmcid") or "").upper() for item in items if item.get("submitted_pmcid")}
    pmcid_map = resolve_pmcids_to_pmids(pmcid_set)

    resolved_pmids: Set[str] = set()
    for item in items:
        resolved = str(item.get("submitted_pmid") or "").strip()
        submitted_url = normalize_url(str(item.get("submitted_url") or ""))
        raw_entry = str(item.get("raw_entry") or "")
        web_title = ""
        web_doi = ""
        if submitted_url:
            web_title, web_doi = fetch_web_metadata(submitted_url)
        item["web_title"] = web_title
        item["web_doi"] = web_doi

        if not resolved:
            pmcid = str(item.get("submitted_pmcid") or "").upper()
            if pmcid:
                resolved = pmcid_map.get(pmcid, "")
                if resolved:
                    item["resolved_via"] = "PMCID"
        if not resolved:
            doi = extract_doi_from_text(submitted_url) or extract_doi_from_text(raw_entry)
            if doi:
                resolved = resolve_doi_to_pmid(client, doi)
                if resolved:
                    item["resolved_via"] = f"DOI:{doi}"
            elif web_doi:
                resolved = resolve_doi_to_pmid(client, web_doi)
                if resolved:
                    item["resolved_via"] = f"WEB_DOI:{web_doi}"
        if not resolved:
            pii = extract_pii_from_text(submitted_url) or extract_pii_from_text(raw_entry)
            if pii:
                resolved = resolve_pii_to_pmid(client, pii)
                if resolved:
                    item["resolved_via"] = f"PII:{pii}"
        if not resolved and submitted_url:
            item["resolution_failed_step"] = "no_pmid_from_url_doi_or_pii"
        item["resolved_pmid"] = resolved
        if resolved:
            resolved_pmids.add(resolved)

    summaries = client.fetch_summaries(sorted(resolved_pmids, key=lambda v: int(v)) if resolved_pmids else [])
    abstracts = client.fetch_abstracts(sorted(resolved_pmids, key=lambda v: int(v)) if resolved_pmids else [])
    db = build_database_membership(workbook, main_sheet, header_row)
    included_count = 0
    confidence_rank = CONFIDENCE_RANK.get(confidence_threshold, CONFIDENCE_RANK["HIGH"])

    for offset, item in enumerate(items, start=1):
        row_idx = header_row + offset
        resolved_pmid = str(item.get("resolved_pmid") or "").strip()
        submitted_url = normalize_url(str(item.get("submitted_url") or ""))
        submitted_pmcid = str(item.get("submitted_pmcid") or "").upper()
        web_title = normalize_space(str(item.get("web_title") or ""))
        web_doi = normalize_doi(str(item.get("web_doi") or ""))
        resolved_via = str(item.get("resolved_via") or "")
        resolution_failed_step = str(item.get("resolution_failed_step") or "")
        summary = summaries.get(resolved_pmid, {}) if resolved_pmid else {}
        abstract = abstracts.get(resolved_pmid, "") if resolved_pmid else ""

        matched_row: Optional[Dict[str, object]] = None
        if resolved_pmid and resolved_pmid in db["records_by_pmid"]:
            matched_row = db["records_by_pmid"][resolved_pmid]
        elif submitted_url and submitted_url in db["records_by_url"]:
            matched_row = db["records_by_url"][submitted_url]
        elif resolved_pmid:
            normalized_pubmed = normalize_pubmed_url(resolved_pmid)
            if normalized_pubmed in db["records_by_url"]:
                matched_row = db["records_by_url"][normalized_pubmed]

        if matched_row and not resolved_pmid:
            resolved_pmid = (
                extract_pmid(matched_row.get("ID"))  # type: ignore[arg-type]
                or extract_pmid(matched_row.get("PubMed URL"))  # type: ignore[arg-type]
                or ""
            )

        research_flag, non_research_why = classify_research_item(submitted_url, resolved_pmid, summary)

        in_main = "N"
        in_low = "N"
        if matched_row and str(matched_row.get("__sheet_name")) == main_sheet.title:
            in_main = "Y"
        if matched_row and str(matched_row.get("__sheet_name")) == LOW_CONF_SHEET_TITLE:
            in_low = "Y"
        in_db = "Y" if matched_row is not None else "N"
        if in_db == "Y":
            included_count += 1

        if in_db == "Y":
            not_included_why = "Included in database"
        elif research_flag == "N":
            not_included_why = non_research_why
        elif submitted_pmcid and not resolved_pmid:
            not_included_why = "PMCID present but could not be resolved/matched to current database."
        elif resolved_pmid and not summary:
            not_included_why = "PMID resolved but PubMed metadata retrieval failed."
        elif resolved_pmid:
            if abstract:
                d_days, _, _, d_conf = extract_duration_info(normalize_space(str(summary.get("title", ""))), abstract)
                if d_days is not None and d_days < min_duration_days:
                    not_included_why = (
                        f"Research paper resolved, but extracted duration ({d_days} days) is below threshold ({min_duration_days})."
                    )
                elif d_days is not None and CONFIDENCE_RANK.get(d_conf, 0) < confidence_rank:
                    not_included_why = (
                        f"Research paper resolved, but duration confidence ({d_conf}) is below threshold ({confidence_threshold})."
                    )
                else:
                    not_included_why = (
                        "Research paper resolved but not present in current filtered database (query/scope/filter mismatch)."
                    )
            else:
                not_included_why = "Research paper resolved but abstract unavailable for duration-based screening."
        elif submitted_url:
            if web_doi:
                not_included_why = (
                    f"URL reachable; extracted DOI ({web_doi}) but DOI->PMID lookup returned no PubMed match."
                )
            elif resolution_failed_step:
                not_included_why = "URL reachable but no PMID/DOI/PII could be extracted for PubMed matching."
            else:
                not_included_why = "Could not resolve submitted URL to a PubMed record and no database URL match was found."
        else:
            not_included_why = "No URL/PMID provided for matching."

        row_data: Dict[str, object] = {
            "Date": "Unavailable from source",
            "Authors": "Unavailable from source",
            "Title": "Unresolved source title",
            "Type of study": "Unclassified source item",
            "Suspected AE Duration (months)": "Not estimable from available abstract/text",
            "Description": "Could not extract abstract text from source.",
            "Findings": "Could not extract findings from available source text.",
            "PubMed URL": "No PubMed record resolved",
            "Direct Paper URL": submitted_url or "No URL provided",
            "ID": "No PMID resolved",
            "Submitted List Entry": str(item.get("raw_entry") or "Unavailable source entry"),
            "Submitted URL": submitted_url or "No URL provided",
            "Submitted PMCID": submitted_pmcid or "No PMCID provided",
            "Resolved PMID": resolved_pmid or "Not resolved",
            "Research Item (Y/N)": research_flag,
            "If Not Research, Why": non_research_why if research_flag == "N" else "Not applicable (research item)",
            "Included in Database (Y/N)": in_db,
            "If Not Included, Why Not": not_included_why,
            "Included In Medium-High (Y/N)": in_main,
            "Included In Low (Y/N)": in_low,
        }

        if matched_row is not None:
            for header in SUBMITTED_INVENTORY_HEADERS:
                if header in matched_row:
                    value = matched_row.get(header)
                    if value not in (None, ""):
                        row_data[header] = value
            if resolved_pmid:
                row_data["Resolved PMID"] = resolved_pmid
                row_data["ID"] = resolved_pmid
        elif resolved_pmid and summary:
            title = normalize_space(str(summary.get("title", "")))
            pubdate = str(summary.get("pubdate", ""))
            year, _month = parse_pubdate(pubdate)
            study_type = "; ".join([str(p).strip() for p in summary.get("pubtype", []) if str(p).strip()])
            authors = format_authors_from_summary(summary)
            direct_from_summary = derive_direct_paper_url(summary, resolved_pmid)
            d_days, d_months, d_evidence, d_conf = extract_duration_info(title, abstract)

            row_data["Date"] = year or "Unavailable from source"
            row_data["Authors"] = authors or "Unavailable from source"
            row_data["Title"] = title or infer_title_from_url(submitted_url)
            row_data["Type of study"] = study_type or "Unclassified source item"
            row_data["Suspected AE Duration (months)"] = (
                d_months if d_months is not None else "Not estimable from available abstract/text"
            )
            row_data["Description"] = first_sentence(abstract) if abstract else "Abstract unavailable from PubMed source."
            row_data["Findings"] = extract_findings_text(abstract) if abstract else "Findings unavailable (no abstract text)."
            row_data["PubMed URL"] = normalize_pubmed_url(resolved_pmid)
            row_data["Direct Paper URL"] = submitted_url or direct_from_summary or normalize_pubmed_url(resolved_pmid)
            row_data["ID"] = resolved_pmid
            row_data["Resolved PMID"] = resolved_pmid
            if d_evidence:
                row_data["Description"] = first_sentence(abstract)
        else:
            row_data["Title"] = web_title or infer_title_from_url(submitted_url) or normalize_space(str(item.get("raw_entry") or ""))
            row_data["PubMed URL"] = normalize_pubmed_url(resolved_pmid) if resolved_pmid else "No PubMed record resolved"
            row_data["Direct Paper URL"] = submitted_url or row_data["PubMed URL"]
            row_data["ID"] = resolved_pmid or "No PMID resolved"
            row_data["Resolved PMID"] = resolved_pmid or (f"Not resolved ({resolved_via})" if resolved_via else "Not resolved")

        for col_idx, header in enumerate(SUBMITTED_INVENTORY_HEADERS, start=1):
            value = row_data.get(header, "Unavailable from source")
            if value in (None, ""):
                value = "Unavailable from source"
            sheet.cell(row=row_idx, column=col_idx).value = value

    copy_sheet_presentation(main_sheet, sheet, header_row, max_col)
    apply_template_data_style(main_sheet, sheet, header_row, max_col)
    enforce_wrapped_text_columns(sheet, header_row, max_col)

    extra_wrap_headers = {
        "Submitted List Entry",
        "If Not Research, Why",
        "If Not Included, Why Not",
    }
    header_map = header_map_from_row(sheet, header_row)
    for row_idx in range(header_row + 1, sheet.max_row + 1):
        if not row_has_any_value(sheet, row_idx, max_col):
            continue
        for header in extra_wrap_headers:
            col_idx = header_map.get(header)
            if col_idx is None:
                continue
            cell = sheet.cell(row=row_idx, column=col_idx)
            alignment = copy(cell.alignment)
            alignment.wrap_text = True
            alignment.vertical = "top"
            cell.alignment = alignment
        sheet.row_dimensions[row_idx].height = None

    url_headers = {"PubMed URL", "Direct Paper URL", "Submitted URL"}
    for row_idx in range(header_row + 1, sheet.max_row + 1):
        if not row_has_any_value(sheet, row_idx, max_col):
            continue
        for header in url_headers:
            col_idx = header_map.get(header)
            if col_idx is None:
                continue
            cell = sheet.cell(row=row_idx, column=col_idx)
            value = normalize_url(str(cell.value or ""))
            if value.startswith("http://") or value.startswith("https://"):
                cell.value = value
                cell.hyperlink = value
                cell.style = "Hyperlink"

    if header_map:
        last_col_letter = get_column_letter(max_col)
        sheet.auto_filter.ref = f"A{header_row}:{last_col_letter}{sheet.max_row}"

    for header in ("Submitted List Entry", "If Not Research, Why", "If Not Included, Why Not"):
        col_idx = header_map.get(header)
        if col_idx is not None:
            current_width = sheet.column_dimensions[get_column_letter(col_idx)].width
            if current_width is None or current_width < 42:
                sheet.column_dimensions[get_column_letter(col_idx)].width = 42

    width_overrides = {
        "Title": 52,
        "Description": 60,
        "Findings": 55,
        "Type of study": 34,
        "Authors": 30,
        "PubMed URL": 40,
        "Direct Paper URL": 45,
        "Submitted URL": 45,
        "If Not Research, Why": 48,
        "If Not Included, Why Not": 48,
    }
    for header, width in width_overrides.items():
        col_idx = header_map.get(header)
        if col_idx is not None:
            sheet.column_dimensions[get_column_letter(col_idx)].width = width

    qa1_ok = len(items) == (sheet.max_row - header_row)

    qa2_error_count = 0
    qa3_error_count = 0
    for row_idx in range(header_row + 1, sheet.max_row + 1):
        in_db_value = normalize_space(str(sheet.cell(row=row_idx, column=header_map["Included in Database (Y/N)"]).value or "")).upper()
        why_value = normalize_space(str(sheet.cell(row=row_idx, column=header_map["If Not Included, Why Not"]).value or ""))
        if in_db_value == "N" and why_value in ("", "Included in database"):
            qa2_error_count += 1
        if in_db_value == "Y" and why_value != "Included in database":
            qa2_error_count += 1

        for col_idx, header in enumerate(SUBMITTED_INVENTORY_HEADERS, start=1):
            value = sheet.cell(row=row_idx, column=col_idx).value
            if value in (None, ""):
                qa3_error_count += 1
            elif isinstance(value, str) and value.strip().upper() == "NR":
                qa3_error_count += 1
            if header not in {"Submitted URL", "PubMed URL", "Direct Paper URL"}:
                continue
            text = normalize_url(str(value or ""))
            if not text:
                continue
            if not (text.startswith("http://") or text.startswith("https://")):
                # Placeholder explanatory text is allowed in URL columns.
                continue
            if sheet.cell(row=row_idx, column=col_idx).hyperlink is None:
                qa3_error_count += 1

    return {
        "submitted_items_total": len(items),
        "submitted_items_included": included_count,
        "qa1_ok": qa1_ok,
        "qa2_ok": qa2_error_count == 0,
        "qa3_ok": qa3_error_count == 0,
        "qa2_error_count": qa2_error_count,
        "qa3_error_count": qa3_error_count,
    }


def parse_reference_list(list_path: Path) -> Tuple[Set[str], Set[str], Set[str], List[str]]:
    raw_text = list_path.read_text(encoding="utf-8")
    urls = set(extract_urls(raw_text))

    pmids: Set[str] = set()
    pmcids: Set[str] = set()
    for url in urls:
        pmid = extract_pmid(url)
        if pmid:
            pmids.add(pmid)
        pmcid = extract_pmcid(url)
        if pmcid:
            pmcids.add(pmcid)

    for token in re.findall(r"\b\d{4,9}\b", raw_text):
        pmids.add(token)
    for token in PMCID_RE.findall(raw_text):
        pmcids.add(token.upper())

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    return pmids, pmcids, urls, lines


def resolve_pmcids_to_pmids(pmcids: Set[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not pmcids:
        return out
    ids = ",".join(sorted(pmcids))
    url = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
    payload = None
    last_exc: Optional[Exception] = None
    for attempt in range(4):
        try:
            response = requests.get(url, params={"ids": ids, "format": "json"}, timeout=40)
            response.raise_for_status()
            payload = response.json()
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(0.8 * (attempt + 1))
    if payload is None:
        if last_exc:
            return out
        return out
    for rec in payload.get("records", []):
        pmcid = str(rec.get("pmcid", "")).upper()
        pmid = str(rec.get("pmid", "")).strip()
        if pmcid and pmid and PMID_RE.fullmatch(pmid):
            out[pmcid] = pmid
    return out


def mine_chronic_terms(seed_texts: Sequence[str], max_terms: int = 10) -> List[str]:
    corpus = " ".join([t.lower() for t in seed_texts if t]).strip()
    if not corpus:
        return []
    selected: List[str] = []
    for term, _ in CHRONIC_QUERY_CANDIDATES:
        if term in corpus:
            selected.append(term)
        if len(selected) >= max_terms:
            break
    return selected


def build_chronic_query(base_query: str, selected_terms: Sequence[str]) -> str:
    if not selected_terms:
        chronic_block = CHRONIC_QUERY_DEFAULT_BLOCK
    else:
        fragments: List[str] = []
        selected_set = set(selected_terms)
        for term, fragment in CHRONIC_QUERY_CANDIDATES:
            if term in selected_set:
                fragments.append(fragment)
        chronic_block = " OR ".join(dict.fromkeys(fragments)) if fragments else CHRONIC_QUERY_DEFAULT_BLOCK
    return f"({base_query}) AND ({chronic_block})"


def run_multi_agent_chronic_builder(
    client: PubMedClient,
    submitted_list_path: Path,
    base_query: str,
    max_terms: int = 10,
) -> Dict[str, object]:
    # Agent 1: submitted-list parser (PubMed + PMC + URLs).
    seed_pmids, seed_pmcids, seed_urls, _ = parse_reference_list(submitted_list_path)

    # Agent 2: PMCID->PMID resolver.
    pmcid_map = resolve_pmcids_to_pmids(seed_pmcids)
    seed_pmids = set(seed_pmids) | set(pmcid_map.values())

    # Agent 3: evidence miner on seed titles/abstracts.
    summaries = client.fetch_summaries(sorted(seed_pmids, key=lambda v: int(v)) if seed_pmids else [])
    abstracts = client.fetch_abstracts(sorted(seed_pmids, key=lambda v: int(v)) if seed_pmids else [])
    seed_texts: List[str] = []
    for pmid in sorted(seed_pmids, key=lambda v: int(v)):
        title = normalize_space(str(summaries.get(pmid, {}).get("title", "")))
        abstract = normalize_space(abstracts.get(pmid, ""))
        if title:
            seed_texts.append(title)
        if abstract:
            seed_texts.append(abstract)

    chronic_terms = mine_chronic_terms(seed_texts, max_terms=max_terms)

    # Agent 4: query builder (chronic-focused).
    effective_query = build_chronic_query(base_query, chronic_terms)

    return {
        "seed_pubmed_count": len(seed_pmids),
        "seed_pmc_count": len(seed_pmcids),
        "seed_url_count": len(seed_urls),
        "resolved_pmc_to_pmid_count": len(pmcid_map),
        "selected_chronic_terms": chronic_terms,
        "effective_query": effective_query,
    }


def reference_list_qa(
    records: Sequence[Dict[str, object]],
    seed_pmids: Set[str],
    seed_urls: Set[str],
) -> Tuple[List[Dict[str, object]], int]:
    out_rows: List[Dict[str, object]] = []
    additional_count = 0

    normalized_seed_urls = {normalize_url(u) for u in seed_urls}

    for record in records:
        row_index = int(record["row_index"])
        pmid = extract_pmid(record.get("ID")) or extract_pmid(record.get("PubMed URL"))
        url = normalize_url(str(record.get("PubMed URL") or ""))

        in_list = False
        basis = ""
        if pmid and pmid in seed_pmids:
            in_list = True
            basis = "PMID"
        elif url and url in normalized_seed_urls:
            in_list = True
            basis = "URL"

        if not in_list:
            additional_count += 1

        out_rows.append(
            {
                "row_index": row_index,
                "pmid": pmid or "",
                "pubmed_url": url,
                "included_in_submitted_list": "Y" if in_list else "N",
                "match_basis": basis or "NONE",
            }
        )

    for row in out_rows:
        row["additional_papers_found_total"] = additional_count

    return out_rows, additional_count


def metadata_qa(
    records: Sequence[Dict[str, object]],
    client: PubMedClient,
) -> List[Dict[str, object]]:
    resolved_pmids = sorted(
        {
            p
            for p in (
                extract_pmid(r.get("ID")) or extract_pmid(r.get("PubMed URL"))
                for r in records
            )
            if p
        },
        key=lambda v: int(v),
    )

    summaries = client.fetch_summaries(resolved_pmids)
    neighbor_ids = sorted(
        {
            str(int(pmid) + delta)
            for pmid in resolved_pmids
            for delta in (-1, 1)
            if int(pmid) + delta > 0
        },
        key=lambda v: int(v),
    )
    neighbor_summaries = client.fetch_summaries(neighbor_ids)

    out_rows: List[Dict[str, object]] = []
    for record in records:
        row_index = record["row_index"]
        pmid_from_id = extract_pmid(record.get("ID"))
        pmid_from_url = extract_pmid(record.get("PubMed URL"))
        pmid_resolved = pmid_from_id or pmid_from_url

        status = "PASS"
        issues: List[str] = []
        pmid_exact_match = "NA"
        if pmid_from_id and pmid_from_url:
            pmid_exact_match = "PASS" if pmid_from_id == pmid_from_url else "FAIL"
            if pmid_exact_match == "FAIL":
                issues.append("PMID_ID_URL_MISMATCH")

        title_sheet = normalize_space(str(record.get("Title") or ""))
        title_pubmed = ""
        title_similarity = ""
        url_expected = ""
        url_match = "NA"
        off_by_one_flag = "NO"
        off_by_one_note = ""

        if not pmid_resolved:
            status = "REVIEW"
            issues.append("NO_VALID_PMID")
        else:
            summary = summaries.get(pmid_resolved)
            if not summary:
                status = "FAIL"
                issues.append("METADATA_LOOKUP_FAILED")
            else:
                title_pubmed = normalize_space(str(summary.get("title", "")))
                url_expected = normalize_pubmed_url(pmid_resolved)

                if record.get("PubMed URL"):
                    url_match = "PASS" if str(record.get("PubMed URL")).strip() == url_expected else "FAIL"
                    if url_match == "FAIL":
                        issues.append("URL_NOT_NORMALIZED")

                if title_sheet:
                    sim = fuzz.ratio(normalize_title(title_sheet), normalize_title(title_pubmed))
                    title_similarity = f"{sim:.1f}"
                    if sim < 70:
                        issues.append("LOW_TITLE_SIMILARITY")

                    left = neighbor_summaries.get(str(int(pmid_resolved) - 1))
                    right = neighbor_summaries.get(str(int(pmid_resolved) + 1))
                    candidate_sim = sim
                    neighbor_best = -1.0
                    neighbor_best_pmid = ""
                    for pmid_neighbor, summary_neighbor in (
                        (str(int(pmid_resolved) - 1), left),
                        (str(int(pmid_resolved) + 1), right),
                    ):
                        if not summary_neighbor:
                            continue
                        neighbor_title = normalize_space(str(summary_neighbor.get("title", "")))
                        neighbor_sim = fuzz.ratio(normalize_title(title_sheet), normalize_title(neighbor_title))
                        if neighbor_sim > neighbor_best:
                            neighbor_best = neighbor_sim
                            neighbor_best_pmid = pmid_neighbor
                    if neighbor_best >= 85 and (neighbor_best - candidate_sim) >= 15:
                        off_by_one_flag = "YES"
                        off_by_one_note = (
                            f"Neighbor PMID {neighbor_best_pmid} title similarity {neighbor_best:.1f} "
                            f"> current {candidate_sim:.1f}"
                        )
                        issues.append("OFF_BY_ONE_SUSPECT")

        if issues and status == "PASS":
            status = "REVIEW"

        out_rows.append(
            {
                "row_index": row_index,
                "pmid_from_id": pmid_from_id or "",
                "pmid_from_url": pmid_from_url or "",
                "pmid_resolved": pmid_resolved or "",
                "pmid_exact_match": pmid_exact_match,
                "title_similarity": title_similarity,
                "url_expected": url_expected,
                "url_match": url_match,
                "off_by_one_flag": off_by_one_flag,
                "off_by_one_note": off_by_one_note,
                "status": status,
                "issues": ";".join(issues),
            }
        )

    return out_rows


def abstract_qa(
    records: Sequence[Dict[str, object]],
    client: PubMedClient,
) -> List[Dict[str, object]]:
    resolved_pmids = sorted(
        {
            p
            for p in (
                extract_pmid(r.get("ID")) or extract_pmid(r.get("PubMed URL"))
                for r in records
            )
            if p
        },
        key=lambda v: int(v),
    )
    abstracts = client.fetch_abstracts(resolved_pmids)

    out_rows: List[Dict[str, object]] = []
    for record in records:
        row_index = record["row_index"]
        pmid = extract_pmid(record.get("ID")) or extract_pmid(record.get("PubMed URL"))
        quote = normalize_space(str(record.get("Description") or ""))
        status = "PASS"
        issues: List[str] = []
        exact_match = "NA"

        if not pmid:
            status = "REVIEW"
            issues.append("NO_VALID_PMID")
        else:
            abstract = abstracts.get(pmid, "")
            if not abstract:
                status = "REVIEW"
                issues.append("NO_ABSTRACT")
            if not quote:
                status = "REVIEW"
                issues.append("NO_QUOTE")
            elif abstract:
                exact = quote in abstract
                exact_match = "PASS" if exact else "FAIL"
                if not exact:
                    status = "FAIL"
                    issues.append("QUOTE_NOT_VERBATIM")

        out_rows.append(
            {
                "row_index": row_index,
                "pmid": pmid or "",
                "quote_field": "Description",
                "quote_text": quote,
                "exact_match": exact_match,
                "status": status,
                "issues": ";".join(issues),
            }
        )
    return out_rows


def write_dict_rows_to_sheet(sheet: Worksheet, rows: Sequence[Dict[str, object]]) -> None:
    if not rows:
        return
    headers = list(rows[0].keys())
    for col_idx, key in enumerate(headers, start=1):
        sheet.cell(row=1, column=col_idx).value = key
    for row_idx, item in enumerate(rows, start=2):
        for col_idx, key in enumerate(headers, start=1):
            sheet.cell(row=row_idx, column=col_idx).value = item.get(key)


def write_csv(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    headers = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def required_list_coverage(
    required_file: Path,
    data_rows: Sequence[Dict[str, object]],
) -> List[Dict[str, object]]:
    required_pmids: List[str] = []
    for line in required_file.read_text(encoding="utf-8").splitlines():
        candidate = line.strip()
        if candidate and PMID_RE.fullmatch(candidate):
            required_pmids.append(candidate)

    present_map: Dict[str, int] = {}
    for row in data_rows:
        pmid = extract_pmid(row.get("ID")) or extract_pmid(row.get("PubMed URL"))
        if pmid and pmid not in present_map:
            present_map[pmid] = int(row["row_index"])

    coverage: List[Dict[str, object]] = []
    for pmid in required_pmids:
        coverage.append(
            {
                "pmid": pmid,
                "present": "YES" if pmid in present_map else "NO",
                "row_index": present_map.get(pmid, ""),
            }
        )
    return coverage


def copy_or_prepare_workbook(input_path: Path, output_path: Path, in_place: bool) -> None:
    if in_place:
        return
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Output path equals input path. Use --in-place to permit source overwrite.")
    shutil.copy2(input_path, output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AE psychosis systematic review pipeline")
    parser.add_argument("--input", required=True, help="Path to source workbook (.xlsx)")
    parser.add_argument("--output", help="Path to output workbook (.xlsx)")
    parser.add_argument("--in-place", action="store_true", help="Allow writing in-place to input workbook")
    parser.add_argument("--reports-dir", default="reports", help="Directory for machine-readable reports")
    parser.add_argument("--query", default=DEFAULT_QUERY, help="PubMed query")
    parser.add_argument("--max-results", type=int, default=150, help="Maximum PubMed records to retrieve")
    parser.add_argument("--mindate", default="1995/01/01", help="Minimum publication date for search")
    parser.add_argument("--maxdate", default="2025/12/31", help="Maximum publication date for search")
    parser.add_argument("--email", default="", help="NCBI email (recommended)")
    parser.add_argument("--api-key", default="", help="NCBI API key (optional)")
    parser.add_argument("--skip-retrieval", action="store_true", help="Skip retrieval stage and run QA only")
    parser.add_argument(
        "--multi-agent-chronic-search",
        action="store_true",
        help=(
            "Enable multi-agent search builder: parse submitted list (PubMed+PMC), mine chronicity signals, "
            "and build a chronic-focused retrieval query."
        ),
    )
    parser.add_argument(
        "--chronic-term-limit",
        type=int,
        default=10,
        help="Maximum number of chronic terms mined from seed papers when multi-agent mode is enabled.",
    )
    parser.add_argument(
        "--min-duration-days",
        type=int,
        default=90,
        help="Minimum explicitly extracted duration (days) required to keep a paper. Default: 90",
    )
    parser.add_argument(
        "--preferred-duration-days",
        type=int,
        default=180,
        help="Preferred long-duration threshold (days) for flagging >=6 months. Default: 180",
    )
    parser.add_argument(
        "--duration-confidence-threshold",
        choices=["LOW", "MEDIUM", "HIGH"],
        default="HIGH",
        help="Minimum extraction confidence accepted for duration filtering. Default: HIGH",
    )
    parser.add_argument(
        "--disable-duration-filter",
        action="store_true",
        help="Do not filter to min duration; still populate duration columns and sort by extracted duration.",
    )
    parser.add_argument(
        "--simple-output",
        action="store_true",
        help=(
            "Only update the main sheet columns (including submitted-list columns if provided). "
            "Skip creation of extra QA sheets and CSV reports."
        ),
    )
    parser.add_argument(
        "--submitted-list",
        help=(
            "Optional path to submitted reference list text/markdown file. "
            "Used for additional QA columns and coverage report."
        ),
    )
    parser.add_argument(
        "--required-pmids",
        help="Optional text file of required PMIDs (one per line) for coverage reporting",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input workbook not found: {input_path}")

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
    elif args.in_place:
        output_path = input_path
    else:
        output_path = input_path.with_name(f"{input_path.stem}_output{input_path.suffix}")

    reports_dir = Path(args.reports_dir).expanduser().resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)

    copy_or_prepare_workbook(input_path, output_path, in_place=args.in_place)

    client = PubMedClient(email=args.email or None, api_key=args.api_key or None)
    wb = load_workbook(output_path)
    ws = wb[wb.sheetnames[0]]
    header_row, header_map = find_header_row_and_map(ws)
    direct_col = ensure_column(ws, header_row, "Direct Paper URL")

    seen = existing_pmids(ws, header_row, header_map)
    retrieved_pmids: List[str] = []
    added_rows: List[int] = []
    effective_query = args.query
    multi_agent_trace: Dict[str, object] = {}

    if not args.skip_retrieval:
        if args.multi_agent_chronic_search:
            if not args.submitted_list:
                raise ValueError("--multi-agent-chronic-search requires --submitted-list")
            submitted_list_path = Path(args.submitted_list).expanduser().resolve()
            if not submitted_list_path.exists():
                raise FileNotFoundError(f"Submitted list file not found: {submitted_list_path}")
            multi_agent_trace = run_multi_agent_chronic_builder(
                client=client,
                submitted_list_path=submitted_list_path,
                base_query=args.query,
                max_terms=max(args.chronic_term_limit, 1),
            )
            effective_query = str(multi_agent_trace.get("effective_query", args.query))

        search_pmids = client.search_pmids(
            query=effective_query,
            max_results=args.max_results,
            mindate=args.mindate,
            maxdate=args.maxdate,
        )
        retrieved_pmids = [pmid for pmid in search_pmids if pmid not in seen]
        summaries = client.fetch_summaries(retrieved_pmids)
        abstracts = client.fetch_abstracts(retrieved_pmids)
        candidates = build_candidate_records(retrieved_pmids, summaries, abstracts)
        added_rows = append_records_to_sheet(ws, header_row, header_map, candidates, direct_col)

    data_rows = sheet_rows_as_records(ws, header_row, header_map)
    direct_link_map = compute_direct_link_map(data_rows, client)
    apply_main_sheet_enrichment(ws, header_row, header_map, direct_col, direct_link_map)
    enrichment_stats = enrich_content_and_duration(
        ws,
        header_row,
        header_map,
        client,
        min_duration_days=max(args.min_duration_days, 0),
        preferred_duration_days=max(args.preferred_duration_days, 0),
        confidence_threshold=args.duration_confidence_threshold,
    )

    filter_stats = {
        "rows_total_before_filter": len(data_rows),
        "rows_kept_after_filter": len(data_rows),
        "rows_dropped_missing_duration": 0,
        "rows_dropped_short_duration": 0,
        "rows_dropped_low_confidence": 0,
    }
    if not args.disable_duration_filter:
        filter_stats = sort_and_filter_by_duration(
            sheet=ws,
            header_row=header_row,
            duration_days_col=int(enrichment_stats["duration_days_col"]),
            min_duration_days=max(args.min_duration_days, 0),
            confidence_col=int(enrichment_stats["duration_conf_col"]),
            confidence_threshold=args.duration_confidence_threshold,
            pubmed_col=header_map["PubMed URL"],
            direct_col=direct_col,
        )

    data_rows = sheet_rows_as_records(ws, header_row, header_map)

    metadata_rows = metadata_qa(data_rows, client)
    abstract_rows = abstract_qa(data_rows, client)
    submitted_rows: List[Dict[str, object]] = []
    additional_papers_total = 0
    submitted_list_path: Optional[Path] = None

    if not args.simple_output:
        metadata_sheet = ensure_clean_sheet(wb, "Metadata_QA")
        abstract_sheet = ensure_clean_sheet(wb, "Abstract_QA")
        write_dict_rows_to_sheet(metadata_sheet, metadata_rows)
        write_dict_rows_to_sheet(abstract_sheet, abstract_rows)

    if args.submitted_list:
        submitted_list_path = Path(args.submitted_list).expanduser().resolve()
        if not submitted_list_path.exists():
            raise FileNotFoundError(f"Submitted list file not found: {submitted_list_path}")

        seed_pmids, seed_pmcids, seed_urls, submitted_lines = parse_reference_list(submitted_list_path)
        pmc_map = resolve_pmcids_to_pmids(seed_pmcids)
        seed_pmids = set(seed_pmids) | set(pmc_map.values())
        submitted_rows, additional_papers_total = reference_list_qa(data_rows, seed_pmids, seed_urls)

        if not args.simple_output:
            submitted_sheet = ensure_clean_sheet(wb, "Submitted_List_QA")
            write_dict_rows_to_sheet(submitted_sheet, submitted_rows)

        # User-requested columns in the primary sheet.
        include_col = ensure_column(ws, header_row, "In Submitted List (Y/N)")
        additional_col = ensure_column(ws, header_row, "Additional Papers Beyond Submitted List")
        in_list_by_row = {int(r["row_index"]): r["included_in_submitted_list"] for r in submitted_rows}
        for row in data_rows:
            row_idx = int(row["row_index"])
            ws.cell(row=row_idx, column=include_col).value = in_list_by_row.get(row_idx, "N")
            ws.cell(row=row_idx, column=additional_col).value = additional_papers_total

        if not args.simple_output:
            write_csv(reports_dir / "submitted_list_qa.csv", submitted_rows)
            (reports_dir / "submitted_list_raw_lines.txt").write_text(
                "\n".join(submitted_lines) + ("\n" if submitted_lines else ""),
                encoding="utf-8",
            )

    coverage_rows: List[Dict[str, object]] = []
    if args.required_pmids:
        required_file = Path(args.required_pmids).expanduser().resolve()
        if required_file.exists():
            coverage_rows = required_list_coverage(required_file, data_rows)
            coverage_sheet = ensure_clean_sheet(wb, "Required_List_Coverage")
            write_dict_rows_to_sheet(coverage_sheet, coverage_rows)

    split_stats = split_low_confidence_sheet(
        workbook=wb,
        main_sheet=ws,
        header_row=header_row,
    )

    submitted_inventory_stats: Dict[str, object] = {
        "submitted_items_total": 0,
        "submitted_items_included": 0,
        "qa1_ok": True,
        "qa2_ok": True,
        "qa3_ok": True,
        "qa2_error_count": 0,
        "qa3_error_count": 0,
    }
    if submitted_list_path is not None:
        submitted_inventory_stats = build_submitted_reference_inventory_sheet(
            workbook=wb,
            main_sheet=ws,
            header_row=header_row,
            submitted_list_path=submitted_list_path,
            client=client,
            min_duration_days=max(args.min_duration_days, 0),
            confidence_threshold=args.duration_confidence_threshold,
        )

    wb.save(output_path)

    if not args.simple_output:
        write_csv(reports_dir / "metadata_qa.csv", metadata_rows)
        write_csv(reports_dir / "abstract_qa.csv", abstract_rows)
        if coverage_rows:
            write_csv(reports_dir / "required_list_coverage.csv", coverage_rows)

    summary = {
        "input_workbook": str(input_path),
        "output_workbook": str(output_path),
        "retrieval_enabled": not args.skip_retrieval,
        "effective_query": effective_query,
        "multi_agent_chronic_search": bool(args.multi_agent_chronic_search),
        "multi_agent_trace": multi_agent_trace,
        "retrieved_new_pmids": len(retrieved_pmids),
        "rows_added": len(added_rows),
        "total_nonempty_rows": len(data_rows),
        "metadata_pass": sum(1 for r in metadata_rows if r["status"] == "PASS"),
        "metadata_review_or_fail": sum(1 for r in metadata_rows if r["status"] != "PASS"),
        "abstract_pass": sum(1 for r in abstract_rows if r["status"] == "PASS"),
        "abstract_review_or_fail": sum(1 for r in abstract_rows if r["status"] != "PASS"),
        "duration_filter_enabled": not args.disable_duration_filter,
        "duration_confidence_threshold": args.duration_confidence_threshold,
        "min_duration_days": max(args.min_duration_days, 0),
        "preferred_duration_days": max(args.preferred_duration_days, 0),
        "duration_rows_with_explicit_value": int(enrichment_stats["explicit_duration_rows"]),
        "duration_rows_flagged_ge_3m": int(enrichment_stats["include_rows"]),
        "duration_rows_flagged_ge_6m": int(enrichment_stats["include_6m_rows"]),
        "duration_rows_newly_included_low_confidence": int(enrichment_stats["low_added_rows"]),
        "rows_total_before_filter": int(filter_stats["rows_total_before_filter"]),
        "rows_kept_after_filter": int(filter_stats["rows_kept_after_filter"]),
        "rows_dropped_missing_duration": int(filter_stats["rows_dropped_missing_duration"]),
        "rows_dropped_short_duration": int(filter_stats["rows_dropped_short_duration"]),
        "rows_dropped_low_confidence": int(filter_stats["rows_dropped_low_confidence"]),
        "submitted_list_enabled": bool(args.submitted_list),
        "submitted_list_total_rows": len(submitted_rows),
        "additional_papers_beyond_submitted_list": additional_papers_total,
        "main_sheet_rows_after_split": int(split_stats["main_rows"]),
        "low_confidence_sheet_rows": int(split_stats["low_rows"]),
        "low_confidence_sheet_title": LOW_CONF_SHEET_TITLE,
        "submitted_inventory_sheet_title": SUBMITTED_INVENTORY_SHEET_TITLE,
        "submitted_inventory_items_total": int(submitted_inventory_stats["submitted_items_total"]),
        "submitted_inventory_items_included": int(submitted_inventory_stats["submitted_items_included"]),
        "submitted_inventory_qa1_ok": bool(submitted_inventory_stats.get("qa1_ok", False)),
        "submitted_inventory_qa2_ok": bool(submitted_inventory_stats.get("qa2_ok", False)),
        "submitted_inventory_qa3_ok": bool(submitted_inventory_stats.get("qa3_ok", False)),
        "submitted_inventory_qa2_error_count": int(submitted_inventory_stats.get("qa2_error_count", 0)),
        "submitted_inventory_qa3_error_count": int(submitted_inventory_stats.get("qa3_error_count", 0)),
        "simple_output_mode": bool(args.simple_output),
    }
    if not args.simple_output:
        (reports_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
