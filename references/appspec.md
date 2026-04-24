# AppSpec (Minimal)

This document defines the minimal intermediate specification for standardized generation in the public skill.

## Goal

Provide a stable `spec -> artifacts` path with explicit source evidence and reproducible defaults.

## Required Fields

- `appKey` string
- `title` string
- `version` string
- `image` string
- `port` number (host side)
- `targetPort` number (container side)
- `type` string (for 1Panel app type)
- `sourceEvidence` object
  - `repository` string
  - `dockerDocs` string
  - `composeFile` string

## Optional Fields

- `tag` string
- `withPanelDeps` boolean
- `volumes` array of `host:container` strings
- `timezone` string (defaults to `Asia/Shanghai`, wired to `TZ` default in generated version `data.yml`)
- `outputDir` string

## Mapping to Generated Artifacts

- root metadata: `<app>/data.yml`
- app readme: `<app>/README.md`
- source evidence: `<app>/source-evidence.json`
- version metadata: `<app>/<version>/data.yml`
- compose: `<app>/<version>/docker-compose.yml`
- env sample: `<app>/<version>/.env.sample`
- lifecycle scripts: `<app>/<version>/scripts/*.sh`

## Validation Expectations

- `source-evidence.json` must exist and include required keys
- compose `${VAR}` references should resolve to env keys declared in version `data.yml`, except allowed implicit keys in `references/implicit-envkeys.md`

## One-command Execution

You can run generation and strict validation together:

- `python3 scripts/generate-from-appspec.py --spec <path-to-spec.json> --validate`
- `python3 scripts/generate-from-appspec.py --spec <path-to-spec.json> --validate --require-validate`

You can also emit an audit-friendly report JSON:

- `python3 scripts/generate-from-appspec.py --spec <path-to-spec.json> --validate --report <report-path.json>`

When `--validate` is enabled, report JSON also includes:

- `validatedAt`
- `validateSummary.fail`
- `validateSummary.warn`
- `validateSummary.info`

And report always includes:

- `qualityGate` (`not_run`, `passed`, `failed`)
