#!/usr/bin/env bash
set -euo pipefail

DIR=""
STRICT_STORE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --strict-store) STRICT_STORE=1; shift 1 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done
[[ -n "$DIR" ]] || { echo "usage: validate.sh --dir <v2-app-dir> [--strict-store]"; exit 2; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ "$STRICT_STORE" == "1" ]]; then
  bash "$SCRIPT_DIR/validate-v2.sh" --dir "$DIR" --strict-store
else
  bash "$SCRIPT_DIR/validate-v2.sh" --dir "$DIR"
fi
