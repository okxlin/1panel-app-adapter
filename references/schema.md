# 1Panel AppStore v2 (apps/) Field Fact Table (dev branch evidence summary)

> This file is used for "field-level alignment" in `scripts/validate-v2.sh`.
> Conclusions come from sample observation of **1Panel-dev/appstore** (dev branch) `apps/` directory (field hierarchy and high-frequency fields).

## Language Codes (locales)

The current panel supports 12 application locale keys: `en`, `zh`, `zh-hant`, `ja`, `ko`, `ru`, `ms`, `pt-br`, `tr`, `es-es`, `fa`, and `lo`. This skill targets all twelve for new delivery artifacts. The panel's UI language names include `zh-Hant`, `pt-BR`, and `es-ES`, while the application DTO and lookup use lowercase keys. Accept those historical case aliases as input; write canonical lowercase keys. Conflicting values for two aliases are invalid.

`--i18n-mode strict` requires non-empty entries for all twelve locales, including nested labelled fields and help descriptions, and rejects recognized placeholder markers and English copies. Translation accuracy still needs review against the application's meaning. Plain inspection retains the historical eight-locale structural baseline and warns about missing newer translations. Identical Chinese words in simplified and traditional Chinese are not inherently invalid. See [1panel-sources.md](1panel-sources.md) for exact source pins.

For network port labels (`PANEL_APP_PORT*` or `rule: paramPort`), Malay `Port` is a valid shared technical term; `Pelabuhan` means a harbour and is rejected. Only this locale and single-word label get the contextual English-copy exception. Normalization corrects the known mistranslation in these fields and preserves other uses of the word.

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
- `title` may use the product name. Strict-store validation requires top-level `description` and `shortDescZh/shortDescEn` to contain descriptive text, rather than just the app name/key or a placeholder. Normalization repairs invalid summaries only when a supplied Chinese/English description provides real text; it preserves valid summaries and does not invent translations.
- The summary lint compares declared `name`/`key` values and known placeholder markers, including a display title copied unchanged into both Chinese and English summaries. Titles may themselves describe the application, so matching a title alone is allowed. Other undeclared product aliases and semantic quality still need review.

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
- `disabled` (bool: locks the install control)
- `edit` (bool: later editability; independent of `disabled`)

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

Official profile keeps source-backed directory defaults fixed. When a path field already exists, use `disabled: true` and `edit: false`; fixed binds and named volumes need no added path field. These are submission-profile choices, not requirements for all 1Panel applications.
