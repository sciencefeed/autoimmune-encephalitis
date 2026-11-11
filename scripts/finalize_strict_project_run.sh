#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 \"/absolute/path/to/project\" [\"/absolute/path/to/sandbox\"] [--high-recall] [--id-column NAME] [--expected-id VALUE ...] [--min-nonempty-rows N] [--header-row N]" >&2
  exit 1
fi

PROJECT_DIR="$1"
shift || true
SANDBOX_DIR=""
ID_COLUMN=""
MIN_NONEMPTY_ROWS="0"
HEADER_ROW=""
HIGH_RECALL="0"
EXPECTED_IDS=()

if [[ $# -gt 0 && "${1:-}" != --* ]]; then
  SANDBOX_DIR="$1"
  shift || true
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --id-column)
      ID_COLUMN="$2"
      shift 2
      ;;
    --expected-id)
      EXPECTED_IDS+=("$2")
      shift 2
      ;;
    --min-nonempty-rows)
      MIN_NONEMPTY_ROWS="$2"
      shift 2
      ;;
    --header-row)
      HEADER_ROW="$2"
      shift 2
      ;;
    --high-recall)
      HIGH_RECALL="1"
      shift
      ;;
    *)
      echo "Unexpected argument: $1" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"${SCRIPT_DIR}/sync_project_from_latest_sandbox.sh" "${PROJECT_DIR}" "${SANDBOX_DIR}"

VERIFY_ARGS=()
while IFS= read -r line; do
  VERIFY_ARGS+=("${line}")
done < <(python3 - "${PROJECT_DIR}" "${ID_COLUMN}" "${MIN_NONEMPTY_ROWS}" "${HEADER_ROW}" "${EXPECTED_IDS[@]}" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path


def parse_policy_field(text: str, field: str) -> str:
    match = re.search(rf"^\s*{re.escape(field)}:\s*\"?(.*?)\"?\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_task_value(text: str, label: str) -> str:
    tick = chr(96)
    pattern = rf"^\s*{re.escape(label)}:\s*{tick}([^{tick}]+){tick}\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def split_csvish(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


project_dir = Path(sys.argv[1]).expanduser().resolve()
override_id = sys.argv[2].strip()
min_rows = sys.argv[3].strip()
header_row = sys.argv[4].strip()
expected_ids = [arg for arg in sys.argv[5:] if arg.strip()]

policy_path = project_dir / "policy" / "pipeline_policy.yaml"
task_path = project_dir / "prompts" / "task_request_template.md"

policy_text = policy_path.read_text()
task_text = task_path.read_text()

workbook_raw = parse_policy_field(policy_text, "workbook_path")
sheet_raw = parse_task_value(task_text, "1. Sheets allowed to edit")
columns_raw = parse_task_value(task_text, "2. Columns allowed to edit")

workbook_path = Path(workbook_raw).expanduser()
if not workbook_path.is_absolute():
    workbook_path = (project_dir / workbook_path).resolve()
else:
    workbook_path = workbook_path.resolve()

sheet_name = split_csvish(sheet_raw)[0]
columns = split_csvish(columns_raw)

candidate_id = override_id
if not candidate_id:
    for name in ("PMID", "ID", "Identifier", "DOI"):
        if name in columns:
            candidate_id = name
            break

parts = [
    "--workbook", str(workbook_path),
    "--sheet", sheet_name,
    "--min-nonempty-rows", min_rows,
]
if candidate_id:
    parts.extend(["--id-column", candidate_id])
if header_row:
    parts.extend(["--header-row", header_row])
for expected_id in expected_ids:
    parts.extend(["--expected-id", expected_id])

for item in parts:
    print(item)
PY
)

echo
echo "Running host-side workbook verification..."
python3 "${SCRIPT_DIR}/verify_saved_workbook_state.py" "${VERIFY_ARGS[@]}"

if [[ "${HIGH_RECALL}" == "1" ]]; then
  echo
  echo "Running high-recall report validation..."
  python3 "${SCRIPT_DIR}/validate_high_recall_reports.py" --project "${PROJECT_DIR}"
fi
