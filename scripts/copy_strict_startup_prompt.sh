#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 \"/absolute/path/to/project\" [--high-recall]" >&2
  exit 1
fi

PROJECT_DIR="$1"
shift || true
KICKOFF="${PROJECT_DIR}/prompts/kickoff_prompt.md"
TASK="${PROJECT_DIR}/prompts/task_request_template.md"
HIGH_RECALL_ADDENDUM="${PROJECT_DIR}/prompts/high_recall_addendum.md"
OUTPUT_FILE="${PROJECT_DIR}/.codex-startup-prompt.md"
HIGH_RECALL="0"

for arg in "$@"; do
  case "$arg" in
    --high-recall)
      HIGH_RECALL="1"
      ;;
    *)
      echo "Unexpected argument: ${arg}" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "${KICKOFF}" ]]; then
  echo "Missing kickoff prompt: ${KICKOFF}" >&2
  exit 1
fi

if [[ ! -f "${TASK}" ]]; then
  echo "Missing task request template: ${TASK}" >&2
  exit 1
fi

if [[ "${HIGH_RECALL}" == "1" && ! -f "${HIGH_RECALL_ADDENDUM}" ]]; then
  echo "Missing high-recall addendum: ${HIGH_RECALL_ADDENDUM}" >&2
  exit 1
fi

if ! command -v pbcopy >/dev/null 2>&1; then
  PBCOPY_AVAILABLE="0"
else
  PBCOPY_AVAILABLE="1"
fi

{
  cat "${KICKOFF}"
  printf '\n\n'
  cat "${TASK}"
  if [[ "${HIGH_RECALL}" == "1" ]]; then
    printf '\n\n'
    cat "${HIGH_RECALL_ADDENDUM}"
  fi
  printf '\n\nDo not begin retrieval, searching, or writing yet. First restate the exact scope, exact sheets/columns allowed, and exact preflight plan. Wait for my confirmation before any execution.\n'
} > "${OUTPUT_FILE}"

if [[ "${PBCOPY_AVAILABLE}" == "1" ]]; then
  if pbcopy < "${OUTPUT_FILE}"; then
    echo "Startup prompt copied to clipboard for:"
    echo "  ${PROJECT_DIR}"
  else
    echo "Failed to copy startup prompt to the clipboard." >&2
    echo "Use this file instead:" >&2
    echo "  ${OUTPUT_FILE}" >&2
  fi
else
  echo "pbcopy is not available on this machine." >&2
  echo "Use this file instead:" >&2
  echo "  ${OUTPUT_FILE}" >&2
fi

echo "Startup prompt file:"
echo "  ${OUTPUT_FILE}"
if [[ "${HIGH_RECALL}" == "1" ]]; then
  echo "Mode:"
  echo "  high-recall addendum included"
fi
