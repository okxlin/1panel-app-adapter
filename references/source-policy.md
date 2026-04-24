# Source Policy

This policy defines source priority and anti-guessing rules for `1panel-app-adapter-public`.

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
