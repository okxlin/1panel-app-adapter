# README Style Guide

Generate separate product-facing files: Chinese `README.md` and English `README_en.md`. This matches current official store examples; the local panel loader itself reads `README.md`. Accept a historical combined README during validation, but use the separate files for new packages.

## Chinese README Structure

Use this section order:

1. `## 产品介绍`
2. `## 主要功能`
3. `## 访问说明`

When the application requires high-risk host access for a core feature, also add `## 安全与部署风险`. Name the exact permission or mount, explain which feature requires it, and state the host-level consequence. Examples include writable Docker/Podman Socket access, privileged mode, host networking or namespaces, added Linux capabilities, device mappings, and relaxed security options. Do not describe these permissions as removable when removing them would break the application's intended function.

## English README Structure

Use this section order:

1. `## Introduction`
2. `## Features`

Add `## Usage` when access, persistence, first-run setup, or a required dependency needs explanation. Keep Chinese and English content equivalent; do not duplicate the English section inside the Chinese file by default.

For the same high-risk core requirements, add `## Security and Deployment Risks` with the exact access, required feature, and host impact.

## Exclusions

Do not include the following in app README files:

- audit logs
- test execution steps
- generator diagnostics
- raw validation transcripts
- fixed numeric version lines such as `Version: 1.2.3` or `当前提交仅包含固定版本 1.2.3`

These belong to delivery evidence, not end-user README content.

README text should stay valid after image or version-directory updates. Keep the selected application version in package metadata and the app store version selector. Name releases in the README only when they define a necessary compatibility or upgrade boundary.

For an image-tag or version-directory refresh that leaves the operator contract unchanged, preserve the existing README files. Change them when authentication, required inputs, persistence, dependencies, or upgrade actions actually change. Keep release numbers, scan counts, and temporary test conclusions in PR or delivery evidence instead of adding text that will become stale on the next update.

Write the application's purpose and verified features, then the few facts a user needs to install and use this package: access method, durable data, required inputs, and any source-backed limitation. Omit internal app keys, evidence filenames, generator details, empty sections, and descriptions of the adapter's capabilities. Do not claim a web UI for a protocol-only service. A necessary upgrade compatibility boundary may name exact releases; a line announcing the currently packaged image version adds no user guidance and becomes stale.

AppSpec can supply `readme.introductionZh/En`, `featuresZh/En` (lists of strings), and `usageZh/En`. The generator leaves explicit placeholders where source-backed product content is absent; final validation must reject them. Migration notes stay in the evidence record unless they describe an actual user action that belongs in the README.

Keep legal material proportional to what is redistributed. An ordinary image reference does not require an extra application license text. Required attribution can live in the README when its license permits; retain separate notices or source files only when the actual terms require them. The bundled fallback icon appends its MIT notice in a collapsible section and records the README hash in external evidence. Preserve that notice while editing, then refresh its material hash.
