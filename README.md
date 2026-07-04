# 1panel-app-adapter

[![README-English](https://img.shields.io/badge/README-English-1f6feb)](./README.md) [![README-简体中文](https://img.shields.io/badge/README-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-fa8c16)](./README.zh-CN.md)

See also: [`DELIVERY_REPORT.md`](./DELIVERY_REPORT.md) for maintainer-facing rule and regression notes.

`1panel-app-adapter` is a cleaned skill for turning Docker application inputs into 1Panel app artifacts. It keeps the operational scripts needed by the workflow, but removes research-only material such as evidence packs, replay logs, and embedded repository snapshots.

## Rule priority

When rules conflict, use this order:

1. `1Panel-dev/1Panel` runtime and source-code behavior
2. Official 1Panel wiki and official docs
3. Official appstore repository conventions
4. External articles and third-party examples

This means the skill is rule-first, not example-first. Repository habits are useful, but they are not treated as runtime truth unless the validator explicitly enforces them.

## Included scripts

- `scripts/scaffold-v2.sh`
- `scripts/migrate-v1-to-v2.sh`
- `scripts/normalize-logo.sh`
- `scripts/detect_architectures.sh`
- `scripts/patch_root_data_yml.py`
- `scripts/patch_version_data_yml.py`
- `scripts/patch_compose_yml.py`
- `scripts/hint-panel-deps.sh`
- `scripts/gen-env-sample.sh`
- `scripts/gen_env_sample.py`
- `scripts/generate-from-appspec.py`
- `scripts/import-baota-app.py` — import Baota/aaPanel Docker Store apps
- `scripts/finalize_runtime_scripts.sh`
- `scripts/validate-v2.sh`
- `scripts/generate.sh` — v2 generator wrapper (compat CLI)
- `scripts/validate.sh` — v2 validation wrapper
- `scripts/cleanup-migrate-backups.sh` — cleanup old migrate backups
- `scripts/test-env-sample-closure.sh` — regression test: .env.sample closure check

## Generate a new app skeleton

```bash
bash scripts/scaffold-v2.sh \
  --app-key <key> \
  --title <title> \
  --image <image> \
  --version <version> \
  --source-repository <url> \
  --source-docker-docs <url> \
  --source-compose-file <url> \
  [--timezone <tz>] \
  [--out-dir <dir>] \
  [--port <host-port>] \
  [--target-port <container-port>] \
  [--type <type>] \
  [--tag <tag>] \
  [--website <url>] \
  [--document <url>] \
  [--github <url>] \
  [--volumes <host:container,...>] \
  [--with-panel-deps] \
  [--force]
```

Notes:

- `--with-panel-db-redis` is an alias of `--with-panel-deps`
- generated compose uses `container_name: ${CONTAINER_NAME}`
- host-path volumes create matching `APP_DATA_DIR_*` fields in version `data.yml`
- generated compose preserves explicit upstream healthchecks, but does not add a default probe automatically
- when `--tag` is omitted, scaffold infers a more specific default tag from `--type`, title, and image
- source evidence is optional provenance material; generators may write `<app>/source-evidence.json`, but finished appstore packages do not need to keep it
- `--timezone` controls the default `TZ` value generated in version `data.yml`
- scaffold refuses to write into a non-empty target app directory unless `--force` is passed
- raw scaffold output is a starting point, not a delivery-ready strict-store artifact
- `--force` allows writing into an existing non-empty app directory but does not clean residual files for you

## Fast path from scaffold to strict-store

```bash
# 1) Generate the skeleton
bash scripts/scaffold-v2.sh   --app-key demo   --title "Demo"   --image nginx:latest   --version 1.0.0   --source-repository <repo-url>   --source-docker-docs <docs-url>   --source-compose-file <compose-url>

# 2) Replace scaffold placeholders in:
#    - README.md
#    - root data.yml description / shortDesc / i18n text

# 3) Check compose variables and .env.sample if you changed envKey / compose content

# 4) Run strict-store validation on the delivery-ready artifact
bash scripts/validate-v2.sh --dir ./1panel-apps/demo --strict-store
```

## Generate from AppSpec

```bash
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --strict-store-validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate --require-validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --strict-store-validate --require-validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate --report artifacts/run-report.json
```

Report JSON includes `validateSummary.fail/warn/info` when validation is executed. `--validate` runs baseline validation; `--strict-store-validate` is reserved for delivery-ready content after placeholders are replaced.
Report JSON also includes `qualityGate` (`not_run` / `passed` / `failed`).

References:

- `references/appspec.md`
- `assets/sample-appspec.json`

## Import Baota/aaPanel Docker Store apps

```bash
# Single app directory containing app.json/icon.png/<version>/docker-compose.yml
python3 scripts/import-baota-app.py \
  --input <baota-app-dir> \
  --out-dir ./1panel-apps \
  --version latest \
  --validate \
  --require-validate

# Batch import an apphub directory whose direct children are app directories
python3 scripts/import-baota-app.py \
  --input <apphub-dir> \
  --batch \
  --out-dir ./1panel-apps \
  --validate \
  --report artifacts/baota-import-report.json

# Emit normalized AppSpec only, then generate through the AppSpec path
python3 scripts/import-baota-app.py \
  --input <baota-app-dir> \
  --version latest \
  --emit-appspec artifacts/app.appspec.json
```

The importer is based on the public `aaPanel/apphub` format and aaPanel Docker app runtime behavior. It converts `${HOST_IP}:${APP_PORT}:<container>` ports to `PANEL_APP_PORT_*`, rewrites `${APP_PATH}` bind mounts to configurable `APP_DATA_DIR*` fields, replaces `baota_net` with `1panel-network`, rewrites `createdBy: bt_apps` to `Apps`, removes Baota CPU/memory deploy limits, and records migration notes in `source-evidence.json`.

References:

- `references/baota-app-format.md`
- `references/baota-to-1panel-mapping.md`

## Migrate an existing app directory

```bash
bash scripts/migrate-v1-to-v2.sh --src <app-dir> [--out <out-root>] [--version <source-ver>] [--target-version <target-ver>]
```

## Validate the result

```bash
bash scripts/validate-v2.sh --dir <app-dir>
bash scripts/validate-v2.sh --dir <app-dir> --strict-store
bash scripts/validate-v2.sh --dir <app-dir> --strict-c
bash scripts/validate-v2.sh --dir <app-dir> --source-evidence-mode required
bash scripts/validate-v2.sh --dir <app-dir> --i18n-mode warn --i18n-scope description
bash scripts/validate-v2.sh --dir <app-dir> --i18n-mode strict --i18n-scope all
```

Validation includes:

- optional `source-evidence.json` provenance checks (`repository`, `dockerDocs`, `composeFile`) when the file is present
- `--source-evidence-mode warn|required|off`; default is `warn`, use `required` only for workflows that explicitly gate on provenance evidence
- source evidence keys must use `https://` URL shape when checked
- compose `${VAR}` closure against version `data.yml` envKey declarations
- duplicate YAML key detection for root/version/compose files
- `docker compose config` validation using `.env.sample` with a safe fallback `CONTAINER_NAME`
- `.env.sample` is treated as a standalone compose reference file; 1Panel runtime values should come from form fields, panel injection, compose defaults, or lifecycle logic instead of relying on `env_file: ./.env.sample`
- when a package also ships a runtime defaults env file such as `dify.env`, keep it documented as a pre-`./.env` defaults layer and avoid embedding user-specific secret samples unless later env layers or explicit compose env mappings override them
- full compose-render validation expects an available `docker compose` CLI in the execution environment
- strict-store placeholder/template residue detection for README and metadata
- implicit env key exceptions from `references/implicit-envkeys.md`
- strict README structure checks from `references/readme-style.md` when `--strict-store` is used
- configurable i18n quality warnings for `additionalProperties.description` and form-field label maps
- label-map completeness hints, including missing locales and legacy `zh-hant` naming
- compose bridge-network checks for service-level `networks:` usage and `1panel-network` recommendations
- multi-service shared-network DNS collision warnings for generic internal service hostnames such as `redis` or `mongo`
- healthchecks are treated as optional runtime enhancements, not delivery gates

## Policy and style references

- `references/source-policy.md`
- `references/readme-style.md`
- `references/implicit-envkeys.md`
- `references/edit-exempt-envkeys.md` — edit:true exception allowlist
- `references/schema.md` — 1Panel AppStore v2 field fact table

## Finalize runtime scripts

```bash
bash scripts/finalize_runtime_scripts.sh <app-dir> <version-dir>
```

Use this when you need to ensure `init.sh`, `upgrade.sh`, and `uninstall.sh` exist before the final validation step.

## Runtime startup lessons

- If a compose wrapper starts as `root` and then drops privileges with `setpriv`, `gosu`, or `su-exec`, set `HOME`, `USER`, and `LOGNAME` for the target user before `exec`; otherwise runtimes such as `pnpm` may still try to write under `/root`.
- For official PostgreSQL 18+ images, prefer mounting persistent data at `/var/lib/postgresql`, not `/var/lib/postgresql/data`, unless a tested custom `PGDATA` path is intentional.
- If generated config needs 1Panel random password fields, generate it inside the app container at startup instead of relying on `scripts/init.sh` to receive every secret.
- For multi-service apps whose main service joins both `1panel-network` and an internal network, use app-prefixed internal service hostnames (`<app>-redis`, `<app>-mongo`, etc.) or explicit internal aliases instead of generic names. Shared Docker DNS can otherwise resolve another app's `redis`, `mongo`, or `db` service.
- Avoid one-shot init sidecars for required startup work in 1Panel apps. 1Panel deployment may rewrite restart policy behavior, making `service_completed_successfully` fragile; prefer idempotent startup or healthcheck initialization.

## Packaging and platform expectations

- intended for GitHub-hosted repositories and Linux execution environments
- text files should use LF line endings
- shell scripts target `bash`
- helper scripts target `python3` with the `PyYAML` package available
- `scripts/normalize-logo.sh` additionally requires ImageMagick tools such as `convert` and `identify`, plus a GNU-compatible `stat`
- public package contents should stay limited to docs, references, assets, and operational scripts

## Implementation plan and scope

This public package follows a staged scope on purpose:

1. define rule priority from authoritative sources first
2. expose a clean skill directory without research artifacts
3. provide scaffold, migrate, patch, env-sample, runtime-script-finalize, and validate scripts
4. align the OpenClaw workflow to the skill path and actual script surface
5. keep improving direct generation quality so scaffold/migrate outputs need less manual backfill and move closer to one-click delivery quality

The workflow description should match what the scripts actually do. As the skill gains richer default generation quality, the workflow and docs should be updated to reflect that richer baseline without overstating unsupported intelligence.
