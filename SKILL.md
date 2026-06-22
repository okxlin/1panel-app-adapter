---
name: 1panel-app-adapter
description: Rule-first skill for generating, migrating, and validating 1Panel app artifacts in Linux and GitHub workflows.
---

# 1panel-app-adapter

This skill is the public, cleaned-up variant of the local research skill. It is designed to generate and validate 1Panel app artifacts with increasingly complete defaults, without bundling evidence packs, replay logs, or third-party repository snapshots.

## Applicability / Non-applicability

**Applicable:**
- Applications with reliable Docker installation paths (official repository, official documentation, official images, official `docker-compose.yml` / `compose.yml`).
- Existing compose that needs to be organized into 1Panel v2 directory structure.
- Existing v1/mixed structure that needs migration, field completion, and pre-submission strict validation.

**Not applicable:**
- Applications without reliable Docker deployment paths, where installation method can only be guessed by inferring images, ports, volumes, environment variables, and dependencies.
- Scenarios requiring determination of whether third-party images, tutorials, or unofficial compose fragments are trustworthy.
- Direct publishing to remote appstore repositories; this skill's responsibility is generation/adaptation/validation, not replacing the submission workflow.

## Rule Priority

Judge every rule in this order:

1. Runtime and source-code hard rules from `1Panel-dev/1Panel`
2. Official 1Panel wiki and official docs
3. Official appstore repository conventions
4. External references and practical articles

Only rules backed by runtime behavior or explicit official documentation should block generation or validation. Repository conventions are guidance unless validator mode explicitly upgrades them.

## Source Policy (Evidence First)

Before adaptation, prioritize reading `references/source-policy.md` and collect evidence according to source priority:
- User-provided official repository/documentation > official image docs > official appstore structure facts > third-party examples
- Without official Docker evidence, stop expanding; do not guess images, ports, volumes, UID/GID, or dependency injection methods
- When using third-party images, user must explicitly accept, and record source and risk in delivery notes

## Recommended Directory Structure (Store-Aligned)

### Field Hierarchy Constraints (Aligned with Official apps/ Facts)

> Note: In the official repository (1Panel-dev/appstore dev branch), the `data.yml` field hierarchy under v2 structure is very stable; this skill's `validate-v2.sh --strict-store` performs strict validation according to this.

> - **Language codes**: Official write as `zh-Hant` (note uppercase H); old write `zh-hant` is only for compatibility, recommend unified replacement.

**Application-level**: `apps/<app>/data.yml`
- Top-level only allows: `name` / `tags` / `title` / `description` / `additionalProperties`
- Top-level `type` appearing: **WARN only** (historical/non-standard field; official regular write doesn't place at top level)
- `architectures`: Must be in `additionalProperties.architectures` (100% present in official samples)

**strict-store additionalProperties required (missing = FAIL):**
- `key` / `name` / `tags` / `type` / `website` / `document` / `architectures`
- `github` / `shortDescZh` / `shortDescEn` / `crossVersionUpdate` / `limit`
- (Others like `recommend` / `description` / `memoryRequired` can maintain WARN by occurrence rate)

**Version-level**: `apps/<app>/<ver|latest|stable>/data.yml`
- Top-level only allows: `additionalProperties`
  - Can be `null` or `object` (but under strict-store, recommend object with required fields filled)
- `formFields` must be in `additionalProperties.formFields` (top-level `formFields` not allowed)
- **Prohibit `architectures`**: Version-level `data.yml` (same level as `docker-compose.yml`) should not have `architectures` (neither top-level nor inside `additionalProperties`)

> Convention supplement (this skill's default artifact style):
> - root `data.yml` top-level `description` uses single-line string (not map).
> - root `data.yml` `additionalProperties.shortDesc` uses `shortDescZh/shortDescEn` (not map).
> - `additionalProperties.description` uses i18n map, **must complete 8 languages**: `en/zh/zh-Hant/ja/ko/ru/ms/pt-br`.
> - root `data.yml` uses hierarchical structure: top-level `tags` and `additionalProperties.tags` both exist and are semantically consistent (allow redundant expression).
> - **Content consistency (strong constraint)**: root `data.yml` `title:`, the following top-level `description:`, and `additionalProperties.shortDescZh:` must be the **same short text** (try to be one sentence).
> - **Translation constraint (strong constraint)**: `additionalProperties.description` must be the multilingual translation of the above `shortDescZh` (not repetition of project name/title).
> - `architectures` (only root `data.yml`) represents Docker image supported architecture list; should be in `additionalProperties.architectures`, using hierarchical array (e.g., `- amd64` / `- arm64`); if cannot reliably obtain (e.g., no manifest info/offline), default only fill `- amd64`.

### formFields Structure Facts (version-level)

Location: `additionalProperties.formFields: [ ... ]`

### `formFields[]` item common fields
- `envKey` (required)
- `type` (required)
- `required` (required)
- `default` (common)
- `rule` (optional; common set below)
- `labelZh` / `labelEn` (high-frequency; recommend providing both)
- `label` (multi-language map, high-frequency)
- `child` (appears when `type: apps`)

### `formFields[].type` allowed set (based on official dev/apps real samples)
- `number`
- `password`
- `select`
- `text`
- `apps`
- `service`

Notes:
- Official repo has **both patterns**:
  - `type: apps` + `child.type: service`
  - Direct `type: service`
- Therefore validator should allow `service` in `formFields[].type`, but adapted artifacts can prefer `apps + child.service` to express "dependency selection → service instance selection" two-step semantics.

### `rule` common set (for this skill validation)
- `paramPort` (most common, for `PANEL_APP_PORT_*`)
- `paramExtUrl`
- `paramCommon`
- `paramComplexity`

### `formFields[].edit` (install form editability)

Based on official v2 app library `docker-compose.yml` and same-directory version-level `data.yml` actual write:
- `edit` is bool in DTO (default equivalent to false), but official library explicitly writes `edit: true` for many fields.
- Our adaptation artifacts suggest (default more "editable"):
  - **Generally enable `edit: true`** (let users adjust in install interface).
  - Only for a few "injection/should not manually modify" envKey exceptions (can omit or `edit: false`), typical: `PANEL_DB_*` / `PANEL_REDIS_*` / `PANEL_MINIO_*` etc. panel injection variables.
  - Dependency selection fields (`type: apps/service`) whether `edit:true` depends on UI interaction, but default can be true.
- Validation strategy: `validate-v2.sh --strict-store` will **WARN** for "obviously user input and required=true but missing edit:true" entries (not FAIL, to avoid mis-killing official historical write).

## Database / Redis Dependency Injection (Panel Fixed envKey)

When applications need to reuse 1Panel store's database/cache applications, **recommend prioritizing panel built-in convention envKeys**, otherwise panel may not correctly inject service address/credentials.

Common fixed envKeys (recommend using as needed):
- Database: `PANEL_DB_TYPE`, `PANEL_DB_HOST`, `PANEL_DB_NAME`, `PANEL_DB_USER`, `PANEL_DB_USER_PASSWORD`
- Redis: `REDIS_HOST`, `REDIS_PORT`, `PANEL_REDIS_ROOT_PASSWORD`, `REDIS_DB`

Scaffold supports optional injection template:
- When running `scripts/scaffold-v2.sh`, add `--with-panel-deps` (or alias `--with-panel-db-redis`), will automatically add above DB/Redis related formFields in generated `<version>/data.yml` (including `labelEn/labelZh` + `label` map, includes `zh-Hant`).

Key points for adaptation:
- `version/data.yml` uses `type: apps` + `child.type: service` to inject `PANEL_DB_HOST` (reference 1Panel store app common dependency injection pattern).
- `docker-compose.yml` if application uses `DATABASE_*` variables, need to map in compose:
  - `DATABASE_HOST: ${PANEL_DB_HOST}`
  - `DATABASE_USER: ${PANEL_DB_USER}`
  - `DATABASE_PASSWORD: ${PANEL_DB_USER_PASSWORD}`
  - `DATABASE_DBNAME: ${PANEL_DB_NAME}`
- Redis password similarly: `REDIS_PASSWORD: ${PANEL_REDIS_ROOT_PASSWORD}` (if application field name differs, map as needed).
> - version `data.yml` `formFields[].label` should keep both `labelZh/labelEn` and `label` map (compatible with different repositories/versions).
> - volumes host paths default prefer falling under `./data/*` subdirectories (e.g., `./cache` normalizes to `./data/cache`).
> - **Named volumes (named volume) maintain upstream semantics**:
>   - If upstream compose uses `volumes: <name>:` and service mounts `- <name>:/path`, adaptation should try to preserve.
>   - **root data.yml restriction**: When application uses named volume as main data volume, root `data.yml` `additionalProperties.limit` set to `1`.
>   - Recommended write (compatible with 1Panel scenario):
>     ```yaml
>     volumes:
>       zeroclaw-data:
>         name: zeroclaw-data
>     ```
>     And keep in service:
>     ```yaml
>     volumes:
>       - zeroclaw-data:/zeroclaw-data
>     ```
>   - Only when upstream explicitly uses host path mapping, convert to `APP_DATA_DIR_*` + `./data/*` form.
> - **Uninstall script**: Adaptation artifact's `<version>/scripts/uninstall.sh` needs to support cleanup volumes; minimal implementation can use:
>   ```bash
>   #!/bin/bash
>   docker-compose down --volumes
>   ```

## Multi-Service Compose Hint Mechanism (Hint Only, No Auto-Modification)

When scaffold/migrate output `docker-compose.yml` detects **multiple services** containing `postgres/mysql/mariadb/redis` keywords, it outputs hints:
- Suggest considering `--with-panel-deps` to switch to 1Panel store dependency injection (`PANEL_DB_* / PANEL_REDIS_*`) mode
- Remind to map application's own `DATABASE_* / REDIS_*` variables to panel fixed variable names in compose
- Can manually run hint check on any compose: `bash scripts/hint-panel-deps.sh <docker-compose.yml>`

## docker-compose.yml ↔ data.yml Field Constraints (Strong Constraints)

### ports → formFields (Official Common Pattern)

Based on official `dev/apps` version-level samples:
- External port field **mostly** uses `envKey: PANEL_APP_PORT_HTTP` (also exists `PANEL_APP_PORT_HTTPS/SSH/API/...`).
- Corresponding `formFields` rule basically fixed as:
  - `type: number`
  - `required: true`
  - `rule: paramPort` (official almost always uses it)
  - `default` is specific port number (1..65535)
- `docker-compose.yml` usually writes:
  - `- "${PANEL_APP_PORT_HTTP}:<container_port>"`

Adaptation suggestions:
- **Port envKey must have prefix**: Unified use `PANEL_APP_PORT_` prefix (e.g., `PANEL_APP_PORT_HTTP` / `PANEL_APP_PORT_API`).
- Single-port web application: Prioritize expose `PANEL_APP_PORT_HTTP`.
- Multi-port application: Use `PANEL_APP_PORT_HTTP/HTTPS/API/SSH/...` semantic naming (keep all uppercase, underscores), all use `rule: paramPort`.

### volumes → Data Directory Fields (Official vs Adaptation Artifact Convention)

Official library compose **mostly uses bind mount** (e.g., `./data:/data`, `./conf/xx:/etc/xx`), but official version-level `data.yml` **usually doesn't** parameterize paths through `APP_DATA_DIR_*` formFields (prefers directly writing fixed relative paths).

Adaptation artifact convention (our own artifact style):
- Although official library directly writes `./data/*`, **our adaptation artifacts prioritize recommending `APP_DATA_DIR(_N)`** to parameterize data directories, for user location selection and migration.
- When compose has bind mount:
  - Default at least provide one `APP_DATA_DIR` (or `APP_DATA_DIR_1`) field;
  - In compose, write host path as `${APP_DATA_DIR}/...` (or `${APP_DATA_DIR_1}/...`).
- If indeed don't want users to change paths (rare scenarios), fix to `./data/*`.

### depends_on / External Dependencies → apps/service Injection

Official library has both patterns:
- `type: apps` + `child.type: service` (nested injection)
- Direct `type: service` (also exists in official library)

Adaptation suggestions:
- **External service/dependency injection prioritize child pattern**: Prioritize `type: apps` + `child.type: service` (express "dependency type selection → service instance selection" two-step semantics).
- Only when panel interaction clearly only needs "select a service instance" and doesn't need dependency type selection, use `type: service`.

- **Enum/boolean must use select**:
  - If compose has `FOO: "true"/"false"`, log level, run mode etc. "finite set" variables, should define in `<version>/data.yml` `formFields` with `type: select` (e.g., values: true/false or debug/info/warn/error), avoid free text.
  - Example: `ZEROCLAW_ALLOW_PUBLIC_BIND` switch should be select (true/false).
  - **`values[].label` must always be pure string, prohibit multi-language map** (strong constraint):
    - 1Panel backend will deserialize `formFields[].values[].label` to `string`; if incorrectly written as multi-language object (e.g., `label: { en: ..., zh: ... }`), will directly error: `cannot unmarshal object into Go struct field ... values.label of type string`.
    - This constraint applies to all `type: select` / `type: apps` / any enum items with `values:`, not just booleans.
  - ❌ Wrong:
    ```yaml
    values:
      - label:
          en: 'True'
          zh: '是'
        value: "true"
    ```
  - ✅ Correct:
    ```yaml
    values:
      - label: "true"
        value: "true"
    ```
- **Boolean text values label must add quotes**: When `values[].label` is `true/false`, must write as string (`"true"/"false"`), avoid YAML parsing as boolean causing frontend/panel issues.
  - ❌ Wrong: `label: true`
  - ✅ Correct: `label: "true"`

- **compose variable closure (strong constraint)**:
  - `docker-compose.yml` variables `${VAR}` / `${VAR:-default}` / `${VAR?msg}` etc., by default must find corresponding declaration in version `data.yml` `formFields.envKey`.
  - Few variables implicitly provided by 1Panel/runtime, maintained in `references/implicit-envkeys.md`.
  - Before adding new implicit variables, confirm they truly belong to platform injection; don't put ordinary application variables into whitelist.

- **External port envKey must use `PANEL_APP_PORT*` prefix**:
  - 1Panel official convention: `envKey` **containing** `PANEL_APP_PORT` prefix will be recognized as port type, used for port occupation check during installation.
  - Therefore: all "externally exposed host port" fields, envKey must be named `PANEL_APP_PORT_*` (e.g., `PANEL_APP_PORT_HTTP`).
  - If upstream uses `HOST_PORT` naming, should map in compose:
    - `HOST_PORT=${PANEL_APP_PORT_HTTP}` (or directly use `${PANEL_APP_PORT_HTTP}` as ports left side).

- **compose image field unified double quotes** (strong constraint):
  - `docker-compose.yml` `image:` always use double quotes, especially digest (`@sha256:...`) or variable form, reduce YAML/panel parsing edge issues:
    ```yaml
    image: "lscr.io/linuxserver/joplin:latest"
    image: "${ZEROCLAW_IMAGE}"
    image: "ghcr.io/org/app@sha256:..."
    ```

- **compose environment variable write prioritize `KEY=VALUE` list** (strong constraint, adaptation artifact requirement):
  - Official library `environment:` has both list-style (`- KEY=...`) and map-style (`KEY: ...`).
  - For stable diff/migration and avoiding YAML edge parsing: **our adaptation artifacts force list-style**.
  - Therefore: adaptation artifact's `docker-compose.yml` `environment:` must use list write:
    ```yaml
    environment:
      - API_KEY=${API_KEY:-}
      - PROVIDER=${PROVIDER}
    ```
  - For required but allow empty default keys (common in API_KEY), recommend `${VAR:-}` form consistent with upstream.
  - **Alias variable (synonym key) handling**: If upstream provides `API_KEY` and `XXX_API_KEY` synonym variable names, adaptation should only expose one main field (usually use upstream default `API_KEY`), another in compose comment form (don't inject two keys simultaneously, avoid ambiguity).
  - Avoid map write:
    ```yaml
    environment:
      API_KEY: ${API_KEY}
    ```

## What this skill does

- Scaffold a v2-style 1Panel app directory with richer default fields
- Migrate an existing app directory into the v2 layout with basic quality backfill
- Import Baota/aaPanel Docker Store app directories into 1Panel v2 layout
- Patch root metadata, version metadata, and compose content
- Generate `.env.sample`
- Validate the resulting app directory

## Supported commands

- `bash scripts/scaffold-v2.sh --help`
- `python3 scripts/generate-from-appspec.py --help`
- `python3 scripts/generate-from-appspec.py --spec <spec.json> --validate`
- `python3 scripts/generate-from-appspec.py --spec <spec.json> --validate --require-validate`
- `python3 scripts/import-baota-app.py --help`
- `python3 scripts/import-baota-app.py --input <baota-app-dir> --validate`
- `python3 scripts/import-baota-app.py --input <apphub-dir> --batch --validate`
- `bash scripts/migrate-v1-to-v2.sh --help`
- `bash scripts/finalize_runtime_scripts.sh --help`
- `bash scripts/validate-v2.sh --help`

## Recommended execution flow

Use this skill in one of three paths.

### Path A: generate a new 1Panel app

1. Run `bash scripts/scaffold-v2.sh ...` to create the v2 app skeleton.
   - include `--source-repository --source-docker-docs --source-compose-file` as required source evidence inputs.
2. Review the generated `data.yml`, version `data.yml`, and `docker-compose.yml` (including default tag, TZ, optional healthcheck, and dependency/env fields when applicable).
3. Verify `<app>/source-evidence.json` exists and is complete.
4. If needed, run `bash scripts/finalize_runtime_scripts.sh <app-dir> <version-dir>` to ensure lifecycle scripts exist.
5. Run `bash scripts/validate-v2.sh --dir <app-dir> --strict-store`.
6. If validation reports issues, use the patch scripts to normalize root metadata, version metadata, or compose content, then validate again.

### Path B: migrate an existing app

1. Run `bash scripts/migrate-v1-to-v2.sh --src <app-dir> [--version <source-ver>] [--target-version <target-ver>] ...`.
2. Ensure source evidence is present in source app (`source-evidence.json`) or provide source-evidence arguments to the migration command.
3. Review the migrated root metadata, version metadata, compose file, lifecycle scripts, and `.env.sample`, then decide whether any high-quality backfill is still needed.
4. If needed, run `bash scripts/finalize_runtime_scripts.sh <app-dir> <version-dir>` to backfill minimal lifecycle scripts.
5. Run `bash scripts/validate-v2.sh --dir <app-dir> --strict-store`.
6. If needed, rerun the patch scripts and validate again until strict-store passes.

### Path C: import a Baota/aaPanel Docker Store app

1. Confirm the input app directory follows the public `aaPanel/apphub` structure: `app.json`, `icon.png`, and a version directory containing `docker-compose.yml` and `.env`.
2. Run `python3 scripts/import-baota-app.py --input <baota-app-dir> --out-dir <out-dir> --version latest --validate --require-validate`.
3. For apphub-style batch input, run `python3 scripts/import-baota-app.py --input <apphub-dir> --batch --out-dir <out-dir> --validate --report <report.json>`.
4. Review `source-evidence.json` and migration notes. Baota metadata alone is not proof that the upstream image, ports, volumes, or env semantics are official.
5. For delivery candidates, run `docker compose --env-file <version>/.env.sample -f <version>/docker-compose.yml config` with a safe `CONTAINER_NAME` value, then run `bash scripts/validate-v2.sh --dir <app-dir> --strict-store` after official source evidence is completed.

Baota import rules are grounded in `references/baota-app-format.md` and `references/baota-to-1panel-mapping.md`. The public `aaPanel/apphub` template defines `HOST_IP`, `CPUS`, `MEMORY_LIMIT`, and `APP_PATH` as required `.env` variables, and aaPanel source creates/reuses `baota_net` before app installation. Imported artifacts convert those runtime assumptions into 1Panel conventions instead of preserving Baota-only variables.

The intended finish line for this skill is: generated, migrated, or imported output exists, root/version/compose structure is normalized, and `validate-v2.sh --strict-store` has been executed with its result recorded for follow-up decisions.

## Supported scaffold arguments

- Required: `--app-key --title --image --version --source-repository --source-docker-docs --source-compose-file`
- Optional: `--out-dir --port --target-port --type --tag --website --document --github --volumes --timezone --with-panel-deps --with-panel-db-redis`

## Common Commands

> Constraint: Any "1Panel-importable application artifact" must be placed under `<out-dir>/<app-key>/...`. Scaffold defaults to `./1panel-apps`.

```bash
# Generate joplin 3.5.13 (auto-tagged)
bash scripts/scaffold-v2.sh \
  --app-key joplin \
  --title "Joplin Server" \
  --image linuxserver/joplin \
  --version 3.5.13 \
  --out-dir examples \
  --port 22300 \
  --target-port 3001 \
  --source-repository https://github.com/laurent22/joplin \
  --source-docker-docs https://hub.docker.com/r/linuxserver/joplin \
  --source-compose-file https://raw.githubusercontent.com/linuxserver/docker-joplin/master/docker-compose.yml

# Override tag manually
bash scripts/scaffold-v2.sh \
  --app-key vaultwarden \
  --title "Vaultwarden" \
  --image vaultwarden/server \
  --version 1.33.2 \
  --out-dir examples \
  --port 28080 \
  --target-port 80 \
  --tag Security \
  --source-repository https://github.com/dani-garcia/vaultwarden \
  --source-docker-docs https://hub.docker.com/r/vaultwarden/server \
  --source-compose-file https://raw.githubusercontent.com/dani-garcia/vaultwarden/main/docker-compose.yml

# Baseline validation
bash scripts/validate-v2.sh --dir examples/joplin

# Audit a finished appstore package that intentionally omits process evidence
bash scripts/validate-v2.sh --dir examples/joplin --source-evidence-mode warn

# Strict store validation
bash scripts/validate-v2.sh --dir examples/joplin --strict-store

# Generate from spec
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json

# Normalize logo (180x180, transparent background, compress to <=10KB)
bash scripts/normalize-logo.sh examples/joplin/logo.png
```

## i18n Translation Quality Check Switch

To avoid "format compliant but translation lazy", `validate-v2.sh` adds configurable translation quality check:

- `--source-evidence-mode required|warn|off`
  - `required`: require `source-evidence.json` and validate its URLs (default, adapter delivery)
  - `warn`: warn but continue when auditing finished appstore packages that intentionally omit process evidence
  - `off`: skip source evidence checks
- `--i18n-mode off|warn|strict`
  - `off`: disable translation quality check (only structure validation)
  - `warn`: only warning (default)
  - `strict`: fail on rule hit (recommend CI use)
- `--i18n-scope description|labels|all`
  - `description`: only validate root `additionalProperties.description`
  - `labels`: only validate version `formFields[].label`
  - `all`: both (default)
- `--i18n-allow-english-labels <CSV>`
  - Short label English whitelist (e.g., `API,URL,ID,OAuth,JWT`), avoid mis-killing technical words.
- `labels` scope supplement: If `formFields[]` only has `labelEn/labelZh` and missing `label:` multi-language map, `validate-v2.sh` will now give **WARN**, and clarify version `formFields.label` expected to complete 8 languages: `en/zh/zh-Hant/ja/ko/ru/ms/pt-br`.

Default strategy:
- `description` more strict (prevent whole sentence English pseudo-translation)
- `formFields.label` hierarchical processing (short words allow whitelist)

**Placeholder translation policy**: `scaffold-v2.sh` generates 8-language `description` using the app title as placeholder. This is intentional — the scaffold provides a valid structure, and users should replace placeholders with real translations before submission. The i18n check flags these as warnings (not errors) to remind users to complete translations.

## Auto Tag Rules (`scaffold-v2.sh`)

Determination order:

1. If `--tag` passed: directly use (manual override).
2. Otherwise, by `--type` give default tag:
   - `tool` -> `Tool`
   - `website` -> `Website`
   - `middleware` -> `Middleware`
3. Then by image name/keywords refine (hit overrides default):
   - `mysql/postgres/redis/mongo/...` -> `Database`
   - `nginx/caddy/apache/openresty/...` -> `Server`
   - `ollama/open-webui/llm/...` -> `AI`
   - `prometheus/grafana/zabbix/...` -> `DevOps`
   - `vault/wazuh/fail2ban/...` -> `Security`
4. Final fallback: `Tool`.

Final tag must pass allowed set validation; not in whitelist will directly fail exit.

## Common Applications → Expected Tags (Examples)

| Application/Image Keywords | Expected Tag |
|---|---|
| mysql / mariadb / postgres / redis / mongo | `Database` |
| nginx / caddy / apache / openresty | `Server` |
| ollama / open-webui / llm / comfyui | `AI` |
| prometheus / grafana / zabbix / loki | `DevOps` |
| vault / wazuh / fail2ban / crowdsec | `Security` |
| jellyfin / plex / emby / navidrome | `Media` |
| minio / nextcloud / seafile / alist | `Storage` |
| Unmatched / generic tool applications | `Tool` |

> Note: If `--tag` passed, always use manual value, but still must pass whitelist validation.

## Output Contract

Delivery should at least clarify:
- Artifact path (usually `artifacts/1panel-apps/<app-key>`)
- Generated/migrated version directory
- Which official sources Docker installation details come from
- Remaining warnings, assumptions, manual confirmation items
- Local test landing: `/opt/1panel/resource/apps/local/<app-key>`

## Notes

- Always use `1panel` naming (don't write `onepanel`).
- Rules come from evidence packages; unverified assumptions should not be elevated to MUST.
- Submission workflow baseline reference official wiki:
  https://github.com/1Panel-dev/appstore/wiki/%E5%A6%82%E4%BD%95%E6%8F%90%E4%BA%A4%E8%87%AA%E5%B7%B1%E6%83%B3%E8%A6%81%E7%9A%84%E5%BA%94%E7%94%A8
- `data.yml` tags must come from observed store set (`1Panel-dev/appstore@dev/apps`).
  Allowed tags:
  `Tool`, `DevOps`, `AI`, `Database`, `Website`, `Middleware`, `Security`, `Runtime`, `Media`, `Storage`, `Game`, `CRM`, `Email`, `Server`, `BI`.
- `scaffold-v2.sh` supports auto-tagging (and supports `--tag` override).
- Default fallback tag is `Tool` (no longer use `Docker`).
- Default logo:
  - This skill built-in placeholder: `assets/default-logo.png` (content source: https://raw.githubusercontent.com/okxlin/appstore/localApps/apps/1panel-apps/logo.png )
  - `scaffold-v2.sh` when generating root directory, if `logo.png` not provided, will copy placeholder to `<app>/logo.png` (won't create empty file).
- **Logo normalization suggestion**: Before delivery, prioritize unifying `<app>/logo.png` to **180x180 PNG**; processing should **maintain original logo ratio, don't stretch, don't compress, don't deform**. If original exceeds `180x180`, only do **proportional shrink**; if original is smaller, don't force enlarge. Finally **center overlay logo onto `180x180` transparent canvas**. If want to balance repository size and store loading efficiency, recommend compressing to **no more than 10KB**. Can directly use: `bash scripts/normalize-logo.sh <logo.png>`.
- **Compose top-level `version` handling**: Delivered to 1Panel `docker-compose.yml` should **remove top-level `version:` field** (e.g., `version: '3.8'`), avoid deprecated/ignored warnings in 1Panel / Docker Compose logs. Adaptation should directly start from `services:` organizing compose content, unless encountering special scenarios requiring old parser.
- **Service-level `createdBy` label convention**: Delivered to 1Panel compose, **each application's each service should by default carry**:
  ```yaml
  labels:
    createdBy: "Apps"
  ```
  This is service-level default convention, not dependent on whether connected to bridge network; and should be included in validation script's **mandatory check**.
- **1Panel bridge network convention**: If application belongs to **bridge-type application** needing connection to 1Panel public entry, reverse proxy chain or other external shared networks, compose must let corresponding service connect to **at least one external network**. Example:
  ```yaml
  services:
    app:
      networks:
        - some-external-network

  networks:
    some-external-network:
      external: true
  ```
  The hard requirement here is "**bridge-type application must connect to external network**", not network name must be fixed as `1panel-network`. `1panel-network` is just default common/recommended name; if use other external network, should not be considered error. Validation script should prioritize checking "whether external network exists", not checking network name equals `1panel-network`.
- **README store-style (default suggestion)**: Root `README.md` should by default organize into 1Panel store style description, not directly retain upstream technical README. Recommend at least clarify: installation method (source build/image), access port, data persistence, key environment variables, version differences and usage suggestions. Unless user explicitly indicates not needed, should be default delivery item.

## Output shape

The scaffold command produces a directory in this shape:

```text
<app-key>/
├── data.yml
├── README.md
├── logo.png
└── <version>/
    ├── data.yml
    ├── docker-compose.yml
    ├── .env.sample
    ├── data/
    └── scripts/
        ├── init.sh
        ├── upgrade.sh
        └── uninstall.sh
```


## .env.sample Consistency Rules

**Scope**: Version-level `<app>/<version>/.env.sample`

**Core principle**: `.env.sample` must list **all** environment variables used in `docker-compose.yml`, including those not declared in `data.yml` formFields.

**Recommended values rule**: `.env.sample` should contain **working default values** where possible, so users can `docker compose up` directly after copying:
- Variables with official defaults → use the default (e.g., `TZ=Asia/Shanghai`, `AUTH_ENABLED=false`)
- Required variables without defaults → provide example values with placeholder markers (e.g., `CPA_BASE_URL=http://host.docker.internal:8317`, `CPA_MANAGEMENT_KEY=replace-with-your-management-key`)
- Optional variables without defaults → leave empty (e.g., `REDIS_QUEUE_ADDR=`)

**Variable categories**:

| Category | In `data.yml` formFields? | In `.env.sample`? | Example |
|----------|---------------------------|-------------------|---------|
| User-configurable ports | Yes | Yes | `PANEL_APP_PORT_HTTP=8080` |
| User-configurable settings | Yes | Yes | `APP_DATA_DIR=./data` |
| Panel-injected (DB/Redis) | No (auto-injected by 1Panel) | Yes | `PANEL_DB_HOST=` |
| Container name | No (auto-generated by 1Panel) | Yes | `CONTAINER_NAME=` |

**Why `CONTAINER_NAME` in .env.sample but not in formFields**:
- 1Panel automatically generates `CONTAINER_NAME` at install time (based on app key + instance ID)
- Users should not manually configure it, so it's excluded from formFields
- However, `.env.sample` must include it for completeness (compose references it via `${CONTAINER_NAME}`)

**Validation**: `validate-v2.sh` should check that all `${VAR}` references in `docker-compose.yml` have corresponding entries in `.env.sample`.

**Regression test**: `scripts/test-env-sample-closure.sh` provides a standalone closure check. Usage:
```bash
bash scripts/test-env-sample-closure.sh <v2-app-dir>
```

## Public packaging rules

- Target platform is Linux with `bash` and `python3`
- Python-based scripts require the `PyYAML` package
- Text files should use LF line endings for GitHub and Linux compatibility
- `container_name` should use `${CONTAINER_NAME}`
- `normalize-logo.sh` requires ImageMagick tools (`convert`, `identify`) and a GNU-compatible `stat`
- Public docs should distinguish hard runtime rules from repository conventions
- source evidence is mandatory and validated (`repository`, `dockerDocs`, `composeFile`)
- compose `${VAR}` usage should close against version formFields envKey declarations, except explicit implicit env key whitelist
- The skill package should not include evidence packs, replay reports, or embedded repository snapshots
