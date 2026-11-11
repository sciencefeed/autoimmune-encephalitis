#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_DIR="${1:-$(pwd)}"
shift || true

if [[ ! -d "${WORKSPACE_DIR}" ]]; then
  echo "Workspace directory not found: ${WORKSPACE_DIR}" >&2
  exit 1
fi

if [[ -t 0 && -t 1 ]]; then
  DOCKER_RUN_CMD=(docker run --rm -it)
else
  DOCKER_RUN_CMD=(docker run --rm)
fi

map_path_arg() {
  local value="$1"
  if [[ "${value}" == "${WORKSPACE_DIR}"* ]]; then
    printf "/work%s" "${value#${WORKSPACE_DIR}}"
  else
    printf "%s" "${value}"
  fi
}

MAPPED_ARGS=()
for arg in "$@"; do
  MAPPED_ARGS+=("$(map_path_arg "$arg")")
done

"${DOCKER_RUN_CMD[@]}" \
  --name "ae-review-pipeline" \
  --user "$(id -u):$(id -g)" \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 512 \
  --memory 8g \
  --cpus 6 \
  --mount "type=bind,src=${WORKSPACE_DIR},dst=/work" \
  --tmpfs "/tmp:rw,noexec,nosuid,size=1g" \
  -w /work \
  ae-review:latest \
  python src/ae_review_pipeline.py "${MAPPED_ARGS[@]}"
