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

## Optional Evidence

The three mandatory URL fields above remain the backward-compatible minimum. Add these objects
only when their values were verified from official source, registry, license, or asset evidence:

```json
{
  "sourceRevision": {
    "tag": "v1.2.3",
    "commit": "0123456789abcdef0123456789abcdef01234567"
  },
  "imageEvidence": {
    "digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "platforms": ["linux/amd64", "linux/arm64"]
  },
  "licenseEvidence": {
    "spdx": "MIT",
    "url": "https://example.com/project/LICENSE"
  },
  "logoEvidence": {
    "source": "https://example.com/project/logo.png",
    "license": "MIT",
    "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }
}
```

- `sourceRevision.tag` is the exact release tag; `sourceRevision.commit` is the full 40- or
  64-hex commit identifier resolved for that tag.
- `imageEvidence.digest` is an immutable `sha256:` image digest. `imageEvidence.platforms`
  records verified OCI platform strings and must not be inferred from the host running the test.
- `licenseEvidence.spdx` records an SPDX expression when known; `licenseEvidence.url` links the
  exact upstream license evidence.
- `logoEvidence.source` is an HTTPS source URL or `bundled:<repo-relative-path>` for a repository
  asset. Record its license when known and the delivered PNG SHA-256 when calculated.

Omit unknown optional keys instead of writing placeholders such as `unknown`, `latest`, or a
floating image tag.

## Public URL Inputs

Treat callback, origin, external base, and other browser-facing public URLs as deployment inputs.
Never synthesize `localhost` or `127.0.0.1` for these fields: those values point back to the
client or container and usually break redirects, webhooks, CORS, or generated links. Expose an
upstream-required public URL as a required 1Panel form field. Leave an optional public URL empty
or omit it, and document which feature stays unavailable until the operator supplies one.

## Anti-Guessing Rules

Do not guess or invent Docker deployment details when not explicitly backed by official sources.
This includes:

- image names and tags
- port mappings
- volume mappings
- environment variable names and semantics
- UID/GID and user/group assumptions
- dependency relationships (DB, Redis, sidecars, service topology)

Before accepting an upstream compose topology with a bundled database or cache, search the target 1Panel appstore and current panel store for a compatible reusable runtime. If the application supports external dependencies and the runtime is selectable, prefer the panel-managed service path. Record why a bundled sidecar remains only when no compatible/selectable runtime exists or upstream requires that topology.

When an app is supposed to reuse a 1Panel-managed database service, do not stop at compose syntax or app install success. Verify with real panel evidence that the chosen dependency is actually exposed through `/apps/services/<db-key>` and the corresponding `databases` resource records. A local runtime app package may install cleanly yet still fail to register as a reusable database service for other apps.

If details are unknown, keep defaults minimal and mark follow-up work outside generated artifacts.

## Registry Access Verification

Do not classify a public image as private from one `docker pull ... denied` result. A stale registry credential in the active Docker client config can override anonymous token negotiation even when the registry manifest is public.

For GHCR and similar token registries:

1. Request an anonymous pull token for the exact repository scope.
2. Request the target manifest with that bearer token and an OCI/Docker manifest `Accept` header.
3. Repeat the pull with a temporary empty `DOCKER_CONFIG` so existing user credentials remain untouched.
4. Verify every packaged tag and architecture; a readable `latest` manifest does not prove a numbered tag exists.

Keep registry HTTP evidence separate from local image-cache evidence. A cached image can make a deployment test pass even when a fresh user cannot pull it.

## Baota/aaPanel Import Evidence

Baota/aaPanel apphub metadata can be used as format evidence for the import process, but it is not by itself official upstream evidence for the target application.

For Baota imports:

- Public format source: `https://github.com/aaPanel/apphub`
- Runtime behavior source: `https://github.com/aaPanel/aaPanel`
- Imported artifacts should include `source-evidence.json.importSource` with `type: "baota"` and the selected source version.
- Preserve `home` and `help` from `app.json` only as unverified declared hints. A recognizable domain, HTTPS URL, or GitHub repository shape is not identity evidence. Promote either value into official source evidence only after independently matching project ownership and the packaged deployment contract.
- When `home` is empty but the input app lives in a git checkout, `repository` may fall back to that apphub repository URL as the app definition source. Keep `evidenceStatus` as `third_party_only` unless the target application's own official source is identified.
- If only Baota/aaPanel metadata is available, keep `evidenceStatus` as `third_party_only` and require manual review before strict-store delivery.

During verification on 2026-06-22, `btpanel/apphub` was not publicly accessible, while `aaPanel/apphub` was publicly accessible and contained real `alist` and `deeplx` app definitions plus the app template.
