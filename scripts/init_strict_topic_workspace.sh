#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 \"/absolute/path/to/new-topic-project\""
  exit 1
fi

TARGET_DIR="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="${SCRIPT_DIR}/../templates/strict_topic"

if [[ ! -d "${TEMPLATE_DIR}" ]]; then
  echo "Template directory not found: ${TEMPLATE_DIR}" >&2
  exit 1
fi

mkdir -p "${TARGET_DIR}"

# Copy template files only if they do not already exist.
rsync -a --ignore-existing "${TEMPLATE_DIR}/" "${TARGET_DIR}/"

echo "Strict topic workspace initialized:"
echo "  ${TARGET_DIR}"
echo
echo "Next steps:"
echo "1) Edit ${TARGET_DIR}/policy/pipeline_policy.yaml"
echo "2) Edit ${TARGET_DIR}/prompts/task_request_template.md"
echo "3) Validate the setup fields:"
echo "   /Users/zeryabmeyer/Documents/Autoimmune\\ Encephalitis/scripts/validate_strict_project_setup.py --project \"${TARGET_DIR}\""
echo "4) Create the workbook from those settings:"
echo "   ${TARGET_DIR}/scripts/create_workbook_template.sh \"${TARGET_DIR}\""
echo "5) Launch the dangerous-mode disposable session:"
echo "   /Users/zeryabmeyer/Documents/Autoimmune\\ Encephalitis/scripts/launch_strict_project_vm.sh \"${TARGET_DIR}\""
echo "6) In the new session, paste the clipboard contents and wait for the preflight restatement"
