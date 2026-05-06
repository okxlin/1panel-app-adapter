#!/usr/bin/env bash
set -euo pipefail

# v2 generator wrapper (compat CLI)
# Output layout: <output>/<app>/{data.yml,README.md,<version>/{data.yml,docker-compose.yml,...}}

APP=""
IMAGE=""
INTERNAL_PORT=""
HOST_PORT=""
OUT=""
VERSION="latest"
TYPE="tool"
TAG=""
AUTH_USER=""
AUTH_PASS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app) APP="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --internal-port) INTERNAL_PORT="$2"; shift 2 ;;
    --host-port) HOST_PORT="$2"; shift 2 ;;
    --output) OUT="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --type) TYPE="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --auth-user) AUTH_USER="$2"; shift 2 ;;
    --auth-pass) AUTH_PASS="$2"; shift 2 ;;
    *) echo "unknown arg: $1"; exit 2 ;;
  esac
done

[[ -n "$APP" && -n "$IMAGE" && -n "$INTERNAL_PORT" && -n "$HOST_PORT" && -n "$OUT" ]] || {
  echo "usage: generate.sh --app <name> --image <image> --internal-port <p> --host-port <p> --output <dir> [--version <ver>] [--type <website|tool|middleware>] [--tag <allowed-tag>] [--auth-user <u> --auth-pass <p>]"
  exit 2
}

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCAFFOLD="$SCRIPT_DIR/scaffold-v2.sh"

args=(
  --app-key "$APP"
  --title "$APP"
  --image "$IMAGE"
  --version "$VERSION"
  --out-dir "$OUT"
  --port "$HOST_PORT"
  --target-port "$INTERNAL_PORT"
  --type "$TYPE"
)
[[ -n "$TAG" ]] && args+=(--tag "$TAG")

# linuxserver/joplin auth convenience (legacy compatibility)
if [[ -n "$AUTH_USER" || -n "$AUTH_PASS" ]]; then
  [[ -n "$AUTH_USER" && -n "$AUTH_PASS" ]] || { echo "auth requires both --auth-user and --auth-pass"; exit 2; }
fi

bash "$SCAFFOLD" "${args[@]}"

VER_DIR="$OUT/$APP/$VERSION"
if [[ -n "$AUTH_USER" && -n "$AUTH_PASS" ]]; then
  awk -v u="$AUTH_USER" -v p="$AUTH_PASS" '
    /environment:/ {print; print "      - CUSTOM_USER="u; print "      - PASSWORD="p; next}
    {print}
  ' "$VER_DIR/docker-compose.yml" > "$VER_DIR/.docker-compose.yml.tmp"
  mv "$VER_DIR/.docker-compose.yml.tmp" "$VER_DIR/docker-compose.yml"
fi

echo "OK: generated(v2) -> $OUT/$APP"
