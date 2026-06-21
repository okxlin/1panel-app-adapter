# Source Policy

This policy defines source priority and anti-guessing rules for `1panel-app-adapter`.

## Priority Order

1. Official upstream repository of the target app
2. Official upstream documentation of the target app
3. Official image registry pages and image documentation
4. Non-official blogs, examples, and forum posts (reference only)

When conflicts exist, use higher-priority sources.

## Mandatory Evidence

Every generated app must provide source evidence containing at least:

- `repository`
- `dockerDocs`
- `composeFile`

These values are written to `<app>/source-evidence.json` and validated by `scripts/validate-v2.sh`.
Each evidence value must use `https://` URL format.

## Anti-Guessing Rules

Do not guess or invent Docker deployment details when not explicitly backed by official sources.
This includes:

- image names and tags
- port mappings
- volume mappings
- environment variable names and semantics
- UID/GID and user/group assumptions
- dependency relationships (DB, Redis, sidecars, service topology)

If details are unknown, keep defaults minimal and mark follow-up work outside generated artifacts.

## Baota/aaPanel Import Evidence

Baota/aaPanel apphub metadata can be used as format evidence for the import process, but it is not by itself official upstream evidence for the target application.

For Baota imports:

- Public format source: `https://github.com/aaPanel/apphub`
- Runtime behavior source: `https://github.com/aaPanel/aaPanel`
- Imported artifacts should include `source-evidence.json.importSource` with `type: "baota"` and the selected source version.
- `home` and `help` fields from `app.json` are classified as upstream evidence only when they match a recognizable official project or documentation source.
- When `home` is empty but the input app lives in a git checkout, `repository` may fall back to that apphub repository URL as the app definition source. Keep `evidenceStatus` as `third_party_only` unless the target application's own official source is identified.
- If only Baota/aaPanel metadata is available, keep `evidenceStatus` as `third_party_only` and require manual review before strict-store delivery.

During verification on 2026-06-22, `btpanel/apphub` was not publicly accessible, while `aaPanel/apphub` was publicly accessible and contained real `alist` and `deeplx` app definitions plus the app template.
