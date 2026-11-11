#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:-$(pwd)}"
shift || true

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "Source directory not found: ${SOURCE_DIR}" >&2
  exit 1
fi

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required but not found in PATH." >&2
  exit 1
fi

SANDBOX_BASE="${SANDBOX_BASE:-/tmp/ae-codex-sandboxes}"
mkdir -p "${SANDBOX_BASE}"

STAMP="$(date +%Y%m%d-%H%M%S)"
SANDBOX_DIR="${SANDBOX_BASE}/sandbox-${STAMP}"
WORKSPACE_COPY="${SANDBOX_DIR}/workspace"
CODEX_HOME_COPY="${SANDBOX_DIR}/codex-home"
MARKER_FILE="${SOURCE_DIR}/.codex-last-sandbox-path"

mkdir -p "${WORKSPACE_COPY}" "${CODEX_HOME_COPY}"

rsync -a \
  --exclude ".DS_Store" \
  "${SOURCE_DIR}/" "${WORKSPACE_COPY}/"

# Reuse local Codex auth/config so the disposable session does not force a fresh device-code login.
if [[ -f "${HOME}/.codex/auth.json" ]]; then
  cp "${HOME}/.codex/auth.json" "${CODEX_HOME_COPY}/auth.json"
fi
if [[ -f "${HOME}/.codex/config.toml" ]]; then
  cp "${HOME}/.codex/config.toml" "${CODEX_HOME_COPY}/config.toml"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="${SCRIPT_DIR}/run_codex_vm.sh"
if [[ ! -x "${LAUNCHER}" ]]; then
  echo "Expected launcher missing or not executable: ${LAUNCHER}" >&2
  exit 1
fi

echo "Disposable sandbox created:"
echo "  Workspace copy: ${WORKSPACE_COPY}"
echo "  Codex home:     ${CODEX_HOME_COPY}"
echo
echo "When finished, disposable files remain for review."
echo "Delete with:"
echo "  rm -rf \"${SANDBOX_DIR}\""
echo

printf '%s\n' "${SANDBOX_DIR}" > "${MARKER_FILE}"
echo "Recorded sandbox path in:"
echo "  ${MARKER_FILE}"
echo

CODEX_STATE_DIR="${CODEX_HOME_COPY}" "${LAUNCHER}" "${WORKSPACE_COPY}" "$@"
