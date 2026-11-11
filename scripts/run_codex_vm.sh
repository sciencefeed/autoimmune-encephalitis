#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="${1:-$(pwd)}"
shift || true

if [[ ! -d "${WORKSPACE_DIR}" ]]; then
  echo "Workspace directory not found: ${WORKSPACE_DIR}" >&2
  exit 1
fi

CODEX_STATE_DIR="${CODEX_STATE_DIR:-$HOME/.codex-docker-state}"
mkdir -p "${CODEX_STATE_DIR}"

DOCKER_IMAGE="${DOCKER_IMAGE:-ae-codex:latest}"

CODEX_ARGS=(--dangerously-bypass-approvals-and-sandbox)
if [[ $# -gt 0 ]]; then
  CODEX_ARGS+=("$@")
fi

if [[ -t 0 && -t 1 ]]; then
  DOCKER_RUN_CMD=(docker run --rm -it)
else
  DOCKER_RUN_CMD=(docker run --rm)
fi

"${DOCKER_RUN_CMD[@]}" \
  --name "ae-codex-session" \
  --user "$(id -u):$(id -g)" \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 512 \
  --memory 8g \
  --cpus 6 \
  --mount "type=bind,src=${WORKSPACE_DIR},dst=/work" \
  --mount "type=bind,src=${CODEX_STATE_DIR},dst=/codex-home" \
  --tmpfs "/tmp:rw,noexec,nosuid,size=1g" \
  -e HOME=/codex-home \
  -e CODEX_HOME=/codex-home \
  -w /work \
  "${DOCKER_IMAGE}" \
  codex "${CODEX_ARGS[@]}"
