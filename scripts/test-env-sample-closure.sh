#!/usr/bin/env bash
set -euo pipefail

# Regression test: .env.sample must cover all compose variables
# Usage: test-env-sample-closure.sh <v2-app-dir>

APP_DIR="${1:?usage: test-env-sample-closure.sh <v2-app-dir>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  echo "FAIL: python interpreter not available" >&2
  exit 2
fi

# Find the latest actual version directory, excluding sibling assets/license folders.
VER_DIR=$(find "$APP_DIR" -mindepth 1 -maxdepth 1 -type d \
  -exec test -f '{}/docker-compose.yml' \; -print | sort -V | tail -1)
if [[ -z "$VER_DIR" ]]; then
  echo "FAIL: no version directory found in $APP_DIR"
  exit 1
fi

COMPOSE="$VER_DIR/docker-compose.yml"
ENV_SAMPLE="$VER_DIR/.env.sample"

if [[ ! -f "$COMPOSE" ]]; then
  echo "FAIL: docker-compose.yml not found in $VER_DIR"
  exit 1
fi

if [[ ! -f "$ENV_SAMPLE" ]]; then
  echo "FAIL: .env.sample not found in $VER_DIR"
  exit 1
fi

set +e
compose_vars_output=$("$PYTHON_BIN" "$SCRIPT_DIR/compose_env_vars.py" "$COMPOSE" 2>&1)
compose_vars_status=$?
set -e
if [[ $compose_vars_status -ne 0 ]]; then
  echo "FAIL: cannot extract Compose variables" >&2
  [[ -z "$compose_vars_output" ]] || echo "$compose_vars_output" >&2
  exit 1
fi
vars_in_compose=()
if [[ -n "$compose_vars_output" ]]; then
  mapfile -t vars_in_compose <<< "$compose_vars_output"
fi
mapfile -t vars_in_sample < <(sed -nE 's/^([A-Za-z_][A-Za-z0-9_]*)=.*/\1/p' "$ENV_SAMPLE" | sort -u)

declare -A sample_lookup=()
for var in "${vars_in_sample[@]}"; do
  sample_lookup["$var"]=1
done

missing=()
for var in "${vars_in_compose[@]}"; do
  if [[ ! -v "sample_lookup[$var]" ]]; then
    missing+=("$var")
  fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "FAIL: compose variables missing from .env.sample: ${missing[*]}"
  exit 1
fi

if [[ -v "sample_lookup[CONTAINER_NAME]" ]]; then
  container_name_value="$(sed -nE 's/^CONTAINER_NAME=(.*)$/\1/p' "$ENV_SAMPLE" | tail -1)"
  container_name_value="${container_name_value#"${container_name_value%%[![:space:]]*}"}"
  container_name_value="${container_name_value%"${container_name_value##*[![:space:]]}"}"
  double_quoted_empty='^"[[:space:]]*"([[:space:]]+#.*)?$'
  single_quoted_empty="^'[[:space:]]*'([[:space:]]+#.*)?$"
  if [[ -z "$container_name_value" || "$container_name_value" == \#* \
    || "$container_name_value" =~ $double_quoted_empty \
    || "$container_name_value" =~ $single_quoted_empty ]]; then
    echo "FAIL: CONTAINER_NAME must be non-empty in .env.sample"
    exit 1
  fi
fi

echo "PASS: .env.sample closure ok (compose_vars=${#vars_in_compose[@]}, sample_vars=${#vars_in_sample[@]})"
