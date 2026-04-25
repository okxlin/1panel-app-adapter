#!/usr/bin/env bash
set -euo pipefail

DIR=""
STRICT_C=0
STRICT_STORE=0
I18N_MODE="warn"
I18N_SCOPE="description"
I18N_ALLOW_EN_LABELS="API,URL,ID,OAuth,JWT,CPU,GPU,RAM,HTTP,HTTPS,TCP,UDP,SSH,DNS"
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
  echo "usage: validate-v2.sh --dir <app-dir> [--strict-c] [--strict-store] [--i18n-mode off|warn|strict] [--i18n-scope description|labels|all] [--i18n-allow-english-labels CSV]"
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
    --strict-c) STRICT_C=1; shift ;;
    --strict-store) STRICT_STORE=1; shift ;;
    --i18n-mode) I18N_MODE="$2"; shift 2 ;;
    --i18n-scope) I18N_SCOPE="$2"; shift 2 ;;
    --i18n-allow-english-labels) I18N_ALLOW_EN_LABELS="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown arg: $1"; usage; exit 2 ;;
  esac
done

[[ -n "$DIR" ]] || { usage; exit 2; }
[[ -d "$DIR" ]] || { echo "[A][FAIL] app dir not found: $DIR"; exit 1; }
case "$I18N_MODE" in off|warn|strict) ;; *) echo "invalid --i18n-mode: $I18N_MODE"; exit 2 ;; esac
case "$I18N_SCOPE" in description|labels|all) ;; *) echo "invalid --i18n-scope: $I18N_SCOPE"; exit 2 ;; esac

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
    label_keys = set(item.get('_labelKeys', []))
    has_label_map = item.get('_hasLabelMap', False)
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
    if item.get('labelEn') and item.get('labelZh') and not has_label_map:
        print(f'[B][WARN] {env}: missing label map (expected locales: en, zh, zh-Hant, ja, ko, ru, ms, pt-br)')
        warnings += 1
    if has_label_map:
        missing = []
        if 'zh-hant' in label_keys and 'zh-Hant' not in label_keys:
            print(f"[B][WARN] {env}: label map uses legacy 'zh-hant'; canonical skill output prefers 'zh-Hant'. Recommend renaming.")
            warnings += 1
        for locale in ['en', 'zh', 'ja', 'ko', 'ru', 'ms', 'pt-br']:
            if locale not in label_keys:
                missing.append(locale)
        if 'zh-Hant' not in label_keys and 'zh-hant' not in label_keys:
            missing.append('zh-Hant(or zh-hant)')
        if missing:
            print(f"[B][WARN] {env}: label map missing locale(s): {', '.join(missing)}")
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
network_output=$("$PYTHON_BIN" - <<'PY' "$COMPOSE"
import re, sys
from pathlib import Path

lines = Path(sys.argv[1]).read_text(encoding='utf-8', errors='ignore').splitlines()
in_services = False
services_indent = None
service_indent = None
current_service = None
service_has_createdby = {}
service_in_labels = False
labels_indent = None
service_in_networks = False
networks_indent = None
service_declares_networks = False
external_networks = []
found_default_bridge = False

for line in lines:
    if not line.strip() or line.lstrip().startswith('#'):
        continue
    indent = len(line) - len(line.lstrip(' '))
    stripped = line.strip()
    if re.match(r'^services:\s*$', stripped):
        in_services = True
        services_indent = indent
        current_service = None
        service_in_labels = False
        labels_indent = None
        service_in_networks = False
        networks_indent = None
        continue
    if in_services:
        if indent <= services_indent and re.match(r'^[A-Za-z0-9_.-]+:\s*$', stripped):
            in_services = False
            current_service = None
            service_in_labels = False
            labels_indent = None
            service_in_networks = False
            networks_indent = None
        else:
            m_service = re.match(r'^([A-Za-z0-9_.-]+):\s*$', stripped)
            if m_service and indent == services_indent + 2:
                current_service = m_service.group(1)
                service_indent = indent
                service_has_createdby.setdefault(current_service, False)
                service_in_labels = False
                labels_indent = None
                service_in_networks = False
                networks_indent = None
                continue
            if current_service is not None:
                if indent <= service_indent:
                    current_service = None
                    service_in_labels = False
                    labels_indent = None
                    service_in_networks = False
                    networks_indent = None
                    continue
                if re.match(r'^labels:\s*$', stripped) and indent == service_indent + 2:
                    service_in_labels = True
                    labels_indent = indent
                    continue
                if re.match(r'^networks:\s*$', stripped) and indent == service_indent + 2:
                    service_in_networks = True
                    networks_indent = indent
                    service_declares_networks = True
                    continue
                if service_in_labels:
                    if indent <= labels_indent:
                        service_in_labels = False
                        labels_indent = None
                    elif re.match(r'^createdBy:\s*["\']?Apps["\']?\s*$', stripped):
                        service_has_createdby[current_service] = True
                if service_in_networks and indent <= networks_indent:
                    service_in_networks = False
                    networks_indent = None
    if re.match(r'^1panel-network:\s*$', stripped):
        found_default_bridge = True

for i, line in enumerate(lines):
    if re.match(r'^\s*[A-Za-z0-9_.-]+:\s*$', line):
        name = line.strip().rstrip(':')
        indent = len(line) - len(line.lstrip(' '))
        j = i + 1
        while j < len(lines):
            l2 = lines[j]
            if not l2.strip() or l2.lstrip().startswith('#'):
                j += 1
                continue
            ind2 = len(l2) - len(l2.lstrip(' '))
            if ind2 <= indent:
                break
            if re.match(r'^\s*external:\s*true\s*$', l2):
                external_networks.append(name)
                break
            j += 1

missing = [name for name, ok in service_has_createdby.items() if not ok]
if missing:
    print('[A][FAIL] compose service(s) missing labels.createdBy: "Apps": ' + ', '.join(missing))
    raise SystemExit(1)
if service_declares_networks and not external_networks:
    print('[A][FAIL] compose declares service-level networks, but no top-level external network is defined; bridge-style apps must join at least one external network')
    raise SystemExit(1)
if external_networks and '1panel-network' not in external_networks:
    print('[B][WARN] compose uses external network(s) but not default 1panel-network: ' + ', '.join(external_networks))
elif not external_networks and not found_default_bridge:
    print('[C][INFO] compose does not declare external bridge network; this is fine unless the app should join 1Panel public network')
PY
)
network_status=$?
set -e
if [[ -n "$network_output" ]]; then
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
  done <<< "$network_output"
fi
if [[ $network_status -ne 0 && $FAILURES -eq 0 ]]; then
  FAILURES=$((FAILURES + 1))
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

set +e
i18n_output=$("$PYTHON_BIN" - <<'PY' "$ROOT" "$VER" "$I18N_MODE" "$I18N_SCOPE" "$I18N_ALLOW_EN_LABELS"
import re, sys
from pathlib import Path

root, ver, mode, scope, allow_csv = sys.argv[1:6]
if mode == 'off':
    raise SystemExit(0)

allow = {x.strip().lower() for x in allow_csv.split(',') if x.strip()}


def emit(level, msg):
    print(f'[{level}] {msg}')


def should_fail(msg):
    if mode == 'strict':
        emit('A][FAIL', msg)
        return True
    emit('B][WARN', msg)
    return False


def ascii_ratio(s):
    if not s:
        return 1.0
    return sum(1 for ch in s if ord(ch) < 128) / len(s)


def has_japanese(s):
    return bool(re.search(r'[\u3040-\u30ff]', s))


def has_korean(s):
    return bool(re.search(r'[\uac00-\ud7af]', s))


def has_cyrillic(s):
    return bool(re.search(r'[\u0400-\u04FF]', s))


def read_lines(path):
    return Path(path).read_text(encoding='utf-8', errors='ignore').splitlines()


def read_desc_map(lines):
    in_ap = False
    in_desc = False
    desc_indent = 0
    out = {}
    for line in lines:
        if re.match(r'^additionalProperties:\s*$', line):
            in_ap = True
            in_desc = False
            continue
        if in_ap and line.strip() and not line.startswith(' '):
            in_ap = False
            in_desc = False
        if not in_ap:
            continue
        m = re.match(r'^(\s*)description:\s*$', line)
        if m and len(m.group(1)) >= 2:
            in_desc = True
            desc_indent = len(m.group(1))
            continue
        if in_desc:
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip(' '))
            if indent <= desc_indent:
                in_desc = False
                continue
            m2 = re.match(r'^\s*([A-Za-z0-9-]+):\s*(.*)$', line)
            if m2 and indent == desc_indent + 2:
                out[m2.group(1)] = m2.group(2).strip().strip('"\'')
    return out


def read_label_items(lines):
    items = []
    cur = None
    in_label = False
    label_indent = None
    for line in lines:
        m_item = re.match(r'^\s*-\s+', line)
        if m_item:
            if cur is not None:
                items.append(cur)
            cur = {'env': 'UNKNOWN', 'label': {}}
            in_label = False
            label_indent = None
            continue
        if cur is None:
            continue
        m_env = re.match(r'^\s*envKey:\s*([A-Za-z0-9_]+)\s*$', line)
        if m_env:
            cur['env'] = m_env.group(1)
        m_label = re.match(r'^(\s*)label:\s*$', line)
        if m_label:
            in_label = True
            label_indent = len(m_label.group(1))
            continue
        if in_label:
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip(' '))
            if indent <= (label_indent or 0):
                in_label = False
                label_indent = None
                continue
            m_loc = re.match(r'^\s*([A-Za-z0-9-]+):\s*(.*)$', line)
            if m_loc:
                cur['label'][m_loc.group(1)] = m_loc.group(2).strip().strip('"\'')
    if cur is not None:
        items.append(cur)
    return items

root_lines = read_lines(root)
ver_lines = read_lines(ver)

if scope in ('description', 'all'):
    vals = {k: read_desc_map(root_lines).get(k, '').strip() for k in ['en', 'zh', 'zh-Hant', 'ja', 'ko', 'ru', 'ms', 'pt-br']}
    if all(vals.values()):
        en = vals['en'].lower().strip()
        for key in ['ja', 'ko', 'ru', 'ms', 'pt-br']:
            if vals[key].lower().strip() == en and should_fail(f'additionalProperties.description.{key} equals English text exactly'):
                raise SystemExit(1)
        if vals['zh'] == vals['zh-Hant'] and should_fail('additionalProperties.description.zh-Hant equals zh exactly'):
            raise SystemExit(1)
        for key in ['ja', 'ko', 'ru']:
            if ascii_ratio(vals[key]) > 0.75 and should_fail(f'additionalProperties.description.{key} looks mostly ASCII/English'):
                raise SystemExit(1)
        if vals['ja'] and not has_japanese(vals['ja']) and should_fail('additionalProperties.description.ja missing Japanese script'):
            raise SystemExit(1)
        if vals['ko'] and not has_korean(vals['ko']) and should_fail('additionalProperties.description.ko missing Korean script'):
            raise SystemExit(1)
        if vals['ru'] and not has_cyrillic(vals['ru']) and should_fail('additionalProperties.description.ru missing Cyrillic script'):
            raise SystemExit(1)

if scope in ('labels', 'all'):
    for item in read_label_items(ver_lines):
        en = (item['label'].get('en') or '').strip()
        if not en:
            continue
        same = sum(1 for key, value in item['label'].items() if key != 'en' and value.strip().lower() == en.lower())
        if same >= 5 and should_fail(f"formFields[{item['env']}] label map has too many locales identical to English ({same})"):
            raise SystemExit(1)
        for key in ['ja', 'ko', 'ru']:
            value = (item['label'].get(key) or '').strip()
            if value and value.lower() == en.lower() and en.lower() not in allow:
                if should_fail(f"formFields[{item['env']}] label.{key} equals English without whitelist term"):
                    raise SystemExit(1)
PY
)
i18n_status=$?
set -e
if [[ -n "$i18n_output" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    echo "$line"
    if [[ "$line" == "[A][FAIL]"* ]]; then
      FAILURES=$((FAILURES + 1))
    elif [[ "$line" == "[B][WARN]"* ]]; then
      WARNINGS=$((WARNINGS + 1))
    fi
  done <<< "$i18n_output"
fi
if [[ $i18n_status -ne 0 && $FAILURES -eq 0 && "$I18N_MODE" == "strict" ]]; then
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

if grep -qE '^[[:space:]]*healthcheck:\s*$' "$COMPOSE"; then
  info "healthcheck present"
else
  info "healthcheck not found"
  if [[ "$STRICT_C" -eq 1 ]]; then
    fail "strict-c enabled: healthcheck missing"
  fi
fi

WARNINGS=$((WARNINGS + PY_WARNINGS))
echo "SUMMARY: fail=$FAILURES warn=$WARNINGS info=$INFOS"
if [[ $FAILURES -gt 0 ]]; then
  exit 1
fi
echo "PASS: $DIR"
