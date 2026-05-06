#!/usr/bin/env bash
set -euo pipefail

# Regression test: .env.sample must cover all compose variables
# Usage: test-env-sample-closure.sh <v2-app-dir>

APP_DIR="${1:?usage: test-env-sample-closure.sh <v2-app-dir>}"

# Find latest version directory
VER_DIR=$(find "$APP_DIR" -mindepth 1 -maxdepth 1 -type d | sort -V | tail -1)
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

# Extract variables from compose
vars_in_compose=$(grep -oE '\$\{[^}]+\}' "$COMPOSE" | sed 's/\${//;s/}//' | sort -u)

# Extract variables from .env.sample
vars_in_sample=$(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$ENV_SAMPLE" | cut -d= -f1 | sort -u)

# Check for missing variables
missing=""
for var in $vars_in_compose; do
  if ! echo "$vars_in_sample" | grep -q "^${var}$"; then
    missing="$missing $var"
  fi
done

if [[ -n "$missing" ]]; then
  echo "FAIL: compose variables missing from .env.sample:$missing"
  exit 1
fi

echo "PASS: .env.sample closure ok (compose_vars=$(echo "$vars_in_compose" | wc -l), sample_vars=$(echo "$vars_in_sample" | wc -l))"
