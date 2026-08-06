#!/usr/bin/env bash
set -euo pipefail

RUN_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ACTION="${1:-help}"

case "$ACTION" in
  validate|start|status|pause|resume|analyze|prepare-promotion)
    shift
    ;;
  help|-h|--help)
    printf '%s\n' \
      "Usage: ./run.sh <validate|start|status|pause|resume|analyze|prepare-promotion> [options]"
    exit 0
    ;;
  *)
    printf 'Unknown action: %s\n' "$ACTION" >&2
    exit 2
    ;;
esac

exec python -m dmw_experiments \
  --storage "$RUN_ROOT" \
  --skip-dotenv-layers \
  "$ACTION" --run-dir "$RUN_ROOT" "$@"
