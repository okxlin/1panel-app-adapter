#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-}"
VER_DIR="${2:-}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  echo "usage: finalize_runtime_scripts.sh <app-dir> <version-dir>"
  exit 0
fi

if [[ -z "$APP_DIR" || -z "$VER_DIR" ]]; then
  echo "usage: finalize_runtime_scripts.sh <app-dir> <version-dir>" >&2
  exit 2
fi

mkdir -p "$VER_DIR/scripts"

if [[ ! -f "$VER_DIR/scripts/init.sh" ]]; then
  python_bin=""
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
      python_bin="$candidate"
      break
    fi
  done
  if [[ -z "$python_bin" ]]; then
    echo "FAIL: python interpreter not available for init.sh generation" >&2
    exit 2
  fi
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  "$python_bin" "$script_dir/runtime_script_utils.py" "$VER_DIR/data.yml" "$VER_DIR/scripts/init.sh"
fi

if [[ ! -f "$VER_DIR/scripts/upgrade.sh" ]]; then
  cat > "$VER_DIR/scripts/upgrade.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
exit 0
SH
  chmod +x "$VER_DIR/scripts/upgrade.sh"
fi

if [[ ! -f "$VER_DIR/scripts/uninstall.sh" ]]; then
  cat > "$VER_DIR/scripts/uninstall.sh" <<'SH'
#!/bin/bash
docker-compose down --volumes
SH
  chmod +x "$VER_DIR/scripts/uninstall.sh"
fi

echo "OK: finalized runtime scripts -> $VER_DIR/scripts"
