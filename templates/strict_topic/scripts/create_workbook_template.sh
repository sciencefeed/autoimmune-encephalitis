#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 \"/absolute/path/to/project\" [\"/absolute/path/to/workbook.xlsx\"] [--force]" >&2
  exit 1
fi

PROJECT_DIR="$1"
shift

WORKBOOK_PATH=""
FORCE="0"

for arg in "$@"; do
  case "$arg" in
    --force)
      FORCE="1"
      ;;
    *)
      if [[ -n "${WORKBOOK_PATH}" ]]; then
        echo "Unexpected extra argument: ${arg}" >&2
        exit 1
      fi
      WORKBOOK_PATH="$arg"
      ;;
  esac
done

python3 - "${PROJECT_DIR}" "${WORKBOOK_PATH}" "${FORCE}" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

from openpyxl import Workbook


def parse_policy_workbook_path(policy_path: Path) -> str:
    text = policy_path.read_text()
    match = re.search(r'^\s*workbook_path:\s*"?(.*?)"?\s*$', text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_task_value(task_text: str, label: str) -> str:
    pattern = rf"^\s*{re.escape(label)}:\s*`([^`]+)`\s*$"
    match = re.search(pattern, task_text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def split_csvish(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


project_dir = Path(sys.argv[1]).expanduser().resolve()
workbook_override = sys.argv[2].strip()
force = sys.argv[3] == "1"

policy_path = project_dir / "policy" / "pipeline_policy.yaml"
task_path = project_dir / "prompts" / "task_request_template.md"

if not policy_path.exists():
    print(f"Missing policy file: {policy_path}", file=sys.stderr)
    raise SystemExit(1)
if not task_path.exists():
    print(f"Missing task template: {task_path}", file=sys.stderr)
    raise SystemExit(1)

task_text = task_path.read_text()
sheet_field = parse_task_value(task_text, "1. Sheets allowed to edit")
columns_field = parse_task_value(task_text, "2. Columns allowed to edit")

if not sheet_field:
    fail("Could not parse allowed sheet name from task_request_template.md")
if not columns_field:
    fail("Could not parse allowed columns from task_request_template.md")

sheet_name = split_csvish(sheet_field)[0]
headers = split_csvish(columns_field)

policy_workbook_path = parse_policy_workbook_path(policy_path)

if sheet_name in {"SHEET_A", "SHEET_B"} or sheet_name.startswith("SHEET_"):
    fail("Task template still contains placeholder sheet names. Replace `SHEET_A, SHEET_B` first.")
if any(header.startswith("COLUMN_") for header in headers):
    fail("Task template still contains placeholder column names. Replace `COLUMN_1, COLUMN_2, COLUMN_3` first.")
if policy_workbook_path == "MASTER_WORKBOOK_PATH":
    fail("Policy file still contains placeholder workbook_path. Replace `MASTER_WORKBOOK_PATH` first.")
if project_dir.name == "TOPIC_NAME":
    fail("Project directory still appears to be a placeholder. Use a real project folder name.")

if workbook_override:
    workbook_path = Path(workbook_override).expanduser()
elif policy_workbook_path:
    workbook_path = Path(policy_workbook_path).expanduser()
else:
    workbook_path = project_dir / f"{project_dir.name}.xlsx"

if not workbook_path.is_absolute():
    workbook_path = (project_dir / workbook_path).resolve()
else:
    workbook_path = workbook_path.resolve()

if workbook_path.exists() and not force:
    print(
        f"Workbook already exists: {workbook_path}\n"
        "Refusing to overwrite without --force.",
        file=sys.stderr,
    )
    raise SystemExit(1)

workbook_path.parent.mkdir(parents=True, exist_ok=True)

wb = Workbook()
ws = wb.active
ws.title = sheet_name

for idx, header in enumerate(headers, start=1):
    ws.cell(row=1, column=idx, value=header)

wb.save(workbook_path)

print(f"Created workbook: {workbook_path}")
print(f"Sheet: {sheet_name}")
print(f"Header row: 1")
print(f"Columns: {len(headers)}")
PY
