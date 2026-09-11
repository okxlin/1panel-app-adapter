# 1Panel AppStore Adapter Skill for Docker Apps

[English](./README.md) | [简体中文](./README.zh-CN.md)

`1panel-app-adapter` is a **1Panel app skill** for adapting Docker applications into packages for the **1Panel App Store** (`AppStore`/`appstore`). It scaffolds new packages, converts Docker Compose and AppSpec inputs, imports aaPanel/Baota apps, migrates v1 packages to v2, and validates store-ready output.

## Capabilities

| Task | Input | Result |
| --- | --- | --- |
| Scaffold an app | Image, ports, volumes, and official source URLs | 1Panel v2 package skeleton |
| Generate from a spec | AppSpec JSON | Reproducible app package and optional report |
| Import an app | aaPanel/Baota `apphub` directory | Normalized 1Panel package |
| Migrate a package | Existing v1 or mixed-layout app | 1Panel v2 directory structure |
| Validate a package | Generated or hand-written app directory | Baseline, strict-store, and i18n findings |

The skill follows 1Panel runtime behavior and official sources before repository conventions or third-party examples. It does not guess deployment details when an application has no reliable Docker source.

## Agent Usage

Ask a skill-compatible coding agent to use the skill explicitly:

```text
Use $1panel-app-adapter to adapt this Docker application into a validated 1Panel AppStore package.
```

The skill supports individual and batch app adaptation, package updates, AppStore submission preparation, and pre-review validation.

## Quick Start

Create a v2 package skeleton from an official Docker source:

```bash
bash scripts/scaffold-v2.sh \
  --app-key demo \
  --title "Demo" \
  --image nginx:latest \
  --version 1.0.0 \
  --source-repository <repository-url> \
  --source-docker-docs <docker-docs-url> \
  --source-compose-file <compose-url>
```

Replace the generated README and metadata placeholders, review Compose variables and `.env.sample`, then run the delivery gate:

```bash
bash scripts/validate-v2.sh \
  --dir ./1panel-apps/demo \
  --strict-store \
  --i18n-mode strict \
  --i18n-scope all \
  --source-evidence-mode required --require-delivery-evidence
```

Scaffold output is a starting point. It is not store-ready until application-specific metadata, translations, topology, image provenance, and runtime behavior have been reviewed.

## Submission Profiles

Generation defaults to `third-party`. Add `--submission-profile official` to scaffold, AppSpec generation, Baota import, migration, and validation when preparing an official store submission. Official mode locks existing directory form fields with `disabled: true` and `edit: false`, keeps the same Compose topology, and omits `.env.sample` from the app. AppSpec also accepts `submissionProfile`; the CLI flag overrides it.

Deliver only `<out-dir>/<app-key>/`. Source evidence is written to the sibling `<out-dir>/.evidence/<app-key>/source-evidence.json`; pass `--source-evidence <path>` when validating a package copied elsewhere. Both profiles generate Chinese `README.md` and English `README_en.md`, and create lifecycle hooks only when there is actual setup work. The fallback icon keeps its MIT notice inside the README without extra license text or source files. Required notices for other redistributed material remain mandatory.

See [submission profiles](./references/submission-profiles.md) and the [pinned 1Panel source facts](./references/1panel-sources.md). Neither profile waives application-specific source or runtime evidence.

## Workflows

### Generate from AppSpec

```bash
python3 scripts/generate-from-appspec.py \
  --spec assets/sample-appspec.json \
  --validate \
  --require-validate \
  --report artifacts/run-report.json
```

See the [AppSpec reference](./references/appspec.md) and [sample AppSpec](./assets/sample-appspec.json). Use `--strict-store-validate` only after replacing generated placeholders with delivery-ready content.

### Import aaPanel or Baota Apps

Precheck a prepared input without generating adapter output:

```bash
python3 scripts/import-baota-app.py \
  --input <baota-app-dir-or-batch-root> \
  --precheck-only \
  --report artifacts/baota-precheck.json
```

Add `--batch` when the input is a prepared batch root.

Import one app:

```bash
python3 scripts/import-baota-app.py \
  --input <baota-app-dir> \
  --out-dir ./1panel-apps \
  --version latest \
  --validate \
  --require-validate
```

Import the direct child directories of an `apphub` checkout:

```bash
python3 scripts/import-baota-app.py \
  --input <apphub-dir> \
  --batch \
  --out-dir ./1panel-apps \
  --validate \
  --report artifacts/baota-import-report.json
```

The importer translates aaPanel/Baota ports, bind mounts, network settings, resource limits, and metadata into a conversion candidate. It does not fetch a live market or prove delivery readiness. Imported values still require independent source, image, security, strict-store, and real 1Panel lifecycle verification. Start with the [migration workflow](./references/baota-migration-workflow.md), then use the [format notes](./references/baota-app-format.md) and [mapping rules](./references/baota-to-1panel-mapping.md) as needed.

### Migrate v1 to v2

```bash
bash scripts/migrate-v1-to-v2.sh \
  --src <app-dir> \
  --out <out-root> \
  --version <source-version> \
  --target-version <target-version>
```

For an existing published app, review [upgrade and maintenance safety](./references/upgrade-maintenance.md) before changing images, variables, dependencies, volumes, or lifecycle scripts.

### Finalize Lifecycle Scripts

```bash
bash scripts/finalize_runtime_scripts.sh <app-dir> <version-dir>

# After proving a non-root writable bind's numeric identity from the exact image:
bash scripts/finalize_runtime_scripts.sh <app-dir> <version-dir> \
  --dir-owner APP_DATA_DIR=<uid>:<gid>:0750 --replace-init
```

The helper creates `init.sh` only for directory fields or an explicit directory ownership plan, resolving paths from the version directory. It preserves custom hooks and leaves packages without initialization work unchanged; add upgrade or uninstall hooks only for required application operations. Replacing an existing `init.sh` requires `--replace-init`. An ownership plan applies non-recursive changes to a direct child of a trusted version directory and must run as root. Prove that host ownership changes are needed as well as the exact image's UID/GID; an image entrypoint may already handle them.

### Validate a Package

```bash
# Baseline validation
bash scripts/validate-v2.sh --dir <app-dir>

# AppStore delivery checks
bash scripts/validate-v2.sh --dir <app-dir> --strict-store \
  --source-evidence-mode required --require-delivery-evidence

# One release in a multi-version package
bash scripts/validate-v2.sh --dir <app-dir> --version <version> --strict-store \
  --source-evidence-mode required --require-delivery-evidence

# Require optional provenance evidence for a gated workflow
bash scripts/validate-v2.sh --dir <app-dir> --source-evidence-mode required

# Require verified license and hash-bound redistribution delivery evidence
bash scripts/validate-v2.sh --dir <app-dir> --source-evidence-mode required \
  --require-delivery-evidence
```

Validation covers:

- root and version `data.yml` structure, required fields, duplicate YAML keys, and allowed tags;
- Compose rendering, variable closure, `.env.sample`, service labels, ports, volumes, and network topology;
- placeholder residue, descriptive summaries, empty/no-op hooks, and AppStore README structure;
- localized descriptions and form labels for `en`, `zh`, `zh-hant`, `ja`, `ko`, `ru`, `ms`, `pt-br`, `tr`, `es-es`, `fa`, and `lo`;
- optional source provenance and strict-store delivery rules.

Full Compose rendering requires the `docker compose` CLI. Source evidence defaults to warning mode and becomes mandatory only with `--source-evidence-mode required`. That historical mode validates provenance; add `--require-delivery-evidence` when license and redistribution delivery must be release-gating.

## Requirements

- Linux or another environment with `bash`
- Python 3 with `PyYAML`
- Docker Compose for full Compose validation
- ImageMagick and GNU-compatible `stat` for `scripts/normalize-logo.sh`

Text and shell files are expected to use LF line endings.

## Rule References

- [Source policy](./references/source-policy.md)
- [Topology preflight](./references/topology-preflight.md)
- [Lifecycle safety](./references/lifecycle-safety.md)
- [1Panel schema facts](./references/schema.md)
- [App README style](./references/readme-style.md)
- [Implicit environment keys](./references/implicit-envkeys.md)
- [Editable field exceptions](./references/edit-exempt-envkeys.md)
- [Upgrade and maintenance safety](./references/upgrade-maintenance.md)

## Frequently Asked Questions

### Is this a 1Panel app skill?

Yes. It gives coding agents source and packaging rules plus scripts for 1Panel application adaptation, generation, migration, and validation.

### Can it convert Docker Compose to a 1Panel AppStore package?

Yes, when the application has trustworthy Docker deployment sources. The generated package still needs application-specific review and runtime testing before submission.

### Does it publish apps to the 1Panel App Store?

No. It prepares and validates local package artifacts. Publishing, pushing branches, and opening pull requests remain separate Git and GitHub actions.
