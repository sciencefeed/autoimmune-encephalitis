#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from openpyxl import load_workbook


PLACEHOLDER_PATTERNS = {
    "topic_name": {"TOPIC_NAME"},
    "workbook_path": {"MASTER_WORKBOOK_PATH"},
}


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def parse_policy_field(text: str, field: str) -> str:
    match = re.search(rf"^\s*{re.escape(field)}:\s*\"?(.*?)\"?\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_task_value(text: str, label: str) -> str:
    pattern = rf"^\s*{re.escape(label)}:\s*`([^`]+)`\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def split_csvish(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def resolve_path(base: Path, raw: str) -> Path:
    candidate = Path(raw).expanduser()
    return candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate strict-topic project setup before launch.")
    parser.add_argument("--project", required=True, help="Absolute path to the project directory")
    parser.add_argument("--require-workbook", action="store_true", help="Fail if workbook file does not exist")
    parser.add_argument("--check-workbook-schema", action="store_true", help="Check that workbook sheet/headers match task template")
    parser.add_argument("--high-recall", action="store_true", help="Require high-recall addendum file")
    args = parser.parse_args()

    project_dir = Path(args.project).expanduser().resolve()
    if not project_dir.is_dir():
        return fail(f"Project directory not found: {project_dir}")

    policy_path = project_dir / "policy" / "pipeline_policy.yaml"
    task_path = project_dir / "prompts" / "task_request_template.md"
    kickoff_path = project_dir / "prompts" / "kickoff_prompt.md"
    high_recall_path = project_dir / "prompts" / "high_recall_addendum.md"

    for path in (policy_path, task_path, kickoff_path):
        if not path.exists():
            return fail(f"Missing required file: {path}")
    if args.high_recall and not high_recall_path.exists():
        return fail(f"Missing high-recall addendum: {high_recall_path}")

    policy_text = policy_path.read_text()
    task_text = task_path.read_text()

    topic_name = parse_policy_field(policy_text, "topic_name")
    workbook_raw = parse_policy_field(policy_text, "workbook_path")
    sheets_raw = parse_task_value(task_text, "1. Sheets allowed to edit")
    columns_raw = parse_task_value(task_text, "2. Columns allowed to edit")

    if not topic_name:
        return fail("Missing topic_name in policy/pipeline_policy.yaml")
    if topic_name in PLACEHOLDER_PATTERNS["topic_name"]:
        return fail("Placeholder topic_name detected in policy/pipeline_policy.yaml")

    if not workbook_raw:
        return fail("Missing workbook_path in policy/pipeline_policy.yaml")
    if workbook_raw in PLACEHOLDER_PATTERNS["workbook_path"]:
        return fail("Placeholder workbook_path detected in policy/pipeline_policy.yaml")

    if not sheets_raw:
        return fail("Could not parse `Sheets allowed to edit` from prompts/task_request_template.md")
    if any(item.startswith("SHEET_") for item in split_csvish(sheets_raw)):
        return fail("Placeholder sheet names still present in prompts/task_request_template.md")

    if not columns_raw:
        return fail("Could not parse `Columns allowed to edit` from prompts/task_request_template.md")
    if any(item.startswith("COLUMN_") for item in split_csvish(columns_raw)):
        return fail("Placeholder column names still present in prompts/task_request_template.md")

    workbook_path = resolve_path(project_dir, workbook_raw)
    print(f"Project: {project_dir}")
    print(f"Workbook path: {workbook_path}")
    print(f"Allowed sheet(s): {sheets_raw}")
    print(f"Allowed columns: {columns_raw}")

    if args.require_workbook or args.check_workbook_schema:
        if not workbook_path.exists():
            return fail(f"Workbook not found: {workbook_path}")

    if args.check_workbook_schema:
        wb = load_workbook(workbook_path, read_only=True)
        first_sheet = split_csvish(sheets_raw)[0]
        if first_sheet not in wb.sheetnames:
            return fail(f"Workbook is missing required sheet: {first_sheet}")
        ws = wb[first_sheet]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        normalized_headers = {str(v).strip() for v in headers if v not in (None, "")}
        expected_headers = split_csvish(columns_raw)
        missing = [h for h in expected_headers if h not in normalized_headers]
        if missing:
            return fail(
                "Workbook schema mismatch. Missing expected header(s): " + ", ".join(missing)
            )
        print(f"Workbook schema check: PASS ({first_sheet})")

    print("Strict project setup validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
