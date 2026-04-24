#!/bin/bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <logo.png> [max-kb]" >&2
  exit 1
fi

LOGO="$1"
MAX_KB="${2:-10}"
MAX_BYTES=$((MAX_KB * 1024))

if [ ! -f "$LOGO" ]; then
  echo "[ERR] file not found: $LOGO" >&2
  exit 1
fi

if ! command -v convert >/dev/null 2>&1; then
  echo "[ERR] ImageMagick 'convert' not found" >&2
  exit 1
fi

if ! command -v identify >/dev/null 2>&1; then
  echo "[ERR] ImageMagick 'identify' not found" >&2
  exit 1
fi

if ! stat -c %s "$LOGO" >/dev/null 2>&1; then
  echo "[ERR] GNU-compatible 'stat -c' not available" >&2
  exit 1
fi

TMP="${LOGO}.tmp.png"

convert "$LOGO" -resize '180x180>' -background none -gravity center -extent 180x180 "$TMP"
mv "$TMP" "$LOGO"

for colors in 256 128 64 32 24 16 12 8; do
  convert "$LOGO" -strip -colors "$colors" -define png:compression-level=9 -define png:compression-strategy=1 "$TMP"
  mv "$TMP" "$LOGO"
  size=$(stat -c %s "$LOGO")
  if [ "$size" -le "$MAX_BYTES" ]; then
    break
  fi
done

identify "$LOGO"
stat -c 'SIZE=%s bytes' "$LOGO"
