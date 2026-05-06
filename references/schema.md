# 1Panel AppStore v2 (apps/) Field Fact Table (dev branch evidence summary)

> This file is used for "field-level alignment" in `scripts/validate-v2.sh`.
> Conclusions come from sample observation of **1Panel-dev/appstore** (dev branch) `apps/` directory (field hierarchy and high-frequency fields).

## Language Codes (locales)

There are two "evidence sources" that need to be compatible:
- **AppStore repo data (1Panel-dev/appstore dev/apps)**: Common `zh-Hant` (H uppercase).
- **1Panel runtime DTO (1Panel-dev/1Panel dev-v2's `agent/app/dto/app.go`)**: Locale field defined as `zh-hant`, and also includes extended language fields like `tr`, `es-es`.

Validation strategy: Accept both; but from "skill artifacts aligned with official repo" perspective, recommend eventually unifying to `zh-Hant`. `zh-hant` only as compatible input. For extended languages like `tr`, `es-es`: **allow existence, not mandatory**.

## Hierarchy Constraints: Application-level vs Version-level

### 1) Application-level: `apps/<app>/data.yml`

**Top-level (root level) allowed fields**:
- `name`
- `tags`
- `title`
- `description`
- `additionalProperties`

Notes:
- Top-level `type` appears in some historical patterns but is not part of official regular schema; recommend not placing at top level (this skill only WARNs).

**`additionalProperties` (application-level) high-frequency/key fields**:
- Strict submission (`--strict-store`) requires (missing = FAIL):
  - `key`
  - `name`
  - `tags`
  - `type`
  - `website`
  - `document`
  - `architectures` (100% present in official samples)
  - `github`
  - `shortDescZh`
  - `shortDescEn`
  - `crossVersionUpdate`
  - `limit`
- High occurrence but can maintain WARN per policy:
  - `recommend`
  - `description`
  - `memoryRequired`

**Special notes**:
- `architectures` needs to be placed in `additionalProperties.architectures`, not at top level.

### 2) Version-level: `apps/<app>/<ver|latest|stable>/data.yml`

**Top-level allowed fields**:
- `additionalProperties`
  - Can be `null` or `object` (official samples show both; strict-store recommends object with required fields filled)

**Prohibited misuse**:
- Top-level `formFields` (should be placed in `additionalProperties.formFields`).

## `formFields` Structure Facts (version-level)

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

### ports / volumes facts supplement
- ports: Official most common field is `PANEL_APP_PORT_HTTP`, typically `type: number` + `rule: paramPort`, compose writes as `"${PANEL_APP_PORT_HTTP}:<container_port>"`.
- volumes: Official compose extensively uses bind mount (`./data:/...`, `./conf/x:/...`), but version-level `data.yml` typically doesn't parameterize paths via `APP_DATA_DIR_*` (prefers fixed relative paths).
