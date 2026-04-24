---
name: 1panel-app-adapter-public
description: Rule-first public skill for generating, migrating, and validating 1Panel app artifacts in Linux and GitHub workflows.
---

# 1panel-app-adapter-public

This skill is the public, cleaned-up variant of the local research skill. It is designed to generate and validate 1Panel app artifacts with increasingly complete defaults, without bundling evidence packs, replay logs, or third-party repository snapshots.

## Rule Priority

Judge every rule in this order:

1. Runtime and source-code hard rules from `1Panel-dev/1Panel`
2. Official 1Panel wiki and official docs
3. Official appstore repository conventions
4. External references and practical articles

Only rules backed by runtime behavior or explicit official documentation should block generation or validation. Repository conventions are guidance unless validator mode explicitly upgrades them.

## What this skill does

- Scaffold a v2-style 1Panel app directory with richer default fields
- Migrate an existing app directory into the v2 layout with basic quality backfill
- Patch root metadata, version metadata, and compose content
- Generate `.env.sample`
- Validate the resulting app directory

## Supported commands

- `bash scripts/scaffold-v2.sh --help`
- `python3 scripts/generate-from-appspec.py --help`
- `python3 scripts/generate-from-appspec.py --spec <spec.json> --validate`
- `python3 scripts/generate-from-appspec.py --spec <spec.json> --validate --require-validate`
- `bash scripts/migrate-v1-to-v2.sh --help`
- `bash scripts/finalize_runtime_scripts.sh --help`
- `bash scripts/validate-v2.sh --help`

## Recommended execution flow

Use this skill in one of two paths.

### Path A: generate a new 1Panel app

1. Run `bash scripts/scaffold-v2.sh ...` to create the v2 app skeleton.
   - include `--source-repository --source-docker-docs --source-compose-file` as required source evidence inputs.
2. Review the generated `data.yml`, version `data.yml`, and `docker-compose.yml` (including default tag, TZ, healthcheck, and dependency/env fields when applicable).
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

The intended finish line for this skill is: generated or migrated output exists, root/version/compose structure is normalized, and `validate-v2.sh --strict-store` has been executed with its result recorded for follow-up decisions.

## Supported scaffold arguments

- Required: `--app-key --title --image --version --source-repository --source-docker-docs --source-compose-file`
- Optional: `--out-dir --port --target-port --type --tag --volumes --timezone --with-panel-deps --with-panel-db-redis`

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

## Public packaging rules

- Target platform is Linux with `bash` and `python3`
- Python-based scripts require the `PyYAML` package
- Text files should use LF line endings for GitHub and Linux compatibility
- `container_name` should use `${CONTAINER_NAME}`
- `normalize-logo.sh` requires ImageMagick tools (`convert`, `identify`) and a GNU-compatible `stat`
- Public docs should distinguish hard runtime rules from repository conventions
- source evidence is mandatory and validated (`repository`, `dockerDocs`, `composeFile`)
- compose `${VAR}` usage should close against version formFields envKey declarations, except explicit implicit env key whitelist
- The public skill package should not include evidence packs, replay reports, or embedded repository snapshots
