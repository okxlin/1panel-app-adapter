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
  cat > "$VER_DIR/scripts/init.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
mkdir -p ./data
SH
  chmod +x "$VER_DIR/scripts/init.sh"
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
