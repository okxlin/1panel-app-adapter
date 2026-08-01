#!/usr/bin/env bash
set -euo pipefail

DIR=""
VERSION_NAME=""
STRICT_C=0
STRICT_STORE=0
I18N_MODE="warn"
I18N_SCOPE="all"
I18N_ALLOW_EN_LABELS="API,URL,ID,OAuth,JWT,CPU,GPU,RAM,HTTP,HTTPS,TCP,UDP,SSH,DNS"
SOURCE_EVIDENCE_MODE="warn"
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
  cat <<'USAGE'
usage: validate-v2.sh --dir <app-dir> [--version <version-dir>] [--strict-c] [--strict-store] [--source-evidence-mode warn|required|off] [--i18n-mode off|warn|strict] [--i18n-scope description|labels|all] [--i18n-allow-english-labels CSV]

behavior notes:
  - multi-version app directories require --version <version-dir> so validation targets one release explicitly
  - --strict-store is intended for delivery-ready artifacts, not raw scaffold placeholders
  - source-evidence.json is optional by default; use --source-evidence-mode required only for provenance-gated delivery workflows
  - when docker compose is available, validator runs a real `docker compose config` render check
  - when docker compose is unavailable, that render check is skipped and reported as a warning
USAGE
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
    --version) VERSION_NAME="$2"; shift 2 ;;
    --strict-c) STRICT_C=1; shift ;;
    --strict-store) STRICT_STORE=1; shift ;;
    --source-evidence-mode) SOURCE_EVIDENCE_MODE="$2"; shift 2 ;;
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
case "$SOURCE_EVIDENCE_MODE" in required|warn|off) ;; *) echo "invalid --source-evidence-mode: $SOURCE_EVIDENCE_MODE"; exit 2 ;; esac

ROOT="$DIR/data.yml"
SOURCE_EVIDENCE="$DIR/source-evidence.json"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMPLICIT_ENVKEYS_FILE="$SCRIPT_DIR/../references/implicit-envkeys.md"
APP_KEY="$(basename "${DIR%/}")"
NESTED_APP_ROOT="$DIR/$APP_KEY"
if [[ -s "$NESTED_APP_ROOT/data.yml" && -s "$NESTED_APP_ROOT/source-evidence.json" ]]; then
  mapfile -t nested_versions < <(find "$NESTED_APP_ROOT" -mindepth 1 -maxdepth 1 -type d ! -name '.*')
  if [[ ${#nested_versions[@]} -gt 0 ]]; then
    echo "[A][FAIL] duplicate nested app root detected: $NESTED_APP_ROOT (pass the parent output directory to the generator, then validate $DIR only after data.yml and source-evidence.json exist directly there)"
    exit 1
  fi
fi
mapfile -t version_dirs < <(find "$DIR" -mindepth 1 -maxdepth 1 -type d ! -name '.*')
if [[ ${#version_dirs[@]} -eq 0 ]]; then
  echo "[A][FAIL] missing version directory"
  exit 1
fi
if [[ -n "$VERSION_NAME" ]]; then
  if [[ "$VERSION_NAME" == */* || "$VERSION_NAME" == .* ]]; then
    echo "[A][FAIL] invalid --version value: $VERSION_NAME"
    exit 1
  fi
  VER_DIR="$DIR/$VERSION_NAME"
  if [[ ! -d "$VER_DIR" ]]; then
    available_versions=$(printf '%s\n' "${version_dirs[@]}" | xargs -n 1 basename | sort | paste -sd ', ' -)
    echo "[A][FAIL] requested version directory not found: $VERSION_NAME"
    echo "[C][INFO] available version directories: $available_versions"
    exit 1
  fi
  info "selected version directory: $VERSION_NAME"
else
  if [[ ${#version_dirs[@]} -ne 1 ]]; then
    available_versions=$(printf '%s\n' "${version_dirs[@]}" | xargs -n 1 basename | sort | paste -sd ', ' -)
    echo "[A][FAIL] multiple version directories found (${#version_dirs[@]}). Re-run with --version <version-dir>."
    echo "[C][INFO] available version directories: $available_versions"
    exit 1
  fi
  VER_DIR="${version_dirs[0]}"
fi
VER="$VER_DIR/data.yml"
COMPOSE="$VER_DIR/docker-compose.yml"

[[ -s "$ROOT" ]] || fail "missing root data.yml"
[[ -s "$VER" ]] || fail "missing version data.yml"
[[ -s "$COMPOSE" ]] || fail "missing docker-compose.yml"
case "$SOURCE_EVIDENCE_MODE" in
  required)
    [[ -s "$SOURCE_EVIDENCE" ]] || fail "missing source-evidence.json"
    ;;
  warn)
    [[ -s "$SOURCE_EVIDENCE" ]] || warn "missing source-evidence.json"
    ;;
  off)
    [[ -s "$SOURCE_EVIDENCE" ]] || info "source-evidence.json check skipped"
    ;;
esac

set +e
yaml_sanity_output=$("$PYTHON_BIN" - <<'PY' "$ROOT" "$VER" "$COMPOSE"
import sys
from pathlib import Path
import yaml

class DupCheckLoader(yaml.SafeLoader):
    pass

def no_dups(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                'while constructing a mapping', node.start_mark,
                f'found duplicate key ({key})', key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping

DupCheckLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, no_dups)

for label, path_str in [('root data.yml', sys.argv[1]), ('version data.yml', sys.argv[2]), ('docker-compose.yml', sys.argv[3])]:
    path = Path(path_str)
    try:
        yaml.load(path.read_text(encoding='utf-8', errors='ignore'), Loader=DupCheckLoader)
    except Exception as exc:
        print(f"[A][FAIL] {label} has invalid YAML or duplicate keys: {exc}")
        raise SystemExit(1)
PY
)
yaml_sanity_status=$?
set -e
if [[ -n "$yaml_sanity_output" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    echo "$line"
    if [[ "$line" == "[A][FAIL]"* ]]; then
      FAILURES=$((FAILURES + 1))
    fi
  done <<< "$yaml_sanity_output"
fi
if [[ $yaml_sanity_status -ne 0 && $FAILURES -eq 0 ]]; then
  FAILURES=$((FAILURES + 1))
fi

if [[ "$STRICT_STORE" -eq 1 ]]; then
  set +e
  placeholder_output=$(grep -RInE '请按官方来源补全|generated 1Panel app template|1panel-app-adapter 生成的|\(placeholder\)|（佔位）|（プレースホルダー）|（플레이스홀더）' "$ROOT" "$DIR/README.md" 2>/dev/null)
  placeholder_status=$?
  set -e
  if [[ $placeholder_status -eq 0 && -n "$placeholder_output" ]]; then
    fail "placeholder template text detected in delivery artifact"
    echo "$placeholder_output"
  fi
fi

if [[ $FAILURES -gt 0 ]]; then
  echo "SUMMARY: fail=$FAILURES warn=$WARNINGS info=$INFOS"
  exit 1
fi

set +e
adaptation_safety_output=$("$PYTHON_BIN" "$SCRIPT_DIR/validate_adaptation_safety.py" \
  --version-data "$VER" \
  --compose "$COMPOSE" \
  --scripts-dir "$VER_DIR/scripts")
adaptation_safety_status=$?
set -e
if [[ -n "$adaptation_safety_output" ]]; then
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    echo "$line"
    if [[ "$line" == "[A][FAIL]"* ]]; then
      FAILURES=$((FAILURES + 1))
    elif [[ "$line" == "[B][WARN]"* ]]; then
      WARNINGS=$((WARNINGS + 1))
    fi
  done <<< "$adaptation_safety_output"
fi
if [[ $adaptation_safety_status -ne 0 && $FAILURES -eq 0 ]]; then
  fail "adaptation safety analysis failed without a finding"
fi

if [[ $FAILURES -gt 0 ]]; then
  echo "SUMMARY: fail=$FAILURES warn=$WARNINGS info=$INFOS"
  exit 1
fi

if [[ -s "$SOURCE_EVIDENCE" && "$SOURCE_EVIDENCE_MODE" != "off" ]]; then
  set +e
  source_ev_output=$("$PYTHON_BIN" "$SCRIPT_DIR/source_evidence.py" "$SOURCE_EVIDENCE")
  source_ev_status=$?
  set -e
  if [[ -n "$source_ev_output" ]]; then
    while IFS= read -r line; do
      [[ -z "$line" ]] && continue
      if [[ "$SOURCE_EVIDENCE_MODE" == "warn" && "$line" == "[A][FAIL]"* ]]; then
        echo "${line/[A][FAIL]/[B][WARN]}"
        WARNINGS=$((WARNINGS + 1))
      else
        echo "$line"
        if [[ "$line" == "[A][FAIL]"* ]]; then
          FAILURES=$((FAILURES + 1))
        fi
      fi
    done <<< "$source_ev_output"
  fi
  if [[ $source_ev_status -ne 0 && "$SOURCE_EVIDENCE_MODE" == "required" && $FAILURES -eq 0 ]]; then
    FAILURES=$((FAILURES + 1))
  elif [[ $source_ev_status -ne 0 && "$SOURCE_EVIDENCE_MODE" == "warn" && -z "$source_ev_output" ]]; then
    warn "source-evidence.json validation failed"
  fi
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
import sys
from pathlib import Path
import yaml
path = Path(sys.argv[1])
try:
    data = yaml.safe_load(path.read_text(encoding='utf-8', errors='ignore')) or {}
except Exception as exc:
    print(f'[A][FAIL] version data.yml cannot be parsed for formFields: {exc}')
    sys.exit(1)

items = (data.get('additionalProperties') or {}).get('formFields') or []

if not items:
    print('[A][FAIL] version formFields is empty')
    sys.exit(1)

failures = 0
warnings = 0
for item in items:
    if not isinstance(item, dict):
        print('[A][FAIL] formFields item must be a mapping')
        failures += 1
        continue
    env = item.get('envKey', '')
    typ = item.get('type', '')
    required = item.get('required', '')
    label = item.get('label')
    label_keys = set(label.keys()) if isinstance(label, dict) else set()
    has_label_map = isinstance(label, dict) and bool(label)
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
    if str(required).lower() == 'true' and typ not in {'apps', 'service'} and 'edit' not in item:
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
import yaml

compose_path = Path(sys.argv[1])
compose_text = compose_path.read_text(encoding='utf-8', errors='ignore')
lines = compose_text.splitlines()
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

try:
    compose_data = yaml.safe_load(compose_text) or {}
except Exception:
    compose_data = {}

if isinstance(compose_data, dict):
    services = compose_data.get('services') or {}
    top_networks = compose_data.get('networks') or {}
    if isinstance(services, dict) and isinstance(top_networks, dict):
        external_net_names = {
            name
            for name, cfg in top_networks.items()
            if isinstance(name, str)
            and isinstance(cfg, dict)
            and str(cfg.get('external', '')).lower() == 'true'
        }
        generic_names = {
            'db', 'database', 'mysql', 'mariadb', 'mongo', 'mongodb',
            'postgres', 'postgresql', 'redis', 'valkey'
        }
        internal_generic_services = {
            name for name in services
            if isinstance(name, str) and name.lower() in generic_names
        }

        def service_network_names(service_cfg):
            nets = service_cfg.get('networks') if isinstance(service_cfg, dict) else None
            if isinstance(nets, list):
                return {item for item in nets if isinstance(item, str)}
            if isinstance(nets, dict):
                return {item for item in nets if isinstance(item, str)}
            return set()

        def environment_values(service_cfg):
            env = service_cfg.get('environment') if isinstance(service_cfg, dict) else None
            values = []
            if isinstance(env, list):
                values.extend(str(item) for item in env)
            elif isinstance(env, dict):
                for key, value in env.items():
                    values.append(f'{key}={value}')
            return values

        risky_refs = []
        for service_name, service_cfg in services.items():
            if not isinstance(service_cfg, dict):
                continue
            svc_nets = service_network_names(service_cfg)
            if not (svc_nets & external_net_names):
                continue
            if not (svc_nets - external_net_names):
                continue
            values = environment_values(service_cfg)
            for generic in sorted(internal_generic_services):
                service_ref = re.escape(generic)
                pattern = re.compile(rf'(^|[=:/@,]){service_ref}([:/,]|$)', re.IGNORECASE)
                if any(pattern.search(value) for value in values):
                    risky_refs.append(f'{service_name}->{generic}')
        if risky_refs:
            print(
                '[B][WARN] multi-service app joins external and internal networks while referencing generic internal service name(s): '
                + ', '.join(sorted(risky_refs))
                + '; prefer app-prefixed service names or explicit internal aliases to avoid Docker DNS collisions on shared networks'
            )
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
env_closure_output=$("$PYTHON_BIN" - <<'PY' "$VER" "$COMPOSE" "$IMPLICIT_ENVKEYS_FILE" "$SCRIPT_DIR"
import re
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[4])
from compose_env_vars import extract_compose_variable_names

ver_path = Path(sys.argv[1])
compose_path = Path(sys.argv[2])
implicit_path = Path(sys.argv[3])

declared = set(re.findall(r'^\s*-\s*envKey:\s*["\']?([A-Za-z_][A-Za-z0-9_]*)["\']?\s*$|^\s*envKey:\s*["\']?([A-Za-z_][A-Za-z0-9_]*)["\']?\s*$', ver_path.read_text(encoding='utf-8', errors='ignore'), flags=re.M))
declared = {g1 or g2 for g1, g2 in declared}

implicit = set()
if implicit_path.is_file():
    for line in implicit_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        m = re.match(r'^\s*-\s*`?([A-Za-z_][A-Za-z0-9_]*)`?\s*$', line)
        if m:
            implicit.add(m.group(1))

compose_text = compose_path.read_text(encoding='utf-8', errors='ignore')
vars_found = extract_compose_variable_names(compose_text)

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

# .env.sample consistency check
set +e
env_sample_output=$("$PYTHON_BIN" - <<'PY' "$COMPOSE" "$VER_DIR/.env.sample" "$SCRIPT_DIR"
import re, sys
from pathlib import Path

sys.path.insert(0, sys.argv[3])
from compose_env_vars import extract_compose_variable_names

compose_path = Path(sys.argv[1])
env_sample_path = Path(sys.argv[2])

if not env_sample_path.is_file():
    print("[A][FAIL] .env.sample missing")
    raise SystemExit(1)

compose_text = compose_path.read_text(encoding='utf-8', errors='ignore')
vars_in_compose = extract_compose_variable_names(compose_text)

env_sample_text = env_sample_path.read_text(encoding='utf-8', errors='ignore')
vars_in_sample = set()
for line in env_sample_text.splitlines():
    line = line.strip()
    if line and not line.startswith('#'):
        m = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=', line)
        if m:
            vars_in_sample.add(m.group(1))

missing_in_sample = sorted(vars_in_compose - vars_in_sample)
if missing_in_sample:
    for key in missing_in_sample:
        print(f"[B][WARN] compose variable missing from .env.sample: {key}")

extra_in_sample = sorted(vars_in_sample - vars_in_compose)
if extra_in_sample:
    for key in extra_in_sample:
        print(f"[C][INFO] .env.sample has extra variable not in compose: {key}")

print(f"[C][INFO] env sample closure ok: compose_vars={len(vars_in_compose)} sample_vars={len(vars_in_sample)}")
PY
)
env_sample_status=$?
set -e
if [[ -n "$env_sample_output" ]]; then
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
  done <<< "$env_sample_output"
fi
if [[ $env_sample_status -ne 0 && $FAILURES -eq 0 ]]; then
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


def read_yaml(path):
    try:
        return yaml.safe_load(Path(path).read_text(encoding='utf-8', errors='ignore')) or {}
    except Exception:
        return {}


def read_desc_map(data):
    desc = (data.get('additionalProperties') or {}).get('description') or {}
    return desc if isinstance(desc, dict) else {}


def read_label_items(data):
    fields = (data.get('additionalProperties') or {}).get('formFields') or []
    items = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        label = field.get('label') or {}
        if not isinstance(label, dict):
            label = {}
        items.append({'env': field.get('envKey') or 'UNKNOWN', 'label': label})
    return items

root_data = read_yaml(root)
ver_data = read_yaml(ver)

if scope in ('description', 'all'):
    vals = {k: str(read_desc_map(root_data).get(k, '')).strip() for k in ['en', 'zh', 'zh-Hant', 'ja', 'ko', 'ru', 'ms', 'pt-br']}
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
    for item in read_label_items(ver_data):
        en = str(item['label'].get('en') or '').strip()
        if not en:
            continue
        same = sum(1 for key, value in item['label'].items() if key != 'en' and str(value).strip().lower() == en.lower())
        if same >= 5 and should_fail(f"formFields[{item['env']}] label map has too many locales identical to English ({same})"):
            raise SystemExit(1)
        for key in ['ja', 'ko', 'ru']:
            value = str(item['label'].get(key) or '').strip()
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

set +e
compose_render_output=$("$PYTHON_BIN" - <<'PY' "$COMPOSE" "$VER_DIR/.env.sample"
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

compose_path = Path(sys.argv[1])
env_sample = Path(sys.argv[2])
if shutil.which('docker') is None:
    print('[B][WARN] docker not available; skipped docker compose config validation')
    raise SystemExit(0)

pairs = {}
if env_sample.is_file():
    for line in env_sample.read_text(encoding='utf-8', errors='ignore').splitlines():
        raw = line.strip()
        if not raw or raw.startswith('#') or '=' not in raw:
            continue
        k, v = raw.split('=', 1)
        pairs[k.strip()] = v
pairs.setdefault('CONTAINER_NAME', 'adapter-validate')
if not pairs.get('CONTAINER_NAME', '').strip():
    pairs['CONTAINER_NAME'] = 'adapter-validate'

with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as tf:
    for k, v in pairs.items():
        tf.write(f'{k}={v}\n')
    temp_env = tf.name

cmd = ['docker', 'compose', '--env-file', temp_env, '-f', str(compose_path), 'config']
try:
    proc = subprocess.run(cmd, capture_output=True, text=True)
finally:
    try:
        os.unlink(temp_env)
    except FileNotFoundError:
        pass

if proc.returncode != 0:
    msg = (proc.stderr or proc.stdout or '').strip().replace('\n', ' | ')
    print(f'[A][FAIL] docker compose config failed: {msg}')
    raise SystemExit(1)

print('[C][INFO] docker compose config ok')
PY
)
compose_render_status=$?
set -e
if [[ -n "$compose_render_output" ]]; then
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
  done <<< "$compose_render_output"
fi
if [[ $compose_render_status -ne 0 && $FAILURES -eq 0 ]]; then
  FAILURES=$((FAILURES + 1))
fi

if [[ "$STRICT_STORE" -eq 1 ]]; then
  [[ -f "$DIR/README.md" ]] || fail "root README.md missing"
  [[ -f "$DIR/logo.png" ]] || fail "root logo.png missing"
  [[ ! -L "$VER_DIR/scripts" ]] || fail "version scripts directory is a symbolic link"
  [[ -d "$VER_DIR/scripts" ]] || fail "version scripts directory missing"
  [[ ! -L "$VER_DIR/scripts/init.sh" ]] || fail "version init.sh is a symbolic link"
  [[ ! -L "$VER_DIR/scripts/upgrade.sh" ]] || fail "version upgrade.sh is a symbolic link"
  [[ ! -L "$VER_DIR/scripts/uninstall.sh" ]] || fail "version uninstall.sh is a symbolic link"
  [[ -f "$VER_DIR/scripts/init.sh" ]] || fail "version init.sh missing"
  [[ -f "$VER_DIR/scripts/upgrade.sh" ]] || fail "version upgrade.sh missing"
  [[ -f "$VER_DIR/scripts/uninstall.sh" ]] || fail "version uninstall.sh missing"
  [[ ! -f "$VER_DIR/scripts/init.sh" || -x "$VER_DIR/scripts/init.sh" ]] || fail "version init.sh is not executable"
  [[ ! -f "$VER_DIR/scripts/upgrade.sh" || -x "$VER_DIR/scripts/upgrade.sh" ]] || fail "version upgrade.sh is not executable"
  [[ ! -f "$VER_DIR/scripts/uninstall.sh" || -x "$VER_DIR/scripts/uninstall.sh" ]] || fail "version uninstall.sh is not executable"
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
fi

WARNINGS=$((WARNINGS + PY_WARNINGS))
echo "SUMMARY: fail=$FAILURES warn=$WARNINGS info=$INFOS"
if [[ $FAILURES -gt 0 ]]; then
  exit 1
fi
echo "PASS: $DIR"
