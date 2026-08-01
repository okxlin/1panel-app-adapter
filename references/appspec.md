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
- `sourceEvidence.imageEvidence` legacy single-service object with optional immutable `digest` and verified `platforms`
- `sourceEvidence.images` array with one object per Compose image: exact version-directory
  `version`, `service`, resolved `reference`, matching registry `digest`, and optional verified
  `platforms`
- `sourceEvidence.licenseEvidence` object with optional `spdx` and `url`
- `sourceEvidence.logoEvidence` object with required `source` when present and optional `license` / `sha256`
- `sourceEvidence.redistributionEvidence` object with `status`, package-relative `requiredFiles`,
  hash-bound `materials`, and an `assets` ledger containing delivered path, source, license,
  SHA-256, and asset-specific required files

The optional provenance objects and `images` array are copied into `source-evidence.json` after validation. A selected
built-in fallback replaces only the `logo.png` ledger entry with the fallback's actual source,
license, delivered hash, and license material; application-level redistribution requirements and
materials are preserved. These objects do not replace the three mandatory source URLs.

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
The standalone delivery command must pass `--source-evidence-mode required
--require-delivery-evidence`; this requires application-license evidence and verifies every
redistribution asset and required material against the delivered artifact. Strict-store plus
required source evidence implies the delivery flag for compatibility, but callers should keep the
explicit flag so the intended gate remains visible.

When validation is enabled, report JSON also includes:

- `validatedAt`
- `validateSummary.fail`
- `validateSummary.warn`
- `validateSummary.info`

And report always includes:

- `qualityGate` (`not_run`, `passed`, `failed`)
