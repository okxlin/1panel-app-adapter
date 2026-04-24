#!/usr/bin/env bash
set -euo pipefail

DIR=""
STRICT_STORE=0
FAILURES=0
WARNINGS=0
INFOS=0
PY_WARNINGS=0
PYTHON_BIN=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  echo "[A][FAIL] python interpreter not available"
  exit 1
fi

usage() {
  echo "usage: validate-v2.sh --dir <app-dir> [--strict-store]"
}

fail() {
  echo "[A][FAIL] $*"
  FAILURES=$((FAILURES + 1))
}

warn() {
  echo "[B][WARN] $*"
  WARNINGS=$((WARNINGS + 1))
}

info() {
  echo "[C][INFO] $*"
  INFOS=$((INFOS + 1))
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) DIR="$2"; shift 2 ;;
    --strict-store) STRICT_STORE=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown arg: $1"; usage; exit 2 ;;
  esac
done

[[ -n "$DIR" ]] || { usage; exit 2; }
[[ -d "$DIR" ]] || { echo "[A][FAIL] app dir not found: $DIR"; exit 1; }

ROOT="$DIR/data.yml"
SOURCE_EVIDENCE="$DIR/source-evidence.json"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMPLICIT_ENVKEYS_FILE="$SCRIPT_DIR/../references/implicit-envkeys.md"
mapfile -t version_dirs < <(find "$DIR" -mindepth 1 -maxdepth 1 -type d ! -name '.*')
if [[ ${#version_dirs[@]} -eq 0 ]]; then
  echo "[A][FAIL] missing version directory"
  exit 1
fi
if [[ ${#version_dirs[@]} -ne 1 ]]; then
  echo "[A][FAIL] expected exactly one version directory, found ${#version_dirs[@]}"
  exit 1
fi
VER_DIR="${version_dirs[0]}"
VER="$VER_DIR/data.yml"
COMPOSE="$VER_DIR/docker-compose.yml"

[[ -s "$ROOT" ]] || fail "missing root data.yml"
[[ -s "$VER" ]] || fail "missing version data.yml"
[[ -s "$COMPOSE" ]] || fail "missing docker-compose.yml"
[[ -s "$SOURCE_EVIDENCE" ]] || fail "missing source-evidence.json"

if [[ $FAILURES -gt 0 ]]; then
  echo "SUMMARY: fail=$FAILURES warn=$WARNINGS info=$INFOS"
  exit 1
fi

set +e
source_ev_output=$("$PYTHON_BIN" - <<'PY' "$SOURCE_EVIDENCE"
import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
required = ["repository", "dockerDocs", "composeFile"]
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception as exc:
    print(f"[A][FAIL] source-evidence.json invalid JSON: {exc}")
    raise SystemExit(1)

failures = 0
for key in required:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        print(f"[A][FAIL] source-evidence.json missing key: {key}")
        failures += 1
        continue
    if not re.match(r'^https://[^\s]+$', value.strip()):
        print(f"[A][FAIL] source-evidence.json key must be https URL: {key}")
        failures += 1

if failures:
    raise SystemExit(1)
PY
)
source_ev_status=$?
set -e
if [[ -n "$source_ev_output" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    echo "$line"
    if [[ "$line" == "[A][FAIL]"* ]]; then
      FAILURES=$((FAILURES + 1))
    fi
  done <<< "$source_ev_output"
fi
if [[ $source_ev_status -ne 0 && $FAILURES -eq 0 ]]; then
  FAILURES=$((FAILURES + 1))
fi

grep -qE '^name:\s*.+$' "$ROOT" || fail "root data.yml missing top-level name"
grep -qE '^tags:\s*$' "$ROOT" || fail "root data.yml missing top-level tags"
grep -qE '^title:\s*.+$' "$ROOT" || fail "root data.yml missing top-level title"
grep -qE '^description:\s*.+$' "$ROOT" || fail "root data.yml missing top-level description"
grep -qE '^additionalProperties:\s*$' "$ROOT" || fail "root data.yml missing additionalProperties"

for key in key name tags type website document architectures github shortDescZh shortDescEn crossVersionUpdate limit; do
  grep -qE "^\s+${key}:" "$ROOT" || fail "root additionalProperties missing ${key}"
done

for locale in en zh zh-Hant ja ko ru ms pt-br; do
  grep -qE "^\s+${locale}:" "$ROOT" || fail "root additionalProperties.description missing locale ${locale}"
done

root_title=$(grep -m1 -E '^title:\s*' "$ROOT" || true)
root_desc=$(grep -m1 -E '^description:\s*' "$ROOT" || true)
short_desc=$(grep -m1 -E '^\s+shortDescZh:\s*' "$ROOT" || true)
if [[ -n "$root_title" && -n "$root_desc" && -n "$short_desc" ]]; then
  title_val=${root_title#title: }
  desc_val=${root_desc#description: }
  short_val=${short_desc#  shortDescZh: }
  [[ "$title_val" == "$desc_val" ]] || warn "root title and description differ"
  [[ "$title_val" == "$short_val" ]] || warn "root title and shortDescZh differ"
fi

grep -qE '^additionalProperties:\s*$' "$VER" || fail "version data.yml missing additionalProperties"
grep -qE '^\s+formFields:\s*$' "$VER" || fail "version additionalProperties.formFields missing"
if grep -qE '^formFields:\s*$' "$VER"; then
  fail "version data.yml must not use top-level formFields"
fi
if grep -qE '^\s*architectures:\s*$' "$VER"; then
  fail "version data.yml must not define architectures"
fi

set +e
py_output=$("$PYTHON_BIN" - <<'PY' "$VER"
import re, sys
from pathlib import Path
path = Path(sys.argv[1])
lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
in_ff = False
ff_indent = None
item_indent = None
items = []
cur = None
for line in lines:
    if not in_ff:
        m = re.match(r'^(\s*)formFields:\s*$', line)
        if m and len(m.group(1)) >= 2:
            in_ff = True
            ff_indent = len(m.group(1))
        continue
    if line.strip() and not line.lstrip().startswith('#'):
        indent = len(line) - len(line.lstrip(' '))
        if indent <= (ff_indent or 0) and not re.match(r'^\s*-\s*', line):
            break
    m_item = re.match(r'^(\s*)-\s*(.*)$', line)
    if m_item:
        if cur:
            items.append(cur)
        item_indent = len(m_item.group(1))
        cur = {}
        rest = m_item.group(2).strip()
        if ':' in rest:
            key, value = rest.split(':', 1)
            cur[key.strip()] = value.strip().strip('"\'')
        continue
    if cur is None or item_indent is None:
        continue
    indent = len(line) - len(line.lstrip(' '))
    if indent == item_indent + 2:
        m_kv = re.match(r'^\s*([A-Za-z0-9_]+):\s*(.*)$', line)
        if m_kv:
            cur[m_kv.group(1)] = m_kv.group(2).strip().strip('"\'')
if cur:
    items.append(cur)

if not items:
    print('[A][FAIL] version formFields is empty')
    sys.exit(1)

failures = 0
warnings = 0
for item in items:
    env = item.get('envKey', '')
    typ = item.get('type', '')
    required = item.get('required', '')
    if not env or not typ or required == '':
        print('[A][FAIL] formFields item missing envKey/type/required')
        failures += 1
        continue
    if env.startswith('PANEL_APP_PORT'):
        if typ != 'number':
            print(f'[A][FAIL] {env} must use type:number')
            failures += 1
        if item.get('rule', '') != 'paramPort':
            print(f'[A][FAIL] {env} must use rule:paramPort')
            failures += 1
    if required.lower() == 'true' and typ not in {'apps', 'service'} and 'edit' not in item:
        print(f'[B][WARN] {env} is required but missing edit:true')
        warnings += 1
if failures:
    sys.exit(1)
sys.exit(0)
PY
)
py_status=$?
set -e
if [[ -n "$py_output" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    echo "$line"
    if [[ "$line" == "[A][FAIL]"* ]]; then
      FAILURES=$((FAILURES + 1))
    elif [[ "$line" == "[B][WARN]"* ]]; then
      PY_WARNINGS=$((PY_WARNINGS + 1))
    fi
  done <<< "$py_output"
fi
if [[ $py_status -ne 0 && $FAILURES -eq 0 ]]; then
  FAILURES=$((FAILURES + 1))
fi

grep -qE '^services:\s*$' "$COMPOSE" || fail "compose missing services"
grep -q 'container_name: ${CONTAINER_NAME}' "$COMPOSE" || fail "compose container_name must use \${CONTAINER_NAME}"
grep -qE 'createdBy:\s*"?Apps"?' "$COMPOSE" || fail "compose labels.createdBy must be Apps"
grep -qE '^\s*image:\s*.+$' "$COMPOSE" || fail "compose missing image"
if grep -qE '^version:\s*' "$COMPOSE"; then
  warn "compose still contains top-level version"
fi
if grep -qE '^\s{6,}[A-Za-z0-9_]+:\s*\$\{' "$COMPOSE"; then
  warn "compose environment appears to use map-style entries; list-style is preferred"
fi
if grep -qE '^\s*ports:\s*$' "$COMPOSE"; then
  if grep -q 'PANEL_APP_PORT' "$COMPOSE"; then
    info "compose uses PANEL_APP_PORT mapping"
  else
    fail "compose exposes ports but does not use PANEL_APP_PORT mapping"
  fi
else
  info "compose does not expose ports"
fi

set +e
env_closure_output=$("$PYTHON_BIN" - <<'PY' "$VER" "$COMPOSE" "$IMPLICIT_ENVKEYS_FILE"
import re
import sys
from pathlib import Path

ver_path = Path(sys.argv[1])
compose_path = Path(sys.argv[2])
implicit_path = Path(sys.argv[3])

declared = set(re.findall(r'^\s*envKey:\s*["\']?([A-Za-z_][A-Za-z0-9_]*)["\']?\s*$', ver_path.read_text(encoding='utf-8', errors='ignore'), flags=re.M))

implicit = set()
if implicit_path.is_file():
    for line in implicit_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        m = re.match(r'^\s*-\s*`?([A-Za-z_][A-Za-z0-9_]*)`?\s*$', line)
        if m:
            implicit.add(m.group(1))

compose_text = compose_path.read_text(encoding='utf-8', errors='ignore')
vars_found = set()
for raw in re.findall(r'\$\{([^}]+)\}', compose_text):
    key = raw.strip()
    key = re.split(r'[:?+\-]', key, maxsplit=1)[0].strip()
    if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
        vars_found.add(key)

missing = sorted(v for v in vars_found if v not in declared and v not in implicit)
if missing:
    for key in missing:
        print(f"[A][FAIL] compose variable not declared in formFields envKey: {key}")
    raise SystemExit(1)

print(f"[C][INFO] env closure ok: compose_vars={len(vars_found)} declared={len(declared)} implicit={len(implicit)}")
PY
)
env_closure_status=$?
set -e
if [[ -n "$env_closure_output" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    echo "$line"
    if [[ "$line" == "[A][FAIL]"* ]]; then
      FAILURES=$((FAILURES + 1))
    elif [[ "$line" == "[B][WARN]"* ]]; then
      WARNINGS=$((WARNINGS + 1))
    elif [[ "$line" == "[C][INFO]"* ]]; then
      INFOS=$((INFOS + 1))
    fi
  done <<< "$env_closure_output"
fi
if [[ $env_closure_status -ne 0 && $FAILURES -eq 0 ]]; then
  FAILURES=$((FAILURES + 1))
fi

if [[ "$STRICT_STORE" -eq 1 ]]; then
  [[ -f "$DIR/README.md" ]] || fail "root README.md missing"
  [[ -f "$DIR/logo.png" ]] || fail "root logo.png missing"
  [[ -d "$VER_DIR/scripts" ]] || fail "version scripts directory missing"
  [[ -f "$VER_DIR/scripts/init.sh" ]] || fail "version init.sh missing"
  [[ -f "$VER_DIR/scripts/upgrade.sh" ]] || fail "version upgrade.sh missing"
  [[ -f "$VER_DIR/scripts/uninstall.sh" ]] || fail "version uninstall.sh missing"
  grep -qE '^## 产品介绍\s*$' "$DIR/README.md" || fail "README.md missing section: ## 产品介绍"
  grep -qE '^## 主要功能\s*$' "$DIR/README.md" || fail "README.md missing section: ## 主要功能"
  grep -qE '^## 访问说明\s*$' "$DIR/README.md" || fail "README.md missing section: ## 访问说明"
  grep -qE '^## Introduction\s*$' "$DIR/README.md" || fail "README.md missing section: ## Introduction"
  grep -qE '^## Features\s*$' "$DIR/README.md" || fail "README.md missing section: ## Features"
fi

WARNINGS=$((WARNINGS + PY_WARNINGS))
echo "SUMMARY: fail=$FAILURES warn=$WARNINGS info=$INFOS"
if [[ $FAILURES -gt 0 ]]; then
  exit 1
fi
echo "PASS: $DIR"
