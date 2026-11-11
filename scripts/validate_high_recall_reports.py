#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Iterable


REQUIRED_CSVS = {
    "domain_coverage_matrix.csv": [
        "Domain",
        "Key synonyms",
        "Canonical latest review/meta-analysis",
        "Coverage status",
    ],
    "review_supersession_audit.csv": [
        "Domain",
        "Latest Review",
        "Latest Review Identifier",
        "Newer Review Found (Y/N)",
        "Canonical Review Selected",
        "Older Review Retained (Y/N)",
        "Retention Reason",
    ],
    "benchmark_recall_set.csv": [
        "Domain",
        "Benchmark Paper",
        "Identifier",
        "Reason It Is Mandatory",
    ],
    "benchmark_recall_results.csv": [
        "Domain",
        "Benchmark Paper",
        "Identifier",
        "Retrieved (Y/N)",
        "Included (Y/N/Uncertain)",
        "If Missed, Failure Mode",
        "Action Needed",
    ],
    "coverage_audit.csv": [
        "Known Important Paper",
        "Source of Importance",
        "Identifier",
        "Retrieved (Y/N)",
        "Included (Y/N/Uncertain)",
        "If Not Included, Why Not",
        "Search Route That Found It",
        "Missed-Paper Failure Mode",
        "Action Needed",
    ],
}

REQUIRED_TEXT = ["final_gap_analysis.md"]

UNRESOLVED_MARKERS = {
    "",
    "tbd",
    "todo",
    "pending",
    "not checked",
    "not assessed",
    "unknown",
    "unclear",
    "needs review",
    "needs human review",
    "not run",
    "missing",
}

NO_UNRESOLVED_PATTERNS = [
    r"\bno unresolved\b",
    r"\bunresolved (?:important )?(?:misses|gaps):\s*none\b",
    r"\bno major unresolved\b",
    r"\bno unexplained misses\b",
]


def norm(value: object) -> str:
    return str(value or "").strip()


def folded(value: object) -> str:
    return re.sub(r"\s+", " ", norm(value)).lower()


def is_bad_marker(value: object) -> bool:
    text = folded(value)
    return text in UNRESOLVED_MARKERS


def yes_no(value: object) -> str:
    text = folded(value)
    if text in {"y", "yes", "true"}:
        return "Y"
    if text in {"n", "no", "false"}:
        return "N"
    if text in {"uncertain", "u"}:
        return "Uncertain"
    return ""


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = [norm(h) for h in (reader.fieldnames or [])]
        rows = [{norm(k): norm(v) for k, v in row.items()} for row in reader]
    return headers, rows


def add_missing_headers(errors: list[str], filename: str, headers: Iterable[str], required: Iterable[str]) -> None:
    header_set = set(headers)
    missing = [h for h in required if h not in header_set]
    if missing:
        errors.append(f"{filename}: missing required header(s): {', '.join(missing)}")


def validate_domain_coverage(filename: str, rows: list[dict[str, str]], errors: list[str]) -> None:
    seen = set()
    for idx, row in enumerate(rows, start=2):
        domain = row.get("Domain", "")
        status = row.get("Coverage status", "")
        latest = row.get("Canonical latest review/meta-analysis", "")
        if is_bad_marker(domain):
            errors.append(f"{filename}: row {idx} has blank/unresolved Domain")
        else:
            seen.add(folded(domain))
        if is_bad_marker(status):
            errors.append(f"{filename}: row {idx} has unresolved Coverage status")
        if is_bad_marker(latest):
            errors.append(f"{filename}: row {idx} lacks a canonical latest review/meta-analysis")
    if len(seen) != len(rows):
        errors.append(f"{filename}: duplicate or blank domains detected")


def validate_supersession(filename: str, rows: list[dict[str, str]], errors: list[str]) -> None:
    for idx, row in enumerate(rows, start=2):
        domain = row.get("Domain", "")
        latest = row.get("Latest Review", "")
        latest_id = row.get("Latest Review Identifier", "")
        newer_found = yes_no(row.get("Newer Review Found (Y/N)", ""))
        canonical = row.get("Canonical Review Selected", "")
        older_retained = yes_no(row.get("Older Review Retained (Y/N)", ""))
        retention_reason = row.get("Retention Reason", "")

        if is_bad_marker(domain):
            errors.append(f"{filename}: row {idx} has blank/unresolved Domain")
        if newer_found not in {"Y", "N"}:
            errors.append(f"{filename}: row {idx} has invalid Newer Review Found (Y/N)")
        if is_bad_marker(canonical):
            errors.append(f"{filename}: row {idx} has no Canonical Review Selected")
        if newer_found == "Y" and (is_bad_marker(latest) or is_bad_marker(latest_id)):
            errors.append(f"{filename}: row {idx} says newer review found but Latest Review/Identifier is incomplete")
        if older_retained == "Y" and is_bad_marker(retention_reason):
            errors.append(f"{filename}: row {idx} retains an older review without a Retention Reason")


def validate_benchmark_set(filename: str, rows: list[dict[str, str]], errors: list[str]) -> None:
    identifiers = set()
    for idx, row in enumerate(rows, start=2):
        for field in ("Domain", "Benchmark Paper", "Identifier", "Reason It Is Mandatory"):
            if is_bad_marker(row.get(field, "")):
                errors.append(f"{filename}: row {idx} has blank/unresolved {field}")
        ident = folded(row.get("Identifier", ""))
        if ident:
            identifiers.add(ident)
    if len(identifiers) != len(rows):
        errors.append(f"{filename}: duplicate or blank benchmark identifiers detected")


def validate_benchmark_results(filename: str, rows: list[dict[str, str]], errors: list[str]) -> None:
    for idx, row in enumerate(rows, start=2):
        retrieved = yes_no(row.get("Retrieved (Y/N)", ""))
        included = yes_no(row.get("Included (Y/N/Uncertain)", ""))
        failure_mode = row.get("If Missed, Failure Mode", "")
        action = row.get("Action Needed", "")

        for field in ("Domain", "Benchmark Paper", "Identifier"):
            if is_bad_marker(row.get(field, "")):
                errors.append(f"{filename}: row {idx} has blank/unresolved {field}")
        if retrieved != "Y":
            errors.append(f"{filename}: row {idx} benchmark paper was not retrieved")
            if is_bad_marker(failure_mode):
                errors.append(f"{filename}: row {idx} missing failure mode for unretrieved benchmark")
            if is_bad_marker(action):
                errors.append(f"{filename}: row {idx} missing action for unretrieved benchmark")
        if included not in {"Y", "N", "Uncertain"}:
            errors.append(f"{filename}: row {idx} has invalid Included (Y/N/Uncertain)")


def validate_coverage_audit(filename: str, rows: list[dict[str, str]], errors: list[str]) -> None:
    for idx, row in enumerate(rows, start=2):
        retrieved = yes_no(row.get("Retrieved (Y/N)", ""))
        included = yes_no(row.get("Included (Y/N/Uncertain)", ""))
        reason = row.get("If Not Included, Why Not", "")
        route = row.get("Search Route That Found It", "")
        failure_mode = row.get("Missed-Paper Failure Mode", "")
        action = row.get("Action Needed", "")

        for field in ("Known Important Paper", "Source of Importance", "Identifier"):
            if is_bad_marker(row.get(field, "")):
                errors.append(f"{filename}: row {idx} has blank/unresolved {field}")
        if retrieved not in {"Y", "N"}:
            errors.append(f"{filename}: row {idx} has invalid Retrieved (Y/N)")
        if included not in {"Y", "N", "Uncertain"}:
            errors.append(f"{filename}: row {idx} has invalid Included (Y/N/Uncertain)")
        if retrieved == "Y" and is_bad_marker(route):
            errors.append(f"{filename}: row {idx} was retrieved but has no Search Route That Found It")
        if included == "N" and is_bad_marker(reason):
            errors.append(f"{filename}: row {idx} was not included but has no reason")
        if retrieved == "N" and (is_bad_marker(failure_mode) or is_bad_marker(action)):
            errors.append(f"{filename}: row {idx} was not retrieved but failure mode/action is incomplete")


def validate_final_gap_analysis(path: Path, errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        errors.append(f"{path.name}: file is empty")
        return

    lower = folded(text)
    for marker in ("tbd", "todo", "pending", "not checked", "not assessed", "not run"):
        if marker in lower:
            errors.append(f"{path.name}: contains unresolved marker `{marker}`")

    mentions_gap = "gap" in lower or "miss" in lower or "unresolved" in lower
    says_no_unresolved = any(re.search(pattern, lower) for pattern in NO_UNRESOLVED_PATTERNS)
    if not mentions_gap:
        errors.append(f"{path.name}: does not explicitly discuss gaps or misses")
    if "unresolved" in lower and not says_no_unresolved:
        errors.append(f"{path.name}: mentions unresolved items without clearly stating they are resolved/none")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate high-recall systematic review report artifacts.")
    parser.add_argument("--project", required=True, help="Project directory containing reports/")
    parser.add_argument("--reports-dir", default="", help="Override reports directory")
    parser.add_argument("--json-out", default="", help="Optional path to write JSON validation result")
    args = parser.parse_args()

    project_dir = Path(args.project).expanduser().resolve()
    reports_dir = Path(args.reports_dir).expanduser().resolve() if args.reports_dir else project_dir / "reports"

    errors: list[str] = []
    warnings: list[str] = []
    checked_files: list[str] = []

    if not project_dir.exists():
        errors.append(f"Project directory not found: {project_dir}")
    if not reports_dir.exists():
        errors.append(f"Reports directory not found: {reports_dir}")

    if not errors:
        for filename, required_headers in REQUIRED_CSVS.items():
            path = reports_dir / filename
            if not path.exists():
                errors.append(f"Missing required report: {path}")
                continue
            checked_files.append(str(path))
            try:
                headers, rows = read_csv(path)
            except Exception as exc:  # pragma: no cover - defensive CLI boundary
                errors.append(f"{filename}: could not parse CSV: {exc}")
                continue
            add_missing_headers(errors, filename, headers, required_headers)
            if not rows:
                errors.append(f"{filename}: has no data rows")
                continue
            if filename == "domain_coverage_matrix.csv":
                validate_domain_coverage(filename, rows, errors)
            elif filename == "review_supersession_audit.csv":
                validate_supersession(filename, rows, errors)
            elif filename == "benchmark_recall_set.csv":
                validate_benchmark_set(filename, rows, errors)
            elif filename == "benchmark_recall_results.csv":
                validate_benchmark_results(filename, rows, errors)
            elif filename == "coverage_audit.csv":
                validate_coverage_audit(filename, rows, errors)

        for filename in REQUIRED_TEXT:
            path = reports_dir / filename
            if not path.exists():
                errors.append(f"Missing required report: {path}")
                continue
            checked_files.append(str(path))
            validate_final_gap_analysis(path, errors)

    result = {
        "ok": not errors,
        "project": str(project_dir),
        "reports_dir": str(reports_dir),
        "checked_files": checked_files,
        "errors": errors,
        "warnings": warnings,
    }

    output = json.dumps(result, indent=2)
    print(output)
    if args.json_out:
        Path(args.json_out).expanduser().write_text(output + "\n", encoding="utf-8")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
