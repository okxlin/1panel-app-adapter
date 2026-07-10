# README Style Guide

This guide defines the expected structure for generated app README files.

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

For the same high-risk core requirements, add `## Security and Deployment Risks` with the exact access, required feature, and host impact.

## Exclusions

Do not include the following in app README files:

- audit logs
- test execution steps
- generator diagnostics
- raw validation transcripts
- fixed numeric version lines such as `Version: 1.2.3` or `当前提交仅包含固定版本 1.2.3`

These belong to delivery evidence, not end-user README content.

README text should stay valid after image or version-directory updates. When version context matters, refer users to the app store version selector, release directory, or source-evidence/delivery notes instead of embedding a concrete version number in README prose.
