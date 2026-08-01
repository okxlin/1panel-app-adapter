#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-}"
VER_DIR="${2:-}"
REPLACE_INIT=0
DIR_OWNER_ARGS=()
SCRIPTS_DIR="$VER_DIR/scripts"

usage() {
  echo "usage: finalize_runtime_scripts.sh <app-dir> <version-dir> [--dir-owner ENV_KEY=UID:GID:MODE] [--replace-init]"
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ -z "$APP_DIR" || -z "$VER_DIR" ]]; then
  usage >&2
  exit 2
fi

shift 2
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir-owner)
      [[ $# -ge 2 ]] || { echo "FAIL: --dir-owner requires ENV_KEY=UID:GID:MODE" >&2; exit 2; }
      DIR_OWNER_ARGS+=("--dir-owner" "$2")
      shift 2
      ;;
    --replace-init)
      REPLACE_INIT=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "FAIL: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

command -v realpath >/dev/null 2>&1 || { echo "FAIL: realpath is required" >&2; exit 2; }
[[ -d "$APP_DIR" && ! -L "$APP_DIR" ]] || { echo "FAIL: app directory must be a real directory" >&2; exit 2; }
[[ -d "$VER_DIR" && ! -L "$VER_DIR" ]] || { echo "FAIL: version directory must be a real directory" >&2; exit 2; }
app_real="$(realpath -e -- "$APP_DIR")"
ver_real="$(realpath -e -- "$VER_DIR")"
[[ "$(dirname -- "$ver_real")" == "$app_real" ]] || { echo "FAIL: version directory must be a direct child of the app directory" >&2; exit 2; }
[[ -f "$VER_DIR/data.yml" && ! -L "$VER_DIR/data.yml" ]] || { echo "FAIL: data.yml must be a regular non-symlink file" >&2; exit 2; }

python_bin=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
    python_bin="$candidate"
    break
  fi
done
if [[ -z "$python_bin" ]]; then
  echo "FAIL: python interpreter not available for lifecycle script generation" >&2
  exit 2
fi
script_dir="$(cd "$(dirname "$0")" && pwd)"
python_args=(
  "$VER_DIR/data.yml"
  "$SCRIPTS_DIR/init.sh"
  --finalize-lifecycle
  "${DIR_OWNER_ARGS[@]}"
)
if [[ "$REPLACE_INIT" -eq 1 ]]; then
  python_args+=(--replace-init)
fi
"$python_bin" "$script_dir/runtime_script_utils.py" "${python_args[@]}"

echo "OK: finalized runtime scripts -> $SCRIPTS_DIR"
