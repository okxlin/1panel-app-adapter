# Upgrade Maintenance

Use this reference when adapting an existing app, adding a new version directory, changing image lineage, changing database/cache services, changing volume paths, or editing `scripts/upgrade.sh`.

## Upgrade Safety Audit

Compare the previous supported version and the candidate version before generating files:

- image repository, tag policy, required architecture, UID/GID, and entrypoint changes
- compose service names, dependency services, networks, ports, health checks, and restart policy
- bind mounts, named volumes, database paths, upload paths, and config paths
- environment variable names, defaults, removed variables, and new required variables
- database engine or major version changes, cache service changes, and official migration notes
- `init.sh`, `upgrade.sh`, and `uninstall.sh` behavior, especially any config rewrite or data move
- README upgrade notes, backup warnings, minimum client/server requirements, and manual steps

If the old version may have data in files, a database, or generated config, assume an upgrade can damage user data until the official migration path and a real upgrade test prove otherwise.

## `.env.sample` And Form Field Changes

When adding or renaming environment variables:

- keep old variables when the upstream image still accepts them
- translate renamed variables in `upgrade.sh` when possible
- set safe defaults for new optional variables
- require explicit user input for new required variables that cannot be inferred
- if converting a dependency host field from manual text input to a 1Panel selector, prefer keeping the same effective envKey when possible so existing `.env` files remain valid
- if selector support adds a new driving field such as `PANEL_DB_TYPE` or renames an existing host envKey, backfill it in `upgrade.sh` instead of assuming old installs will recreate `.env` from scratch
- preserve an existing selector value such as `localmysql` even when new installs no longer offer it; removing an option from `data.yml` must not rewrite a working old `.env` or database host
- source any required runtime administrator password from the selected installed runtime during validation; do not replace an old application's stored database password with a form default or a newly generated value
- keep `.env.sample`, `data.yml` formFields, and compose `${VAR}` references closed and consistent

If a new version directory is a GPU or CUDA variant with narrower platform coverage than the default version:

- keep the version directory name explicit, for example `latest-cuda`
- preserve the normal package behavior and persistence layout unless upstream documents a real runtime difference
- document hardware prerequisites and variant-specific architecture limits in README and provenance notes so root-level multi-arch metadata does not overstate support for that variant

Do not silently replace a persisted secret, database password, install path, or public URL during upgrade.

## Upgrade Script Rules

Use `scripts/upgrade.sh` only for deterministic local migration work that 1Panel cannot express through compose/env files.

- Back up files before overwriting generated config.
- Include SQLite sidecar files such as `*.db-wal` and `*.db-shm` when backing up SQLite data.
- Prefer database-native dumps over hot-copying live database directories.
- Make migrations idempotent so a retry does not corrupt data.
- Print clear warnings for manual backup, unsupported direct jumps, or required intermediate versions.
- Keep destructive cleanup out of `upgrade.sh` unless the removed path is known to be disposable cache.

## Version Retention

Keep intermediate version directories when upstream requires staged upgrades or when skipping a major version is not documented as safe. If automation manages image updates, update its ignore/allowed-version rules together with the retained version policy.

## README Upgrade Notes

For updates that are not a plain patch-level image refresh, README should mention:

- whether direct upgrade from the previous packaged version is supported
- backup scope: app data, generated config, database dump, or external dependency data
- required intermediate versions or minimum compatible clients
- expected migration duration and log marker to wait for when upstream documents one
- any changed image namespace, database/cache dependency, or removed feature

## Validation Handoff

Static validation is not enough for updates. After `validate-v2.sh --strict-store` passes, run a real 1Panel upgrade test from the previous supported version to the candidate version. Before submitting the upgrade request, wait for and record source-version HTTP readiness; a running container alone does not prove the source application was usable. The report should record app key, install name, `fromVersion`, `toVersion`, seeded persistence data, source readiness, upgrade action, migration log/wait condition when relevant, selector/link evidence before and after upgrade, restart/access verification, uninstall, and cleanup. Audit linked database cleanup separately from manually managed external schemas/users.
