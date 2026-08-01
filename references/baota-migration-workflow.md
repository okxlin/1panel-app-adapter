# Baota/aaPanel Migration Workflow

Use this workflow after a Baota or aaPanel catalog has been selected as a candidate source. The importer is a format converter. It does not fetch a live market, decide duplicates, prove upstream ownership, qualify images, or replace real 1Panel lifecycle testing.

## Input Modes

Choose exactly one input mode before running the importer.

### Live market snapshot

A live market may expose catalog JSON plus per-app template archives. Snapshot those responses into a task-owned staging directory with the market-specific fetcher, retain the retrieval URL and time, and safely extract each archive into a prepared app directory.

Do not pass catalog JSON, an archive, or a remote URL to `import-baota-app.py`. The importer accepts local prepared directories only. Reject archive members with absolute paths, `..` traversal, or links escaping the staging root before extraction. Prepared `app.json`, `icon.png`, version directories, and Compose files must not be symlinks.

### Prepared app directories

A prepared single-app input has this minimum shape:

```text
<app-key>/
|-- app.json
|-- icon.png
`-- <version>/
    |-- docker-compose.yml
    `-- .env
```

A prepared batch root contains one such app directory per direct child. See `baota-app-format.md` for field details. Catalog metadata and template content are untrusted input even when they came from a panel vendor.

## Deterministic Gate Order

Run the gates in this order. Passing an earlier gate does not prove a later one.

| Gate | Required result | Owner |
| --- | --- | --- |
| 1. Snapshot and duplicate search | Frozen source plus no official-store or target-store duplicate | Batch workflow |
| 2. Prepared-input precheck | Every directory reported; no precheck errors | This importer |
| 3. Conversion | `converted_candidate`; requested version exists | This importer |
| 4. Source and topology qualification | Independent official upstream evidence; topology is suitable | Adapter review |
| 5. Image and security qualification | Every image/tag/architecture pullable, trusted, and policy-compliant | Batch/security workflow |
| 6. Strict store validation | Every packaged version passes strict validation | Adapter validator |
| 7. Real lifecycle validation | Install, default workflow, restart, uninstall, and cleanup pass | `1panel-test-targets` |
| 8. Delivery review | Final files and evidence agree; repository policy passes | PR workflow |

Stop before conversion when duplicate or suitability preflight blocks a candidate. Conversion success means only that the source structure was translated.

## 1. Precheck the Entire Prepared Input

For one app:

```bash
python3 scripts/import-baota-app.py \
  --input <prepared-app-dir> \
  --precheck-only \
  --report <reports>/<app-key>-precheck.json
```

For a batch:

```bash
python3 scripts/import-baota-app.py \
  --input <prepared-batch-root> \
  --batch \
  --precheck-only \
  --report <reports>/baota-precheck.json
```

Batch precheck inspects every non-hidden direct child directory, including malformed directories without `app.json`. It does not create adapter output. A report file is written only when `--report` is supplied.

For one app, use `result.fields.versions` as source-declared candidates. In a batch, read the same field under each `items[].result`. A declared version is not automatically an existing, official, pullable, or deliverable version.

## 2. Convert One Explicit Version at a Time

One invocation converts one version:

```bash
python3 scripts/import-baota-app.py \
  --input <prepared-app-dir> \
  --out-dir <candidate-output-root> \
  --version <exact-version> \
  --validate \
  --require-validate \
  --report <reports>/<app-key>-<version>-convert.json
```

Repeat the command for every version selected for packaging. Do not infer a newest fixed version from catalog array order. Do not silently substitute `latest` for a missing requested version.

Read these report fields separately:

- `declaredVersions`: normalized source-declared versions.
- `importableVersions`: declared versions with a prepared Compose file inside the input root.
- `availableVersions`: backward-compatible alias of `declaredVersions`.
- `selectedVersion`: the exact version converted by this run.
- `packagedVersions`: version directories currently present in the output app.
- `stage`: conversion or validation stage reached.
- `candidateStatus`: conversion/delivery assessment, not runtime readiness.
- `delivery.blockers`: unresolved evidence or manual-review gates.

Repeated imports preserve per-version source evidence in `source-evidence.json.versionEvidence`. Versions are sorted deterministically with `latest` first. Top-level `importSource.versions` is merged only for the same prepared source identity; per-version provenance remains separate across different source roots. This is bookkeeping, not proof that the evidence is authoritative.

For reviewable intermediate JSON, emit one AppSpec per version:

```bash
python3 scripts/import-baota-app.py \
  --input <prepared-app-dir> \
  --version <exact-version> \
  --emit-appspec <spec-root>/<app-key>-<version>.json
```

`generate-from-appspec.py` also writes each AppSpec to its explicit top-level `version` directory and merges per-version evidence when the same app is generated repeatedly.

## 3. Qualify the Converted Candidate

Independently verify all of the following before declaring a Baota conversion deliverable:

1. The app is absent from the frozen official and target store snapshots, including aliases, repository URLs, and images.
2. `repository`, `dockerDocs`, and `composeFile` identify the target application's official upstream sources for the packaged version.
3. The transformed ports, volumes, environment, dependencies, networks, permissions, and default workflow match those official sources.
4. Every runtime image and tag is anonymously pullable and every claimed architecture is present in registry manifests.
5. Image provenance, vulnerability policy, required high-risk permissions, and any exception evidence pass the active batch/security policy.
6. Every `manualReviewReasons` item is resolved by an artifact correction or explicit evidence. Do not delete a reason merely to make the gate pass.

The raw `app.json.home` and `app.json.help` values remain `importSource.declaredHome` and `importSource.declaredHelp` hints. A plausible URL or GitHub hostname does not prove that the listing, image, or Compose is official.

For a reviewed AppSpec, set `evidenceStatus: official_complete` only after the three official source fields are independently verified. Set `architectureEvidence: registry_manifest_verified` only after every packaged image/tag and declared architecture has manifest evidence. A Baota AppSpec remains delivery-blocked while either value is unverified or a manual-review reason remains.

## 4. Run Delivery Gates

Generate or update the candidate, then validate every packaged version explicitly:

```bash
python3 scripts/generate-from-appspec.py \
  --spec <reviewed-appspec.json> \
  --out-dir <candidate-output-root> \
  --strict-store-validate \
  --report <reports>/<app-key>-<version>-generate.json

bash scripts/validate-v2.sh \
  --dir <candidate-output-root>/<app-key> \
  --version <exact-version> \
  --strict-store \
  --i18n-mode strict \
  --i18n-scope all
```

`--strict-store-validate` fails closed for Baota AppSpecs when source, architecture, or manual-review delivery gates remain unresolved. The explicit validator command adds the repository delivery i18n gate and must run for each packaged version.

Then use `1panel-test-targets` to install the exact submitted files through a real 1Panel v2 local-app flow. For every distinct runtime contract, verify local-app recognition, install task success, container/dependency health, the ordinary default user workflow, restart, uninstall, and task-owned cleanup. A parseable Compose file, a healthy container, or HTTP 200 cannot replace this evidence.

## Stop and Handoff Rules

- Keep `converted_candidate`, `manual_review_required`, `delivery_ready`, and runtime-tested states distinct.
- Assign every batch candidate exactly one final batch disposition: `adapt`, `duplicate`, `unsuitable`, `deferred`, or `blocked`.
- Do not commit `source-evidence.json` into a target store that keeps process evidence outside `apps/<app-key>`.
- Do not use importer reports from an earlier source snapshot to approve changed source or generated files.
- Route publication, CI audit, mergeability checks, and merge verification through the active PR workflow. The importer never authorizes publication.
