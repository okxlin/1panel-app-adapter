# 1panel-app-adapter

[![README-English](https://img.shields.io/badge/README-English-1f6feb)](./README.md) [![README-简体中文](https://img.shields.io/badge/README-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-fa8c16)](./README.zh-CN.md)

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
- `scripts/finalize_runtime_scripts.sh`
- `scripts/validate-v2.sh`

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
  [--volumes <host:container,...>] \
  [--with-panel-deps]
```

Notes:

- `--with-panel-db-redis` is an alias of `--with-panel-deps`
- generated compose uses `container_name: ${CONTAINER_NAME}`
- host-path volumes create matching `APP_DATA_DIR_*` fields in version `data.yml`
- generated compose includes a minimal HTTP healthcheck template for common web-style services
- when `--tag` is omitted, scaffold infers a more specific default tag from `--type`, title, and image
- source evidence is mandatory and is written to `<app>/source-evidence.json`
- `--timezone` controls the default `TZ` value generated in version `data.yml`

## Generate from AppSpec

```bash
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate --require-validate
python3 scripts/generate-from-appspec.py --spec assets/sample-appspec.json --validate --report artifacts/run-report.json
```

Report JSON includes `validateSummary.fail/warn/info` when validation is executed.
Report JSON also includes `qualityGate` (`not_run` / `passed` / `failed`).

References:

- `references/appspec.md`
- `assets/sample-appspec.json`

## Migrate an existing app directory

```bash
bash scripts/migrate-v1-to-v2.sh --src <app-dir> [--out <out-root>] [--version <source-ver>] [--target-version <target-ver>]
```

## Validate the result

```bash
bash scripts/validate-v2.sh --dir <app-dir>
bash scripts/validate-v2.sh --dir <app-dir> --strict-store
bash scripts/validate-v2.sh --dir <app-dir> --i18n-mode warn --i18n-scope description
bash scripts/validate-v2.sh --dir <app-dir> --i18n-mode strict --i18n-scope all
```

Validation includes:

- `source-evidence.json` existence and required keys (`repository`, `dockerDocs`, `composeFile`)
- source evidence keys must use `https://` URL shape
- compose `${VAR}` closure against version `data.yml` envKey declarations
- implicit env key exceptions from `references/implicit-envkeys.md`
- strict README structure checks from `references/readme-style.md` when `--strict-store` is used
- configurable i18n quality warnings for `additionalProperties.description` and form-field label maps

## Policy and style references

- `references/source-policy.md`
- `references/readme-style.md`
- `references/implicit-envkeys.md`

## Finalize runtime scripts

```bash
bash scripts/finalize_runtime_scripts.sh <app-dir> <version-dir>
```

Use this when you need to ensure `init.sh`, `upgrade.sh`, and `uninstall.sh` exist before the final validation step.

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
