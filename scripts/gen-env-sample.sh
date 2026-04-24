#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="python3"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

VER_DATA="${1:-}"
OUT="${2:-}"

if [[ -z "$VER_DATA" || -z "$OUT" ]]; then
  echo "usage: gen-env-sample.sh <version-data.yml> <out-.env.sample>" >&2
  exit 2
fi
[[ -f "$VER_DATA" ]] || { echo "FAIL: not found: $VER_DATA" >&2; exit 1; }

"$PYTHON_BIN" "$(dirname "$0")/gen_env_sample.py" "$VER_DATA" "$OUT"
