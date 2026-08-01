# AppSpec (Minimal)

This document defines the minimal intermediate specification for standardized generation in the skill.

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
- `sourceEvidence.sourceRevision` object with optional exact `tag` and full `commit`
- `sourceEvidence.imageEvidence` object with optional immutable `digest` and verified `platforms`
- `sourceEvidence.licenseEvidence` object with optional `spdx` and `url`
- `sourceEvidence.logoEvidence` object with required `source` when present and optional `license` / `sha256`

The optional provenance objects are copied unchanged into `source-evidence.json` after validation.
They do not replace the three mandatory source URLs and may be omitted for older AppSpec inputs.

## Mapping to Generated Artifacts

`--out-dir <parent>` is a parent directory. For `appKey: demo`, generation writes
`<parent>/demo/`; do not pass `<parent>/demo` as `--out-dir`, which would request
`<parent>/demo/demo/`.

- root metadata: `<app>/data.yml`
- app readme: `<app>/README.md`
- source evidence: `<app>/source-evidence.json`
- version metadata: `<app>/<version>/data.yml`
- compose: `<app>/<version>/docker-compose.yml`
- env sample: `<app>/<version>/.env.sample`
- lifecycle scripts: `<app>/<version>/scripts/*.sh`

The requested app root must directly contain `data.yml`, `source-evidence.json`,
and the selected version directory. A duplicate `<app-key>/<app-key>/` root is invalid.

## Validation Expectations

- `source-evidence.json` must exist and include required keys
- compose `${VAR}` references should resolve to env keys declared in version `data.yml`, except allowed implicit keys in `references/implicit-envkeys.md`

## One-command Execution

You can run generation with either baseline or strict-store validation:

- `python3 scripts/generate-from-appspec.py --spec <path-to-spec.json> --validate`
- `python3 scripts/generate-from-appspec.py --spec <path-to-spec.json> --strict-store-validate`
- `python3 scripts/generate-from-appspec.py --spec <path-to-spec.json> --validate --require-validate`
- `python3 scripts/generate-from-appspec.py --spec <path-to-spec.json> --strict-store-validate --require-validate`

You can also emit an audit-friendly report JSON:

- `python3 scripts/generate-from-appspec.py --spec <path-to-spec.json> --validate --report <report-path.json>`

`--validate` runs baseline validation suitable for raw generated output.
`--strict-store-validate` runs `validate-v2.sh --strict-store` and should be used only after README / metadata placeholders are replaced.

When validation is enabled, report JSON also includes:

- `validatedAt`
- `validateSummary.fail`
- `validateSummary.warn`
- `validateSummary.info`

And report always includes:

- `qualityGate` (`not_run`, `passed`, `failed`)
