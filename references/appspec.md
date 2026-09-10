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
- `volumes` array of Compose short mount strings: `./data:/data`, `task-data:/data:ro`, or `/cache`; named and anonymous volumes remain Docker-managed
- `ports` array with `envKey`, `containerPort`, and `hostDefault`
- `formFields` array for application-specific inputs and defaults
- `composeOverride` object with `enabled: true` and a `compose` mapping to preserve an existing service graph, fixed file mounts, and environment controls
- `submissionProfile`: `third-party` (default) or `official`; `--submission-profile` overrides it
- `descriptionI18n`: translations keyed by the twelve runtime locale codes
- `readme`: `introductionZh/En`, `featuresZh/En` (string arrays), and `usageZh/En`; see `readme-style.md`
- `sourceEvidence.sourceRevision` object with optional exact `tag` and full `commit`
- `sourceEvidence.imageEvidence` legacy single-service object with optional immutable `digest` and verified `platforms`
- `sourceEvidence.images` array with one object per Compose image: exact version-directory
  `version`, `service`, resolved `reference`, matching registry `digest`, and optional verified
  `platforms`; a service with writable binds also needs `runtimeIdentity` with numeric startup and
  steady-state UID/GID, HTTPS source, and `writableBindOwner` policy as defined in source-policy.md
- `sourceEvidence.licenseEvidence` object with optional `spdx` and `url`
- `sourceEvidence.logoEvidence` object with required `source` when present and optional `license` / `sha256`
- `sourceEvidence.redistributionEvidence` object with `status`, package-relative `requiredFiles`,
  hash-bound `materials`, and an `assets` ledger containing delivered path, source, license,
  SHA-256, and asset-specific required files

The optional provenance objects and `images` array are copied into the external `.evidence/<app-key>/source-evidence.json` after validation. A selected
built-in fallback replaces only the `logo.png` ledger entry with the fallback's actual source,
license, delivered hash, and license material; application-level redistribution requirements and
materials are preserved. These objects do not replace the three mandatory source URLs.

## Mapping to Generated Artifacts

`--out-dir <parent>` is a parent directory. For `appKey: demo`, generation writes
`<parent>/demo/`; do not pass `<parent>/demo` as `--out-dir`, which would request
`<parent>/demo/demo/`.

- root metadata: `<app>/data.yml`
- app READMEs: `<app>/README.md` (Chinese), `<app>/README_en.md` (English)
- source evidence: `<parent>/.evidence/<app-key>/source-evidence.json` (not delivered)
- version metadata: `<app>/<version>/data.yml`
- compose: `<app>/<version>/docker-compose.yml`
- env sample: `<app>/<version>/.env.sample` for third-party; outside the app for official
- lifecycle scripts: `<app>/<version>/scripts/init.sh` only when path initialization is needed; add other hooks only for real lifecycle work

The requested app root must directly contain `data.yml`, both READMEs, `logo.png`,
and the selected version directory. Source evidence stays outside the app. A duplicate `<app-key>/<app-key>/` root is invalid.

## Validation Expectations

- the external `source-evidence.json` must exist and include required keys; standalone validation accepts `--source-evidence <path>`
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

The report records `submissionProfile`, `sourceEvidence`, `appDir`, `validation`, `strictValidation`, and `delivery`. A basic validation pass leaves the result at `generated_candidate` until all delivery gates are satisfied. A profile switch does not waive source, image, capability, or runtime evidence.
