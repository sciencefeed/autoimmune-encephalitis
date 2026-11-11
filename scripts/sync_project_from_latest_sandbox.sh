#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 \"/absolute/path/to/project\" [\"/absolute/path/to/sandbox\"]" >&2
  exit 1
fi

PROJECT_DIR="$1"
SANDBOX_DIR="${2:-}"
MARKER_FILE="${PROJECT_DIR}/.codex-last-sandbox-path"

if [[ ! -d "${PROJECT_DIR}" ]]; then
  echo "Project directory not found: ${PROJECT_DIR}" >&2
  exit 1
fi

if [[ -z "${SANDBOX_DIR}" ]]; then
  if [[ -f "${MARKER_FILE}" ]]; then
    SANDBOX_DIR="$(tr -d '\r\n' < "${MARKER_FILE}")"
  fi
fi

if [[ -z "${SANDBOX_DIR}" ]]; then
  SANDBOX_DIR="$(
    ls -td /tmp/ae-codex-sandboxes/* 2>/dev/null | while IFS= read -r candidate; do
      if [[ -d "${candidate}/workspace" ]]; then
        printf '%s\n' "${candidate}"
        break
      fi
    done
  )"
fi

if [[ -z "${SANDBOX_DIR}" || ! -d "${SANDBOX_DIR}/workspace" ]]; then
  echo "Could not find a sandbox workspace to sync from." >&2
  exit 1
fi

echo "Syncing from sandbox:"
echo "  ${SANDBOX_DIR}/workspace"
echo "to project:"
echo "  ${PROJECT_DIR}"

rsync -a \
  --exclude ".DS_Store" \
  "${SANDBOX_DIR}/workspace/" "${PROJECT_DIR}/"

echo "Sync complete."
