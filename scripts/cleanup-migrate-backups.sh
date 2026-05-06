#!/usr/bin/env bash
set -euo pipefail

# Keep only the latest N backup runs under:
#   <backup-root>/
# Backup runs are timestamped directories: YYYYMMDD-HHMMSS

KEEP="${1:-10}"
ROOT="${2:-./1panel-migrate-backups}"

if ! [[ "$KEEP" =~ ^[0-9]+$ ]]; then
  echo "usage: cleanup-migrate-backups.sh [keepN] [backup-root]" >&2
  exit 2
fi

mkdir -p "$ROOT"

mapfile -t runs < <(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
count=${#runs[@]}

if (( count <= KEEP )); then
  echo "OK: backups=$count, keep=$KEEP (nothing to delete)"
  exit 0
fi

to_delete=("${runs[@]:0:count-KEEP}")

echo "Backups total: $count"
echo "Keeping latest: $KEEP"
echo "Deleting: ${#to_delete[@]}"

for d in "${to_delete[@]}"; do
  echo "- rm -rf $ROOT/$d"
  rm -rf "$ROOT/$d"
done

echo "OK: cleanup done"
