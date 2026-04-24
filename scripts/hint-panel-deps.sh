#!/usr/bin/env bash
set -euo pipefail

compose_file="${1:-}"
[[ -n "$compose_file" ]] || { echo "usage: hint-panel-deps.sh <docker-compose.yml>" >&2; exit 2; }
[[ -f "$compose_file" ]] || exit 0

svc_count=$(awk '
  $1=="services:" {in_services=1; next}
  in_services && /^[^[:space:]]/ {exit}
  in_services && /^[[:space:]][[:space:]][A-Za-z0-9_.-]+:[[:space:]]*$/ {c++}
  END{print c+0}
' "$compose_file" 2>/dev/null || echo 0)

if [[ "$svc_count" -gt 1 ]]; then
  if grep -Eqi '(postgres|postgresql|mysql|mariadb|redis)' "$compose_file"; then
    echo "[HINT] Detected db/redis services in compose. Consider --with-panel-deps (PANEL_DB_*/PANEL_REDIS_* mapping)."
  fi
fi
