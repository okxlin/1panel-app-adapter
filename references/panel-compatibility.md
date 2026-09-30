# 1Panel v1 and v2 compatibility

The default delivery target includes **v1 and older/current v2**, not only the
latest panel. Prefer one package using shared behavior. Keep application
capabilities, persistence and security controls intact; narrowing the supported
panel range is a separate, explicit decision. Reading v1 input and generating
v2-shaped files does not establish v1 runtime compatibility.

Record the exact target panel versions, their source/binary identity, Docker
and Compose versions, and dependency keys before adaptation. The helper names
`scaffold-v2.sh`, `migrate-v1-to-v2.sh` and `validate-v2.sh` describe the package
layout and existing CLI, not a minimum panel version or a compatibility test.
When no exact lower bound is established, keep the common path and report the
unverified versions; do not invent a universal minimum or claim every v1/v2
release works. Match source ancestry/layout to the actual panel binary: an
upstream tag name alone is insufficient evidence.

## Shared behavior and version-specific behavior

| Boundary | Compatibility decision |
| --- | --- |
| Root/version metadata | Preserve `additionalProperties`, nested `formFields`, legacy scalar labels and source-backed fields. Older loaders may ignore newer metadata, so an ignored capability flag cannot enforce a required runtime condition. |
| Application type | Serialize `tool`, `website`, or `runtime` in lowercase. Keep display categories in `tags`. `Tool` can install successfully while skipping database creation; require a real association and application-user SQL, not only a running container. |
| Locale keys | Keep all twelve canonical translations and equal-valued `zh-Hant`, `pt-BR`, `es-ES` aliases in serialized maps. Preserve `labelZh`/`labelEn` for early v1. Current readers lowercase keys; some old readers do not, and their missing-key test can return an empty label instead of falling back. Never resolve conflicting aliases by choosing one silently. |
| Database port | `PANEL_DB_PORT` can be injected in both generations when `PANEL_DB_HOST` resolves to a panel database record. An arbitrary hostname, Redis selector or unregistered custom app key does not prove that path. |
| Lifecycle | Common hooks are `init.sh`, `upgrade.sh`, `uninstall.sh`. Newer internal start/stop/restart hooks require a verified caller; ordinary app operations do not automatically use them. |
| Upgrade preparation | Legacy and staged flows differ. A common package must render with old stored values and resolve image/build inputs before the earliest preparation step that needs them. |
| PHP/runtime version switch | Newer panels can change runtime versions; older creation/editing paths remain part of acceptance. Do not make the newer switch API a prerequisite for an otherwise compatible package. |

### Metadata output

`appstore_i18n.compatible_metadata` expands aliases only at metadata write
boundaries. Internal normalization and translation checks remain canonical.
Generators, metadata patchers and `--normalize` use this same output policy.
For manual packages, review labels on old and new readers as well as the root
description and nested field descriptions. Some panel backends reserialize
typed locale structures; source-function replay or extra YAML keys alone do
not prove the rendered UI after that conversion.

### Database-derived values

Static validation recognizes `PANEL_DB_PORT` for a required
`PANEL_DB_HOST` service selector with a known `mysql`, `mariadb` or `postgresql`
key, or a required `PANEL_DB_TYPE` apps selector whose service child is
`PANEL_DB_HOST` and whose default/options are those known database keys.
Ambiguous, optional, manual-host and unknown-provider shapes retain the
undeclared-variable failure. This is structural eligibility, not successful
database resolution or provisioning; the validator reports that distinction.

For each target panel, prove that the actual selection resolves to a database
record and that the installed environment contains the selected port. Preserve
nonstandard ports, existing hosts and database credentials across upgrades.
The env-sample generator leaves undeclared derived values unset. Supply a
reviewed target-specific value in the disposable render fixture when needed;
do not hardcode an assumed port into the product or invent a user-editable
port form merely to satisfy closure. A Compose fallback is acceptable only
when it matches the exact supported deployment contract. If official-mode
temporary rendering cannot resolve a required value, report that missing input
instead of treating an empty render as runtime success.

## Evidence required for a compatibility claim

Keep a version matrix in external delivery evidence, not in product README
diagnostics. Include an identified v1 target, an older v2 target, the relevant
behavior transition and the current supported v2 target. Choose additional
versions when a changed field, dependency or lifecycle boundary requires them.

- Parse the exact package with the target loader; check visible labels and
  help, including traditional Chinese and mixed-case locale names.
- Test selector enumeration, the installed host/port, and linked database
  creation/cleanup separately. Include a non-default database port.
- Exercise clean install, changed parameters, restart/rebuild, persisted data,
  same-panel old-app-to-new-app upgrade and uninstall on each claimed line.
- Probe application readiness independently of panel task success, on both
  upgrade and rollback. A newer panel may commit the upgrade without waiting
  for all containers to become healthy.
- Preserve the earlier panel path when adding a newer capability. If an
  equivalent implementation is impossible, stop the compatibility claim and
  explain the exact minimum version and user-visible effect before narrowing
  the target. Never silently remove application capabilities to broaden it.

Schema checks, reader replays, live installation tests and actual deployed
evidence are different classes. Record which ran and which remain unavailable.
Retain all existing source, license, image, topology and safety gates.

## Live regression baseline for adapter 1.3.2

On 2026-09-30, generated two-version probe packages passed real panel API and
container tests on **v1.10.34-lts, v2.0.0, v2.2.5 and v2.3.2**, using Docker
29.5.3 and Compose 5.5.0. Each target enumerated a registered remote MySQL
8.4.11 service on port **13306**, created an associated database/user, and
executed SQL using that application user. Installation, parameter changes,
restart, a backed-up 1.0.0 → 1.0.1 package upgrade, retained files/SQL/parameters,
and uninstall passed. Hook logs confirmed `init`, `upgrade`, and `uninstall`;
ordinary restart did not invoke `restart.sh`.

Real bundled browser UIs on v1.10.34-lts, v2.0.0 and v2.3.2 also rendered the
generated port/value/database field labels correctly for `zh-Hant`, `pt-BR`
and `es-ES` (nine checks with screenshots). This covers those visible field
labels, not every root description, help text or translation.

The tests used isolated third-party `moelin/1panel` images with recorded image
digests, binary SHA-256 and API-reported versions. A reviewed bootstrap wrapper
fixed the disposable container base path; panel binaries were unchanged. This
is a live container baseline, not proof of every v1/v2 release, older Docker
engines, native/systemd installations, panel-version migration, failed-upgrade
rollback, or application-specific workloads. Retain exact artifacts and
per-target runtime evidence with the delivery record.

Carry these observed differences into future tests:

- v1 local-app synchronization uses `/api/v1/apps/sync`. Its remote-service
  options omit `status`; verify the exact registry entry, the connection-check
  API and real SQL instead of treating an absent field as stopped or running.
- Older installed-app APIs omit `linkDB`/`resourceKeys`. Verify the panel's
  association record and independently execute application-user SQL. v1 also
  renames the Compose service; locate the exact installation's container by
  project/record identity rather than assuming the submitted service name.
- Upgrades may preserve installed configuration files. Verify the new Compose
  or image version separately; package a required configuration migration in
  `upgrade.sh` rather than assuming the new template overwrites user data.
- `deleteDB` can leave a remote MySQL user behind. Check schema and user removal
  separately. Clean only resources owned by the test or explicitly approved
  application cleanup; never drop a shared account from a generic hook.

## Pinned authorities

- [v1 scalar form labels, v1.10.21-lts](https://github.com/1Panel-dev/1Panel/blob/aaae8a5d3bf4c35f0f344010623776e212dbe109/frontend/src/views/app-store/detail/params/index.vue#L249).
- [v1 maintenance locale reader](https://github.com/1Panel-dev/1Panel/blob/20b89a8fdd94d437470130ce241e70ee1425a430/frontend/src/views/app-store/detail/params/index.vue#L249) and [database-port injection](https://github.com/1Panel-dev/1Panel/blob/20b89a8fdd94d437470130ce241e70ee1425a430/backend/app/service/app.go#L446).
- [v2.0.0 label/description lookup](https://github.com/1Panel-dev/1Panel/blob/8b9337b45a3512c54061a6b1ef4a75ab42af5505/frontend/src/utils/util.ts#L633); the same lookup remains in [v2.1.0](https://github.com/1Panel-dev/1Panel/blob/6c3f56516fd405201aa1bb49367bf737fae3ca4e/frontend/src/utils/util.ts#L688).
- [v2.3.2 upgrade phases](https://github.com/1Panel-dev/1Panel/blob/65243c68c463cc055ab044093f641ea5d2e9e28b/agent/app/service/app_upgrade.go#L175), [database-port injection](https://github.com/1Panel-dev/1Panel/blob/65243c68c463cc055ab044093f641ea5d2e9e28b/agent/app/service/app.go#L514), and [runtime version updates](https://github.com/1Panel-dev/1Panel/blob/65243c68c463cc055ab044093f641ea5d2e9e28b/agent/app/service/runtime_update.go#L16).
