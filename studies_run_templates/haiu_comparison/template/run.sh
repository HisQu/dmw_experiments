#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-help}"

case "$ACTION" in
  validate|start|status|pause|resume|migrate-artifacts|analyze|prepare-promotion)
    shift
    ;;
  help|-h|--help)
    printf '%s\n' \
      "Usage: ./run.sh <validate|start|status|pause|resume|migrate-artifacts|analyze|prepare-promotion> [options]"
    exit 0
    ;;
  *)
    printf 'Unknown action: %s\n' "$ACTION" >&2
    exit 2
    ;;
esac

REPOSITORY_ROOT="$(git -C "$RUN_ROOT" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
  PYTHON_EXECUTABLE="$VIRTUAL_ENV/bin/python"
elif [[ -n "$REPOSITORY_ROOT" && -x "$REPOSITORY_ROOT/.venv/bin/python" ]]; then
  PYTHON_EXECUTABLE="$REPOSITORY_ROOT/.venv/bin/python"
else
  PYTHON_EXECUTABLE="$(command -v python3 || command -v python)"
fi

exec "$PYTHON_EXECUTABLE" -m dmw_experiments \
  --storage "$RUN_ROOT" \
  --skip-dotenv-layers \
  "$ACTION" --run-dir "$RUN_ROOT" "$@"
