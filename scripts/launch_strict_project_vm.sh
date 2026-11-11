#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 \"/absolute/path/to/project\" [--high-recall]" >&2
  exit 1
fi

PROJECT_DIR="$1"
shift || true
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COPY_ARGS=("${PROJECT_DIR}")
VALIDATE_ARGS=(
  --project "${PROJECT_DIR}"
  --require-workbook
  --check-workbook-schema
)

for arg in "$@"; do
  case "$arg" in
    --high-recall)
      COPY_ARGS+=("--high-recall")
      VALIDATE_ARGS+=("--high-recall")
      ;;
    *)
      echo "Unexpected argument: ${arg}" >&2
      exit 1
      ;;
  esac
done

python3 "${SCRIPT_DIR}/validate_strict_project_setup.py" "${VALIDATE_ARGS[@]}"

python3 - "${PROJECT_DIR}" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path


project_dir = Path(sys.argv[1]).expanduser().resolve()
policy_path = project_dir / "policy" / "pipeline_policy.yaml"

if not policy_path.exists():
    print(f"Missing policy file: {policy_path}", file=sys.stderr)
    raise SystemExit(1)

text = policy_path.read_text()
match = re.search(r'^\s*workbook_path:\s*"?(.*?)"?\s*$', text, re.MULTILINE)
workbook_value = match.group(1).strip() if match else ""

if not workbook_value:
    print(
        "Missing workbook_path in policy/pipeline_policy.yaml. "
        "Set it first, then run scripts/create_workbook_template.sh.",
        file=sys.stderr,
    )
    raise SystemExit(1)
if workbook_value == "MASTER_WORKBOOK_PATH":
    print(
        "Placeholder workbook_path detected in policy/pipeline_policy.yaml. "
        "Replace `MASTER_WORKBOOK_PATH` first, then run scripts/create_workbook_template.sh.",
        file=sys.stderr,
    )
    raise SystemExit(1)

workbook_path = Path(workbook_value).expanduser()
if not workbook_path.is_absolute():
    workbook_path = (project_dir / workbook_path).resolve()
else:
    workbook_path = workbook_path.resolve()

if not workbook_path.exists():
    print(
        f"Workbook not found: {workbook_path}\n"
        f"Create it first with: {project_dir / 'scripts' / 'create_workbook_template.sh'} \"{project_dir}\"",
        file=sys.stderr,
    )
    raise SystemExit(1)
PY

"${SCRIPT_DIR}/copy_strict_startup_prompt.sh" "${COPY_ARGS[@]}"

echo
echo "Launching disposable dangerous-mode Codex session..."
echo "Paste the clipboard contents into the new session, or paste from .codex-startup-prompt.md if needed."
echo "Then wait for the preflight restatement,"
echo "then reply: Confirmed. Proceed under those constraints."
echo

"${SCRIPT_DIR}/run_codex_vm_disposable.sh" "${PROJECT_DIR}"
