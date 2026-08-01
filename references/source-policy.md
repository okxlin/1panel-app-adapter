# Source Policy

This policy defines source priority and anti-guessing rules for `1panel-app-adapter`.

## Priority Order

1. Official upstream repository of the target app
2. Official upstream documentation of the target app
3. Official image registry pages and image documentation
4. Non-official blogs, examples, and forum posts (reference only)

When conflicts exist, use higher-priority sources.

## Historical Official Source Fallback

A single 404 or moved page is not a terminal condition. Treat it as one failed lookup, not as
proof that the exact-version Docker contract is unavailable. Before assigning a terminal route,
use this bounded fallback sequence:

1. Inspect the exact release tag or source tree for Compose files, Dockerfiles, deployment
   examples, install scripts, and filenames containing `compose`, `docker`, `deploy`, or `install`.
2. Inspect versioned branches, release assets, and the relevant path history in the same official
   repository. Do not silently substitute current default-branch behavior for the target version.
3. Search official documentation repositories and other repositories owned by the same upstream
   organization. Pin any historical Compose or deployment evidence to an exact commit and verify
   that it covers the target release family.
4. Inspect official image documentation, OCI metadata, entrypoints, and startup source for the
   remaining image/runtime facts. Registry evidence can corroborate a deployment contract but
   cannot invent a missing service graph.

Record every attempted official source with its URL or repository/ref/path, result, and reason for
accepting or rejecting it. Continue source discovery while another official exact-version or
version-compatible source path remains unchecked. A terminal stop is justified only after this
fallback is exhausted and the remaining gap is a concrete unsafe unknown, such as an unproven
service, image, variable, mount, network, runtime identity, migration, persistence, or upgrade
contract that would otherwise have to be guessed. Name that unknown and the unsafe decision it
blocks. An unavailable page by itself is only a temporary lookup failure.

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
  "images": [{
    "version": "1.2.3",
    "service": "app",
    "reference": "example/app@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "digest": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "platforms": ["linux/amd64", "linux/arm64"]
  }],
  "licenseEvidence": {
    "spdx": "MIT",
    "url": "https://example.com/project/LICENSE"
  },
  "logoEvidence": {
    "source": "https://example.com/project/logo.png",
    "license": "MIT",
    "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  },
  "redistributionEvidence": {
    "status": "verified",
    "requiredFiles": ["ASSET-LICENSES/logo.txt"],
    "materials": [{
      "path": "ASSET-LICENSES/logo.txt",
      "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "purpose": "logo license"
    }],
    "assets": [{
      "path": "logo.png",
      "source": "https://example.com/project/logo.png",
      "license": "MIT",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "requiredFiles": ["ASSET-LICENSES/logo.txt"]
    }]
  }
}
```

- `sourceRevision.tag` is the exact release tag; `sourceRevision.commit` is the full 40- or
  64-hex commit identifier resolved for that tag.
- `imageEvidence` remains a backward-compatible single-service record. Delivery validation accepts
  it only when the selected Compose has exactly one image and the record includes that image's
  registry digest. The Compose reference may be an immutable digest or a source-backed version tag;
  report that a tag reference itself can still move. Use `images` for every multi-service package
  and prefer it for new packages.
- Each `images[]` entry binds one exact version directory and Compose service to its resolved
  `reference` and matching registry `digest`. The `(version, service)` pair must be unique. Cover
  every service with an `image:` key, including databases, caches, browsers, migration helpers, and
  other sidecars. Prefer an `@sha256:` runtime reference; when a source-backed version tag must
  remain in Compose, record its resolved digest and report that the runtime reference itself can
  still move. Unrecorded auxiliary images block delivery evidence. For a multi-platform tag, use
  the OCI index digest in `digest` and record each platform child digest separately in the report.
  `imageEvidence.digest` and each `images[].digest` are immutable `sha256:` image digests.
  `imageEvidence.platforms` records verified OCI platform strings and must not be inferred from the
  host running the test; the same rule applies to `images[].platforms`. Use the same registry descriptor
  to build every platform-to-child-digest association and require it to name both values. Never assign
  a platform child digest by list position, current host architecture, or a separate registry query.
- `licenseEvidence.spdx` records an SPDX expression when known; `licenseEvidence.url` links the
  exact upstream license evidence.
- `logoEvidence.source` is an HTTPS source URL or `bundled:<package-relative-path>` for a bundled
  asset. For verified delivery, ship a regular non-symlink file at that package path and include it
  in the hash-bound required-material ledger. Record its license when known and the delivered PNG
  SHA-256 when calculated.
- `redistributionEvidence.status` is `verified` only after every listed asset license and required
  material is resolved. Keep it `unresolved` for imported or custom media without equivalent
  evidence. Use safe package-relative paths, list every required delivered file, and bind each
  asset and required-material entry to the SHA-256 of the actual packaged file. Every required
  path must have one `materials` entry. Absolute paths, traversal, symlinks, missing materials,
  untracked `logo.png`, and hash mismatches block delivery readiness.

Omit unknown optional keys instead of writing placeholders such as `unknown`, `latest`, or a
floating image tag.

## License Delivery

Record the exact version's application license in `licenseEvidence`. When the license has material
use restrictions, also name it, link its official terms, and summarize the deployment-relevant
restriction in the README, not only `source-evidence.json`. Do not invent an SPDX identifier or add
an undocumented root-metadata key merely to duplicate that evidence.

When the exact application or asset terms require attribution, a copyright notice, a license copy,
source disclosure, or a NOTICE file for redistribution, include the required material in the
delivered AppStore package; a URL in `source-evidence.json` is not a substitute. Preserve required
text verbatim and use the filename or README placement allowed by those exact terms. Verify asset
terms separately; do not assume the application code license covers a logo, icon, font, trademark,
or other bundled media. If asset redistribution or trademark permission remains unresolved, ship
the neutral placeholder instead.

The built-in neutral placeholder is project-authored at `assets/default-logo.svg`, licensed under
the MIT text in `assets/default-logo.LICENSE.txt`, and rendered to `assets/default-logo.png` with
SHA-256 `a8f604f27c3451536301f1a4ca7ac5ae8c479312a225c42c4dc0edda2a20bf76`.
When selected, the generator delivers the SVG at `<app>/assets/default-logo.svg` and hash-binds it
alongside the raster and MIT text so an artifact-only reviewer can reproduce the source claim.

## Public URL Inputs

Treat callback, origin, external base, and other browser-facing public URLs as deployment inputs.
Never synthesize `localhost` or `127.0.0.1` for these fields: those values point back to the
client or container and usually break redirects, webhooks, CORS, or generated links. Expose an
upstream-required public URL as a required 1Panel form field. Leave an optional public URL empty
or omit it, and document which feature stays unavailable until the operator supplies one.

Use one full public URL and the exact current upstream variable when the selected topology needs an
external origin, callback, or webhook value. Do not reconstruct the external URL from separate
host, protocol, or port fields unless version-matched official documentation proves that behavior
equivalent. Deprecated aliases are not current upstream variables merely because the image still
accepts them.

Keep the external URL separate from the internal listener. For a reverse proxy, record the
documented internal scheme and port, TLS termination boundary, forwarded-header requirements, and
trusted-proxy or hop settings. Do not set the internal listener to HTTPS merely because the public
URL is HTTPS; application-side HTTPS requires the application's source-backed certificate and key
configuration.

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

## Authoritative Deployment Control Inventory

Before scaffolding or changing Compose, build an authoritative control inventory for the selected
deployment topology and exact version. Read the official launch command or Compose file together
with the published image configuration, Dockerfile, and entrypoint when they affect runtime
behavior. Record all of these controls, including fixed values:

- services, images, commands, entrypoints, and runtime users;
- environment variables and their source-backed fixed values or required inputs;
- healthchecks, startup ordering, and dependency conditions;
- ports, networks, aliases, and isolation boundaries;
- mount sources, targets, types, modes, propagation, and security options;
- capabilities, privileged mode, devices, and host PID, IPC, or network namespaces.

After editing, compare the final Compose control by control with the inventory. Preserve every
source-backed control and justify every omission or change with an exact official source or
target-platform incompatibility plus an equivalent replacement. Keep official fixed hardening
values fixed in Compose; do not drop one merely because it does not need an install form field.
When official examples conflict, identify the selected topology and explain which versioned source
governs instead of silently combining examples.

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
