# DELIVERY_REPORT

## Scope

This repository provides a public 1Panel app adapter toolkit focused on:

- v2 app skeleton generation
- strict-store style validation
- source-evidence-aware packaging
- compose ↔ formFields env closure checks
- basic migration / normalization helpers

This repository does **not** currently include the full internal evidence-pack used by the private skill system.

---

## Rule Baseline

Current rule set is primarily aligned against:

1. 1Panel official appstore `apps/` structure and common field patterns
2. public app-adapter behavior expected by this repository
3. internal skill parity goals for critical generation / validation behavior

Key structural expectations include:

- root `data.yml` uses:
  - `name`
  - `tags`
  - `title`
  - `description`
  - `additionalProperties`
- version `data.yml` uses:
  - top-level `additionalProperties`
  - `additionalProperties.formFields`
- compose variables should be declared in version `data.yml` or allowed implicit env keys
- `.env.sample` should cover compose variables used by generated artifacts

---

## Key Decisions

### 1. Source evidence is required
Public generation requires source references:

- `--source-repository`
- `--source-docker-docs`
- `--source-compose-file`

Reason:
- improves traceability
- reduces undocumented speculative packaging
- makes generated artifacts easier to audit later

### 2. `.env.sample` must close over compose variables
Generated `.env.sample` is treated as a regression-sensitive artifact.

Reason:
- prevents missing runtime variables
- catches drift between `formFields`, compose, and helper scripts
- improves install/debug experience

### 3. DB / Redis injection follows current public/internal parity target
Current generated dependency env keys aim to stay aligned with the actively maintained adapter rules, especially around:

- `PANEL_DB_*`
- `REDIS_HOST`
- `REDIS_PORT`
- `PANEL_REDIS_ROOT_PASSWORD`
- `REDIS_DB`

### 4. Default validation keeps i18n checks enabled
Validator default keeps:

- `I18N_MODE=warn`
- `I18N_SCOPE=all`

Reason:
- structure-only pass is not enough for store-quality output
- label / description quality drift should remain visible by default

### 5. Named volumes are preserved explicitly
When named volumes are detected, generated compose output should preserve them and declare top-level `volumes:` entries.

Reason:
- clearer semantics
- more stable compose behavior
- closer to intended upstream storage model

---

## Regression Coverage

The following flows are expected to work and should be rechecked after behavior changes:

### A. scaffold-v2
Generate a v2 app package with:

- metadata
- version data.yml
- docker-compose.yml
- lifecycle scripts
- `.env.sample`

### B. validate-v2 --strict-store
Validate generated output against the repository's strict-store rules.

### C. generate-from-appspec.py
Generate an app package from minimal JSON app spec and optionally run validation.

### D. env sample closure
Ensure compose variables are covered by `.env.sample`.

Regression helper:
- `scripts/test-env-sample-closure.sh`

---

## Known Gaps

Current known limitations:

1. default i18n content may still be placeholder-quality
   - structure passes
   - translation quality may still emit warnings

2. this public repository does not ship the full internal evidence-pack
   - rule traceability is summarized here
   - raw internal sampling / replay material is not fully published

3. some public-repo constraints are product decisions
   - especially source-evidence requirements
   - these are intentional and may be stricter than older internal snapshots in some areas

---

## Compatibility Notes

Current public adapter aims for strong parity with internal critical behavior in:

- generation flow
- validation flow
- env closure
- panel dependency field modeling
- named volume preservation

Parity does **not** mean byte-for-byte identity with the internal private skill repository.

Differences may remain in:

- evidence assets
- workspace-specific output defaults
- internal-only delivery / audit materials

---

## Change Log Summary

### Recent stabilizations
- fixed `.env.sample` closure regressions
- aligned Redis-related env keys with current expected behavior
- restored validator default i18n scope to `all`
- added named volume top-level declaration support
- added regression helper for env sample closure

---

## Maintainer Notes

When changing rules, update at least these together:

- `scripts/scaffold-v2.sh`
- `scripts/validate-v2.sh`
- `scripts/gen_env_sample.py`
- `scripts/generate-from-appspec.py`
- this `DELIVERY_REPORT.md`

When behavior changes affect generated artifacts, also rerun:

- scaffold generation
- strict-store validation
- appspec generation
- env sample closure regression

---

## Current Quality Gate

A change is considered healthy when:

- generation succeeds
- strict-store validation passes
- `.env.sample` covers compose vars
- no critical drift is introduced in DB / Redis / port / volume modeling

Warnings related to placeholder translations may remain acceptable until real localized content generation is introduced.

### Latest hardening
- strict-store now fails on duplicate YAML keys in root/version/compose artifacts
- strict-store now fails on placeholder/template residue in README and metadata
- validator now runs `docker compose config` using `.env.sample` with a safe `CONTAINER_NAME` fallback
- scaffold now refuses to write into non-empty target app directories unless `--force` is explicitly passed

---

## Latest Audit Results

All three generation chains achieved 0 warn:

| Chain | fail | warn | info | Status |
|-------|------|------|------|--------|
| scaffold-v2 | 0 | 0 | 5 | PASS |
| generate-from-appspec.py | 0 | 0 | 5 | PASS |
| migrate-v1-to-v2 | 0 | 0 | 5 | PASS |

Key fixes in this round:

- i18n placeholder strategy: language-specific suffixes (佔位、プレースホルダー、플레이스홀더、заполнитель)
- migrate root description: applies same placeholder strategy as scaffold
- migrate healthcheck: auto-added for website/tool types with HTTP ports
- label map auto-fill: when formFields has labelEn/labelZh but no label map
- .env.sample closure: compose-aware filtering
- validator envKey regex: supports YAML list items
