#!/usr/bin/env bash
set -euo pipefail

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

APP_KEY=""
TITLE=""
IMAGE=""
VERSION=""
OUT_DIR=""
PORT=""
TARGET_PORT=""
TYPE="tool"
TAG=""
WEBSITE=""
DOCUMENT=""
GITHUB_URL=""
VOLUMES=""
WITH_PANEL_DEPS=0
FORCE=0
SOURCE_REPOSITORY=""
SOURCE_DOCKER_DOCS=""
SOURCE_COMPOSE_FILE=""
TIMEZONE="Asia/Shanghai"

infer_tag() {
  local explicit_tag="$1"
  local app_type="$2"
  local title="$3"
  local image="$4"
  local haystack

  if [[ -n "$explicit_tag" ]]; then
    printf '%s' "$explicit_tag"
    return
  fi

  case "${app_type,,}" in
    website) printf 'Website'; return ;;
    middleware) printf 'Middleware'; return ;;
    database) printf 'Database'; return ;;
    ai) printf 'AI'; return ;;
    security) printf 'Security'; return ;;
    storage) printf 'Storage'; return ;;
    server) printf 'Server'; return ;;
    devops) printf 'DevOps'; return ;;
    media) printf 'Media'; return ;;
  esac

  haystack="${title,,} ${image,,}"
  if [[ "$haystack" == *redis* || "$haystack" == *mysql* || "$haystack" == *mariadb* || "$haystack" == *postgres* || "$haystack" == *postgresql* || "$haystack" == *mongo* || "$haystack" == *sqlite* ]]; then
    printf 'Database'
  elif [[ "$haystack" == *nginx* || "$haystack" == *apache* || "$haystack" == *caddy* || "$haystack" == *traefik* || "$haystack" == *haproxy* ]]; then
    printf 'Website'
  elif [[ "$haystack" == *ai* || "$haystack" == *llm* || "$haystack" == *openai* || "$haystack" == *model* || "$haystack" == *chatgpt* || "$haystack" == *ollama* ]]; then
    printf 'AI'
  elif [[ "$haystack" == *jenkins* || "$haystack" == *gitlab* || "$haystack" == *gitea* || "$haystack" == *drone* || "$haystack" == *argo* || "$haystack" == *tekton* ]]; then
    printf 'DevOps'
  elif [[ "$haystack" == *docker* || "$haystack" == *k8s* || "$haystack" == *kubernetes* || "$haystack" == *rancher* || "$haystack" == *portainer* ]]; then
    printf 'DevOps'
  elif [[ "$haystack" == *ansible* || "$haystack" == *terraform* || "$haystack" == *vault* || "$haystack" == *consul* ]]; then
    printf 'DevOps'
  elif [[ "$haystack" == *plex* || "$haystack" == *emby* || "$haystack" == *jellyfin* || "$haystack" == *navidrome* || "$haystack" == *sonarr* || "$haystack" == *radarr* ]]; then
    printf 'Media'
  elif [[ "$haystack" == *nextcloud* || "$haystack" == *owncloud* || "$haystack" == *seafile* || "$haystack" == *minio* || "$haystack" == *s3* ]]; then
    printf 'Storage'
  elif [[ "$haystack" == *grafana* || "$haystack" == *prometheus* || "$haystack" == *zabbix* || "$haystack" == *uptime* || "$haystack" == *monitor* ]]; then
    printf 'Server'
  elif [[ "$haystack" == *web* || "$haystack" == *site* || "$haystack" == *blog* || "$haystack" == *wiki* || "$haystack" == *cms* ]]; then
    printf 'Website'
  else
    printf 'Tool'
  fi
}

usage(){
  cat <<'USAGE'
usage: scaffold-v2.sh --app-key <key> --title <title> --image <image> --version <ver> [options]

required:
  --app-key
  --title
  --image
  --version

options:
  --out-dir <parent>      output app root is <parent>/<app-key> (default parent: ./1panel-apps)
  --port <host-port>      default: 8080
  --target-port <port>    default: 80
  --type <type>           default: tool
  --tag <tag>             optional explicit tag override
  --website <url>         website URL for root data.yml additionalProperties.website
  --document <url>        document URL for root data.yml additionalProperties.document
  --github <url>          github/repo URL for root data.yml additionalProperties.github
  --volumes <a:b,c:d>     optional mounts
  --with-panel-deps       inject PANEL_DB_*/PANEL_REDIS_* fields
  --force                 overwrite existing target app directory
  --with-panel-db-redis   alias of --with-panel-deps
  --source-repository <url>   official source repository URL (required)
  --source-docker-docs <url>  official docker docs/image URL (required)
  --source-compose-file <url> official compose reference URL (required)
  --timezone <tz>             default TZ value for version data.yml (default: Asia/Shanghai)

behavior notes:
  - --out-dir is always a parent directory; do not pass a path already ending in <app-key>
  - the app root directly contains data.yml, source-evidence.json, and the selected version directory
  - raw scaffold output contains placeholder README / metadata text by design
  - replace placeholder content before expecting --strict-store to pass
  - --force allows writing into an existing non-empty app directory; it does not clean residual files for you
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app-key) APP_KEY="$2"; shift 2 ;;
    --title) TITLE="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --version) VERSION="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --target-port) TARGET_PORT="$2"; shift 2 ;;
    --type) TYPE="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --website) WEBSITE="$2"; shift 2 ;;
    --document) DOCUMENT="$2"; shift 2 ;;
    --github) GITHUB_URL="$2"; shift 2 ;;
    --volumes) VOLUMES="$2"; shift 2 ;;
    --with-panel-deps|--with-panel-db-redis) WITH_PANEL_DEPS=1; shift ;;
    --force) FORCE=1; shift ;;
    --source-repository) SOURCE_REPOSITORY="$2"; shift 2 ;;
    --source-docker-docs) SOURCE_DOCKER_DOCS="$2"; shift 2 ;;
    --source-compose-file) SOURCE_COMPOSE_FILE="$2"; shift 2 ;;
    --timezone) TIMEZONE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1"; usage; exit 2 ;;
  esac
done

[[ -n "$APP_KEY" && -n "$TITLE" && -n "$IMAGE" && -n "$VERSION" ]] || { usage; exit 2; }
[[ -n "$SOURCE_REPOSITORY" && -n "$SOURCE_DOCKER_DOCS" && -n "$SOURCE_COMPOSE_FILE" ]] || {
  echo "FAIL: source evidence is required. Provide --source-repository --source-docker-docs --source-compose-file" >&2
  exit 2
}

OUT_DIR="${OUT_DIR:-./1panel-apps}"
PORT="${PORT:-8080}"
TARGET_PORT="${TARGET_PORT:-80}"
TIMEZONE="${TIMEZONE:-Asia/Shanghai}"

APP_DIR="$OUT_DIR/$APP_KEY"
VER_DIR="$APP_DIR/$VERSION"
if [[ -e "$APP_DIR" ]]; then
  shopt -s nullglob dotglob
  existing_entries=("$APP_DIR"/*)
  shopt -u nullglob dotglob
  if [[ ${#existing_entries[@]} -gt 0 && "$FORCE" -ne 1 ]]; then
    echo "FAIL: target app directory already exists and is not empty: $APP_DIR" >&2
    echo "Hint: remove it first or re-run with --force when overwrite is intentional." >&2
    exit 2
  fi
fi
mkdir -p "$VER_DIR/data" "$VER_DIR/scripts"
: > "$VER_DIR/data/.gitkeep"
: > "$VER_DIR/scripts/.gitkeep"

TAG_VALUE="$(infer_tag "$TAG" "$TYPE" "$TITLE" "$IMAGE")"
ARCHES=$(bash "$(dirname "$0")/detect_architectures.sh" "$IMAGE" 2>/dev/null || echo amd64)

"$PYTHON_BIN" - "$APP_DIR/data.yml" "$TITLE" "$APP_KEY" "$TAG_VALUE" "$TYPE" "$ARCHES" "$WEBSITE" "$DOCUMENT" "$GITHUB_URL" <<'PY'
import sys
from pathlib import Path
import yaml

out = Path(sys.argv[1])
title = sys.argv[2]
app_key = sys.argv[3]
tag_value = sys.argv[4]
app_type = sys.argv[5]
arches = [x for x in sys.argv[6].split() if x] or ["amd64"]
website = sys.argv[7] if len(sys.argv) > 7 else ""
document = sys.argv[8] if len(sys.argv) > 8 else ""
github_url = sys.argv[9] if len(sys.argv) > 9 else ""

payload = {
    "name": title,
    "tags": [tag_value],
    "title": title,
    "description": title,
    "additionalProperties": {
        "key": app_key,
        "name": title,
        "tags": [tag_value],
        "shortDescZh": title,
        "shortDescEn": title,
        "description": {
            "en": title,
            "zh": title,
            "zh-Hant": f"{title}（佔位）",
            "ja": f"{title}（プレースホルダー）",
            "ko": f"{title}（플레이스홀더）",
            "ru": f"{title}（заполнитель）",
            "ms": f"{title} (placeholder)",
            "pt-br": f"{title} (placeholder)",
        },
        "type": app_type,
        "crossVersionUpdate": True,
        "limit": 0,
        "website": website,
        "github": github_url,
        "document": document,
        "architectures": arches,
    },
}

out.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
PY

cat > "$APP_DIR/README.md" <<MD
# ${TITLE}

## 产品介绍

${TITLE} 是由 1panel-app-adapter 生成的 1Panel 应用模板，请按官方来源补全业务说明。

## 主要功能

- 提供基于容器镜像的标准化安装入口
- 预置 1Panel 所需的基础参数与生命周期脚本

## 访问说明

- 默认通过 PANEL_APP_PORT_HTTP 对外访问
- 安装后访问地址：http://<server-ip>:<port>

## Introduction

${TITLE} is a generated 1Panel app template produced by 1panel-app-adapter.

## Features

- Standardized container-based installation entry
- Baseline 1Panel fields and lifecycle scripts

- app key: ${APP_KEY}
- version: select the required version from the app store version list
MD

"$PYTHON_BIN" - "$APP_DIR/source-evidence.json" "$SOURCE_REPOSITORY" "$SOURCE_DOCKER_DOCS" "$SOURCE_COMPOSE_FILE" <<'PY'
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
payload = {
    "repository": sys.argv[2],
    "dockerDocs": sys.argv[3],
    "composeFile": sys.argv[4],
}
out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

if [[ ! -f "$APP_DIR/logo.png" ]]; then
  DEFAULT_LOGO="$(cd "$(dirname "$0")" && pwd)/../assets/default-logo.png"
  if [[ -f "$DEFAULT_LOGO" ]]; then
    cp "$DEFAULT_LOGO" "$APP_DIR/logo.png"
  else
    echo "[WARN] logo.png not provided and default logo missing; add a valid PNG before publishing" >&2
  fi
fi

FORM_FIELDS=""
FORM_FIELDS+="    - default: ${PORT}\\n"
FORM_FIELDS+="      edit: true\\n"
FORM_FIELDS+="      envKey: PANEL_APP_PORT_HTTP\\n"
FORM_FIELDS+="      labelEn: Port\\n"
FORM_FIELDS+="      labelZh: 端口\\n"
FORM_FIELDS+="      label:\\n"
FORM_FIELDS+="        en: Port\\n"
FORM_FIELDS+="        zh: 端口\\n"
FORM_FIELDS+="        zh-Hant: 埠\\n"
FORM_FIELDS+="        ja: ポート\\n"
FORM_FIELDS+="        ko: 포트\\n"
FORM_FIELDS+="        ru: Порт\\n"
FORM_FIELDS+="        ms: Port\\n"
FORM_FIELDS+="        pt-br: Porta\\n"
FORM_FIELDS+="      required: true\\n"
FORM_FIELDS+="      rule: paramPort\\n"
FORM_FIELDS+="      type: number\\n"
FORM_FIELDS+="    - default: ${TIMEZONE}\\n"
FORM_FIELDS+="      edit: true\\n"
FORM_FIELDS+="      envKey: TZ\\n"
FORM_FIELDS+="      labelEn: Timezone\\n"
FORM_FIELDS+="      labelZh: 时区\\n"
FORM_FIELDS+="      label:\\n"
FORM_FIELDS+="        en: Timezone\\n"
FORM_FIELDS+="        zh: 时区\\n"
FORM_FIELDS+="        zh-Hant: 時區\\n"
FORM_FIELDS+="        ja: タイムゾーン\\n"
FORM_FIELDS+="        ko: 시간대\\n"
FORM_FIELDS+="        ru: Часовой пояс\\n"
FORM_FIELDS+="        ms: Zon waktu\\n"
FORM_FIELDS+="        pt-br: Fuso horário\\n"
FORM_FIELDS+="      required: true\\n"
FORM_FIELDS+="      type: text\\n"

if [[ "$WITH_PANEL_DEPS" -eq 1 ]]; then
  FORM_FIELDS+="    - default: mysql\\n"
  FORM_FIELDS+="      envKey: PANEL_DB_TYPE\\n"
  FORM_FIELDS+="      labelEn: Database\\n"
  FORM_FIELDS+="      labelZh: 数据库服务\\n"
  FORM_FIELDS+="      label:\\n"
  FORM_FIELDS+="        en: Database\\n"
  FORM_FIELDS+="        zh: 数据库服务\\n"
  FORM_FIELDS+="        zh-Hant: 資料庫服務\\n"
  FORM_FIELDS+="        ja: データベース\\n"
  FORM_FIELDS+="        ko: 데이터베이스\\n"
  FORM_FIELDS+="        ru: База данных\\n"
  FORM_FIELDS+="        ms: Pangkalan Data\\n"
  FORM_FIELDS+="        pt-br: Banco de dados\\n"
  FORM_FIELDS+="      required: true\\n"
  FORM_FIELDS+="      type: apps\\n"
  FORM_FIELDS+="      child:\\n"
  FORM_FIELDS+="        - default: \"\"\\n"
  FORM_FIELDS+="          envKey: PANEL_DB_HOST\\n"
  FORM_FIELDS+="          required: true\\n"
  FORM_FIELDS+="          type: service\\n"
  FORM_FIELDS+="    - default: ${APP_KEY}\\n"
  FORM_FIELDS+="      edit: true\\n"
  FORM_FIELDS+="      envKey: PANEL_DB_NAME\\n"
  FORM_FIELDS+="      labelEn: Database Name\\n"
  FORM_FIELDS+="      labelZh: 数据库名\\n"
  FORM_FIELDS+="      label:\\n"
  FORM_FIELDS+="        en: Database Name\\n"
  FORM_FIELDS+="        zh: 数据库名\\n"
  FORM_FIELDS+="        zh-Hant: 資料庫名\\n"
  FORM_FIELDS+="        ja: データベース名\\n"
  FORM_FIELDS+="        ko: 데이터베이스 이름\\n"
  FORM_FIELDS+="        ru: Имя базы данных\\n"
  FORM_FIELDS+="        ms: Nama pangkalan data\\n"
  FORM_FIELDS+="        pt-br: Nome do banco de dados\\n"
  FORM_FIELDS+="      required: true\\n"
  FORM_FIELDS+="      random: true\\n"
  FORM_FIELDS+="      type: text\\n"
  FORM_FIELDS+="    - default: ${APP_KEY}\\n"
  FORM_FIELDS+="      edit: true\\n"
  FORM_FIELDS+="      envKey: PANEL_DB_USER\\n"
  FORM_FIELDS+="      labelEn: Database User\\n"
  FORM_FIELDS+="      labelZh: 数据库用户\\n"
  FORM_FIELDS+="      label:\\n"
  FORM_FIELDS+="        en: Database User\\n"
  FORM_FIELDS+="        zh: 数据库用户\\n"
  FORM_FIELDS+="        zh-Hant: 資料庫使用者\\n"
  FORM_FIELDS+="        ja: データベースユーザー\\n"
  FORM_FIELDS+="        ko: 데이터베이스 사용자\\n"
  FORM_FIELDS+="        ru: Пользователь базы данных\\n"
  FORM_FIELDS+="        ms: Nama pengguna pangkalan data\\n"
  FORM_FIELDS+="        pt-br: Usuário do banco de dados\\n"
  FORM_FIELDS+="      required: true\\n"
  FORM_FIELDS+="      random: true\\n"
  FORM_FIELDS+="      type: text\\n"
  FORM_FIELDS+="    - default: \"\"\\n"
  FORM_FIELDS+="      edit: true\\n"
  FORM_FIELDS+="      envKey: PANEL_DB_USER_PASSWORD\\n"
  FORM_FIELDS+="      labelEn: Database Password\\n"
  FORM_FIELDS+="      labelZh: 数据库密码\\n"
  FORM_FIELDS+="      label:\\n"
  FORM_FIELDS+="        en: Database Password\\n"
  FORM_FIELDS+="        zh: 数据库密码\\n"
  FORM_FIELDS+="        zh-Hant: 資料庫密碼\\n"
  FORM_FIELDS+="        ja: データベースパスワード\\n"
  FORM_FIELDS+="        ko: 데이터베이스 비밀번호\\n"
  FORM_FIELDS+="        ru: Пароль базы данных\\n"
  FORM_FIELDS+="        ms: Kata laluan pangkalan data\\n"
  FORM_FIELDS+="        pt-br: Senha do banco de dados\\n"
  FORM_FIELDS+="      required: true\\n"
  FORM_FIELDS+="      random: true\\n"
  FORM_FIELDS+="      type: password\\n"
  FORM_FIELDS+="    - default: \"\"\\n"
  FORM_FIELDS+="      edit: true\\n"
  FORM_FIELDS+="      envKey: REDIS_HOST\\n"
  FORM_FIELDS+="      labelEn: Redis Host\\n"
  FORM_FIELDS+="      labelZh: Redis地址\\n"
  FORM_FIELDS+="      label:\\n"
  FORM_FIELDS+="        en: Redis Host\\n"
  FORM_FIELDS+="        zh: Redis Host\\n"
  FORM_FIELDS+="        zh-Hant: Redis 主機\\n"
  FORM_FIELDS+="        ja: Redis ホスト\\n"
  FORM_FIELDS+="        ko: Redis 호스트\\n"
  FORM_FIELDS+="        ru: Хост Redis\\n"
  FORM_FIELDS+="        ms: Hos Redis\\n"
  FORM_FIELDS+="        pt-br: Host Redis\\n"
  FORM_FIELDS+="      required: true\\n"
  FORM_FIELDS+="      type: service\\n"
  FORM_FIELDS+="    - default: 6379\\n"
  FORM_FIELDS+="      edit: true\\n"
  FORM_FIELDS+="      envKey: REDIS_PORT\\n"
  FORM_FIELDS+="      labelEn: Redis Port\\n"
  FORM_FIELDS+="      labelZh: Redis端口\\n"
  FORM_FIELDS+="      label:\\n"
  FORM_FIELDS+="        en: Redis Port\\n"
  FORM_FIELDS+="        zh: Redis端口\\n"
  FORM_FIELDS+="        zh-Hant: Redis 服務連接埠\\n"
  FORM_FIELDS+="        ja: Redis サービスポート\\n"
  FORM_FIELDS+="        ko: Redis 서비스 포트\\n"
  FORM_FIELDS+="        ru: Порт службы Redis\\n"
  FORM_FIELDS+="        ms: Port Perkhidmatan Redis\\n"
  FORM_FIELDS+="        pt-br: Porta do serviço Redis\\n"
  FORM_FIELDS+="      required: true\\n"
  FORM_FIELDS+="      rule: paramPort\\n"
  FORM_FIELDS+="      type: number\\n"
  FORM_FIELDS+="    - default: \"\"\\n"
  FORM_FIELDS+="      edit: true\\n"
  FORM_FIELDS+="      envKey: PANEL_REDIS_ROOT_PASSWORD\\n"
  FORM_FIELDS+="      labelEn: Redis Password\\n"
  FORM_FIELDS+="      labelZh: Redis密码\\n"
  FORM_FIELDS+="      label:\\n"
  FORM_FIELDS+="        en: Redis Password\\n"
  FORM_FIELDS+="        zh: Redis 密码\\n"
  FORM_FIELDS+="        zh-Hant: Redis 密碼\\n"
  FORM_FIELDS+="        ja: Redis パスワード\\n"
  FORM_FIELDS+="        ko: Redis 비밀번호\\n"
  FORM_FIELDS+="        ru: Пароль Redis\\n"
  FORM_FIELDS+="        ms: Kata laluan Redis\\n"
  FORM_FIELDS+="        pt-br: Senha do Redis\\n"
  FORM_FIELDS+="      required: true\\n"
  FORM_FIELDS+="      type: password\\n"
  FORM_FIELDS+="    - default: 0\\n"
  FORM_FIELDS+="      edit: true\\n"
  FORM_FIELDS+="      envKey: REDIS_DB\\n"
  FORM_FIELDS+="      labelEn: Redis Database\\n"
  FORM_FIELDS+="      labelZh: Redis数据库\\n"
  FORM_FIELDS+="      label:\\n"
  FORM_FIELDS+="        en: Redis Database\\n"
  FORM_FIELDS+="        zh: Redis 数据库\\n"
  FORM_FIELDS+="        zh-Hant: Redis 資料庫\\n"
  FORM_FIELDS+="        ja: Redis データベース\\n"
  FORM_FIELDS+="        ko: Redis 데이터베이스\\n"
  FORM_FIELDS+="        ru: База данных Redis\\n"
  FORM_FIELDS+="        ms: Pangkalan Data Redis\\n"
  FORM_FIELDS+="        pt-br: Banco de dados Redis\\n"
  FORM_FIELDS+="      required: true\\n"
  FORM_FIELDS+="      type: number\\n"
fi

if [[ -n "$VOLUMES" ]]; then
  idx=1
  IFS=',' read -r -a mounts_for_fields <<< "$VOLUMES" || true
  for item in "${mounts_for_fields[@]}"; do
    [[ -z "$item" ]] && continue
    host="${item%%:*}"
    if [[ "$host" != ./* && "$host" != /* && "$host" != \$\{*\} ]]; then
      continue
    fi
    if [[ "$host" == ./* && "$host" != ./data && "$host" != ./data/* ]]; then
      host="./data/${host#./}"
    fi
    FORM_FIELDS+="    - default: ${host}\\n"
    FORM_FIELDS+="      edit: true\\n"
    FORM_FIELDS+="      envKey: APP_DATA_DIR_${idx}\\n"
    FORM_FIELDS+="      labelEn: Data Directory ${idx}\\n"
    FORM_FIELDS+="      labelZh: 数据目录 ${idx}\\n"
    FORM_FIELDS+="      label:\\n"
    FORM_FIELDS+="        en: Data Directory ${idx}\\n"
    FORM_FIELDS+="        zh: 数据目录 ${idx}\\n"
    FORM_FIELDS+="        zh-Hant: 資料目錄 ${idx}\\n"
    FORM_FIELDS+="        ja: データディレクトリ ${idx}\\n"
    FORM_FIELDS+="        ko: 데이터 디렉터리 ${idx}\\n"
    FORM_FIELDS+="        ru: Каталог данных ${idx}\\n"
    FORM_FIELDS+="        ms: Direktori data ${idx}\\n"
    FORM_FIELDS+="        pt-br: Diretório de dados ${idx}\\n"
    FORM_FIELDS+="      required: true\\n"
    FORM_FIELDS+="      type: text\\n"
    idx=$((idx+1))
  done
fi

cat > "$VER_DIR/data.yml" <<YAML
additionalProperties:
  formFields:
YAML
printf "%b" "$FORM_FIELDS" >> "$VER_DIR/data.yml"

"$PYTHON_BIN" - "$VER_DIR/docker-compose.yml" "$APP_KEY" "$IMAGE" "$TARGET_PORT" "$WITH_PANEL_DEPS" "$TYPE" "$TAG_VALUE" <<'PY'
import sys
from pathlib import Path
import yaml

out = Path(sys.argv[1])
app_key = sys.argv[2]
image = sys.argv[3]
target_port = sys.argv[4]
with_panel_deps = sys.argv[5] == "1"
app_type = sys.argv[6].strip().lower()
tag_value = sys.argv[7].strip().lower()

environment = ["TZ=${TZ}"]
if with_panel_deps:
    environment.extend([
        "PANEL_DB_HOST=${PANEL_DB_HOST}",
        "PANEL_DB_NAME=${PANEL_DB_NAME}",
        "PANEL_DB_USER=${PANEL_DB_USER}",
        "PANEL_DB_USER_PASSWORD=${PANEL_DB_USER_PASSWORD}",
        "REDIS_HOST=${REDIS_HOST}",
        "REDIS_PORT=${REDIS_PORT}",
        "PANEL_REDIS_ROOT_PASSWORD=${PANEL_REDIS_ROOT_PASSWORD}",
        "REDIS_DB=${REDIS_DB}",
    ])

payload = {
    "services": {
        app_key: {
            "image": image,
            "container_name": "${CONTAINER_NAME}",
            "ports": [f"${{PANEL_APP_PORT_HTTP}}:{target_port}"],
            "environment": environment,
            "labels": {"createdBy": "Apps"},
            "restart": "on-failure:3",
        }
    }
}

out.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
PY

if [[ -n "$VOLUMES" ]]; then
  echo "    volumes:" >> "$VER_DIR/docker-compose.yml"
  named_volumes=()
  idx=1
  IFS=',' read -r -a mounts <<< "$VOLUMES" || true
  for item in "${mounts[@]}"; do
    [[ -z "$item" ]] && continue
    host="${item%%:*}"
    cont="${item#*:}"
    if [[ "$host" != ./* && "$host" != /* && "$host" != \$\{*\} ]]; then
      echo "      - \"${host}:${cont}\"" >> "$VER_DIR/docker-compose.yml"
      named_volumes+=("$host")
    else
      echo "      - \"\${APP_DATA_DIR_${idx}}:${cont}\"" >> "$VER_DIR/docker-compose.yml"
      idx=$((idx+1))
    fi
  done
  if [[ ${#named_volumes[@]} -gt 0 ]]; then
    echo "" >> "$VER_DIR/docker-compose.yml"
    echo "volumes:" >> "$VER_DIR/docker-compose.yml"
    for vol in "${named_volumes[@]}"; do
      echo "  ${vol}:" >> "$VER_DIR/docker-compose.yml"
      echo "    name: ${vol}" >> "$VER_DIR/docker-compose.yml"
    done
  fi
fi

"$PYTHON_BIN" "$(dirname "$0")/gen_env_sample.py" "$VER_DIR/data.yml" "$VER_DIR/.env.sample" "$VER_DIR/docker-compose.yml"
"$PYTHON_BIN" "$(dirname "$0")/runtime_script_utils.py" "$VER_DIR/data.yml" "$VER_DIR/scripts/init.sh"

cat > "$VER_DIR/scripts/upgrade.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
exit 0
SH
chmod +x "$VER_DIR/scripts/upgrade.sh"

cat > "$VER_DIR/scripts/uninstall.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$ROOT_DIR"
docker-compose down
SH
chmod +x "$VER_DIR/scripts/uninstall.sh"

for required_path in "$APP_DIR/data.yml" "$APP_DIR/source-evidence.json" "$VER_DIR"; do
  if [[ ! -e "$required_path" ]]; then
    echo "FAIL: scaffold postcondition missing direct app-root artifact: $required_path" >&2
    exit 1
  fi
done
if [[ -s "$APP_DIR/$APP_KEY/data.yml" && -s "$APP_DIR/$APP_KEY/source-evidence.json" ]]; then
  echo "FAIL: duplicate nested app root detected: $APP_DIR/$APP_KEY" >&2
  exit 1
fi

bash "$(dirname "$0")/hint-panel-deps.sh" "$VER_DIR/docker-compose.yml" || true
echo "OK: scaffolded -> $APP_DIR"
