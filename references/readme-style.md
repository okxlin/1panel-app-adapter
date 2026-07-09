# README Style Guide

This guide defines the expected structure for generated app README files.

## Chinese README Structure

Use this section order:

1. `## 产品介绍`
2. `## 主要功能`
3. `## 访问说明`

## English README Structure

Use this section order:

1. `## Introduction`
2. `## Features`

## Exclusions

Do not include the following in app README files:

- audit logs
- test execution steps
- generator diagnostics
- raw validation transcripts
- fixed numeric version lines such as `Version: 1.2.3` or `当前提交仅包含固定版本 1.2.3`

These belong to delivery evidence, not end-user README content.

README text should stay valid after image or version-directory updates. When version context matters, refer users to the app store version selector, release directory, or source-evidence/delivery notes instead of embedding a concrete version number in README prose.
